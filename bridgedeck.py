#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import copy2, which
from typing import Any


DEFAULT_DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
DEFAULT_SETTINGS_PATH = Path.home() / ".cc-switch" / "settings.json"
DEFAULT_AUTH_PATH = Path.home() / ".cc-switch" / "codex_oauth_auth.json"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_CLI_LAUNCHER_DIR = Path.home() / ".cc-switch" / "codex-cli-launchers"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8899
APP_VERSION = "0.2.4"
MAX_REQUEST_BYTES = 1024 * 1024
LOCAL_BRIDGE_BASE_URL = "http://127.0.0.1:8876"
CC_SWITCH_BASE_URL = "http://127.0.0.1:15721"


def now_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse JSON file: {path}") from exc


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def mask_token(token: str | None) -> str:
    if not token:
        return ""
    token = token.strip()
    if token == "local-bridge":
        return token
    if len(token) <= 10:
        return token
    return f"{token[:6]}...{token[-4:]}"


def sha12(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    if "@" in value:
        value = value.split("@", 1)[0]
    value = re.sub(r"[^a-z0-9._-]+", "-", value).strip("-._")
    return value or "account"


def decode_jwt_payload(token: str | None) -> dict[str, Any]:
    if not token or "." not in token:
        return {}
    try:
        payload = token.split(".", 2)[1]
        payload += "=" * (-len(payload) % 4)
        parsed = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def jwt_identity(token: str | None) -> dict[str, Any]:
    payload = decode_jwt_payload(token)
    auth = payload.get("https://api.openai.com/auth")
    profile = payload.get("https://api.openai.com/profile")
    auth_obj = auth if isinstance(auth, dict) else {}
    profile_obj = profile if isinstance(profile, dict) else {}
    return {
        "account_id": auth_obj.get("chatgpt_account_id") or payload.get("chatgpt_account_id") or "",
        "email": profile_obj.get("email") or payload.get("email") or "",
        "plan": auth_obj.get("chatgpt_plan_type") or "",
        "exp": payload.get("exp"),
    }


def classify_error_text(text: str | None) -> str:
    value = (text or "").lower()
    if "refresh_token_reused" in value or "refresh token reused" in value:
        return "refresh_token_reused"
    if "unsupported_country_region_territory" in value or "country, region, or territory not supported" in value:
        return "unsupported_region"
    if "connection refused" in value or "bridge_down" in value:
        return "bridge_down"
    if "proxy_down" in value:
        return "proxy_down"
    return "network_error" if value else "ok"


def tcp_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class ManagerPaths:
    db: Path
    settings: Path
    auth_store: Path


class BridgeManager:
    def __init__(self, paths: ManagerPaths) -> None:
        self.paths = paths
        self._lock = threading.Lock()

    def _backup_file(self, path: Path, label: str) -> str | None:
        if not path.exists():
            return None
        backup_dir = self.paths.db.parent / "bridgedeck-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(path.expanduser()).strip("/"))
        target = backup_dir / f"{safe_name}.toolbak-{label}-{now_ts()}-{time.time_ns()}-{uuid.uuid4().hex[:8]}"
        copy2(path, target)
        os.chmod(target, 0o600)
        return str(target)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.paths.db))
        conn.row_factory = sqlite3.Row
        return conn

    def _provider_columns(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(providers)").fetchall()
        return {str(row["name"]) for row in rows}

    def _load_settings(self) -> dict[str, Any]:
        raw = load_json(self.paths.settings, {})
        return raw if isinstance(raw, dict) else {}

    def _save_settings(self, settings: dict[str, Any]) -> None:
        dump_json(self.paths.settings, settings)

    def _current_provider_from_settings(self) -> str | None:
        settings = self._load_settings()
        value = settings.get("currentProviderClaude")
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = settings.get("current_provider_claude")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _set_current_provider_in_settings(self, provider_id: str) -> None:
        settings = self._load_settings()
        settings["currentProviderClaude"] = provider_id
        self._save_settings(settings)

    def _load_accounts(self) -> list[dict[str, Any]]:
        store = load_json(self.paths.auth_store, {})
        accounts = store.get("accounts") if isinstance(store, dict) else {}
        if not isinstance(accounts, dict):
            return []
        result = []
        for account_id, payload in accounts.items():
            if not isinstance(account_id, str):
                continue
            data = payload if isinstance(payload, dict) else {}
            email = data.get("email") if isinstance(data.get("email"), str) else ""
            refresh_token = data.get("refresh_token") if isinstance(data.get("refresh_token"), str) else ""
            label = email or account_id[:8]
            result.append(
                {
                    "account_id": account_id,
                    "email": email,
                    "label": label,
                    "refresh_sha12": sha12(refresh_token),
                    "authenticated_at": data.get("authenticated_at"),
                    "default_cli_home": str(Path.home() / f".codex-cli-{safe_slug(label)}"),
                }
            )
        result.sort(key=lambda item: item.get("email") or item["account_id"])
        return result

    def _account_map(self) -> dict[str, dict[str, Any]]:
        return {item["account_id"]: item for item in self._load_accounts()}

    def _load_auth_store_raw(self) -> dict[str, Any]:
        store = load_json(self.paths.auth_store, {})
        return store if isinstance(store, dict) else {}

    def _codex_auth_summary(self, codex_home: Path) -> dict[str, Any]:
        auth_path = codex_home / "auth.json"
        payload = load_json(auth_path, {})
        tokens = payload.get("tokens") if isinstance(payload, dict) else {}
        token_obj = tokens if isinstance(tokens, dict) else {}
        access_token = token_obj.get("access_token") if isinstance(token_obj.get("access_token"), str) else ""
        refresh_token = token_obj.get("refresh_token") if isinstance(token_obj.get("refresh_token"), str) else ""
        id_token = token_obj.get("id_token") if isinstance(token_obj.get("id_token"), str) else ""
        identity = jwt_identity(access_token)
        is_default = codex_home == DEFAULT_CODEX_HOME
        token_fields = {
            "access_token": bool(access_token),
            "refresh_token": bool(refresh_token),
            "id_token": bool(id_token),
        }
        risk_flags = []
        if not is_default and any(token_fields.values()):
            risk_flags.append("stale_cli_token_profile")
        return {
            "path": str(codex_home),
            "exists": auth_path.exists(),
            "is_default": is_default,
            "run_command": "codex" if is_default else f"CODEX_HOME={codex_home} codex",
            "auth_mode": payload.get("auth_mode") if isinstance(payload.get("auth_mode"), str) else "",
            "last_refresh": payload.get("last_refresh") if isinstance(payload.get("last_refresh"), str) else "",
            "token_account_id": token_obj.get("account_id") if isinstance(token_obj.get("account_id"), str) else "",
            "access_account_id": identity.get("account_id") or "",
            "email": identity.get("email") or "",
            "plan": identity.get("plan") or "",
            "refresh_sha12": sha12(refresh_token),
            "access_exp": identity.get("exp"),
            "token_fields": token_fields,
            "risk_flags": risk_flags,
            "status": "stale_launcher" if risk_flags else "ok",
        }

    def _known_cli_homes(self) -> list[dict[str, Any]]:
        homes: list[Path] = [DEFAULT_CODEX_HOME]
        for item in Path.home().glob(".codex-cli-*"):
            if item.is_dir() and item not in homes:
                homes.append(item)
        return [self._codex_auth_summary(home) for home in homes]

    def _known_cli_launchers(self) -> list[dict[str, Any]]:
        if not DEFAULT_CLI_LAUNCHER_DIR.exists():
            return []
        launchers: list[dict[str, Any]] = []
        for item in sorted(DEFAULT_CLI_LAUNCHER_DIR.glob("codex-*.command")):
            if not item.is_file():
                continue
            try:
                body = item.read_text(encoding="utf-8")
            except Exception:
                body = ""
            account_match = re.search(r"/accounts/([^/'\" ]+)/v1", body)
            home_match = re.search(r"CODEX_HOME=(?:'([^']+)'|\"([^\"]+)\"|([^ \n]+))", body)
            launchers.append(
                {
                    "path": str(item),
                    "name": item.stem.removeprefix("codex-"),
                    "account_id": account_match.group(1) if account_match else "",
                    "codex_home": next((v for v in (home_match.groups() if home_match else ()) if v), ""),
                    "launcher_only": "OPENAI_API_KEY" in body and "/accounts/" in body and "/v1" in body,
                }
            )
        return launchers

    def _codex_desktop_status(self) -> dict[str, Any]:
        config_path = DEFAULT_CODEX_HOME / "config.toml"
        data = {
            "detected": config_path.exists(),
            "config_path": str(config_path),
            "base_url": "",
            "managed_by": "unknown",
            "risk_flags": [],
        }
        if not config_path.exists():
            return data
        try:
            text = config_path.read_text(encoding="utf-8")
        except Exception as exc:
            data["risk_flags"].append(f"config_read_error:{exc}")
            return data
        match = re.search(r'^\s*base_url\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            data["base_url"] = match.group(1)
        if CC_SWITCH_BASE_URL in data["base_url"]:
            data["managed_by"] = "cc_switch"
        elif LOCAL_BRIDGE_BASE_URL in data["base_url"]:
            data["managed_by"] = "bridgedeck_or_local_bridge"
            data["risk_flags"].append("desktop_local_bridge_route")
        elif data["base_url"]:
            data["managed_by"] = "custom"
        else:
            data["managed_by"] = "default"
        return data

    def _list_codex_providers(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, name, provider_type, is_current, sort_index, meta, settings_config
            FROM providers
            WHERE app_type = 'codex'
            ORDER BY sort_index ASC, name ASC
            """
        ).fetchall()
        providers: list[dict[str, Any]] = []
        for row in rows:
            meta = self._extract_json(row["meta"])
            settings = self._extract_json(row["settings_config"])
            binding = meta.get("authBinding") if isinstance(meta.get("authBinding"), dict) else {}
            auth = settings.get("auth") if isinstance(settings.get("auth"), dict) else {}
            tokens = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
            meta_account = binding.get("accountId") if isinstance(binding.get("accountId"), str) else ""
            token_account = tokens.get("account_id") if isinstance(tokens.get("account_id"), str) else ""
            refresh_token = tokens.get("refresh_token") if isinstance(tokens.get("refresh_token"), str) else ""
            providers.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "provider_type": row["provider_type"] or "",
                    "is_current": bool(row["is_current"]),
                    "sort_index": row["sort_index"],
                    "meta_provider_type": meta.get("providerType") if isinstance(meta.get("providerType"), str) else "",
                    "meta_account_id": meta_account,
                    "token_account_id": token_account,
                    "refresh_sha12": sha12(refresh_token),
                    "token_mismatch": bool(meta_account and token_account and meta_account != token_account),
                }
            )
        return providers

    def _account_matrix(
        self,
        accounts: list[dict[str, Any]],
        providers: list[dict[str, Any]],
        codex_providers: list[dict[str, Any]],
        cli_homes: list[dict[str, Any]],
        cli_launchers: list[dict[str, Any]],
        desktop: dict[str, Any],
    ) -> list[dict[str, Any]]:
        provider_by_account: dict[str, list[dict[str, Any]]] = {}
        for provider in providers:
            account_id = str(provider.get("account_id") or "")
            if account_id:
                provider_by_account.setdefault(account_id, []).append(provider)
        codex_by_account: dict[str, list[dict[str, Any]]] = {}
        for provider in codex_providers:
            account_id = str(provider.get("meta_account_id") or provider.get("token_account_id") or "")
            if account_id:
                codex_by_account.setdefault(account_id, []).append(provider)
        homes_by_account: dict[str, list[dict[str, Any]]] = {}
        for home in cli_homes:
            account_id = str(home.get("token_account_id") or home.get("access_account_id") or "")
            if account_id:
                homes_by_account.setdefault(account_id, []).append(home)
        launchers_by_account: dict[str, list[dict[str, Any]]] = {}
        for launcher in cli_launchers:
            account_id = str(launcher.get("account_id") or "")
            if account_id:
                launchers_by_account.setdefault(account_id, []).append(launcher)

        bridge_ok = tcp_open("127.0.0.1", 8876)
        proxy_ok = tcp_open("127.0.0.1", 15721)
        matrix: list[dict[str, Any]] = []
        for account in accounts:
            account_id = str(account.get("account_id") or "")
            account_providers = provider_by_account.get(account_id, [])
            account_codex = codex_by_account.get(account_id, [])
            account_homes = homes_by_account.get(account_id, [])
            account_launchers = launchers_by_account.get(account_id, [])
            risk_flags: list[str] = []
            if not bridge_ok:
                risk_flags.append("bridge_down")
            if not proxy_ok:
                risk_flags.append("proxy_down")
            if any(p.get("token_mismatch") for p in account_codex):
                risk_flags.append("codex_provider_mismatch")
            if any("stale_cli_token_profile" in h.get("risk_flags", []) for h in account_homes):
                risk_flags.append("stale_cli_token_profile")
            if not account_launchers:
                risk_flags.append("missing_cli_launcher")
            if desktop.get("managed_by") == "cc_switch":
                desktop_state = "cc_switch"
            elif desktop.get("detected"):
                desktop_state = str(desktop.get("managed_by") or "detected")
            else:
                desktop_state = "not_detected"
            status = "ok"
            if "bridge_down" in risk_flags:
                status = "bridge_down"
            elif "proxy_down" in risk_flags:
                status = "proxy_down"
            elif "stale_cli_token_profile" in risk_flags:
                status = "stale_launcher"
            elif "codex_provider_mismatch" in risk_flags:
                status = "refresh_token_reused"
            advice = "正常"
            if status == "bridge_down":
                advice = "启动 local_codex_bridge.py"
            elif status == "proxy_down":
                advice = "启动 CC Switch"
            elif status == "stale_launcher":
                advice = "迁移旧 tokenful CLI profile"
            elif status == "refresh_token_reused":
                advice = "回 CC Switch 重新授权该账号"
            elif "missing_cli_launcher" in risk_flags:
                advice = "生成 Codex CLI 启动器"
            matrix.append(
                {
                    "account_id": account_id,
                    "email": account.get("email") or "",
                    "label": account.get("label") or "",
                    "account_status": status,
                    "quota_status": "unknown",
                    "claude_current": any(bool(p.get("is_current")) for p in account_providers),
                    "claude_providers": [p.get("name") for p in account_providers],
                    "cli_launchers": account_launchers,
                    "codex_cli_homes": account_homes,
                    "codex_desktop": desktop_state,
                    "desktop_detected": bool(desktop.get("detected")),
                    "risk_flags": risk_flags,
                    "advice": advice,
                }
            )
        return matrix

    def health(self) -> dict[str, Any]:
        snapshot = self.snapshot(include_secrets=False)
        risk_flags: list[str] = []
        if not tcp_open("127.0.0.1", 8876):
            risk_flags.append("bridge_down")
        if not tcp_open("127.0.0.1", 15721):
            risk_flags.append("proxy_down")
        for home in snapshot.get("cli_homes", []):
            if isinstance(home, dict):
                risk_flags.extend(str(item) for item in home.get("risk_flags", []))
        for provider in snapshot.get("codex_providers", []):
            if isinstance(provider, dict) and provider.get("token_mismatch"):
                risk_flags.append("codex_provider_mismatch")
        status = "ok" if not risk_flags else str(risk_flags[0])
        return {
            "ok": True,
            "status": status,
            "risk_flags": sorted(set(risk_flags)),
            "account_matrix": snapshot.get("account_matrix", []),
            "codex_desktop": snapshot.get("codex_desktop", {}),
        }

    def _default_provider_name(self, account: dict[str, Any], existing: set[str]) -> str:
        email = account.get("email") or ""
        prefix = "Local Codex Bridge"
        if email:
            left = email.split("@", 1)[0].strip()
            if left:
                candidate = f"{prefix} - {left}"
                if candidate not in existing:
                    return candidate
        short_id = account["account_id"][:8]
        candidate = f"{prefix} - {short_id}"
        if candidate not in existing:
            return candidate
        suffix = 2
        while True:
            candidate = f"{prefix} - {short_id}-{suffix}"
            if candidate not in existing:
                return candidate
            suffix += 1

    def _extract_json(self, text: Any) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _build_provider_payload(
        self,
        account_id: str,
        *,
        settings_config: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        settings = copy.deepcopy(settings_config) if isinstance(settings_config, dict) else {}
        if not isinstance(settings, dict):
            settings = {}
        env = settings.get("env")
        if not isinstance(env, dict):
            env = {}
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:8876/accounts/{account_id}"
        env["ANTHROPIC_AUTH_TOKEN"] = "local-bridge"
        env.setdefault("ANTHROPIC_MODEL", "gpt-5.4")
        env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", "gpt-5.4-mini")
        env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", "gpt-5.3-codex")
        env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "gpt-5.4")
        settings["env"] = env

        m = copy.deepcopy(meta) if isinstance(meta, dict) else {}
        if not isinstance(m, dict):
            m = {}
        # Keep Codex OAuth binding semantics for quota/account UI, route via local bridge transport.
        m["providerType"] = "codex_oauth"
        m["apiFormat"] = "openai_responses"
        m["codexOauthTransport"] = "local_bridge"
        binding = m.get("authBinding")
        if not isinstance(binding, dict):
            binding = {}
        binding["source"] = "managed_account"
        binding["authProvider"] = "codex_oauth"
        binding["accountId"] = account_id
        m["authBinding"] = binding

        return settings, m

    def _pick_template_provider(self, conn: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT settings_config, meta
            FROM providers
            WHERE app_type = 'claude'
            ORDER BY
              CASE
                WHEN name = 'Local Codex Bridge - Pro' THEN 0
                WHEN name = 'Local Codex Bridge - Plus' THEN 1
                ELSE 9
              END,
              sort_index ASC
            LIMIT 1
            """
        ).fetchall()
        if not rows:
            return {}, {}
        row = rows[0]
        return self._extract_json(row["settings_config"]), self._extract_json(row["meta"])

    def snapshot(self, include_secrets: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": APP_VERSION,
            "paths": {
                "db": str(self.paths.db),
                "settings": str(self.paths.settings),
                "auth_store": str(self.paths.auth_store),
            },
            "exists": {
                "db": self.paths.db.exists(),
                "settings": self.paths.settings.exists(),
                "auth_store": self.paths.auth_store.exists(),
            },
            "accounts": self._load_accounts(),
            "providers": [],
            "codex_providers": [],
            "cli_homes": self._known_cli_homes(),
            "cli_launchers": self._known_cli_launchers(),
            "codex_desktop": self._codex_desktop_status(),
            "account_matrix": [],
            "current_provider_from_settings": self._current_provider_from_settings(),
        }

        if not self.paths.db.exists():
            data["account_matrix"] = self._account_matrix(
                data["accounts"],
                data["providers"],
                data["codex_providers"],
                data["cli_homes"],
                data["cli_launchers"],
                data["codex_desktop"],
            )
            return data

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, provider_type, is_current, sort_index, meta, settings_config
                FROM providers
                WHERE app_type = 'claude'
                ORDER BY sort_index ASC, name ASC
                """
            ).fetchall()

            for row in rows:
                meta = self._extract_json(row["meta"])
                settings = self._extract_json(row["settings_config"])
                env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
                account_id = ""
                auth_binding = meta.get("authBinding")
                if isinstance(auth_binding, dict):
                    value = auth_binding.get("accountId")
                    if isinstance(value, str):
                        account_id = value
                auth_token = (
                    env.get("ANTHROPIC_AUTH_TOKEN")
                    if isinstance(env.get("ANTHROPIC_AUTH_TOKEN"), str)
                    else ""
                )

                data["providers"].append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "provider_type": row["provider_type"] or "",
                        "is_current": bool(row["is_current"]),
                        "sort_index": row["sort_index"],
                        "meta_provider_type": meta.get("providerType") if isinstance(meta.get("providerType"), str) else "",
                        "api_format": meta.get("apiFormat") if isinstance(meta.get("apiFormat"), str) else "",
                        "account_id": account_id,
                        "base_url": env.get("ANTHROPIC_BASE_URL") if isinstance(env.get("ANTHROPIC_BASE_URL"), str) else "",
                        "auth_token": auth_token if include_secrets else "",
                        "auth_token_masked": mask_token(auth_token),
                    }
                )

            data["codex_providers"] = self._list_codex_providers(conn)

        data["account_matrix"] = self._account_matrix(
            data["accounts"],
            data["providers"],
            data["codex_providers"],
            data["cli_homes"],
            data["cli_launchers"],
            data["codex_desktop"],
        )

        return data

    def set_current_provider(self, provider_id: str) -> dict[str, Any]:
        if not provider_id.strip():
            raise ValueError("provider_id 不能为空")
        with self._lock:
            db_bak = self._backup_file(self.paths.db, "set-current")
            settings_bak = self._backup_file(self.paths.settings, "set-current")
            with self._connect() as conn:
                hit = conn.execute(
                    "SELECT id FROM providers WHERE app_type = 'claude' AND id = ? LIMIT 1",
                    (provider_id,),
                ).fetchone()
                if not hit:
                    raise ValueError(f"provider 不存在: {provider_id}")
                conn.execute("UPDATE providers SET is_current = 0 WHERE app_type = 'claude'")
                conn.execute(
                    "UPDATE providers SET is_current = 1 WHERE app_type = 'claude' AND id = ?",
                    (provider_id,),
                )
                conn.commit()
            self._set_current_provider_in_settings(provider_id)
            return {
                "ok": True,
                "message": "已设置当前 provider",
                "provider_id": provider_id,
                "backups": [db_bak, settings_bak],
            }

    def create_or_update_provider(
        self,
        account_id: str,
        provider_name: str,
        set_current: bool,
    ) -> dict[str, Any]:
        if not account_id.strip():
            raise ValueError("account_id 不能为空")
        if not provider_name.strip():
            raise ValueError("provider_name 不能为空")

        account_ids = {item["account_id"] for item in self._load_accounts()}
        if account_id not in account_ids:
            raise ValueError(f"未找到账号: {account_id}")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "create-provider")
            settings_bak = self._backup_file(self.paths.settings, "create-provider")

            with self._connect() as conn:
                columns = self._provider_columns(conn)
                existing = conn.execute(
                    "SELECT id, settings_config, meta FROM providers WHERE app_type = 'claude' AND name = ? LIMIT 1",
                    (provider_name,),
                ).fetchone()
                if existing:
                    provider_id = str(existing["id"])
                    current_settings = self._extract_json(existing["settings_config"])
                    current_meta = self._extract_json(existing["meta"])
                else:
                    provider_id = str(uuid.uuid4())
                    template_settings, template_meta = self._pick_template_provider(conn)
                    current_settings = template_settings
                    current_meta = template_meta

                new_settings, new_meta = self._build_provider_payload(
                    account_id,
                    settings_config=current_settings,
                    meta=current_meta,
                )
                settings_text = json.dumps(new_settings, ensure_ascii=False)
                meta_text = json.dumps(new_meta, ensure_ascii=False)

                if existing:
                    updates = {
                        "settings_config": settings_text,
                        "meta": meta_text,
                        "provider_type": "codex_oauth",
                    }
                    assignments = []
                    values: list[Any] = []
                    for key, value in updates.items():
                        if key in columns:
                            assignments.append(f"{key} = ?")
                            values.append(value)
                    if not assignments:
                        raise RuntimeError("providers 表缺少可更新字段")
                    values.extend([provider_id, "claude"])
                    conn.execute(
                        f"UPDATE providers SET {', '.join(assignments)} WHERE id = ? AND app_type = ?",
                        values,
                    )
                else:
                    row = {
                        "id": provider_id,
                        "app_type": "claude",
                        "name": provider_name,
                        "settings_config": settings_text,
                        "meta": meta_text,
                        "provider_type": "codex_oauth",
                        "created_at": int(time.time()),
                        "sort_index": conn.execute(
                            "SELECT COALESCE(MAX(sort_index), 0) + 1 FROM providers WHERE app_type = 'claude'"
                        ).fetchone()[0],
                        "icon": "openai",
                        "icon_color": "#10A37F",
                        "is_current": 0,
                        "in_failover_queue": 0,
                        "cost_multiplier": "1.0",
                    }
                    insert_cols = [c for c in row.keys() if c in columns]
                    placeholders = ", ".join(["?"] * len(insert_cols))
                    conn.execute(
                        f"INSERT INTO providers ({', '.join(insert_cols)}) VALUES ({placeholders})",
                        [row[c] for c in insert_cols],
                    )

                if set_current:
                    conn.execute("UPDATE providers SET is_current = 0 WHERE app_type = 'claude'")
                    conn.execute(
                        "UPDATE providers SET is_current = 1 WHERE app_type = 'claude' AND id = ?",
                        (provider_id,),
                    )
                conn.commit()

            if set_current:
                self._set_current_provider_in_settings(provider_id)

            return {
                "ok": True,
                "message": "provider 已创建/更新",
                "provider_id": provider_id,
                "provider_name": provider_name,
                "set_current": set_current,
                "backups": [db_bak, settings_bak],
            }

    def patch_provider(self, provider_id: str) -> dict[str, Any]:
        if not provider_id.strip():
            raise ValueError("provider_id 不能为空")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "patch-provider")
            with self._connect() as conn:
                columns = self._provider_columns(conn)
                row = conn.execute(
                    "SELECT id, name, settings_config, meta FROM providers WHERE app_type = 'claude' AND id = ? LIMIT 1",
                    (provider_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"provider 不存在: {provider_id}")

                meta = self._extract_json(row["meta"])
                settings = self._extract_json(row["settings_config"])
                binding = meta.get("authBinding")
                if not isinstance(binding, dict):
                    raise ValueError("该 provider 没有 authBinding，无法自动补丁")
                account_id = binding.get("accountId")
                if not isinstance(account_id, str) or not account_id.strip():
                    raise ValueError("该 provider 缺少 authBinding.accountId")

                new_settings, new_meta = self._build_provider_payload(
                    account_id,
                    settings_config=settings,
                    meta=meta,
                )
                updates = {
                    "settings_config": json.dumps(new_settings, ensure_ascii=False),
                    "meta": json.dumps(new_meta, ensure_ascii=False),
                    "provider_type": "codex_oauth",
                }
                assignments = []
                values: list[Any] = []
                for key, value in updates.items():
                    if key in columns:
                        assignments.append(f"{key} = ?")
                        values.append(value)
                if not assignments:
                    raise RuntimeError("providers 表缺少可更新字段，无法打补丁")
                values.extend([provider_id, "claude"])
                conn.execute(
                    f"UPDATE providers SET {', '.join(assignments)} WHERE id = ? AND app_type = ?",
                    values,
                )
                conn.commit()

            return {
                "ok": True,
                "message": "provider 已打桥接补丁",
                "provider_id": provider_id,
                "backups": [db_bak],
            }

    def repair_plus_pro(self) -> dict[str, Any]:
        target_names = ["Local Codex Bridge - Plus", "Local Codex Bridge - Pro"]
        with self._lock:
            db_bak = self._backup_file(self.paths.db, "repair-plus-pro")
            patched: list[str] = []
            with self._connect() as conn:
                columns = self._provider_columns(conn)
                rows = conn.execute(
                    """
                    SELECT id, name, settings_config, meta
                    FROM providers
                    WHERE app_type = 'claude' AND name IN (?, ?)
                    """,
                    (target_names[0], target_names[1]),
                ).fetchall()
                for row in rows:
                    meta = self._extract_json(row["meta"])
                    settings = self._extract_json(row["settings_config"])
                    binding = meta.get("authBinding")
                    if not isinstance(binding, dict):
                        continue
                    account_id = binding.get("accountId")
                    if not isinstance(account_id, str) or not account_id.strip():
                        continue

                    new_settings, new_meta = self._build_provider_payload(
                        account_id,
                        settings_config=settings,
                        meta=meta,
                    )
                    updates = {
                        "settings_config": json.dumps(new_settings, ensure_ascii=False),
                        "meta": json.dumps(new_meta, ensure_ascii=False),
                        "provider_type": "codex_oauth",
                    }
                    assignments = []
                    values: list[Any] = []
                    for key, value in updates.items():
                        if key in columns:
                            assignments.append(f"{key} = ?")
                            values.append(value)
                    if not assignments:
                        continue
                    values.extend([row["id"], "claude"])
                    conn.execute(
                        f"UPDATE providers SET {', '.join(assignments)} WHERE id = ? AND app_type = ?",
                        values,
                    )
                    patched.append(str(row["name"]))
                conn.commit()

            return {
                "ok": True,
                "message": "Plus/Pro 修复完成",
                "patched": patched,
                "backups": [db_bak],
            }

    def create_or_sync_cli_home(
        self,
        account_id: str,
        target_dir: str,
        profile_name: str,
    ) -> dict[str, Any]:
        return self.create_cli_launcher(account_id, target_dir, profile_name, compatibility=True)

    def _validate_cli_home(self, target_dir: str) -> Path:
        target = Path(target_dir).expanduser()
        if not target.is_absolute():
            target = Path.home() / target
        target = target.resolve()
        if target == DEFAULT_CODEX_HOME.resolve():
            raise ValueError("CLI 独立账号不要写入默认 ~/.codex，请使用 ~/.codex-cli-*")
        home = Path.home().resolve()
        if target.parent != home or not target.name.startswith(".codex-cli-"):
            raise ValueError("CLI Home 必须是当前用户 Home 下的 ~/.codex-cli-* 目录")
        if target.is_symlink():
            raise ValueError("CLI Home 不能是符号链接")
        target_auth = target / "auth.json"
        if target_auth.is_symlink():
            raise ValueError("auth.json 不能是符号链接")
        return target

    def create_cli_launcher(
        self,
        account_id: str,
        target_dir: str,
        profile_name: str,
        *,
        compatibility: bool = False,
    ) -> dict[str, Any]:
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("account_id 不能为空")
        target = self._validate_cli_home(target_dir)
        with self._lock:
            store = self._load_auth_store_raw()
            accounts = store.get("accounts")
            if not isinstance(accounts, dict):
                raise ValueError("auth store 缺少 accounts")
            account_payload = accounts.get(account_id)
            if not isinstance(account_payload, dict):
                raise ValueError(f"未找到账号: {account_id}")
            target.mkdir(parents=True, exist_ok=True)
            os.chmod(target, 0o700)
            launcher_dir = DEFAULT_CLI_LAUNCHER_DIR
            launcher_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(launcher_dir, 0o700)
            launcher_name = safe_slug(profile_name or account_payload.get("email") or account_id[:8])
            launcher_path = launcher_dir / f"codex-{launcher_name}.command"
            codex_bin = which("codex") or "codex"
            base_url = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{account_id}/v1"
            config_arg = f'base_url="{base_url}"'
            launcher_path.write_text(
                "#!/bin/zsh\n"
                f"export CODEX_HOME={json.dumps(str(target))}\n"
                'export OPENAI_API_KEY="local-bridge"\n'
                f"exec {json.dumps(codex_bin)} -c '{config_arg}' \"$@\"\n",
                encoding="utf-8",
            )
            launcher_path.chmod(0o755)

            return {
                "ok": True,
                "message": "CLI 启动器已创建",
                "account_id": account_id,
                "target_dir": str(target),
                "run_command": f"CODEX_HOME={target} OPENAI_API_KEY=local-bridge codex -c 'base_url=\"{base_url}\"'",
                "launcher": str(launcher_path),
                "base_url": base_url,
                "launcher_only": True,
                "compatibility": compatibility,
                "warning": "不再复制或刷新 OpenAI token；旧 auth.json 如存在会在状态页标记为 stale_launcher。",
                "backups": [],
            }

    def migrate_cli_launcher(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        target = self._validate_cli_home(target_dir)
        auth_path = target / "auth.json"
        backups: list[str | None] = []
        if auth_path.exists():
            backup = self._backup_file(auth_path, "migrate-cli-launcher")
            backups.append(backup)
            archived = target / f"auth.json.disabled-by-bridgedeck-{now_ts()}"
            os.replace(auth_path, archived)
        result = self.create_cli_launcher(account_id, str(target), profile_name)
        result["message"] = "CLI 启动器已迁移"
        result["backups"] = [item for item in backups if item]
        return result


def is_loopback_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def host_from_header(value: str | None) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(f"//{value}")
    return parsed.hostname or ""


def origin_host(value: str | None) -> str:
    if not value:
        return ""
    return urllib.parse.urlsplit(value).hostname or ""


def mask_email_value(value: Any) -> Any:
    if not isinstance(value, str) or "@" not in value:
        return value
    left, domain = value.split("@", 1)
    if not left or not domain:
        return value
    visible = left[0] if len(left) <= 2 else f"{left[:2]}***{left[-1]}"
    return f"{visible}@{domain}"


def mask_id_value(value: Any) -> Any:
    if not isinstance(value, str) or len(value) <= 12:
        return value
    return f"{value[:8]}...{value[-4:]}"


def redact_path_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    home = str(Path.home())
    if value == home:
        return "~"
    if value.startswith(f"{home}/"):
        return f"~/{value[len(home) + 1:]}"
    return value


def redact_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = copy.deepcopy(payload)
    paths = redacted.get("paths")
    if isinstance(paths, dict):
        for key, value in list(paths.items()):
            paths[key] = redact_path_value(value)
    for account in redacted.get("accounts", []):
        if isinstance(account, dict):
            account["account_id"] = mask_id_value(account.get("account_id"))
            account["email"] = mask_email_value(account.get("email"))
            account["label"] = mask_email_value(account.get("label"))
            account["default_cli_home"] = redact_path_value(account.get("default_cli_home"))
    for provider in redacted.get("providers", []):
        if isinstance(provider, dict):
            provider["account_id"] = mask_id_value(provider.get("account_id"))
            provider["base_url"] = re.sub(r"/accounts/[^/?#]+", "/accounts/<redacted>", str(provider.get("base_url") or ""))
            provider["auth_token"] = ""
            provider["auth_token_masked"] = mask_token(provider.get("auth_token_masked"))
    for provider in redacted.get("codex_providers", []):
        if isinstance(provider, dict):
            provider["meta_account_id"] = mask_id_value(provider.get("meta_account_id"))
            provider["token_account_id"] = mask_id_value(provider.get("token_account_id"))
    for home in redacted.get("cli_homes", []):
        if isinstance(home, dict):
            home["path"] = redact_path_value(home.get("path"))
            home["run_command"] = redact_path_value(home.get("run_command"))
            home["token_account_id"] = mask_id_value(home.get("token_account_id"))
            home["access_account_id"] = mask_id_value(home.get("access_account_id"))
            home["email"] = mask_email_value(home.get("email"))
    for launcher in redacted.get("cli_launchers", []):
        if isinstance(launcher, dict):
            launcher["path"] = redact_path_value(launcher.get("path"))
            launcher["codex_home"] = redact_path_value(launcher.get("codex_home"))
            launcher["account_id"] = mask_id_value(launcher.get("account_id"))
    desktop = redacted.get("codex_desktop")
    if isinstance(desktop, dict):
        desktop["config_path"] = redact_path_value(desktop.get("config_path"))
        desktop["base_url"] = re.sub(r"/accounts/[^/?#]+", "/accounts/<redacted>", str(desktop.get("base_url") or ""))
    for row in redacted.get("account_matrix", []):
        if isinstance(row, dict):
            row["account_id"] = mask_id_value(row.get("account_id"))
            row["email"] = mask_email_value(row.get("email"))
            row["label"] = mask_email_value(row.get("label"))
            for launcher in row.get("cli_launchers", []):
                if isinstance(launcher, dict):
                    launcher["path"] = redact_path_value(launcher.get("path"))
                    launcher["codex_home"] = redact_path_value(launcher.get("codex_home"))
                    launcher["account_id"] = mask_id_value(launcher.get("account_id"))
    return redacted


def send_security_headers(handler: BaseHTTPRequestHandler, *, csp_nonce: str | None = None) -> None:
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
    handler.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if csp_nonce:
        handler.send_header(
            "Content-Security-Policy",
            (
                "default-src 'none'; "
                f"script-src 'nonce-{csp_nonce}'; "
                f"style-src 'nonce-{csp_nonce}'; "
                "connect-src 'self'; img-src 'self' data:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
        )


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    send_security_headers(handler)
    handler.end_headers()
    handler.wfile.write(body)


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BridgeDeck</title>
  <style nonce="__CSP_NONCE__">
    :root { --bg:#0f1115; --panel:#171a21; --line:#2a3040; --text:#e8ecf5; --muted:#9aa4b5; --ok:#39c980; --warn:#f0b429; --bad:#ff6b6b; --brand:#56a8ff; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }
    .wrap { max-width: 1280px; margin: 24px auto; padding: 0 16px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px; margin-bottom:14px; }
    .sectionHint { color:var(--muted); font-size:12px; margin:-4px 0 12px; line-height:1.5; }
    .layout { display:grid; grid-template-columns: 320px minmax(0, 1fr); gap:14px; align-items:start; }
    .sidebar { position: sticky; top: 16px; }
    .main { min-width:0; }
    h1 { margin:0 0 12px; font-size:20px; }
    h2 { margin:0 0 10px; font-size:16px; }
    .muted { color: var(--muted); font-size: 12px; }
    .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:8px; }
    input, select, button, textarea { border-radius:8px; border:1px solid var(--line); background:#0f1320; color:var(--text); padding:8px 10px; }
    input, select { min-width: 220px; }
    button { cursor:pointer; background:#1d2535; }
    button.primary { background: var(--brand); border-color: #3d8ce0; color: #041122; font-weight:700; }
    button.warn { background:#3a2b12; border-color:#6d4f1a; color:#ffd68a; }
    .tableWrap { width:100%; overflow-x:hidden; border-radius:10px; }
    table { width:100%; min-width:0; border-collapse: collapse; font-size:12px; table-layout: fixed; }
    th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; overflow-wrap:anywhere; word-break:break-word; }
    .nameCol { width:20%; }
    .smallCol { width:10%; }
    .accountCol { width:16%; }
    .urlCol { width:30%; }
    .tokenCol { width:12%; }
    .providerNameCell { display:flex; gap:8px; align-items:flex-start; min-width:0; }
    .providerNameCell input { flex:0 0 auto; min-width:0; margin-top:3px; }
    .providerNameText { min-width:0; overflow-wrap:anywhere; word-break:break-word; }
    .ok { color: var(--ok); }
    .bad { color: var(--bad); }
    .warnText { color: var(--warn); }
    .paths { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:11px; color: var(--muted); line-height:1.4; }
    .cmd, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color:#b7d8ff; word-break: break-all; }
    .steps { margin:0; padding-left:20px; color:var(--text); font-size:13px; line-height:1.65; }
    .steps code { color:#b7d8ff; }
    .stepNote { display:block; color:var(--muted); font-size:12px; margin-top:2px; }
    .guideTarget { color:var(--muted); font-size:12px; margin-bottom:10px; }
    .miniBtn { padding:5px 8px; font-size:12px; }
    .topGrid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; margin-top:12px; }
    .tile { border:1px solid var(--line); border-radius:8px; padding:10px; background:#101520; min-height:66px; }
    .tileLabel { color:var(--muted); font-size:11px; margin-bottom:6px; }
    .tileValue { font-size:18px; font-weight:700; }
    .recommend { margin-top:10px; padding:10px; border:1px solid var(--line); border-radius:8px; background:#111827; }
    .recommend.okState { border-color:#265f43; background:#102018; }
    .recommend.warnState { border-color:#7a5a1c; background:#211a0e; }
    .recommend.badState { border-color:#7a3232; background:#251414; }
    .quickbar { display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }
    summary { cursor:pointer; font-weight:700; }
    details.card { padding:0; }
    details.card > summary { padding:14px; list-style:none; }
    details.card > summary::-webkit-details-marker { display:none; }
    details.card > .detailsBody { padding:0 14px 14px; }
    textarea { width:100%; min-height:120px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px; }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .sidebar { position: static; }
      .topGrid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 560px) {
      .topGrid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>BridgeDeck</h1>
      <div id="status" class="muted">加载中...</div>
      <div class="topGrid">
        <div class="tile"><div class="tileLabel">账号</div><div id="tileAccounts" class="tileValue">-</div></div>
        <div class="tile"><div class="tileLabel">Claude Provider</div><div id="tileProviders" class="tileValue">-</div></div>
        <div class="tile"><div class="tileLabel">Codex Mismatch</div><div id="tileMismatches" class="tileValue">-</div></div>
        <div class="tile"><div class="tileLabel">CLI Home</div><div id="tileCliHomes" class="tileValue">-</div></div>
      </div>
      <div id="recommendation" class="recommend">加载中...</div>
      <div class="quickbar">
        <button class="primary" onclick="scrollToSection('providerCreateCard')">创建 Claude 桥接</button>
        <button onclick="scrollToSection('cliHomeCard')">切换 Codex CLI</button>
        <button onclick="scrollToSection('statusCard')">检查状态</button>
        <button onclick="refreshData()">刷新</button>
      </div>
      <div class="paths" id="paths"></div>
    </div>

    <div class="layout">
      <aside class="sidebar">
        <div class="card">
          <h2 id="guideTitle">当前操作</h2>
          <div id="guideTarget" class="guideTarget">随右侧当前板块自动切换</div>
          <ol id="guideSteps" class="steps"></ol>
        </div>
      </aside>

      <main class="main">
        <div class="card guideSection" id="providerCreateCard" data-guide="providerCreate">
          <h2>Claude 桥接账号</h2>
          <div class="sectionHint">把某个 ChatGPT 账号接到 Claude Code。通常只需要选账号，然后创建并设为当前。</div>
          <div class="row">
            <label>ChatGPT 账号</label>
            <select id="account"></select>
            <label>显示名称</label>
            <input id="providerName" placeholder="Local Codex Bridge - xxx" />
            <label><input type="checkbox" id="setCurrent" checked /> 设为当前</label>
            <button class="primary" onclick="createProvider()">创建/更新 Claude 桥接</button>
          </div>
          <div class="muted">工具会自动写入本地 bridge 配置，不需要手动编辑 URL/token。</div>
        </div>

        <div class="card guideSection" id="cliHomeCard" data-guide="cliHome">
          <h2>Codex CLI 切换</h2>
          <div class="sectionHint">生成 launcher-only 启动器：只设置 <code>CODEX_HOME</code>、<code>OPENAI_API_KEY</code> 和账号路由，不复制 OpenAI token，不改默认 <code>~/.codex</code>。</div>
          <div class="row">
            <label>账号</label>
            <select id="cliAccount"></select>
            <label>保存目录</label>
            <input id="cliHome" placeholder="~/.codex-cli-pro20x" />
            <label>启动器名称</label>
            <input id="cliProfileName" placeholder="pro20x" />
            <button class="primary" onclick="createCliHome()">生成启动器</button>
            <button onclick="migrateCliHome()">迁移旧 CLI 目录</button>
          </div>
          <div class="muted">切换 CLI 账号 = 使用对应启动脚本打开新的 Codex CLI，可多个账号同时运行。</div>
          <div class="paths" id="cliCommand"></div>
          <div class="muted" style="margin-top:10px;">可用账号：点“选用”自动填入推荐目录。</div>
          <div class="tableWrap">
            <table id="cliAccountsTable">
              <thead>
                <tr>
                  <th class="nameCol">账号名</th>
                  <th class="urlCol">email</th>
                  <th class="accountCol">account_id</th>
                  <th class="urlCol">推荐 CLI Home</th>
                  <th class="smallCol">操作</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
        </div>

        <details class="card guideSection" id="providerManageCard" data-guide="providerManage">
          <summary>高级：Claude Provider 管理</summary>
          <div class="detailsBody">
          <div class="sectionHint">只在需要切换、修复、排查 token 时使用。日常只看“当前”和“账号”。</div>
          <div class="row">
            <button onclick="refreshData()">刷新</button>
            <button class="miniBtn" id="tokenToggle" onclick="toggleTokens()">显示 token</button>
            <button onclick="setCurrentFromSelected()">设选中为当前</button>
            <button onclick="patchSelected()">修复选中桥接</button>
            <button class="warn" onclick="repairPlusPro()">修复 Plus/Pro</button>
          </div>
          <div class="tableWrap">
            <table id="providersTable">
              <thead>
                <tr>
                  <th class="nameCol">name</th>
                  <th class="smallCol">当前</th>
                  <th class="accountCol">account</th>
                  <th class="urlCol">base_url</th>
                  <th class="tokenCol">token</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
          </div>
        </details>

        <details class="card guideSection" id="statusCard" data-guide="status" open>
          <summary>账号状态检查</summary>
          <div class="detailsBody">
          <div class="sectionHint">自动检测 Claude Code、Codex CLI、Codex Desktop 当前状态。BridgeDeck 只检测 Desktop，不接管默认配置。</div>
          <div class="tableWrap">
            <table id="accountMatrixTable">
              <thead>
                <tr>
                  <th class="nameCol">账号</th><th class="smallCol">Claude</th><th class="smallCol">CLI</th><th class="smallCol">Desktop</th><th class="smallCol">状态</th><th class="urlCol">建议</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
          <br />
          <div class="tableWrap">
            <table id="codexProvidersTable">
              <thead>
                <tr>
                  <th class="nameCol">名称</th><th class="smallCol">当前</th><th class="accountCol">绑定账号</th><th class="accountCol">实际账号</th><th class="smallCol">状态</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
          <div id="diagnosis" class="recommend"></div>
          <br />
          <div class="muted">已配置 CLI 目录：这里只显示已经存在的 CODEX_HOME。</div>
          <div class="tableWrap">
            <table id="cliHomesTable">
              <thead>
                <tr>
                  <th class="urlCol">CLI 目录</th><th class="urlCol">切换命令</th><th class="accountCol">账号</th><th class="urlCol">email</th><th class="smallCol">状态</th><th class="urlCol">更新时间</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
          </div>
        </details>

        <details class="card guideSection" data-guide="log">
          <summary>执行日志</summary>
          <div class="detailsBody">
          <textarea id="log" readonly></textarea>
          </div>
        </details>
      </main>
    </div>
  </div>

  <script nonce="__CSP_NONCE__">
    const CSRF_TOKEN = "__CSRF_TOKEN__";
    let lastData = null;
    let tokenVisible = false;
    let lastAccounts = [];
    const GUIDES = {
      providerCreate: {
        title: 'Claude 桥接账号',
        target: '右侧板块：Claude 桥接账号',
        steps: [
          '选择 Claude Code 要使用的 ChatGPT 账号。',
          '显示名称不用改，除非你想重命名。',
          '保持“设为当前”勾选。',
          '点击“创建/更新 Claude 桥接”。',
          '下方 Provider 管理里看到“设置同步”就生效。'
        ]
      },
      cliHome: {
        title: 'Codex CLI 切换',
        target: '右侧板块：Codex CLI 切换',
        steps: [
          '在可用账号表点“选用”。',
          '保存目录保持 ~/.codex-cli-xxx。',
          '点击“生成启动器”。',
          '用页面输出的 launcher 启动该账号。',
          '以后也可双击生成的 .command 启动器。'
        ]
      },
      providerManage: {
        title: 'Claude Provider 管理',
        target: '右侧板块：Claude Provider 管理',
        steps: [
          '先点“刷新”。',
          '在 name 左侧选中一个 provider。',
          '点“设选中为当前”切换 Claude。',
          '点“修复选中桥接”只修当前行。',
          '点“修复 Plus/Pro”批量修两个固定桥接。'
        ]
      },
      status: {
        title: '状态检查',
        target: '右侧板块：账号状态检查',
        steps: [
          '账号矩阵看 Claude、CLI、Desktop 三端状态。',
          'stale_launcher 表示旧 CLI 目录里还有 token。',
          'Codex Provider mismatch 表示绑定账号和实际 token 不一致。',
          '~/.codex 只检测，不由 BridgeDeck 接管。',
          '~/.codex-cli-* 用 launcher-only 方式启动。'
        ]
      },
      log: {
        title: '执行日志',
        target: '右侧板块：执行日志',
        steps: [
          '每次刷新、创建、修复都会写日志。',
          '失败时先看这里的错误文本。',
          'refresh_token 失效时，回 CC Switch 重新登录该账号。',
          'stale_launcher 时，用“迁移旧 CLI 目录”。'
        ]
      }
    };
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function maskEmail(value) {
      const text = String(value || '');
      if (!text.includes('@')) return text;
      const [left, domain] = text.split('@');
      if (!left || !domain) return text;
      const visible = left.length <= 2 ? left[0] : `${left.slice(0, 2)}***${left.slice(-1)}`;
      return `${visible}@${domain}`;
    }
    function maskId(value) {
      const text = String(value || '');
      if (text.length <= 12) return text;
      return `${text.slice(0, 8)}...${text.slice(-4)}`;
    }
    function humanPath(value) {
      return String(value || '').replace(/^\\/Users\\/[^/]+/, '~');
    }
    function log(msg) {
      const box = document.getElementById('log');
      box.value += `[${new Date().toLocaleTimeString()}] ${msg}\\n`;
      box.scrollTop = box.scrollHeight;
    }
    function selectedProviderId() {
      const chosen = document.querySelector('input[name="providerPick"]:checked');
      return chosen ? chosen.value : '';
    }
    function scrollToSection(id) {
      const section = document.getElementById(id);
      if (!section) return;
      if (section.tagName === 'DETAILS') section.open = true;
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setGuide(section.dataset.guide || 'providerCreate');
    }
    function setGuide(key) {
      const guide = GUIDES[key] || GUIDES.providerCreate;
      document.getElementById('guideTitle').textContent = guide.title;
      document.getElementById('guideTarget').textContent = guide.target;
      document.getElementById('guideSteps').innerHTML = guide.steps.map((step) => `<li>${esc(step)}</li>`).join('');
    }
    function initGuideObserver() {
      const sections = Array.from(document.querySelectorAll('.guideSection'));
      if (!sections.length) return;
      setGuide(sections[0].dataset.guide || 'providerCreate');
      sections.forEach((section) => {
        section.addEventListener('mouseenter', () => setGuide(section.dataset.guide || 'providerCreate'));
        section.addEventListener('focusin', () => setGuide(section.dataset.guide || 'providerCreate'));
      });
      if (!('IntersectionObserver' in window)) return;
      const observer = new IntersectionObserver((entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setGuide(visible.target.dataset.guide || 'providerCreate');
      }, { root: null, rootMargin: '-20% 0px -55% 0px', threshold: [0.15, 0.35, 0.6] });
      sections.forEach((section) => observer.observe(section));
    }
    function tokenText(provider) {
      return tokenVisible ? (provider.auth_token || '') : (provider.auth_token_masked || '');
    }
    async function toggleTokens() {
      tokenVisible = !tokenVisible;
      document.getElementById('tokenToggle').textContent = tokenVisible ? '隐藏 token' : '显示 token';
      await refreshData();
    }
    function applyCliAccountDefaults(item) {
      if (!item) return;
      const shortId = item.account_id.slice(0, 8);
      const label = item.email && item.email.includes('@') ? item.email.split('@')[0] : shortId;
      document.getElementById('cliHome').value = humanPath(item.default_cli_home || `~/.codex-cli-${label}`);
      document.getElementById('cliProfileName').value = label;
    }
    function selectCliAccount(accountId) {
      const cliSel = document.getElementById('cliAccount');
      const idx = lastAccounts.findIndex((a) => a.account_id === accountId);
      if (idx < 0) return;
      cliSel.selectedIndex = idx;
      applyCliAccountDefaults(lastAccounts[idx]);
      log(`CLI 账号已选中: ${maskId(accountId)}`);
    }
    async function api(path, method='GET', payload=null) {
      const init = { method, headers: { 'X-CCSBT-Token': CSRF_TOKEN } };
      if (payload !== null) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(payload);
      }
      const resp = await fetch(path, init);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || data.ok === false) {
        throw new Error(data.error || data.message || `HTTP ${resp.status}`);
      }
      return data;
    }
    function renderAccounts(accounts) {
      lastAccounts = accounts;
      const sel = document.getElementById('account');
      const cliSel = document.getElementById('cliAccount');
      sel.innerHTML = '';
      cliSel.innerHTML = '';
      accounts.forEach((a) => {
        const opt = document.createElement('option');
        opt.value = a.account_id;
        const mail = a.email ? ` (${maskEmail(a.email)})` : '';
        opt.textContent = `${maskId(a.account_id)}${mail}`;
        sel.appendChild(opt);
        cliSel.appendChild(opt.cloneNode(true));
      });
      function applyAccountDefaults(item) {
        if (!item) return;
        const shortId = item.account_id.slice(0, 8);
        const label = item.email && item.email.includes('@') ? item.email.split('@')[0] : shortId;
        if (!document.getElementById('providerName').value.trim()) {
          document.getElementById('providerName').value = `Local Codex Bridge - ${label}`;
        }
        applyCliAccountDefaults(item);
      }
      if (accounts.length > 0 && !document.getElementById('providerName').value.trim()) {
        const a = accounts[0];
        applyAccountDefaults(a);
      }
      sel.onchange = () => {
        const idx = sel.selectedIndex;
        const item = accounts[idx];
        if (!item) return;
        const shortId = item.account_id.slice(0, 8);
        let name = `Local Codex Bridge - ${shortId}`;
        if (item.email && item.email.includes('@')) name = `Local Codex Bridge - ${item.email.split('@')[0]}`;
        document.getElementById('providerName').value = name;
      };
      cliSel.onchange = () => applyAccountDefaults(accounts[cliSel.selectedIndex]);
      renderCliAccounts(accounts);
    }
    function renderCliAccounts(accounts) {
      const body = document.querySelector('#cliAccountsTable tbody');
      body.innerHTML = '';
      accounts.forEach((a) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${esc(maskEmail(a.email || a.label || ''))}</td>
          <td>${esc(maskEmail(a.email || ''))}</td>
          <td class="mono">${esc(maskId(a.account_id || ''))}</td>
          <td class="mono">${esc(humanPath(a.default_cli_home || ''))}</td>
          <td><button class="miniBtn" onclick="selectCliAccount('${esc(a.account_id)}')">选用</button></td>
        `;
        body.appendChild(tr);
      });
    }
    function renderProviders(data) {
      const body = document.querySelector('#providersTable tbody');
      body.innerHTML = '';
      data.providers.forEach((p) => {
        const tr = document.createElement('tr');
        const currentBySettings = data.current_provider_from_settings === p.id;
        tr.innerHTML = `
          <td><label class="providerNameCell"><input type="radio" name="providerPick" value="${esc(p.id)}"><span class="providerNameText">${esc(p.name)}</span></label></td>
          <td>${p.is_current ? '<span class="ok">当前</span>' : '<span class="muted">未选</span>'} ${currentBySettings ? '<span class="ok">设置同步</span>' : ''}</td>
          <td class="mono">${esc(maskId(p.account_id || ''))}</td>
          <td class="mono">${esc(p.base_url || '')}</td>
          <td class="mono">${esc(tokenText(p))}</td>
        `;
        body.appendChild(tr);
      });
    }
    function renderCodexProviders(data) {
      const body = document.querySelector('#codexProvidersTable tbody');
      body.innerHTML = '';
      data.codex_providers.forEach((p) => {
        const tr = document.createElement('tr');
        const status = p.token_mismatch ? '<span class="bad">账号不一致</span>' : '<span class="ok">正常</span>';
        tr.innerHTML = `
          <td>${esc(p.name)}</td>
          <td>${p.is_current ? '<span class="ok">当前使用</span>' : '<span class="muted">备用</span>'}</td>
          <td>${esc(maskId(p.meta_account_id || ''))}</td>
          <td>${esc(maskId(p.token_account_id || ''))}</td>
          <td>${status}</td>
        `;
        body.appendChild(tr);
      });
    }
    function statusText(value) {
      const map = {
        ok: 'ok',
        near_limit: '接近限额',
        limit_reached: '额度用完',
        refresh_token_reused: '需重新授权',
        unsupported_region: '地区受限',
        bridge_down: 'bridge 断开',
        proxy_down: 'CC Switch 断开',
        stale_launcher: '旧 CLI token'
      };
      return map[value] || value || '';
    }
    function renderAccountMatrix(data) {
      const body = document.querySelector('#accountMatrixTable tbody');
      body.innerHTML = '';
      (data.account_matrix || []).forEach((row) => {
        const status = row.account_status || 'ok';
        const cls = status === 'ok' ? 'ok' : (status === 'stale_launcher' ? 'warnText' : 'bad');
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${esc(maskEmail(row.email || row.label || maskId(row.account_id || '')))}</td>
          <td>${row.claude_current ? '<span class="ok">当前</span>' : '<span class="muted">备用</span>'}</td>
          <td>${(row.cli_launchers || []).length ? '<span class="ok">launcher</span>' : '<span class="warnText">未生成</span>'}</td>
          <td>${esc(statusText(row.codex_desktop || ''))}</td>
          <td><span class="${cls}">${esc(statusText(status))}</span></td>
          <td>${esc(row.advice || '')}</td>
        `;
        body.appendChild(tr);
      });
    }
    function cliRunCommand(home) {
      if (home.run_command) return humanPath(home.run_command);
      const path = humanPath(home.path || '');
      return path === '~/.codex' ? 'codex' : `CODEX_HOME=${path} codex`;
    }
    function renderCliHomes(data) {
      const body = document.querySelector('#cliHomesTable tbody');
      body.innerHTML = '';
      data.cli_homes.forEach((h) => {
        const tr = document.createElement('tr');
        const stale = (h.risk_flags || []).includes('stale_cli_token_profile');
        tr.innerHTML = `
          <td class="cmd">${esc(humanPath(h.path))}</td>
          <td class="cmd">${esc(cliRunCommand(h))}</td>
          <td>${esc(maskId(h.token_account_id || h.access_account_id || ''))}</td>
          <td>${esc(maskEmail(h.email || ''))}</td>
          <td>${stale ? '<span class="warnText">stale_launcher</span>' : '<span class="ok">ok</span>'}</td>
          <td>${esc(h.last_refresh || '')}</td>
        `;
        body.appendChild(tr);
      });
    }
    function renderHealth(data) {
      const accountCount = data.accounts.length;
      const providerCount = data.providers.length;
      const mismatchCount = data.codex_providers.filter((p) => p.token_mismatch).length;
      const staleCount = data.cli_homes.filter((h) => (h.risk_flags || []).includes('stale_cli_token_profile')).length;
      const cliHomeCount = data.cli_homes.length;
      document.getElementById('tileAccounts').textContent = accountCount;
      document.getElementById('tileProviders').textContent = providerCount;
      document.getElementById('tileMismatches').textContent = mismatchCount;
      document.getElementById('tileMismatches').className = `tileValue ${mismatchCount ? 'bad' : 'ok'}`;
      document.getElementById('tileCliHomes').textContent = cliHomeCount;
      const box = document.getElementById('recommendation');
      let state = 'okState';
      let text = '状态正常。需要切账号时，直接使用上方两个创建入口。';
      if (accountCount === 0) {
        state = 'warnState';
        text = '未发现 CC Switch Codex OAuth 账号。先在 CC Switch 登录目标 ChatGPT 账号，再回这里刷新。';
      } else if (staleCount > 0) {
        state = 'warnState';
        text = `发现 ${staleCount} 个旧 CLI tokenful profile。建议迁移为 launcher-only，避免 refresh_token 重复使用。`;
      } else if (mismatchCount > 0) {
        state = 'badState';
        text = `发现 ${mismatchCount} 个 Codex Provider 账号不匹配。回 CC Switch 重新授权对应账号。`;
      } else if (providerCount === 0) {
        state = 'warnState';
        text = '还没有 Claude Provider。点击“创建 Claude 桥接”，选择账号后创建。';
      }
      box.className = `recommend ${state}`;
      box.textContent = text;
    }
    function renderDiagnosis(data) {
      const currentCodex = data.codex_providers.filter((p) => p.is_current);
      const mismatches = data.codex_providers.filter((p) => p.token_mismatch);
      const defaultCli = data.cli_homes.find((h) => humanPath(h.path) === '~/.codex');
      const staleHomes = data.cli_homes.filter((h) => (h.risk_flags || []).includes('stale_cli_token_profile'));
      const advice = [];
      let state = 'okState';
      if (data.accounts.length === 0) {
        state = 'warnState';
        advice.push('未检测到 CC Switch 中的 Codex OAuth 账号：先去 CC Switch 登录账号。');
      }
      if (currentCodex.length === 0) {
        state = 'warnState';
        advice.push('没有检测到当前 Codex Provider：在 CC Switch 里选一个 Codex Provider。');
      } else {
        advice.push(`当前 Codex Provider：${currentCodex.map((p) => p.name).join(', ')}。`);
      }
      if (mismatches.length > 0) {
        state = 'badState';
        advice.push(`发现 ${mismatches.length} 个账号不一致：回 CC Switch 重新授权对应账号。`);
      } else {
        advice.push('绑定账号与实际 token 账号一致。');
      }
      if (staleHomes.length > 0) {
        state = state === 'badState' ? state : 'warnState';
        advice.push(`发现 ${staleHomes.length} 个旧 CLI tokenful profile：建议迁移为 launcher-only。`);
      }
      if (defaultCli) {
        advice.push(`默认 Codex Desktop/CLI：只检测，不由 BridgeDeck 接管，${maskEmail(defaultCli.email || '') || '无邮箱信息'}。`);
      } else {
        state = state === 'badState' ? state : 'warnState';
        advice.push('未检测到默认 ~/.codex/auth.json：Codex Desktop/默认 CLI 可能还没登录。');
      }
      const box = document.getElementById('diagnosis');
      box.className = `recommend ${state}`;
      box.innerHTML = `<b>自动检测意见</b><br>${advice.map((item) => `- ${esc(item)}`).join('<br>')}`;
    }
    async function refreshData() {
      const data = await api(tokenVisible ? '/api/data?include_secrets=1' : '/api/data');
      lastData = data;
      const mismatches = data.codex_providers.filter((p) => p.token_mismatch).length;
      document.getElementById('status').innerHTML = `版本: <b>${esc(data.version || '')}</b> | 账号: <b>${data.accounts.length}</b> | Claude providers: <b>${data.providers.length}</b> | Codex mismatches: <b class="${mismatches ? 'bad' : 'ok'}">${mismatches}</b>`;
      document.getElementById('paths').textContent = `db: ${humanPath(data.paths.db)}\\nsettings: ${humanPath(data.paths.settings)}\\nauth_store: ${humanPath(data.paths.auth_store)}`;
      renderHealth(data);
      renderAccounts(data.accounts);
      renderAccountMatrix(data);
      renderProviders(data);
      renderCodexProviders(data);
      renderCliHomes(data);
      renderDiagnosis(data);
      log('数据已刷新');
    }
    async function createProvider() {
      const accountId = document.getElementById('account').value;
      const providerName = document.getElementById('providerName').value.trim();
      const setCurrent = document.getElementById('setCurrent').checked;
      if (!accountId || !providerName) {
        log('请选择账号并填写 provider 名称');
        return;
      }
      const res = await api('/api/create-provider', 'POST', { account_id: accountId, provider_name: providerName, set_current: setCurrent });
      log(`${res.message}: ${res.provider_name} (${res.provider_id})`);
      await refreshData();
    }
    async function createCliHome() {
      const accountId = document.getElementById('cliAccount').value;
      const targetDir = document.getElementById('cliHome').value.trim();
      const profileName = document.getElementById('cliProfileName').value.trim();
      if (!accountId || !targetDir) return log('请选择账号并填写 CLI Home');
      const res = await api('/api/create-cli-launcher', 'POST', { account_id: accountId, target_dir: targetDir, profile_name: profileName });
      document.getElementById('cliCommand').textContent = `启动命令: ${humanPath(res.run_command)}\\n启动脚本: ${humanPath(res.launcher)}`;
      log(`${res.message}: ${res.target_dir}`);
      await refreshData();
    }
    async function migrateCliHome() {
      const accountId = document.getElementById('cliAccount').value;
      const targetDir = document.getElementById('cliHome').value.trim();
      const profileName = document.getElementById('cliProfileName').value.trim();
      if (!accountId || !targetDir) return log('请选择账号并填写 CLI Home');
      const res = await api('/api/migrate-cli-launcher', 'POST', { account_id: accountId, target_dir: targetDir, profile_name: profileName });
      document.getElementById('cliCommand').textContent = `启动命令: ${humanPath(res.run_command)}\\n启动脚本: ${humanPath(res.launcher)}`;
      log(`${res.message}: ${res.target_dir}`);
      await refreshData();
    }
    async function setCurrentFromSelected() {
      const id = selectedProviderId();
      if (!id) return log('请先选中一个 provider');
      const res = await api('/api/set-current', 'POST', { provider_id: id });
      log(`${res.message}: ${id}`);
      await refreshData();
    }
    async function patchSelected() {
      const id = selectedProviderId();
      if (!id) return log('请先选中一个 provider');
      const res = await api('/api/patch-provider', 'POST', { provider_id: id });
      log(`${res.message}: ${id}`);
      await refreshData();
    }
    async function repairPlusPro() {
      const res = await api('/api/repair-plus-pro', 'POST', {});
      log(`${res.message}: ${JSON.stringify(res.patched)}`);
      await refreshData();
    }
    initGuideObserver();
    refreshData().catch((e) => log(`初始化失败: ${e.message}`));
  </script>
</body>
</html>
"""


def build_handler(
    manager: BridgeManager,
    csrf_token: str,
    csp_nonce: str,
    allow_sensitive: bool,
    allow_remote_access: bool,
):
    class Handler(BaseHTTPRequestHandler):
        def _valid_host(self) -> bool:
            host = host_from_header(self.headers.get("Host"))
            if not host:
                return False
            return allow_remote_access or is_loopback_host(host)

        def _valid_origin(self) -> bool:
            origin = origin_host(self.headers.get("Origin"))
            if not origin:
                return True
            return allow_remote_access or is_loopback_host(origin)

        def _valid_csrf(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-CCSBT-Token", ""), csrf_token)

        def _valid_fetch_metadata(self) -> bool:
            site = self.headers.get("Sec-Fetch-Site")
            if not site:
                return True
            return site in {"same-origin", "same-site", "none"}

        def do_GET(self) -> None:
            if not self._valid_host():
                json_response(self, 403, {"ok": False, "error": "Invalid Host header"})
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                body = (
                    INDEX_HTML.replace("__CSRF_TOKEN__", csrf_token)
                    .replace("__CSP_NONCE__", csp_nonce)
                    .encode("utf-8")
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                send_security_headers(self, csp_nonce=csp_nonce)
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/data":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    query = urllib.parse.parse_qs(parsed.query)
                    include_secrets = query.get("include_secrets", ["0"])[0] == "1"
                    if include_secrets and not allow_sensitive:
                        json_response(self, 403, {"ok": False, "error": "Secret display is disabled for remote mode"})
                        return
                    snapshot = manager.snapshot(include_secrets=include_secrets)
                    if not allow_sensitive:
                        snapshot = redact_snapshot(snapshot)
                    payload = {"ok": True, **snapshot}
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/health":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.health()
                    if not allow_sensitive:
                        payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            json_response(self, 404, {"ok": False, "error": "Not Found"})

        def do_POST(self) -> None:
            if not self._valid_host():
                json_response(self, 403, {"ok": False, "error": "Invalid Host header"})
                return
            if not self._valid_origin():
                json_response(self, 403, {"ok": False, "error": "Invalid Origin header"})
                return
            if not self._valid_fetch_metadata():
                json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                return
            if not allow_sensitive:
                json_response(self, 403, {"ok": False, "error": "Write APIs are disabled for remote mode"})
                return
            if not self._valid_csrf():
                json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                json_response(self, 400, {"ok": False, "error": "Invalid Content-Length"})
                return
            if length > MAX_REQUEST_BYTES:
                json_response(self, 413, {"ok": False, "error": "Request body too large"})
                return
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    payload = {}
            except Exception:
                payload = {}

            try:
                if self.path in {"/api/set-current", "/api/switch-claude"}:
                    provider_id = str(payload.get("provider_id") or "")
                    result = manager.set_current_provider(provider_id)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/create-provider":
                    account_id = str(payload.get("account_id") or "")
                    provider_name = str(payload.get("provider_name") or "")
                    set_current = bool(payload.get("set_current", True))
                    result = manager.create_or_update_provider(account_id, provider_name, set_current)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/patch-provider":
                    provider_id = str(payload.get("provider_id") or "")
                    result = manager.patch_provider(provider_id)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/repair-plus-pro":
                    result = manager.repair_plus_pro()
                    json_response(self, 200, result)
                    return
                if self.path in {"/api/create-cli-home", "/api/create-cli-launcher"}:
                    account_id = str(payload.get("account_id") or "")
                    target_dir = str(payload.get("target_dir") or "")
                    profile_name = str(payload.get("profile_name") or "")
                    if self.path == "/api/create-cli-home":
                        result = manager.create_or_sync_cli_home(account_id, target_dir, profile_name)
                    else:
                        result = manager.create_cli_launcher(account_id, target_dir, profile_name)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/migrate-cli-launcher":
                    account_id = str(payload.get("account_id") or "")
                    target_dir = str(payload.get("target_dir") or "")
                    profile_name = str(payload.get("profile_name") or "")
                    result = manager.migrate_cli_launcher(account_id, target_dir, profile_name)
                    json_response(self, 200, result)
                    return
                json_response(self, 404, {"ok": False, "error": "Not Found"})
            except Exception as exc:  # noqa: BLE001
                json_response(self, 400, {"ok": False, "error": str(exc)})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BridgeDeck local account bridge helper")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to cc-switch.db")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH, help="Path to settings.json")
    parser.add_argument("--auth-store", type=Path, default=DEFAULT_AUTH_PATH, help="Path to codex_oauth_auth.json")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Listen host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding to a non-loopback host. Remote mode is read-only and cannot reveal secrets.",
    )
    parser.add_argument(
        "--allow-remote-write",
        action="store_true",
        help="Allow write APIs and token reveal when using --allow-remote. Use only on trusted networks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    host_is_loopback = is_loopback_host(str(args.host))
    if not args.allow_remote and not host_is_loopback:
        raise SystemExit("Refusing to listen on non-loopback host without --allow-remote")
    if args.allow_remote_write and not args.allow_remote:
        raise SystemExit("--allow-remote-write requires --allow-remote")
    manager = BridgeManager(
        ManagerPaths(
            db=args.db,
            settings=args.settings,
            auth_store=args.auth_store,
        )
    )
    allow_sensitive = host_is_loopback or bool(args.allow_remote_write)
    handler = build_handler(
        manager,
        secrets.token_urlsafe(32),
        secrets.token_urlsafe(32),
        allow_sensitive=allow_sensitive,
        allow_remote_access=bool(args.allow_remote),
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"BridgeDeck running at http://{args.host}:{args.port}")
    print(f"db={args.db}")
    print(f"settings={args.settings}")
    print(f"auth_store={args.auth_store}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
