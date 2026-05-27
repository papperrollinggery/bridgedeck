#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import html
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import copy2, which
from typing import Any


DEFAULT_DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
DEFAULT_SETTINGS_PATH = Path.home() / ".cc-switch" / "settings.json"
DEFAULT_AUTH_PATH = Path.home() / ".cc-switch" / "codex_oauth_auth.json"
DEFAULT_CCSWITCH_COMMON_CONFIG_PATH = Path.home() / ".ccswitch-common-config.json"
DEFAULT_CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
DEFAULT_CLAUDE_INSTALLED_PLUGINS_PATH = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_CODEX_AUTH_PATH = DEFAULT_CODEX_HOME / "auth.json"
DEFAULT_AIMAMI_REGISTRY_PATH = DEFAULT_CODEX_HOME / "accounts" / "registry.json"
DEFAULT_AIMAMI_SNAPSHOTS_DIR = DEFAULT_CODEX_HOME / "accounts" / "snapshots"
DEFAULT_AIMAMI_EXPORT_DIR = Path.home() / "Downloads"
DEFAULT_AIMAMI_INJECT_VERIFICATION_PATH = Path.home() / ".cc-switch" / "bridgedeck-aimami-inject-verification.json"
DEFAULT_AIMAMI_APP_PATH = Path("/Applications/AiMaMi.app")
CODEX_APP_DYNAMIC_TOOLS = (
    "automation_update",
    "read_thread_terminal",
    "load_workspace_dependencies",
)
CODEX_REMOTE_THREAD_CLIENT_MARKERS = ("remote", "ios", "chatgpt")
CODEX_DESKTOP_LOG_ROOT = Path.home() / "Library" / "Logs" / "com.openai.codex"
CODEX_DESKTOP_SENTRY_SCOPE_PATH = (
    Path.home() / "Library" / "Application Support" / "Codex" / "sentry" / "scope_v3.json"
)
DEFAULT_INSTALL_STATE_PATH = Path(
    os.environ.get(
        "BRIDGEDECK_INSTALL_STATE_PATH",
        str(Path.home() / "Library" / "Application Support" / "BridgeDeck" / "install-state.json"),
    )
)
DEFAULT_CLI_LAUNCHER_DIR = Path.home() / ".cc-switch" / "codex-cli-launchers"
DEFAULT_LOCAL_BRIDGE_STATE_PATH = Path(
    os.environ.get(
        "BRIDGEDECK_LOCAL_BRIDGE_STATE_PATH",
        str(Path.home() / ".cc-switch" / "bridgedeck-local-bridge-state.json"),
    )
)
DEFAULT_LOCAL_BRIDGE_LOG_PATHS = (
    Path.home() / ".cc-switch" / "bridgedeck-local-bridge.log",
    Path.home() / "Library" / "Logs" / "local-codex-bridge.log",
)
DEFAULT_OMC_CODEX_SHIM_PATHS = (
    DEFAULT_CLI_LAUNCHER_DIR / "bin" / "codex",
    Path.home() / ".codebuddy" / "bin" / "codex",
    Path.home() / ".workbuddy" / "bin" / "codex",
)
DEFAULT_ZPROFILE_PATH = Path.home() / ".zprofile"
DEFAULT_AUTO_SWITCH_PATH = Path.home() / ".cc-switch" / "bridgedeck-auto-switch.json"
DEFAULT_AIMAMI_FOLLOW_PATH = Path.home() / ".cc-switch" / "bridgedeck-aimami-follow.json"
DEFAULT_API_KEYS_PATH = Path.home() / ".cc-switch" / "bridgedeck-keys.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8899
APP_VERSION = "0.2.22"
MAX_REQUEST_BYTES = 1024 * 1024
LOCAL_BRIDGE_BASE_URL = "http://127.0.0.1:8876"
CC_SWITCH_BASE_URL = "http://127.0.0.1:15721"
LOCAL_BRIDGE_PORT = 8876
COMMON_UPSTREAM_PROXY_PORTS = (1087, 7890, 6152, 8080)
LEGACY_PROXY_PROCESS_HINTS = (
    ("v2rayu", "V2rayU (v2ray)"),
    ("v2ray-core", "v2ray-core"),
    ("v2ray", "v2ray-core"),
)
KNOWN_PROXY_PROCESS_HINTS = (
    *LEGACY_PROXY_PROCESS_HINTS,
    ("shadowrocket", "Shadowrocket"),
    ("clash", "Clash"),
    ("mihomo", "Mihomo"),
    ("sing-box", "sing-box"),
    ("surge", "Surge"),
    ("xray", "Xray"),
)
COMPACT_WINDOW_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
COMPACT_THRESHOLD_ENV = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
MAX_CONTEXT_TOKENS_ENV = "CLAUDE_CODE_MAX_CONTEXT_TOKENS"
CLAUDE_CODE_ATTRIBUTION_HEADER_ENV = "CLAUDE_CODE_ATTRIBUTION_HEADER"
CLAUDE_CODE_ATTRIBUTION_DISABLED_VALUE = "0"
DEFAULT_COMPACT_WINDOW_TOKENS = 220_000
DEFAULT_COMPACT_THRESHOLD_PERCENT = 80
DEFAULT_BRIDGE_PROVIDER_MODEL = "gpt-5.5"
BRIDGE_MODEL_OPTIONS = (
    {
        "id": "gpt-5.5",
        "name": "gpt-5.5",
        "context_tokens": 272_000,
        "max_output_tokens": 128_000,
        "thinking_levels": ("low", "medium", "high", "xhigh"),
    },
    {"id": "gpt-5.4", "name": "gpt-5.4", "context_tokens": 220_000, "thinking_levels": ("low", "medium", "high", "xhigh")},
    {"id": "gpt-5.4-mini", "name": "gpt-5.4 Mini", "context_tokens": 220_000, "thinking_levels": ("low", "medium", "high", "xhigh")},
    {"id": "gpt-5.3-codex", "name": "gpt-5.3-codex", "context_tokens": 220_000},
    {"id": "gpt-5.3-codex-spark", "name": "gpt-5.3-codex-spark", "context_tokens": 220_000},
)
MODEL_ENV_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
)
MODEL_DISPLAY_ENV_KEYS = (
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
)
SAFE_COMMON_CONFIG_KEYS = (
    "hooks",
    "permissions",
    "statusLine",
    "cleanupPeriodDays",
    "enableAllProjectMcpServers",
    "enabledMcpjsonServers",
    "enabledPlugins",
)
SAFE_COMMON_ENV_KEYS = (
    "ENABLE_TOOL_SEARCH",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    CLAUDE_CODE_ATTRIBUTION_HEADER_ENV,
)
PROVIDER_SCOPED_ENV_KEYS = {
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    *MODEL_ENV_KEYS,
    *MODEL_DISPLAY_ENV_KEYS,
    COMPACT_WINDOW_ENV,
    COMPACT_THRESHOLD_ENV,
    MAX_CONTEXT_TOKENS_ENV,
}
CODEX_GLOBAL_ENV_CONFLICT_KEYS = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
)
CANONICAL_BRIDGE_NAMES = (
    "Local Codex Bridge - Plus",
    "Local Codex Bridge - Pro",
    "Local Codex Bridge - Pro 20x",
)
PROVIDER_SURFACE_APP_TYPES = {
    "claude_code": "claude",
    "claude_desktop": "claude-desktop",
}
PROVIDER_APP_TYPE_SURFACES = {value: key for key, value in PROVIDER_SURFACE_APP_TYPES.items()}
CLAUDE_DESKTOP_ROUTE_SPECS = (
    {
        "alias": "claude-haiku-4-5",
        "slot": "haiku",
        "env": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "display_env": "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
        "display_name": "Haiku 4.5",
        "default_model": "gpt-5.3-codex-spark",
    },
    {
        "alias": "claude-sonnet-4-6",
        "slot": "sonnet",
        "env": "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "display_env": "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
        "display_name": "Sonnet 4.6",
        "default_model": "gpt-5.3-codex",
    },
    {
        "alias": "claude-opus-4-7",
        "slot": "opus",
        "env": "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "display_env": "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
        "display_name": "Opus 4.7",
        "default_model": "gpt-5.5",
    },
)
MANAGED_CODEX_SHIM_MARKER = "BridgeDeck managed codex-current shim"
MANAGED_CODEX_PATH_START = "# >>> BridgeDeck codex shim >>>"
MANAGED_CODEX_PATH_END = "# <<< BridgeDeck codex shim <<<"
MANAGED_CODEX_DESKTOP_BRIDGE_START = "# >>> BridgeDeck temporary Codex Desktop bridge >>>"
MANAGED_CODEX_DESKTOP_BRIDGE_END = "# <<< BridgeDeck temporary Codex Desktop bridge <<<"
CODEX_DESKTOP_BRIDGE_DISABLED_REASON = "codex_desktop_compact_route_unsupported"
CODEX_DESKTOP_BRIDGE_DISABLED_MESSAGE = (
    "Codex Desktop Stability Route 已禁用：Local Bridge 不支持 /v1/responses/compact，启用会导致上下文压缩 404。"
)
PROXY_DIAG_OPENAI_URL = "https://api.openai.com/v1/models"
PROXY_DIAG_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_PROXY_LOOKUP_KEYS = ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy")
CODEX_NATIVE_PROXY_REQUIRED_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "WS_PROXY",
    "WSS_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "ws_proxy",
    "wss_proxy",
    "NO_PROXY",
    "no_proxy",
)
CODEX_NATIVE_NO_PROXY_VALUE = "localhost,127.0.0.1,::1"
CODEX_NATIVE_PROXY_CANDIDATES = (
    "http://127.0.0.1:1087",
    "http://127.0.0.1:7890",
    "http://127.0.0.1:6789",
)
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_OAUTH_CALLBACK_HOST = "127.0.0.1"
CODEX_OAUTH_CALLBACK_PORT = 1455
CODEX_OAUTH_SCOPE = "openid profile email offline_access"
CODEX_DEVICE_SCOPE = "openid profile email"
CODEX_DEVICE_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
CODEX_DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
CODEX_DEVICE_VERIFY_URL = "https://auth.openai.com/codex/device"
CODEX_DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
CODEX_DEVICE_CODE_VERIFIER = "cc-switch-codex-oauth"
CODEX_DEVICE_USER_AGENT = "cc-switch-codex-oauth"
CODEX_OAUTH_FLOW_TTL_SECS = 10 * 60


def now_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


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


def mask_token_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return mask_token(value)


def truncate_log_text(value: str | None, *, limit: int = 240) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def sha12(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def default_compact_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "window_tokens": str(DEFAULT_COMPACT_WINDOW_TOKENS),
        "threshold_percent": str(DEFAULT_COMPACT_THRESHOLD_PERCENT),
    }


def _parse_int_setting(value: Any, field_name: str, *, min_value: int, max_value: int) -> int:
    text = str(value or "").strip().replace(",", "").replace("_", "")
    if not text or not re.fullmatch(r"\d+", text):
        raise ValueError(f"{field_name} 必须是数字")
    parsed = int(text)
    if parsed < min_value or parsed > max_value:
        raise ValueError(f"{field_name} 必须在 {min_value}-{max_value} 之间")
    return parsed


def _bool_setting(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return bool(value)


def normalize_compact_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config if isinstance(config, dict) else {}
    window_raw = str(config.get("window_tokens") or config.get("window") or "").strip()
    enabled = _bool_setting(config["enabled"]) if "enabled" in config else bool(window_raw)
    if not enabled:
        return {"enabled": False, "window_tokens": "", "threshold_percent": ""}

    window = (
        _parse_int_setting(window_raw, "上下文窗口", min_value=10_000, max_value=2_000_000)
        if window_raw
        else DEFAULT_COMPACT_WINDOW_TOKENS
    )
    threshold_raw = str(config.get("threshold_percent") or config.get("pct") or "").strip()
    threshold = (
        _parse_int_setting(threshold_raw, "压缩阈值", min_value=1, max_value=100)
        if threshold_raw
        else DEFAULT_COMPACT_THRESHOLD_PERCENT
    )
    return {"enabled": True, "window_tokens": str(window), "threshold_percent": str(threshold)}


def apply_compact_config_to_env(env: dict[str, Any], compact_config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_compact_config(compact_config)
    if normalized["enabled"]:
        env[COMPACT_WINDOW_ENV] = normalized["window_tokens"]
        env[COMPACT_THRESHOLD_ENV] = normalized["threshold_percent"]
    else:
        env.pop(COMPACT_WINDOW_ENV, None)
        env.pop(COMPACT_THRESHOLD_ENV, None)
    return normalized


def normalize_openai_model_id(value: Any) -> str:
    model = str(value or "").strip()
    if re.match(r"(?i)^gpt-", model):
        return model.lower()
    return model


def normalize_provider_model_env(env: dict[str, Any]) -> None:
    for key in MODEL_ENV_KEYS:
        if isinstance(env.get(key), str):
            env[key] = normalize_openai_model_id(env[key])


def apply_bridge_safe_model_display_names(env: dict[str, Any]) -> None:
    for spec in CLAUDE_DESKTOP_ROUTE_SPECS:
        display_env = spec.get("display_env")
        if not isinstance(display_env, str):
            continue
        current = env.get(display_env)
        current_text = current.strip() if isinstance(current, str) else ""
        if not current_text or re.match(r"(?i)^gpt-", current_text):
            env[display_env] = spec["display_name"]


def bridge_model_option(model_id: str | None) -> dict[str, Any] | None:
    normalized = normalize_openai_model_id(model_id)
    for item in BRIDGE_MODEL_OPTIONS:
        if item["id"] == normalized:
            return item
    return None


def normalize_bridge_model_config(config: dict[str, Any] | None) -> dict[str, str]:
    config = config if isinstance(config, dict) else {}
    model = normalize_openai_model_id(config.get("model") or config.get("id") or DEFAULT_BRIDGE_PROVIDER_MODEL)
    option = bridge_model_option(model)
    if option is None and not re.match(r"(?i)^gpt-", model):
        raise ValueError(f"不支持的模型: {model}")

    context_raw = str(config.get("context_tokens") or config.get("context_length") or "").strip()
    if not context_raw and option and option.get("context_tokens"):
        context_raw = str(option["context_tokens"])
    context_tokens = ""
    if context_raw:
        context_tokens = str(_parse_int_setting(context_raw, "模型上下文", min_value=10_000, max_value=2_000_000))

    max_output_raw = str(config.get("max_output_tokens") or config.get("max_completion_tokens") or "").strip()
    if not max_output_raw and option and option.get("max_output_tokens"):
        max_output_raw = str(option["max_output_tokens"])
    max_output_tokens = ""
    if max_output_raw:
        max_output_tokens = str(_parse_int_setting(max_output_raw, "最大输出", min_value=1_000, max_value=2_000_000))

    return {"model": model, "context_tokens": context_tokens, "max_output_tokens": max_output_tokens}


def apply_bridge_context_config_to_env(env: dict[str, Any], model_config: dict[str, Any] | None) -> dict[str, str]:
    normalized = normalize_bridge_model_config(model_config)
    if normalized["context_tokens"]:
        env[MAX_CONTEXT_TOKENS_ENV] = normalized["context_tokens"]
    else:
        env.pop(MAX_CONTEXT_TOKENS_ENV, None)
    normalize_provider_model_env(env)
    return normalized


def apply_bridge_model_config_to_env(env: dict[str, Any], model_config: dict[str, Any] | None) -> dict[str, str]:
    normalized = apply_bridge_context_config_to_env(env, model_config)
    env["ANTHROPIC_MODEL"] = normalized["model"]
    normalize_provider_model_env(env)
    return normalized


def clear_forced_bridge_model_from_env(env: dict[str, Any]) -> str:
    model = env.get("ANTHROPIC_MODEL")
    env.pop("ANTHROPIC_MODEL", None)
    normalize_provider_model_env(env)
    return model if isinstance(model, str) else ""


def provider_surface_app_type(surface: str | None) -> str:
    normalized = str(surface or "claude_code").strip().lower().replace("-", "_")
    if normalized in PROVIDER_SURFACE_APP_TYPES:
        return PROVIDER_SURFACE_APP_TYPES[normalized]
    if normalized in PROVIDER_APP_TYPE_SURFACES:
        return normalized
    raise ValueError(f"不支持的 provider surface: {surface}")


def provider_surface_for_app_type(app_type: str | None) -> str:
    return PROVIDER_APP_TYPE_SURFACES.get(str(app_type or "").strip(), str(app_type or "").strip() or "unknown")


def bridge_model_context_tokens(model_id: str | None) -> int:
    option = bridge_model_option(model_id)
    if option and option.get("context_tokens"):
        return int(option["context_tokens"])
    return 0


def bridge_model_supports_1m(model_id: str | None) -> bool:
    return bridge_model_context_tokens(model_id) >= 1_000_000


def claude_desktop_routes_from_env(env: dict[str, Any]) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    for spec in CLAUDE_DESKTOP_ROUTE_SPECS:
        model = normalize_openai_model_id(env.get(spec["env"]) or spec["default_model"])
        display_name = env.get(spec["display_env"])
        if not isinstance(display_name, str) or not display_name.strip() or re.match(r"(?i)^gpt-", display_name.strip()):
            display_name = spec["display_name"]
        routes[spec["alias"]] = {
            "model": model,
            "labelOverride": display_name,
            "supports1m": bridge_model_supports_1m(model),
        }
    return routes


def normalize_claude_desktop_routes(meta: dict[str, Any], env: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    next_meta = copy.deepcopy(meta)
    routes = next_meta.get("claudeDesktopModelRoutes")
    current_routes = routes if isinstance(routes, dict) else {}
    expected = claude_desktop_routes_from_env(env)
    issues: list[dict[str, Any]] = []
    changed = False

    if next_meta.get("apiFormat") != "openai_responses":
        issues.append({"field": "meta.apiFormat", "current": next_meta.get("apiFormat"), "expected": "openai_responses"})
        next_meta["apiFormat"] = "openai_responses"
        changed = True
    if next_meta.get("claudeDesktopMode") != "proxy":
        issues.append({"field": "meta.claudeDesktopMode", "current": next_meta.get("claudeDesktopMode"), "expected": "proxy"})
        next_meta["claudeDesktopMode"] = "proxy"
        changed = True

    normalized_routes = copy.deepcopy(current_routes)
    for alias, wanted in expected.items():
        existing = normalized_routes.get(alias)
        if not isinstance(existing, dict):
            issues.append({"field": f"route.{alias}", "current": "missing", "expected": wanted})
            normalized_routes[alias] = copy.deepcopy(wanted)
            changed = True
            continue
        next_route = copy.deepcopy(existing)
        for key, wanted_value in wanted.items():
            if next_route.get(key) != wanted_value:
                issues.append(
                    {
                        "field": f"route.{alias}.{key}",
                        "current": next_route.get(key),
                        "expected": wanted_value,
                    }
                )
                next_route[key] = wanted_value
                changed = True
        normalized_routes[alias] = next_route

    if next_meta.get("claudeDesktopModelRoutes") != normalized_routes:
        next_meta["claudeDesktopModelRoutes"] = normalized_routes
        changed = True
    return next_meta, issues, changed


def common_provider_env(env: dict[str, Any]) -> dict[str, Any]:
    common = {
        str(key): copy.deepcopy(value)
        for key, value in env.items()
        if isinstance(key, str) and key not in PROVIDER_SCOPED_ENV_KEYS
    }
    normalize_provider_model_env(common)
    return common


def is_claude_attribution_disabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    return str(value).strip().lower() in {"0", "false"}


def ensure_claude_attribution_default(env: dict[str, Any], *, force: bool = False) -> bool:
    current = env.get(CLAUDE_CODE_ATTRIBUTION_HEADER_ENV)
    if force or current is None:
        env[CLAUDE_CODE_ATTRIBUTION_HEADER_ENV] = CLAUDE_CODE_ATTRIBUTION_DISABLED_VALUE
        return current != CLAUDE_CODE_ATTRIBUTION_DISABLED_VALUE
    return False


def attribution_env_status(value: Any, *, source_present: bool) -> str:
    if not source_present:
        return "unknown"
    if value is None:
        return "enabled"
    return "disabled" if is_claude_attribution_disabled(value) else "enabled"


def env_from_json_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    env = payload.get("env")
    return env if isinstance(env, dict) else {}


def strip_toml_section_keys(text: str, section: str, keys: tuple[str, ...]) -> tuple[str, list[str]]:
    removed: list[str] = []
    output: list[str] = []
    in_section = False
    header = f"[{section}]"
    key_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == header
        if in_section:
            match = key_pattern.match(line)
            if match and match.group(1) in keys:
                removed.append(match.group(1))
                continue
        output.append(line)
    return "".join(output), sorted(set(removed))


def toml_section_bool_keys(text: str, section: str) -> dict[str, bool]:
    values: dict[str, bool] = {}
    in_section = False
    key_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)\s*(?:#.*)?$", re.IGNORECASE)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == f"[{section}]"
            continue
        if not in_section:
            continue
        match = key_pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2).lower() == "true"
    return values


def has_toml_section_key(text: str, section: str, key: str) -> bool:
    return key in toml_section_bool_keys(text, section)


def ensure_toml_section_bool_key(text: str, section: str, key: str, value: bool) -> str:
    if has_toml_section_key(text, section, key):
        return text
    lines = text.splitlines(keepends=True)
    header = f"[{section}]"
    for idx, line in enumerate(lines):
        if line.strip() == header:
            insert_at = idx + 1
            lines.insert(insert_at, f"{key} = {'true' if value else 'false'}\n")
            return "".join(lines)
    suffix = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{suffix}\n{header}\n{key} = {'true' if value else 'false'}\n"


def strip_managed_codex_desktop_bridge(text: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"\n?{re.escape(MANAGED_CODEX_DESKTOP_BRIDGE_START)}.*?{re.escape(MANAGED_CODEX_DESKTOP_BRIDGE_END)}\n?",
        re.DOTALL,
    )
    updated, count = pattern.subn("\n", text)
    return updated.lstrip("\n"), count > 0


def strip_legacy_bridgedeck_provider_config(text: str, *, remove_static_keys: bool = False) -> tuple[str, list[str]]:
    removed: list[str] = []
    output: list[str] = []
    skip_section = False
    legacy_provider = bool(re.search(r'(?m)^\s*model_provider\s*=\s*["\']bridgedeck["\']\s*$', text))
    top_level_key_pattern = re.compile(r'^\s*(model_provider)\s*=\s*["\']bridgedeck["\']\s*$')
    legacy_static_key_pattern = re.compile(r"^\s*(model|model_reasoning_effort|service_tier)\s*=")
    in_top_level = True
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_top_level = False
            skip_section = stripped == "[model_providers.bridgedeck]"
            if skip_section:
                removed.append("model_providers.bridgedeck")
                continue
        if skip_section:
            continue
        if in_top_level and top_level_key_pattern.match(line):
            removed.append("model_provider")
            continue
        if in_top_level and remove_static_keys and legacy_static_key_pattern.match(line):
            removed.append(legacy_static_key_pattern.match(line).group(1))  # type: ignore[union-attr]
            continue
        output.append(line)
    return "".join(output), sorted(set(removed))


def codex_desktop_bridge_block(account_id: str) -> str:
    base_url = f"{LOCAL_BRIDGE_BASE_URL}/v1"
    return "\n".join(
        [
            MANAGED_CODEX_DESKTOP_BRIDGE_START,
            'model_provider = "bridgedeck"',
            "",
            "[model_providers.bridgedeck]",
            'name = "OpenAI"',
            f'base_url = "{base_url}"',
            'wire_api = "responses"',
            'experimental_bearer_token = "local-bridge"',
            "requires_openai_auth = false",
            "supports_websockets = false",
            MANAGED_CODEX_DESKTOP_BRIDGE_END,
            "",
        ]
    )


def bridge_account_id_from_base_url(base_url: str) -> str:
    marker = f"{LOCAL_BRIDGE_BASE_URL}/accounts/"
    if not base_url.startswith(marker):
        return ""
    rest = base_url[len(marker):]
    account_id = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return urllib.parse.unquote(account_id).strip()


def bridge_account_id_from_env(env: dict[str, Any]) -> str:
    base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
    return bridge_account_id_from_base_url(base_url)


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    if "@" in value:
        value = value.split("@", 1)[0]
    value = re.sub(r"[^a-z0-9._-]+", "-", value).strip("-._")
    return value or "account"


def codex_binary_path() -> str:
    homebrew_codex = Path("/opt/homebrew/bin/codex")
    if homebrew_codex.exists():
        return str(homebrew_codex)
    return which("codex") or "codex"


def current_codex_launcher_path() -> Path:
    return DEFAULT_CLI_LAUNCHER_DIR / "codex-current.command"


def write_executable_file(path: Path, body: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{path} 不能是符号链接")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_private_text_file(path: Path, body: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{path} 不能是符号链接")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


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
        "user_id": auth_obj.get("chatgpt_account_user_id") or auth_obj.get("chatgpt_user_id") or auth_obj.get("user_id") or "",
        "exp": payload.get("exp"),
    }


def account_id_from_aimami_key(value: str | None) -> str:
    text = (value or "").strip()
    if "::" not in text:
        return ""
    return text.rsplit("::", 1)[1].strip()


def path_inside_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base_dir.resolve(strict=False))
        return True
    except ValueError:
        return False


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def codex_oauth_authorize_url(state: str, challenge: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "redirect_uri": CODEX_OAUTH_REDIRECT_URI,
            "scope": CODEX_OAUTH_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "bridgedeck",
        }
    )
    return f"{CODEX_OAUTH_AUTHORIZE_URL}?{query}"


def parse_oauth_code_input(value: str) -> dict[str, str]:
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = urllib.parse.urlsplit(text)
        if parsed.query:
            params = urllib.parse.parse_qs(parsed.query)
            return {
                "code": (params.get("code") or [""])[0],
                "state": (params.get("state") or [""])[0],
            }
    except Exception:
        pass
    if "#" in text and "code=" not in text:
        code, state = text.split("#", 1)
        return {"code": code.strip(), "state": state.strip()}
    if "code=" in text:
        params = urllib.parse.parse_qs(text.lstrip("?"))
        return {
            "code": (params.get("code") or [""])[0],
            "state": (params.get("state") or [""])[0],
        }
    return {"code": text, "state": ""}


class CodexDeviceAuthorizationPending(RuntimeError):
    pass


def _openai_oauth_opener() -> urllib.request.OpenerDirector:
    proxy_url, _ = detect_codex_proxy_url()
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
    return urllib.request.build_opener(urllib.request.ProxyHandler(proxies))


def _post_json_url(url: str, payload: dict[str, Any], *, user_agent: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
        method="POST",
    )
    try:
        with _openai_oauth_opener().open(request, timeout=30) as response:
            parsed = json.loads(response.read(MAX_REQUEST_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(1200).decode("utf-8", "replace")
        try:
            parsed_detail = json.loads(detail)
            code = str(((parsed_detail.get("error") or {}) if isinstance(parsed_detail, dict) else {}).get("code") or "")
        except Exception:
            code = ""
        if code in ("deviceauth_authorization_unknown", "deviceauth_authorization_pending"):
            raise CodexDeviceAuthorizationPending("等待用户完成设备授权") from exc
        raise RuntimeError(f"Device authorization failed: HTTP {exc.code} {truncate_log_text(detail)}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Device authorization failed: invalid response")
    return parsed


def request_codex_device_code() -> dict[str, Any]:
    payload = _post_json_url(
        CODEX_DEVICE_USERCODE_URL,
        {"client_id": CODEX_OAUTH_CLIENT_ID, "scope": CODEX_DEVICE_SCOPE},
        user_agent=CODEX_DEVICE_USER_AGENT,
    )
    if not payload.get("device_auth_id") or not payload.get("user_code"):
        raise RuntimeError("Device authorization failed: missing user_code")
    return payload


def extract_codex_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("access_token") and payload.get("refresh_token"):
        return payload
    for key in ("token", "tokens", "oauth_token"):
        candidate = payload.get(key)
        if not isinstance(candidate, dict):
            continue
        if not candidate.get("access_token") or not candidate.get("refresh_token"):
            continue
        merged = dict(candidate)
        for identity_key in ("account_id", "email", "organization_id"):
            if identity_key in payload and identity_key not in merged:
                merged[identity_key] = payload[identity_key]
        return merged
    return {}


def exchange_codex_device_auth(device_auth_id: str, user_code: str) -> dict[str, Any]:
    payload = _post_json_url(
        CODEX_DEVICE_TOKEN_URL,
        {
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "device_auth_id": device_auth_id,
            "user_code": user_code,
        },
        user_agent=CODEX_DEVICE_USER_AGENT,
    )
    token_payload = extract_codex_token_payload(payload)
    if token_payload:
        return token_payload
    code = str(payload.get("authorization_code") or payload.get("code") or "")
    if not code:
        raise RuntimeError("Device authorization failed: missing authorization code")
    verifier = str(payload.get("code_verifier") or CODEX_DEVICE_CODE_VERIFIER)
    return exchange_codex_oauth_code(
        code,
        verifier,
        redirect_uri=CODEX_DEVICE_REDIRECT_URI,
    )


def exchange_codex_oauth_code(
    code: str,
    verifier: str,
    *,
    redirect_uri: str = CODEX_OAUTH_REDIRECT_URI,
) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        CODEX_OAUTH_TOKEN_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": CODEX_DEVICE_USER_AGENT,
        },
        method="POST",
    )
    try:
        with _openai_oauth_opener().open(request, timeout=30) as response:
            payload = json.loads(response.read(MAX_REQUEST_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(1200).decode("utf-8", "replace")
        raise RuntimeError(f"OAuth token exchange failed: HTTP {exc.code} {truncate_log_text(detail)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OAuth token exchange failed: invalid response")
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise RuntimeError("OAuth token exchange failed: missing token fields")
    return payload


def refresh_codex_oauth_token(refresh_token: str) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "refresh_token": refresh_token,
            "scope": CODEX_DEVICE_SCOPE,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        CODEX_OAUTH_TOKEN_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": CODEX_DEVICE_USER_AGENT,
        },
        method="POST",
    )
    try:
        with _openai_oauth_opener().open(request, timeout=30) as response:
            payload = json.loads(response.read(MAX_REQUEST_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(1200).decode("utf-8", "replace")
        raise RuntimeError(f"OAuth token refresh failed: HTTP {exc.code} {truncate_log_text(detail)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OAuth token refresh failed: invalid response")
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise RuntimeError("OAuth token refresh failed: missing token fields")
    return payload


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


def read_local_url(url: str, *, timeout: float, max_bytes: int) -> bytes:
    request = urllib.request.Request(url, headers={"Connection": "close"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return response.read(max_bytes)


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists() or path.is_symlink():
        return {}
    values: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                values[key] = value
    except Exception:
        return {}
    return values


def proxy_url_from_env_values(values: dict[str, str]) -> str:
    for key in CODEX_PROXY_LOOKUP_KEYS:
        value = str(values.get(key) or "").strip()
        if value:
            return value
    return ""


def detect_codex_proxy_url() -> tuple[str, str]:
    env_file = load_env_file(DEFAULT_CODEX_HOME / ".env")
    env_proxy = proxy_url_from_env_values(env_file)
    if env_proxy:
        return env_proxy, str(DEFAULT_CODEX_HOME / ".env")
    for key in CODEX_PROXY_LOOKUP_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value, f"env:{key}"
    return "", ""


def choose_codex_native_proxy_url() -> tuple[str, str]:
    env_path = DEFAULT_CODEX_HOME / ".env"
    file_proxy = proxy_url_from_env_values(load_env_file(env_path))
    if file_proxy:
        host, port = parse_proxy_target(file_proxy)
        if host and port and tcp_open(host, port):
            return file_proxy, str(env_path)
    for key in CODEX_PROXY_LOOKUP_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if not value:
            continue
        host, port = parse_proxy_target(value)
        if host and port and tcp_open(host, port):
            return value, f"env:{key}"
    for value in CODEX_NATIVE_PROXY_CANDIDATES:
        host, port = parse_proxy_target(value)
        if host and port and tcp_open(host, port):
            return value, "detected-listener"
    if file_proxy:
        return file_proxy, str(env_path)
    for key in CODEX_PROXY_LOOKUP_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value, f"env:{key}"
    return "", ""


def codex_native_proxy_required_values(proxy_url: str) -> dict[str, str]:
    return {
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "ALL_PROXY": proxy_url,
        "WS_PROXY": proxy_url,
        "WSS_PROXY": proxy_url,
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
        "all_proxy": proxy_url,
        "ws_proxy": proxy_url,
        "wss_proxy": proxy_url,
        "NO_PROXY": CODEX_NATIVE_NO_PROXY_VALUE,
        "no_proxy": CODEX_NATIVE_NO_PROXY_VALUE,
    }


def update_env_text_with_values(original: str, replacements: dict[str, str]) -> str:
    output: list[str] = []
    for raw_line in original.splitlines():
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in replacements:
                continue
        output.append(raw_line.rstrip("\n"))
    while output and not output[-1].strip():
        output.pop()
    if output:
        output.append("")
    for key in CODEX_NATIVE_PROXY_REQUIRED_KEYS:
        output.append(f"{key}={replacements[key]}")
    return "\n".join(output) + "\n"


def parse_proxy_target(proxy_url: str) -> tuple[str, int]:
    if not proxy_url:
        return "", 0
    try:
        parsed = urllib.parse.urlsplit(proxy_url)
    except Exception:
        return "", 0
    host = parsed.hostname or ""
    port = int(parsed.port or (443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else 0))
    return host, port


def read_codex_auth_state(path: Path = DEFAULT_CODEX_AUTH_PATH) -> dict[str, Any]:
    if not path.exists() or path.is_symlink():
        return {"present": False, "authenticated": False, "path": str(path)}
    raw = load_json(path, {})
    raw = raw if isinstance(raw, dict) else {}
    tokens = raw.get("tokens") if isinstance(raw.get("tokens"), dict) else {}
    access_token = str(tokens.get("access_token") or "")
    account_id = str(tokens.get("account_id") or "")
    identity = jwt_identity(access_token)
    return {
        "present": True,
        "authenticated": bool(access_token and account_id),
        "path": str(path),
        "account_id": identity.get("account_id") or account_id,
        "email": identity.get("email") or "",
        "plan": identity.get("plan") or "",
        "access_token": access_token,
    }


def probe_remote_url(
    url: str,
    *,
    proxy_url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 15.0,
    max_bytes: int = 1200,
) -> dict[str, Any]:
    request_headers = {"Connection": "close", **(headers or {})}
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    try:
        with opener.open(request, timeout=timeout) as response:
            sample = response.read(max_bytes).decode("utf-8", "replace")
            return {
                "ok": True,
                "reached": True,
                "status_code": int(response.getcode() or 0),
                "content_type": response.headers.get("Content-Type", ""),
                "body_excerpt": truncate_log_text(sample, limit=max_bytes),
            }
    except urllib.error.HTTPError as exc:
        sample = exc.read(max_bytes).decode("utf-8", "replace")
        return {
            "ok": False,
            "reached": True,
            "status_code": int(exc.code or 0),
            "content_type": exc.headers.get("Content-Type", ""),
            "body_excerpt": truncate_log_text(sample, limit=max_bytes),
        }
    except urllib.error.URLError as exc:
        detail = getattr(exc, "reason", exc)
        return {
            "ok": False,
            "reached": False,
            "status_code": 0,
            "error": f"{type(detail).__name__}: {detail}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reached": False,
            "status_code": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def openai_probe_is_healthy(probe: dict[str, Any] | None) -> bool:
    return bool(probe and safe_int(probe.get("status_code"), 0) == 401)


def probe_error_text(probe: dict[str, Any] | None) -> str:
    if not isinstance(probe, dict):
        return ""
    return " ".join(
        str(probe.get(key) or "")
        for key in ("error", "body_excerpt", "content_type")
        if probe.get(key)
    )


def looks_like_tls_proxy_failure(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    ssl_markers = ("ssl", "tls", "handshake", "certificate", "wrong version number")
    eof_markers = ("unexpected_eof", "eof occurred", "connection reset", "remote end closed", "protocol violation")
    return any(marker in lowered for marker in ssl_markers) and any(marker in lowered for marker in eof_markers)


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def read_local_bridge_state(path: Path = DEFAULT_LOCAL_BRIDGE_STATE_PATH) -> dict[str, Any]:
    if not path.exists() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    state: dict[str, Any] = {"updated_at": payload.get("updated_at")}
    usage = payload.get("usage_metrics") if isinstance(payload.get("usage_metrics"), dict) else {}
    if usage:
        state["usage_metrics"] = {
            "request_count": safe_int(usage.get("request_count"), 0),
            "input_tokens": safe_int(usage.get("input_tokens"), 0),
            "output_tokens": safe_int(usage.get("output_tokens"), 0),
            "total_tokens": safe_int(usage.get("total_tokens"), 0),
            "cached_tokens": safe_int(usage.get("cached_tokens"), 0),
            "cache_creation_tokens": safe_int(usage.get("cache_creation_tokens"), 0),
            "cache_miss_tokens": safe_int(usage.get("cache_miss_tokens"), 0),
            "cache_hit_rate": safe_float(usage.get("cache_hit_rate"), 0.0),
            "cache_miss_rate": safe_float(usage.get("cache_miss_rate"), 0.0),
            "last_account_id": str(usage.get("last_account_id") or ""),
            "last_model": str(usage.get("last_model") or ""),
            "last_requested_model": str(usage.get("last_requested_model") or ""),
            "last_request_type": str(usage.get("last_request_type") or ""),
            "last_request_id": str(usage.get("last_request_id") or ""),
            "last_duration_ms": safe_int(usage.get("last_duration_ms"), 0),
            "last_status_code": safe_int(usage.get("last_status_code"), 0),
            "last_bridge_port": safe_int(usage.get("last_bridge_port"), 0),
            "last_client_label": str(usage.get("last_client_label") or ""),
            "last_session_id": str(usage.get("last_session_id") or ""),
            "last_prompt_cache_key_present": bool(usage.get("last_prompt_cache_key_present")),
            "last_cache_key_source": str(usage.get("last_cache_key_source") or ""),
            "last_updated_at": usage.get("last_updated_at"),
        }
    events = payload.get("usage_events")
    if isinstance(events, list):
        state["usage_events"] = [
            {
                "at": safe_int(item.get("at"), 0),
                "account_id": str(item.get("account_id") or ""),
                "model": str(item.get("model") or ""),
                "actual_model": str(item.get("actual_model") or item.get("model") or ""),
                "requested_model": str(item.get("requested_model") or item.get("model") or ""),
                "request_type": str(item.get("request_type") or ""),
                "request_id": str(item.get("request_id") or ""),
                "status_code": safe_int(item.get("status_code"), 0),
                "source": str(item.get("source") or ""),
                "route_path": str(item.get("route_path") or ""),
                "bridge_port": safe_int(item.get("bridge_port"), 0),
                "client_port": safe_int(item.get("client_port"), 0),
                "client_label": str(item.get("client_label") or ""),
                "desktop_route": bool(item.get("desktop_route")),
                "session_id": str(item.get("session_id") or ""),
                "prompt_cache_key_present": bool(item.get("prompt_cache_key_present")),
                "cache_key_source": str(item.get("cache_key_source") or ""),
                "duration_ms": safe_int(item.get("duration_ms"), 0),
                "input_tokens": safe_int(item.get("input_tokens"), 0),
                "output_tokens": safe_int(item.get("output_tokens"), 0),
                "total_tokens": safe_int(item.get("total_tokens"), 0),
                "cached_tokens": safe_int(item.get("cached_tokens"), 0),
                "cache_creation_tokens": safe_int(item.get("cache_creation_tokens"), 0),
                "cache_miss_tokens": safe_int(item.get("cache_miss_tokens"), 0),
                "cache_hit_rate": safe_float(item.get("cache_hit_rate"), 0.0),
                "cache_miss_rate": safe_float(item.get("cache_miss_rate"), 0.0),
                "cost_usd": safe_float(item.get("cost_usd"), 0.0),
            }
            for item in events[-200:]
            if isinstance(item, dict)
        ]
    active = payload.get("active_stream")
    if isinstance(active, dict):
        state["active_stream"] = {
            "account_id": str(active.get("account_id") or ""),
            "client_disconnected": bool(active.get("client_disconnected")),
            "downstream_writes": safe_int(active.get("downstream_writes"), 0),
            "duration_s": safe_float(active.get("duration_s"), 0.0),
            "actual_effort": str(active.get("actual_effort") or ""),
            "effort": str(active.get("effort") or ""),
            "first_visible_after_ms": active.get("first_visible_after_ms"),
            "guard_mode": str(active.get("guard_mode") or ""),
            "guard_seconds": safe_int(active.get("guard_seconds"), 0),
            "last_event_name": str(active.get("last_event_name") or ""),
            "model": str(active.get("model") or ""),
            "reasoning_events": safe_int(active.get("reasoning_events"), 0),
            "requested_effort": str(active.get("requested_effort") or ""),
            "request_id": str(active.get("request_id") or ""),
            "started_at": safe_int(active.get("started_at"), 0),
            "status": str(active.get("status") or ""),
            "terminal_event_seen": bool(active.get("terminal_event_seen")),
            "tool_arg_buffer_chars": safe_int(active.get("tool_arg_buffer_chars"), 0),
            "tool_arg_coalesced_calls": safe_int(active.get("tool_arg_coalesced_calls"), 0),
            "tool_arg_delta_events": safe_int(active.get("tool_arg_delta_events"), 0),
            "tool_arg_ping_events": safe_int(active.get("tool_arg_ping_events"), 0),
            "tool_args_mode": str(active.get("tool_args_mode") or ""),
            "tool_events": safe_int(active.get("tool_events"), 0),
            "upstream_events": safe_int(active.get("upstream_events"), 0),
            "visible_text_events": safe_int(active.get("visible_text_events"), 0),
        }
    error = payload.get("last_stream_error")
    if not isinstance(error, dict):
        return state
    state["last_stream_error"] = {
            "account_id": str(error.get("account_id") or ""),
            "model": str(error.get("model") or ""),
            "request_id": str(error.get("request_id") or ""),
            "duration_ms": error.get("duration_ms"),
            "error_type": str(error.get("error_type") or ""),
            "error": str(error.get("error") or ""),
            "upstream_request_id": str(error.get("upstream_request_id") or ""),
    }
    return state


def read_tail_text(path: Path, *, max_bytes: int = 512 * 1024) -> str:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
                handle.readline()
            return handle.read(max_bytes).decode("utf-8", "replace")
    except Exception:
        return ""


def _bridge_stream_log_paths(extra: list[Path] | None = None) -> list[Path]:
    paths: list[Path] = []
    for path in [*(extra or []), *DEFAULT_LOCAL_BRIDGE_LOG_PATHS]:
        if path not in paths:
            paths.append(path)
    return paths


def parse_bridge_stream_log(path: Path, *, max_events: int = 80) -> list[dict[str, Any]]:
    text = read_tail_text(path)
    if not text:
        return []
    events: list[dict[str, Any]] = []
    pattern = re.compile(r"^(?P<ts>\S+)\s+\[(?P<tag>bridge-(?:stream-error|stream-end|long-stream-warning))\]\s+(?P<body>\{.*\})$")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        try:
            body = json.loads(match.group("body"))
        except Exception:
            continue
        if not isinstance(body, dict):
            continue
        tag = match.group("tag")
        error_type = str(body.get("error_type") or "")
        kind = "stream_end"
        if bool(body.get("client_disconnected")):
            kind = "client_disconnect"
        elif bool(body.get("idle_timeout_seen")):
            kind = "bridge_idle_timeout"
        elif bool(body.get("answer_incomplete_risk")):
            kind = "answer_incomplete_risk"
        elif tag == "bridge-long-stream-warning":
            kind = "long_stream"
        elif error_type == "BridgeClientDisconnect":
            kind = "client_disconnect"
        elif error_type == "BridgeStreamIdleTimeout":
            kind = "bridge_idle_timeout"
        elif tag == "bridge-stream-error":
            kind = "upstream_stream_error"
        events.append(
            {
                "timestamp": match.group("ts"),
                "tag": tag,
                "kind": kind,
                "account_id": str(body.get("account_id") or ""),
                "model": str(body.get("model") or ""),
                "request_id": str(body.get("request_id") or ""),
                "duration_ms": safe_int(body.get("duration_ms"), 0),
                "duration_s": safe_float(body.get("duration_s"), 0.0),
                "error_type": error_type,
                "error": truncate_log_text(str(body.get("error") or ""), limit=160),
                "client_disconnected": bool(body.get("client_disconnected")),
                "terminal_event_seen": bool(body.get("terminal_event_seen")),
                "idle_timeout_seen": bool(body.get("idle_timeout_seen")),
                "answer_incomplete_risk": bool(body.get("answer_incomplete_risk")),
                "answer_end_class": str(body.get("answer_end_class") or ""),
                "completed_response_status": str(body.get("completed_response_status") or ""),
                "completed_incomplete_reason": str(body.get("completed_incomplete_reason") or ""),
                "completed_output_tokens": body.get("completed_output_tokens"),
                "completed_total_tokens": body.get("completed_total_tokens"),
                "visible_text_tail_sha12": str(body.get("visible_text_tail_sha12") or ""),
                "actual_effort": str(body.get("actual_effort") or body.get("effort") or ""),
                "requested_effort": str(body.get("requested_effort") or ""),
                "tool_arg_buffer_chars": safe_int(body.get("tool_arg_buffer_chars"), 0),
                "tool_arg_coalesced_calls": safe_int(body.get("tool_arg_coalesced_calls"), 0),
                "tool_arg_delta_events": safe_int(body.get("tool_arg_delta_events"), 0),
                "tool_arg_ping_events": safe_int(body.get("tool_arg_ping_events"), 0),
                "tool_args_mode": str(body.get("tool_args_mode") or ""),
                "upstream_events": safe_int(body.get("upstream_events"), 0),
                "downstream_writes": safe_int(body.get("downstream_writes"), 0),
                "visible_text_chars": safe_int(body.get("visible_text_chars"), 0),
                "visible_text_events": safe_int(body.get("visible_text_events"), 0),
                "reasoning_events": safe_int(body.get("reasoning_events"), 0),
                "tool_events": safe_int(body.get("tool_events"), 0),
                "terminal_events": safe_int(body.get("terminal_events"), 0),
                "first_visible_after_ms": body.get("first_visible_after_ms"),
                "last_event_name": str(body.get("last_event_name") or ""),
                "log_path": str(path),
            }
        )
    return events[-max_events:]


def bridge_stream_diagnostics(log_paths: list[Path] | None = None) -> dict[str, Any]:
    paths = _bridge_stream_log_paths(log_paths)
    events: list[dict[str, Any]] = []
    for path in paths:
        events.extend(parse_bridge_stream_log(path))
    events.sort(key=lambda item: str(item.get("timestamp") or ""))
    events = events[-80:]
    latest = events[-1] if events else {}
    def count_kind(kind: str) -> int:
        keys = {
            str(item.get("request_id") or item.get("timestamp") or idx)
            for idx, item in enumerate(events)
            if item.get("kind") == kind
        }
        return len(keys)

    counts = {
        "client_disconnect": count_kind("client_disconnect"),
        "bridge_idle_timeout": count_kind("bridge_idle_timeout"),
        "upstream_stream_error": count_kind("upstream_stream_error"),
        "answer_incomplete_risk": count_kind("answer_incomplete_risk"),
        "long_stream": count_kind("long_stream"),
        "stream_end": count_kind("stream_end"),
    }
    if not events:
        status = "unknown"
        message = "还没有采集到 Local Bridge 流式日志。"
    elif latest.get("kind") == "client_disconnect":
        status = "warning"
        message = "最近一次是客户端断开：Bridge 仍在接收上游流，不是 Bridge idle timeout。"
    elif latest.get("kind") == "bridge_idle_timeout":
        status = "warning"
        message = "最近一次是 Bridge idle timeout：上游在超时窗口内没有继续产出。"
    elif latest.get("kind") == "long_stream":
        status = "warning"
        message = "检测到长时间未结束的流：需要观察是否只有 reasoning/tool 事件、没有可见文本。"
    elif latest.get("kind") == "upstream_stream_error":
        status = "warning"
        message = "最近一次是上游流式错误。"
    elif latest.get("kind") == "answer_incomplete_risk":
        status = "warning"
        message = "最近一次正常 completed，但答案结尾像半句；需区分模型提前完成和客户端渲染中断。"
    else:
        status = "ok"
        message = "最近流式请求正常结束。"
    return {
        "ok": True,
        "status": status,
        "message": message,
        "latest": latest,
        "counts": counts,
        "events": events[-20:],
        "log_paths": [str(path) for path in paths if path.exists()],
    }


def _hook_command_label(command: Any) -> str:
    text = str(command or "").strip()
    if not text:
        return "unknown"
    lowered = text.lower()
    if "clawd" in lowered:
        return "Clawd on Desk hook"
    if "http://" in lowered or "https://" in lowered:
        return "HTTP hook"
    token = text.split()[0]
    name = Path(token).name
    return name or "command"


def _hook_timeout(entry: dict[str, Any]) -> int | None:
    for key in ("timeout", "timeoutSeconds", "timeout_seconds"):
        if key in entry:
            return safe_int(entry.get(key), 0)
    return None


def _hook_is_async(entry: dict[str, Any]) -> bool:
    return any(bool(entry.get(key)) for key in ("async", "run_in_background", "runInBackground", "background"))


def _iter_hook_entries(event: str, value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _iter_hook_entries(event, item)
        return
    if not isinstance(value, dict):
        return
    if "command" in value or value.get("type") == "command":
        yield event, value
    for key in ("hooks", "commands"):
        child = value.get(key)
        if isinstance(child, (list, dict)):
            yield from _iter_hook_entries(event, child)


def claude_hook_risk_status(path: Path = DEFAULT_CLAUDE_SETTINGS_PATH) -> dict[str, Any]:
    if path.is_symlink():
        return {
            "ok": False,
            "status": "unknown",
            "message": "Claude settings 是符号链接，未读取 hooks。",
            "settings_path": str(path),
            "events": {},
            "risks": [],
        }
    if not path.exists():
        return {
            "ok": True,
            "status": "unknown",
            "message": "未发现 Claude settings.json。",
            "settings_path": str(path),
            "events": {},
            "risks": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "unknown",
            "message": f"Claude settings.json 不可读: {type(exc).__name__}",
            "settings_path": str(path),
            "events": {},
            "risks": [],
        }
    hooks = payload.get("hooks") if isinstance(payload, dict) else None
    if not isinstance(hooks, dict):
        return {
            "ok": True,
            "status": "ok",
            "message": "未配置 Claude hooks。",
            "settings_path": str(path),
            "events": {},
            "risks": [],
        }
    event_counts: dict[str, int] = {}
    risks: list[dict[str, Any]] = []
    watched_events = {"PreToolUse", "PostToolUse", "Stop", "PermissionRequest"}
    for event, value in hooks.items():
        event_name = str(event)
        for _, entry in _iter_hook_entries(event_name, value):
            event_counts[event_name] = event_counts.get(event_name, 0) + 1
            timeout = _hook_timeout(entry)
            is_async = _hook_is_async(entry)
            command_label = _hook_command_label(entry.get("command"))
            reason = ""
            severity = "info"
            if timeout is not None and timeout >= 120:
                reason = f"timeout={timeout}s，可能造成会话看起来停住"
                severity = "warning"
            elif event_name == "PermissionRequest" and timeout is not None and timeout >= 60:
                reason = f"PermissionRequest timeout={timeout}s，授权等待过长"
                severity = "warning"
            elif event_name in watched_events and timeout is None and not is_async:
                reason = "同步 hook 未声明 timeout，卡住时不易定位"
                severity = "warning"
            if reason:
                risks.append(
                    {
                        "event": event_name,
                        "command_label": command_label,
                        "timeout": timeout,
                        "async": is_async,
                        "severity": severity,
                        "reason": reason,
                    }
                )
    status = "warning" if any(item.get("severity") == "warning" for item in risks) else "ok"
    message = "Claude hooks 存在长 timeout/同步等待风险。" if status == "warning" else "Claude hooks 未发现明显长等待风险。"
    return {
        "ok": True,
        "status": status,
        "message": message,
        "settings_path": str(path),
        "events": event_counts,
        "risks": risks[:12],
        "risk_count": len(risks),
    }


def mask_url_credentials(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
    except Exception:
        return value
    if not parsed.scheme or not parsed.netloc or ("@" not in parsed.netloc):
        return value
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return urllib.parse.urlunsplit((parsed.scheme, f"<redacted>@{host}{port}", parsed.path, parsed.query, parsed.fragment))


def run_quiet(args: list[str], *, timeout: float = 3) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def _file_mtime(path: Path) -> tuple[float, str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return 0.0, ""
    return mtime, dt.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")


def _parse_ps_lstart(value: str) -> tuple[float, str]:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return 0.0, ""
    try:
        parsed = dt.datetime.strptime(text, "%a %b %d %H:%M:%S %Y")
        return parsed.timestamp(), parsed.isoformat(timespec="seconds")
    except ValueError:
        return 0.0, text


def _codex_process_rows() -> list[dict[str, Any]]:
    proc = run_quiet(["/bin/ps", "-axo", "pid,lstart,command"], timeout=3)
    if not proc or proc.returncode != 0:
        return []
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*(\d+)\s+([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d+\s+\d\d:\d\d:\d\d\s+\d{4})\s+(.+)$")
    for line in proc.stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        command = match.group(3)
        if "Codex.app" not in command and "/Resources/codex app-server" not in command and "/Resources/node_repl" not in command:
            continue
        start_epoch, started_at = _parse_ps_lstart(match.group(2))
        label = "codex"
        if "/Contents/MacOS/Codex" in command:
            label = "codex_app"
        elif "codex app-server" in command and "--listen stdio://" in command:
            label = "stdio_app_server"
        elif "codex app-server" in command:
            label = "desktop_app_server"
        elif "/Resources/node_repl" in command:
            label = "node_repl"
        rows.append(
            {
                "pid": safe_int(match.group(1), 0),
                "label": label,
                "started_at": started_at,
                "start_epoch": start_epoch,
                "command": command,
            }
        )
    return rows


def codex_desktop_process_state(
    *,
    config_path: Path | None = None,
    env_path: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path or (DEFAULT_CODEX_HOME / "config.toml")
    env_path = env_path or (DEFAULT_CODEX_HOME / ".env")
    rows = _codex_process_rows()
    app_servers = [row for row in rows if row.get("label") == "desktop_app_server"]
    primary = app_servers[0] if app_servers else {}
    start_epoch = float(primary.get("start_epoch") or 0)
    config_mtime, config_mtime_at = _file_mtime(config_path)
    env_mtime, env_mtime_at = _file_mtime(env_path)
    restart_required_for_config = bool(start_epoch and config_mtime and config_mtime > start_epoch + 1)
    restart_required_for_env = bool(start_epoch and env_mtime and env_mtime > start_epoch + 1)
    return {
        "ok": True,
        "app_running": any(row.get("label") == "codex_app" for row in rows),
        "app_server_running": bool(primary),
        "app_server_pid": primary.get("pid", 0),
        "app_server_started_at": primary.get("started_at", ""),
        "app_server_start_epoch": start_epoch,
        "config_mtime": config_mtime_at,
        "env_mtime": env_mtime_at,
        "restart_required_for_config": restart_required_for_config,
        "restart_required_for_env": restart_required_for_env,
        "restart_required": restart_required_for_config or restart_required_for_env,
        "processes": rows,
    }


def codex_cli_version_state() -> dict[str, Any]:
    global_version = ""
    bundled_version = ""
    global_path = which("codex") or ""
    if global_path:
        proc = run_quiet([global_path, "--version"], timeout=2)
        if proc and proc.returncode == 0:
            global_version = proc.stdout.strip() or proc.stderr.strip()
    bundled_path = Path("/Applications/Codex.app/Contents/Resources/codex")
    if bundled_path.exists():
        proc = run_quiet([str(bundled_path), "--version"], timeout=2)
        if proc and proc.returncode == 0:
            bundled_version = proc.stdout.strip() or proc.stderr.strip()
    return {
        "global_cli_path": global_path,
        "global_cli_version": global_version,
        "bundled_cli_path": str(bundled_path) if bundled_path.exists() else "",
        "bundled_cli_version": bundled_version,
        "version_split": bool(global_version and bundled_version and global_version != bundled_version),
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bridge_install_scan(root: Path | None = None, include_tests: bool = False) -> dict[str, Any]:
    root = (root or Path(__file__).resolve().parent).resolve()
    python = sys.executable or "python3"
    checks: list[dict[str, Any]] = []
    recommendations: list[str] = []
    ok = True

    def add_check(check_id: str, label: str, status: str, detail: str = "") -> None:
        nonlocal ok
        checks.append({"id": check_id, "label": label, "status": status, "detail": detail})
        if status == "failed":
            ok = False

    scripts = [root / "bridgedeck.py", root / "local_codex_bridge.py"]
    missing = [str(path) for path in scripts if not path.exists()]
    if missing:
        add_check("resources", "核心脚本", "failed", "缺失: " + ", ".join(missing))
    else:
        add_check("resources", "核心脚本", "ok", "bridgedeck.py / local_codex_bridge.py")
        proc = subprocess.run(
            [python, "-m", "py_compile", *(str(path) for path in scripts)],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        add_check(
            "py_compile",
            "Python 编译扫描",
            "ok" if proc.returncode == 0 else "failed",
            (proc.stderr or proc.stdout or "通过").strip()[:500],
        )

    package_script = root / "package-bridgedeck-dmg.command"
    if package_script.exists():
        proc = subprocess.run(
            ["/bin/zsh", "-n", str(package_script)],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        add_check(
            "package_shell_syntax",
            "打包脚本语法",
            "ok" if proc.returncode == 0 else "failed",
            (proc.stderr or proc.stdout or "通过").strip()[:500],
        )
    else:
        add_check("package_shell_syntax", "打包脚本语法", "warning", "源码运行环境未包含打包脚本")

    app_resource = Path("/Applications/BridgeDeck.app/Contents/Resources/bridgedeck.py")
    if app_resource.exists() and (root / "bridgedeck.py").exists():
        repo_hash = sha256_file(root / "bridgedeck.py")
        app_hash = sha256_file(app_resource)
        if repo_hash == app_hash:
            add_check("installed_app_current", "Applications App 版本", "ok", "与当前脚本一致")
        else:
            add_check("installed_app_current", "Applications App 版本", "warning", "Applications 中的 App 不是当前源码版本")
            recommendations.append("重新打包并替换 /Applications/BridgeDeck.app，然后重启 8899 UI")
    elif app_resource.exists():
        add_check("installed_app_current", "Applications App 版本", "warning", "无法比较当前源码")
    else:
        add_check("installed_app_current", "Applications App 版本", "warning", "未安装到 /Applications")

    if include_tests:
        proc = subprocess.run(
            [python, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        add_check(
            "unit_tests",
            "单元测试扫描",
            "ok" if proc.returncode == 0 else "failed",
            (proc.stderr or proc.stdout or "通过").strip()[-500:],
        )
    else:
        add_check("unit_tests", "单元测试扫描", "skipped", "打包时可用 BRIDGEDECK_PACKAGE_TESTS=1 启用")

    if not recommendations and ok:
        recommendations.append("安装扫描通过，可启动 UI")
    status = "ok" if ok and not any(c["status"] == "warning" for c in checks) else ("failed" if not ok else "warning")
    return {
        "ok": ok,
        "status": status,
        "version": APP_VERSION,
        "root": str(root),
        "checked_at": now_iso(),
        "checks": checks,
        "recommendations": recommendations,
    }


def write_install_state(scan: dict[str, Any], path: Path | None = None) -> None:
    target = path or DEFAULT_INSTALL_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": APP_VERSION,
        "status": scan.get("status"),
        "ok": bool(scan.get("ok")),
        "checked_at": scan.get("checked_at") or now_iso(),
        "root": scan.get("root", ""),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def codex_config_feature_state(config_path: Path | None = None) -> dict[str, Any]:
    config_path = config_path or (DEFAULT_CODEX_HOME / "config.toml")
    mtime, mtime_at = _file_mtime(config_path)
    data: dict[str, Any] = {
        "ok": True,
        "exists": config_path.exists(),
        "config_path": str(config_path),
        "mtime": mtime_at,
        "mtime_epoch": mtime,
        "canonical_hooks_present": False,
        "canonical_hooks_enabled": True,
        "hooks_effective_enabled": True,
        "legacy_codex_hooks_present": False,
        "legacy_codex_hooks_enabled": False,
        "active_legacy_key_present": False,
        "feature_keys": [],
        "backup_legacy_refs": [],
        "error": "",
    }
    if config_path.is_symlink():
        data.update({"ok": False, "error": "~/.codex/config.toml 是符号链接"})
        return data
    if not config_path.exists():
        return data
    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        data.update({"ok": False, "error": str(exc)})
        return data
    features = toml_section_bool_keys(text, "features")
    data["feature_keys"] = sorted(features.keys())
    data["canonical_hooks_present"] = "hooks" in features
    data["canonical_hooks_enabled"] = bool(features.get("hooks", True))
    data["hooks_effective_enabled"] = bool(features.get("hooks", True))
    data["legacy_codex_hooks_present"] = "codex_hooks" in features
    data["legacy_codex_hooks_enabled"] = bool(features.get("codex_hooks", False))
    data["active_legacy_key_present"] = "codex_hooks" in features
    refs: list[str] = []
    for pattern in ("*.toml*", "backups/**/*.toml", "backups/**/*.toml.*"):
        for path in DEFAULT_CODEX_HOME.glob(pattern):
            if path == config_path or not path.is_file():
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if re.search(r"(?m)^\s*codex_hooks\s*=", body):
                refs.append(str(path))
            if len(refs) >= 12:
                break
        if len(refs) >= 12:
            break
    data["backup_legacy_refs"] = refs
    return data


def codex_recent_desktop_logs(*, limit: int = 5) -> list[Path]:
    if not CODEX_DESKTOP_LOG_ROOT.exists():
        return []
    paths: list[Path] = []
    try:
        paths = [path for path in CODEX_DESKTOP_LOG_ROOT.rglob("*.log") if path.is_file()]
    except Exception:
        return []
    return sorted(paths, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)[:limit]


def codex_desktop_log_state(*, limit: int = 5, max_bytes_per_log: int = 1_500_000) -> dict[str, Any]:
    paths = codex_recent_desktop_logs(limit=limit)
    counts = {
        "codex_hooks_deprecation": 0,
        "unknown_conversation": 0,
        "reconnect": 0,
        "slow_config_read": 0,
        "slow_skills_list": 0,
    }
    last_seen = {key: "" for key in counts}
    max_config_read_ms = 0
    max_skills_list_ms = 0
    timestamp_pattern = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z)")
    duration_pattern = re.compile(r"durationMs=(\d+)")

    def mark_seen(key: str, ts: str) -> None:
        if not ts:
            return
        if not last_seen.get(key) or ts > last_seen[key]:
            last_seen[key] = ts

    for path in paths:
        try:
            raw = path.read_bytes()
            body = raw[-max_bytes_per_log:].decode("utf-8", "replace")
        except Exception:
            continue
        for line in body.splitlines():
            ts_match = timestamp_pattern.match(line)
            ts = ts_match.group(1) if ts_match else ""
            lower = line.lower()
            if "codex_hooks" in line and "deprecated" in lower:
                counts["codex_hooks_deprecation"] += 1
                mark_seen("codex_hooks_deprecation", ts)
            if "unknown conversation" in lower:
                counts["unknown_conversation"] += 1
                mark_seen("unknown_conversation", ts)
            if "reconnecting" in lower or "reconnect" in lower:
                counts["reconnect"] += 1
                mark_seen("reconnect", ts)
            duration_match = duration_pattern.search(line)
            duration_ms = safe_int(duration_match.group(1), 0) if duration_match else 0
            if "method=config/read" in line:
                max_config_read_ms = max(max_config_read_ms, duration_ms)
                if duration_ms >= 3000:
                    counts["slow_config_read"] += 1
                    mark_seen("slow_config_read", ts)
            if "method=skills/list" in line:
                max_skills_list_ms = max(max_skills_list_ms, duration_ms)
                if duration_ms >= 3000:
                    counts["slow_skills_list"] += 1
                    mark_seen("slow_skills_list", ts)

    signals = [key for key, value in counts.items() if value]
    return {
        "ok": True,
        "status": "warning" if signals else "ok",
        "log_root": str(CODEX_DESKTOP_LOG_ROOT),
        "paths": [str(path) for path in paths],
        "counts": counts,
        "last_seen": last_seen,
        "signals": signals,
        "max_config_read_ms": max_config_read_ms,
        "max_skills_list_ms": max_skills_list_ms,
    }


def _otel_log_value(body: str, key: str) -> str:
    quoted = re.search(rf"{re.escape(key)}=\"([^\"]*)\"", body)
    if quoted:
        return quoted.group(1)
    bare = re.search(rf"{re.escape(key)}=([^\s}}]+)", body)
    return bare.group(1) if bare else ""


def _is_remote_thread_start(origin: dict[str, Any]) -> bool:
    client_name = str(origin.get("client_name") or "").lower()
    return any(marker in client_name for marker in CODEX_REMOTE_THREAD_CLIENT_MARKERS)


def codex_thread_start_log_origin(thread_id: str, logs_db_path: Path | None = None) -> dict[str, Any]:
    path = logs_db_path or (DEFAULT_CODEX_HOME / "logs_2.sqlite")
    base: dict[str, Any] = {
        "found": False,
        "logs_db_path": str(path),
        "thread_id": thread_id,
        "client_name": "",
        "client_version": "",
        "connection_id": "",
        "dynamic_tool_count": None,
        "created_local": "",
        "remote_origin": False,
    }
    if not thread_id:
        return base
    if path.is_symlink() or not path.exists() or not path.is_file():
        return base

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            table = conn.execute("select name from sqlite_master where type='table' and name='logs'").fetchone()
            if not table:
                return base
            row = conn.execute(
                """
                select ts, feedback_log_body
                from logs
                where instr(coalesce(feedback_log_body, ''), ?) > 0
                  and instr(coalesce(feedback_log_body, ''), 'app_server.thread_start.create_thread') > 0
                order by ts desc, ts_nanos desc, id desc
                limit 1
                """,
                (f"thread_id={thread_id}",),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return base

    if not row:
        return base
    body = str(row["feedback_log_body"] or "")
    dynamic_tool_count_raw = _otel_log_value(body, "thread_start.dynamic_tool_count")
    ts = safe_int(row["ts"], 0)
    origin = {
        **base,
        "found": True,
        "client_name": _otel_log_value(body, "app_server.client_name"),
        "client_version": _otel_log_value(body, "app_server.client_version"),
        "connection_id": _otel_log_value(body, "app_server.connection_id"),
        "dynamic_tool_count": safe_int(dynamic_tool_count_raw, 0) if dynamic_tool_count_raw else None,
        "created_local": dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else "",
    }
    origin["remote_origin"] = _is_remote_thread_start(origin)
    return origin


CODEX_DESKTOP_APP_STATE_NUMERIC_KEYS = (
    "thread_count_total",
    "thread_count_active",
    "thread_count_streaming_owner",
    "thread_count_streaming_with_active_runtime",
    "thread_count_streaming_without_active_runtime",
    "thread_count_with_inflight_turn",
    "pending_request_count",
    "inflight_turn_count",
    "host_child_process_count_total",
    "host_child_app_server_process_count",
    "host_descendant_app_server_process_count",
    "main_process_rss_bytes",
    "renderer_process_working_set_kb",
)
CODEX_DESKTOP_APP_STATE_FRESH_SECONDS = 10 * 60


def _timestamp_epoch(value: Any) -> tuple[float, str]:
    if isinstance(value, bool):
        return 0.0, ""
    if isinstance(value, (int, float)):
        epoch = safe_float(value, 0.0)
        if epoch > 0:
            return epoch, dt.datetime.fromtimestamp(epoch, dt.UTC).isoformat().replace("+00:00", "Z")
        return 0.0, ""
    text = str(value or "").strip()
    if not text:
        return 0.0, ""
    numeric = safe_float(text, 0.0)
    if numeric > 10_000_000:
        return numeric, dt.datetime.fromtimestamp(numeric, dt.UTC).isoformat().replace("+00:00", "Z")
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        parsed = parsed.astimezone(dt.UTC)
        return parsed.timestamp(), parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        return 0.0, text


def codex_desktop_app_state(
    scope_path: Path | None = None,
    *,
    max_age_seconds: int = CODEX_DESKTOP_APP_STATE_FRESH_SECONDS,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    path = scope_path or CODEX_DESKTOP_SENTRY_SCOPE_PATH
    checked_at = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    base: dict[str, Any] = {
        "ok": True,
        "status": "missing",
        "message": "Codex Desktop Sentry app-state 文件不存在。",
        "scope_path": str(path),
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "latest": {},
        "signals": [],
        "stale_stream_count": 0,
        "maybe_resume_marked_streaming_count": 0,
        "app_state_snapshot_count": 0,
        "fresh": False,
        "freshness_source": "",
        "latest_age_seconds": 0,
        "max_age_seconds": max_age_seconds,
    }
    if path.is_symlink():
        return {
            **base,
            "ok": False,
            "status": "unreadable",
            "message": "Codex Desktop Sentry app-state 文件是符号链接，已跳过。",
        }
    if not path.exists() or not path.is_file():
        return base
    mtime_epoch, mtime_at = _file_mtime(path)
    base["scope_mtime"] = mtime_at
    base["scope_mtime_epoch"] = mtime_epoch
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "ok": False,
            "status": "unreadable",
            "message": f"Codex Desktop Sentry app-state 读取失败：{exc}",
        }

    scope = payload.get("scope") if isinstance(payload, dict) else {}
    breadcrumbs = scope.get("breadcrumbs") if isinstance(scope, dict) else []
    if not isinstance(breadcrumbs, list):
        breadcrumbs = payload.get("breadcrumbs") if isinstance(payload, dict) else []
    if not isinstance(breadcrumbs, list):
        breadcrumbs = []

    latest: dict[str, Any] = {}
    app_state_snapshot_count = 0
    maybe_resume_marked_streaming_count = 0
    latest_turn_completed_but_marked_streaming = False
    for breadcrumb in breadcrumbs:
        if not isinstance(breadcrumb, dict):
            continue
        category = str(breadcrumb.get("category") or "")
        message = str(breadcrumb.get("message") or "")
        data = breadcrumb.get("data") if isinstance(breadcrumb.get("data"), dict) else {}
        if category == "app_state" and message == "app_state_snapshot":
            app_state_snapshot_count += 1
            latest = {key: safe_int(data.get(key), 0) for key in CODEX_DESKTOP_APP_STATE_NUMERIC_KEYS}
            latest["snapshot_reason"] = str(data.get("snapshot_reason") or "")
            _, timestamp_at = _timestamp_epoch(breadcrumb.get("timestamp"))
            latest["timestamp"] = timestamp_at or str(breadcrumb.get("timestamp") or "")
        if "maybe_resume_success" in message and "markedStreaming=true" in message:
            maybe_resume_marked_streaming_count += 1
            if "latestTurnStatus=completed" in message:
                latest_turn_completed_but_marked_streaming = True

    if not latest:
        return {
            **base,
            "status": "no_app_state",
            "message": "Codex Desktop Sentry scope 内没有 app_state_snapshot。",
            "app_state_snapshot_count": 0,
        }

    stale_stream_count = safe_int(latest.get("thread_count_streaming_without_active_runtime"), 0)
    latest_timestamp_epoch, latest_timestamp_at = _timestamp_epoch(latest.get("timestamp"))
    freshness_source = "app_state_timestamp" if latest_timestamp_epoch else ("scope_mtime" if mtime_epoch else "")
    freshness_epoch = latest_timestamp_epoch or mtime_epoch
    latest_age_seconds = 0
    fresh = False
    if freshness_epoch:
        latest_age_seconds = max(0, int(checked_at.timestamp() - freshness_epoch))
        fresh = latest_age_seconds <= max(0, int(max_age_seconds))
    app_server_children = max(
        safe_int(latest.get("host_child_app_server_process_count"), 0),
        safe_int(latest.get("host_descendant_app_server_process_count"), 0),
    )
    signals: list[str] = []
    if stale_stream_count:
        signals.append("streaming_without_active_runtime")
    if latest_turn_completed_but_marked_streaming:
        signals.append("completed_turn_marked_streaming")
    if app_server_children >= 6:
        signals.append("app_server_children_high")
    if signals and not fresh:
        signals.append("unfresh_app_state_evidence")

    status = "ok"
    message = "Codex Desktop Sentry app-state 未发现 stale streaming。"
    ok = True
    if stale_stream_count or latest_turn_completed_but_marked_streaming:
        ok = False
        if fresh:
            status = "stale_stream_state"
            message = "Codex Desktop 存在 streaming owner 但没有 active runtime。"
        else:
            status = "stale_stream_state_unfresh"
            message = "Codex Desktop Sentry app-state 存在 stale stream 信号，但证据已过期。"
    elif "app_server_children_high" in signals:
        status = "app_server_children_high"
        message = f"Codex Desktop app-server 子进程偏高：{app_server_children}。"

    return {
        **base,
        "ok": ok,
        "status": status,
        "message": message,
        "latest": latest,
        "signals": signals,
        "fresh": fresh,
        "freshness_source": freshness_source,
        "latest_timestamp": latest_timestamp_at,
        "latest_timestamp_epoch": latest_timestamp_epoch,
        "latest_age_seconds": latest_age_seconds,
        "max_age_seconds": max_age_seconds,
        "stale_stream_count": stale_stream_count,
        "maybe_resume_marked_streaming_count": maybe_resume_marked_streaming_count,
        "latest_turn_completed_but_marked_streaming": latest_turn_completed_but_marked_streaming,
        "app_state_snapshot_count": app_state_snapshot_count,
    }


def codex_app_dynamic_tools_state(
    state_db_path: Path | None = None,
    *,
    logs_db_path: Path | None = None,
    thread_id: str | None = None,
    recent_limit: int = 12,
) -> dict[str, Any]:
    path = state_db_path or (DEFAULT_CODEX_HOME / "state_5.sqlite")
    thread_start_logs_db_path = logs_db_path or (path.parent / "logs_2.sqlite")
    base: dict[str, Any] = {
        "ok": True,
        "status": "missing",
        "message": "Codex state_5.sqlite 不存在。",
        "state_db_path": str(path),
        "expected_tools": [f"codex_app.{name}" for name in CODEX_APP_DYNAMIC_TOOLS],
        "latest": {},
        "suspect_threads": [],
    }
    if path.is_symlink():
        return {
            **base,
            "ok": False,
            "status": "unreadable",
            "message": "Codex state_5.sqlite 是符号链接，已跳过。",
        }
    if not path.exists() or not path.is_file():
        return base

    def row_public(row: sqlite3.Row) -> dict[str, Any]:
        names = str(row["dynamic_tool_names"] or "")
        return {
            "id": str(row["id"] or ""),
            "created_local": str(row["created_local"] or ""),
            "source": str(row["source"] or ""),
            "thread_source": str(row["thread_source"] or ""),
            "cwd": str(row["cwd"] or ""),
            "title": str(row["title"] or ""),
            "model_provider": str(row["model_provider"] or ""),
            "dynamic_tools": safe_int(row["dynamic_tools"], 0),
            "dynamic_tool_names": [name for name in names.split(",") if name],
        }

    def missing_expected_tools(item: dict[str, Any]) -> list[str]:
        present = set(item.get("dynamic_tool_names") or [])
        return [tool for tool in base["expected_tools"] if tool not in present]

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            table_rows = conn.execute(
                "select name from sqlite_master where type='table' and name in ('threads','thread_dynamic_tools')"
            ).fetchall()
            tables = {str(row["name"]) for row in table_rows}
            if {"threads", "thread_dynamic_tools"} - tables:
                return {
                    **base,
                    "ok": False,
                    "status": "schema_missing",
                    "message": "Codex state_5.sqlite 缺少 threads/thread_dynamic_tools 表。",
                    "tables": sorted(tables),
                }

            sql = """
                select
                    t.id,
                    datetime(t.created_at, 'unixepoch', 'localtime') as created_local,
                    coalesce(t.source, '') as source,
                    coalesce(t.thread_source, '') as thread_source,
                    coalesce(t.cwd, '') as cwd,
                    coalesce(t.title, '') as title,
                    coalesce(t.model_provider, '') as model_provider,
                    coalesce(d.cnt, 0) as dynamic_tools,
                    coalesce(d.names, '') as dynamic_tool_names
                from threads t
                left join (
                    select
                        thread_id,
                        count(*) as cnt,
                        group_concat(namespace || '.' || name) as names
                    from thread_dynamic_tools
                    group by thread_id
                ) d on d.thread_id = t.id
            """
            if thread_id:
                rows = conn.execute(sql + " where t.id = ?", (thread_id,)).fetchall()
            else:
                rows = conn.execute(
                    sql + " where coalesce(t.source, '') = 'vscode' order by t.created_at desc limit ?",
                    (max(1, int(recent_limit)),),
                ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {
            **base,
            "ok": False,
            "status": "unreadable",
            "message": f"Codex state_5.sqlite 读取失败：{exc}",
        }

    items = [row_public(row) for row in rows]
    latest = items[0] if items else {}
    suspects = [item for item in items if missing_expected_tools(item)]
    for item in items:
        item["missing_expected_tools"] = missing_expected_tools(item)
        if item.get("missing_expected_tools") or item.get("thread_source") != "user":
            origin = codex_thread_start_log_origin(str(item.get("id") or ""), logs_db_path=thread_start_logs_db_path)
            if origin.get("found"):
                item["thread_start_log"] = origin

    if thread_id and not latest:
        return {
            **base,
            "ok": False,
            "status": "thread_missing",
            "message": f"Codex state_5.sqlite 未找到线程 {thread_id}。",
        }
    latest_origin = latest.get("thread_start_log") if isinstance(latest.get("thread_start_log"), dict) else {}
    if latest and latest.get("missing_expected_tools") and _is_remote_thread_start(latest_origin):
        client = str(latest_origin.get("client_name") or "remote client")
        count = latest_origin.get("dynamic_tool_count")
        count_part = f"，thread/start dynamic_tool_count={count}" if count is not None else ""
        return {
            **base,
            "ok": False,
            "status": "remote_dynamic_tools_missing",
            "message": f"Codex 线程由 {client} 创建{count_part}；重启本机 Codex 不会补回 dynamic tools。",
            "latest": latest,
            "suspect_threads": suspects,
        }
    if latest and latest.get("missing_expected_tools"):
        return {
            **base,
            "ok": False,
            "status": "missing_dynamic_tools",
            "message": "Codex 线程启动时未注入 codex_app dynamic tools。",
            "latest": latest,
            "suspect_threads": suspects,
        }
    if latest and latest.get("thread_source") != "user":
        return {
            **base,
            "ok": False,
            "status": "non_user_thread_source",
            "message": "Codex 线程 thread_source 不是 user，可能走了非标准启动路径。",
            "latest": latest,
            "suspect_threads": suspects,
        }
    if suspects:
        return {
            **base,
            "ok": False,
            "status": "recent_missing_dynamic_tools",
            "message": "近期 Codex 线程曾缺失 codex_app dynamic tools。",
            "latest": latest,
            "suspect_threads": suspects,
        }
    if latest:
        return {
            **base,
            "status": "ok",
            "message": "近期 Codex 用户线程 dynamic tools 正常。",
            "latest": latest,
            "suspect_threads": [],
        }
    return {
        **base,
        "status": "no_vscode_threads",
        "message": "Codex state_5.sqlite 未找到 vscode 来源线程。",
    }


def pids_listening_on_port(port: int) -> list[int]:
    proc = run_quiet(["/usr/sbin/lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"])
    if not proc or proc.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return sorted(set(pids))


def process_command(pid: int) -> str:
    proc = run_quiet(["/bin/ps", "-p", str(pid), "-o", "command="])
    if not proc or proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def proxy_process_label(command: str) -> str:
    text = str(command or "").strip()
    lowered = text.lower()
    for needle, label in KNOWN_PROXY_PROCESS_HINTS:
        if needle in lowered:
            return label
    if not text:
        return "unknown"
    parts = text.split()
    first = Path(parts[0]).name if parts else ""
    if first in {"python", "python3", "node", "bash", "zsh", "sh"} and len(parts) > 1:
        return Path(parts[1]).name or first
    return first or "unknown"


def proxy_process_is_legacy_conflict(command: str) -> bool:
    lowered = str(command or "").lower()
    return any(needle in lowered for needle, _label in LEGACY_PROXY_PROCESS_HINTS)


def proxy_port_processes(port: int) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for item in port_processes(port):
        command = str(item.get("command") or "")
        processes.append(
            {
                "pid": safe_int(item.get("pid"), 0),
                "label": proxy_process_label(command),
                "command": command,
                "legacy_conflict": proxy_process_is_legacy_conflict(command),
            }
        )
    return processes


def process_environment_text(pid: int) -> str:
    proc = run_quiet(["/bin/ps", "eww", "-p", str(pid)])
    if not proc or proc.returncode != 0:
        return ""
    return proc.stdout


def find_bridge_script_from_command(command: str) -> Path | None:
    for part in command.split():
        if part.endswith("local_codex_bridge.py"):
            path = Path(part)
            if path.exists():
                return path
    return None


def find_local_bridge_script(processes: list[dict[str, Any]] | None = None) -> Path | None:
    env_path = os.environ.get("CODEX_BRIDGE_SCRIPT", "").strip()
    if env_path and Path(env_path).expanduser().exists():
        return Path(env_path).expanduser()
    for proc in processes or []:
        path = find_bridge_script_from_command(str(proc.get("command") or ""))
        if path:
            return path
    candidates = [
        Path(__file__).resolve().with_name("local_codex_bridge.py"),
        Path.home() / "Documents/Codex/2026-04-20-https-github-com-farion1231-cc-switch/local_codex_bridge.py",
        Path.home() / ".cc-switch/local_codex_bridge.py",
        Path.home() / "local_codex_bridge.py",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def python_supports_local_bridge(python_bin: str) -> bool:
    proc = run_quiet([python_bin, "-c", "import httpx"], timeout=2)
    return bool(proc and proc.returncode == 0)


def find_local_bridge_python() -> str | None:
    env_path = os.environ.get("BRIDGEDECK_BRIDGE_PYTHON", "").strip()
    candidates = [
        Path(env_path).expanduser() if env_path else None,
        Path.home() / ".cc-switch/bridgedeck-bridge-venv/bin/python",
        Path("/opt/homebrew/bin/python3"),
        Path("/usr/local/bin/python3"),
        Path(which("python3")).expanduser() if which("python3") else None,
        Path(sys.executable).expanduser() if sys.executable else None,
        Path("/usr/bin/python3"),
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        python_bin = str(candidate)
        if python_bin in seen or not candidate.exists():
            continue
        seen.add(python_bin)
        if python_supports_local_bridge(python_bin):
            return python_bin
    return None


def detect_upstream_proxy(processes: list[dict[str, Any]] | None = None) -> str:
    value = os.environ.get("CODEX_BRIDGE_UPSTREAM_PROXY", "").strip()
    if value:
        return value
    for proc in processes or []:
        env_text = process_environment_text(int(proc.get("pid") or 0))
        match = re.search(r"CODEX_BRIDGE_UPSTREAM_PROXY=([^ \n]+)", env_text)
        if match:
            return match.group(1)
    for port in COMMON_UPSTREAM_PROXY_PORTS:
        if tcp_open("127.0.0.1", port):
            return f"http://127.0.0.1:{port}"
    return ""


def port_processes(port: int) -> list[dict[str, Any]]:
    return [{"pid": pid, "command": process_command(pid)} for pid in pids_listening_on_port(port)]


def aimami_processes() -> list[dict[str, Any]]:
    proc = run_quiet(["/bin/ps", "axo", "pid=,command="], timeout=2)
    if not proc or proc.returncode != 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        pid_text, _, command = text.partition(" ")
        lowered = command.lower()
        if "aimami" not in lowered and "ai mommy" not in lowered:
            continue
        rows.append({"pid": safe_int(pid_text, 0), "command": command})
    return [row for row in rows if row.get("pid")]


def port_active_connections(port: int) -> list[dict[str, Any]]:
    proc = run_quiet(["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:ESTABLISHED", "-F", "pcn"], timeout=2)
    if not proc or proc.returncode not in (0, 1):
        return []
    connections: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in proc.stdout.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            if current:
                connections.append(current)
            current = {"pid": safe_int(value, 0)}
        elif tag == "c":
            current["command"] = value
        elif tag == "n":
            current["endpoint"] = value
    if current:
        connections.append(current)
    filtered: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for item in connections:
        endpoint = str(item.get("endpoint") or "")
        pid = safe_int(item.get("pid"), 0)
        if not pid or f":{port}" not in endpoint:
            continue
        key = (pid, endpoint)
        if key in seen:
            continue
        seen.add(key)
        filtered.append(
            {
                "pid": pid,
                "command": str(item.get("command") or ""),
                "endpoint": endpoint,
            }
        )
    return filtered


@dataclass
class ManagerPaths:
    db: Path
    settings: Path
    auth_store: Path


@dataclass
class CodexOAuthFlow:
    flow_id: str
    set_default: bool
    created_at: float
    state: str = ""
    verifier: str = ""
    auth_url: str = ""
    status: str = "pending"
    device_auth_id: str = ""
    user_code: str = ""
    verification_url: str = CODEX_DEVICE_VERIFY_URL
    interval: int = 5
    expires_at: str = ""
    next_poll_at: float = 0.0
    bridge_provider_exists: bool = False
    account_id: str = ""
    email: str = ""
    error: str = ""


class BridgeManager:
    def __init__(self, paths: ManagerPaths) -> None:
        self.paths = paths
        self._lock = threading.RLock()
        self._oauth_lock = threading.RLock()
        self._oauth_flows: dict[str, CodexOAuthFlow] = {}
        self._load_oauth_flows()
        self._oauth_callback_server: ThreadingHTTPServer | None = None
        self._oauth_callback_thread: threading.Thread | None = None

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

    def _cleanup_oauth_flows(self) -> None:
        cutoff = time.time() - CODEX_OAUTH_FLOW_TTL_SECS
        expired = [
            flow_id
            for flow_id, flow in self._oauth_flows.items()
            if flow.created_at < cutoff and flow.status != "completed"
        ]
        for flow_id in expired:
            self._oauth_flows.pop(flow_id, None)
        if expired:
            self._persist_oauth_flows_locked()

    def _oauth_flow_state_path(self) -> Path:
        return self.paths.db.parent / "bridgedeck-oauth-flows.json"

    def _oauth_flow_to_dict(self, flow: CodexOAuthFlow) -> dict[str, Any]:
        return {
            "flow_id": flow.flow_id,
            "set_default": flow.set_default,
            "created_at": flow.created_at,
            "state": flow.state,
            "verifier": flow.verifier,
            "auth_url": flow.auth_url,
            "status": flow.status,
            "device_auth_id": flow.device_auth_id,
            "user_code": flow.user_code,
            "verification_url": flow.verification_url,
            "interval": flow.interval,
            "expires_at": flow.expires_at,
            "next_poll_at": flow.next_poll_at,
            "bridge_provider_exists": flow.bridge_provider_exists,
            "account_id": flow.account_id,
            "email": flow.email,
            "error": flow.error,
        }

    def _load_oauth_flows(self) -> None:
        try:
            raw = load_json(self._oauth_flow_state_path(), {})
        except Exception:
            return
        entries = raw.get("flows") if isinstance(raw, dict) else []
        if not isinstance(entries, list):
            return
        cutoff = time.time() - CODEX_OAUTH_FLOW_TTL_SECS
        for item in entries:
            if not isinstance(item, dict):
                continue
            flow_id = str(item.get("flow_id") or "")
            created_at = safe_float(item.get("created_at"), 0.0)
            if not flow_id or (created_at < cutoff and str(item.get("status") or "") != "completed"):
                continue
            status = str(item.get("status") or "pending")
            if status == "exchanging":
                status = "pending"
            self._oauth_flows[flow_id] = CodexOAuthFlow(
                flow_id=flow_id,
                set_default=bool(item.get("set_default")),
                created_at=created_at or time.time(),
                state=str(item.get("state") or ""),
                verifier=str(item.get("verifier") or ""),
                auth_url=str(item.get("auth_url") or ""),
                status=status,
                device_auth_id=str(item.get("device_auth_id") or ""),
                user_code=str(item.get("user_code") or ""),
                verification_url=str(item.get("verification_url") or CODEX_DEVICE_VERIFY_URL),
                interval=max(2, min(30, safe_int(item.get("interval"), 5))),
                expires_at=str(item.get("expires_at") or ""),
                next_poll_at=safe_float(item.get("next_poll_at"), 0.0),
                bridge_provider_exists=bool(item.get("bridge_provider_exists")),
                account_id=str(item.get("account_id") or ""),
                email=str(item.get("email") or ""),
                error=str(item.get("error") or ""),
            )

    def _persist_oauth_flows_locked(self) -> None:
        dump_json(
            self._oauth_flow_state_path(),
            {
                "version": 1,
                "updated_at": int(time.time()),
                "flows": [self._oauth_flow_to_dict(flow) for flow in self._oauth_flows.values()],
            },
        )

    def _oauth_flow_payload(self, flow: CodexOAuthFlow) -> dict[str, Any]:
        return {
            "ok": flow.status != "error",
            "flow_id": flow.flow_id,
            "status": flow.status,
            "auth_url": flow.auth_url,
            "verification_url": flow.verification_url,
            "user_code": flow.user_code,
            "interval": flow.interval,
            "expires_at": flow.expires_at,
            "set_default": flow.set_default,
            "bridge_provider_exists": flow.bridge_provider_exists,
            "account_id": mask_id_value(flow.account_id),
            "email": mask_email_value(flow.email),
            "error": flow.error,
        }

    def _ensure_oauth_callback_server(self) -> dict[str, Any]:
        with self._oauth_lock:
            if self._oauth_callback_server:
                return {"ok": True, "port": CODEX_OAUTH_CALLBACK_PORT}

            manager = self

            class OAuthCallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:
                    parsed = urllib.parse.urlsplit(self.path)
                    if parsed.path != "/auth/callback":
                        self.send_response(404)
                        self.end_headers()
                        return
                    params = urllib.parse.parse_qs(parsed.query)
                    state = (params.get("state") or [""])[0]
                    code = (params.get("code") or [""])[0]
                    try:
                        result = manager.complete_codex_oauth_callback(state, code)
                        ok = bool(result.get("ok"))
                        title = "BridgeDeck 授权完成" if ok else "BridgeDeck 授权失败"
                        detail = str(result.get("message") or result.get("error") or "")
                        status = 200 if ok else 400
                    except Exception as exc:  # noqa: BLE001
                        title = "BridgeDeck 授权失败"
                        detail = str(exc)
                        status = 400
                    safe_title = html.escape(title)
                    safe_detail = html.escape(detail)
                    body = (
                        "<!doctype html><meta charset='utf-8'>"
                        f"<title>{safe_title}</title>"
                        "<body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;"
                        "background:#0c0f14;color:#edf2fb;padding:32px'>"
                        f"<h1>{safe_title}</h1><p>{safe_detail}</p><p>可以关闭这个窗口。</p></body>"
                    ).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, fmt: str, *args: Any) -> None:
                    return

            try:
                server = ThreadingHTTPServer((CODEX_OAUTH_CALLBACK_HOST, CODEX_OAUTH_CALLBACK_PORT), OAuthCallbackHandler)
            except OSError as exc:
                return {"ok": False, "port": CODEX_OAUTH_CALLBACK_PORT, "error": str(exc)}
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._oauth_callback_server = server
            self._oauth_callback_thread = thread
            return {"ok": True, "port": CODEX_OAUTH_CALLBACK_PORT}

    def start_codex_oauth(self, *, set_default: bool = False) -> dict[str, Any]:
        device = request_codex_device_code()
        interval_raw = str(device.get("interval") or "5")
        try:
            interval = max(2, min(30, int(float(interval_raw))))
        except ValueError:
            interval = 5
        flow = CodexOAuthFlow(
            flow_id=uuid.uuid4().hex,
            set_default=bool(set_default),
            created_at=time.time(),
            auth_url=CODEX_DEVICE_VERIFY_URL,
            device_auth_id=str(device.get("device_auth_id") or ""),
            user_code=str(device.get("user_code") or ""),
            verification_url=CODEX_DEVICE_VERIFY_URL,
            interval=interval,
            expires_at=str(device.get("expires_at") or ""),
            next_poll_at=time.time() + interval,
        )
        with self._oauth_lock:
            self._cleanup_oauth_flows()
            self._oauth_flows[flow.flow_id] = flow
            self._persist_oauth_flows_locked()
        result = self._oauth_flow_payload(flow)
        result.update(
            {
                "ok": True,
                "callback_server": False,
                "callback_port": 0,
                "callback_error": "",
                "message": "验证码已生成",
            }
        )
        return result

    def codex_oauth_status(self, flow_id: str) -> dict[str, Any]:
        with self._oauth_lock:
            self._cleanup_oauth_flows()
            flow = self._oauth_flows.get(flow_id)
            if not flow:
                return {"ok": False, "status": "missing", "error": "授权流程不存在或已过期"}
            should_poll = bool(flow.device_auth_id and flow.user_code and flow.status == "pending" and time.time() >= flow.next_poll_at)
        if should_poll:
            return self._complete_codex_device_flow(flow)
        return self._oauth_flow_payload(flow)

    def complete_codex_oauth(self, flow_id: str, code_input: str) -> dict[str, Any]:
        parsed = parse_oauth_code_input(code_input)
        code = parsed.get("code") or ""
        incoming_state = parsed.get("state") or ""
        if not code:
            raise ValueError("缺少授权 code")
        with self._oauth_lock:
            flow = self._oauth_flows.get(flow_id)
            if not flow:
                raise ValueError("授权流程不存在或已过期")
            if flow.device_auth_id and flow.user_code:
                return self._complete_codex_device_flow(flow)
            if incoming_state and incoming_state != flow.state:
                flow.status = "error"
                flow.error = "OAuth state 不一致"
                self._persist_oauth_flows_locked()
                raise ValueError(flow.error)
        return self._complete_codex_oauth_flow(flow, code)

    def complete_codex_oauth_callback(self, state: str, code: str) -> dict[str, Any]:
        if not state or not code:
            raise ValueError("缺少 OAuth state 或 code")
        with self._oauth_lock:
            flow = next((item for item in self._oauth_flows.values() if item.state == state), None)
            if not flow:
                raise ValueError("OAuth state 不存在或已过期")
        return self._complete_codex_oauth_flow(flow, code)

    def _bridge_provider_for_account(self, account_id: str) -> dict[str, Any] | None:
        if not account_id:
            return None
        with self._connect() as conn:
            row = self._select_existing_bridge_provider_for_account(conn, account_id)
            if not row:
                return None
            return {"id": str(row["id"]), "name": str(row["name"])}

    def apply_codex_oauth_bridge(self, flow_id: str) -> dict[str, Any]:
        with self._oauth_lock:
            flow = self._oauth_flows.get(flow_id)
            if not flow:
                raise ValueError("授权流程不存在或已过期")
            if flow.status != "completed" or not flow.account_id:
                raise ValueError("账号尚未完成授权")
            account_id = flow.account_id

        existing = self._bridge_provider_for_account(account_id)
        snapshot = self.snapshot(include_secrets=False)
        providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
        existing_names = {str(provider.get("name") or "") for provider in providers}
        quota: dict[str, Any] = {}
        try:
            quota_rows = self.quotas().get("quotas", [])
            quota = next(
                (
                    item
                    for item in quota_rows
                    if isinstance(item, dict) and str(item.get("account_id") or "") == account_id
                ),
                {},
            )
        except Exception:
            quota = {}

        provider_name = str(existing.get("name") or "") if existing else self._provider_name_for_quota(account_id, quota, existing_names)
        result = self.create_or_update_provider(account_id, provider_name, False)
        mode = "updated" if existing else "created"
        with self._oauth_lock:
            flow.bridge_provider_exists = True
            self._persist_oauth_flows_locked()
        return {
            "ok": True,
            "mode": mode,
            "provider_id": result.get("provider_id"),
            "provider_name": result.get("provider_name") or provider_name,
            "message": "已更新 CC Switch Local Bridge" if existing else "已加入 CC Switch Local Bridge",
        }

    def _complete_codex_device_flow(self, flow: CodexOAuthFlow) -> dict[str, Any]:
        with self._oauth_lock:
            if flow.status == "completed":
                return {**self._oauth_flow_payload(flow), "message": "该账号已完成授权"}
            if flow.status == "exchanging":
                return {**self._oauth_flow_payload(flow), "message": "正在交换 token"}
            flow.status = "exchanging"
            flow.error = ""
            self._persist_oauth_flows_locked()
        try:
            token_data = exchange_codex_device_auth(flow.device_auth_id, flow.user_code)
            account_id = self._save_codex_oauth_account(token_data, set_default=flow.set_default)
            identity = jwt_identity(str(token_data.get("access_token") or ""))
            with self._oauth_lock:
                flow.status = "completed"
                flow.account_id = account_id
                flow.email = str(identity.get("email") or "")
                flow.bridge_provider_exists = self._bridge_provider_for_account(account_id) is not None
                flow.error = ""
                self._persist_oauth_flows_locked()
                return {
                    **self._oauth_flow_payload(flow),
                    "message": f"授权完成：{mask_email_value(flow.email) or mask_id_value(account_id)}",
                }
        except CodexDeviceAuthorizationPending:
            with self._oauth_lock:
                flow.status = "pending"
                flow.error = ""
                flow.next_poll_at = time.time() + flow.interval
                self._persist_oauth_flows_locked()
                return {**self._oauth_flow_payload(flow), "message": "等待用户输入验证码并确认"}
        except Exception as exc:  # noqa: BLE001
            with self._oauth_lock:
                flow.status = "error"
                flow.error = str(exc)
                self._persist_oauth_flows_locked()
                return self._oauth_flow_payload(flow)

    def _complete_codex_oauth_flow(self, flow: CodexOAuthFlow, code: str) -> dict[str, Any]:
        with self._oauth_lock:
            if flow.status == "completed":
                return {**self._oauth_flow_payload(flow), "message": "该账号已完成授权"}
            if flow.status == "exchanging":
                return {**self._oauth_flow_payload(flow), "message": "正在交换 token"}
            flow.status = "exchanging"
            flow.error = ""
            self._persist_oauth_flows_locked()
        try:
            token_data = exchange_codex_oauth_code(code, flow.verifier)
            account_id = self._save_codex_oauth_account(token_data, set_default=flow.set_default)
            identity = jwt_identity(str(token_data.get("access_token") or ""))
            with self._oauth_lock:
                flow.status = "completed"
                flow.account_id = account_id
                flow.email = str(identity.get("email") or "")
                flow.bridge_provider_exists = self._bridge_provider_for_account(account_id) is not None
                flow.error = ""
                self._persist_oauth_flows_locked()
                return {
                    **self._oauth_flow_payload(flow),
                    "message": f"授权完成：{mask_email_value(flow.email) or mask_id_value(account_id)}",
                }
        except Exception as exc:  # noqa: BLE001
            with self._oauth_lock:
                flow.status = "error"
                flow.error = str(exc)
                self._persist_oauth_flows_locked()
                return self._oauth_flow_payload(flow)

    def _save_codex_oauth_account(self, token_data: dict[str, Any], *, set_default: bool) -> str:
        access_token = str(token_data.get("access_token") or "")
        refresh_token = str(token_data.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise RuntimeError("OAuth token response missing required fields")
        identity = jwt_identity(access_token)
        account_id = str(identity.get("account_id") or token_data.get("account_id") or "")
        if not account_id:
            raise RuntimeError("无法从 token 识别 ChatGPT account_id")
        email = str(identity.get("email") or "")
        self._upsert_oauth_account_record(
            account_id=account_id,
            email=email,
            refresh_token=refresh_token,
            set_default=set_default,
            source="codex_oauth",
        )
        return account_id

    def _upsert_oauth_account_record(
        self,
        *,
        account_id: str,
        email: str,
        refresh_token: str,
        set_default: bool = False,
        source: str = "manual",
    ) -> dict[str, Any]:
        account_id = account_id.strip()
        email = email.strip()
        refresh_token = refresh_token.strip()
        if not account_id:
            raise ValueError("account_id 不能为空")
        if not refresh_token:
            raise ValueError("refresh_token 不能为空")
        with self._lock:
            raw = load_json(self.paths.auth_store, {})
            store = raw if isinstance(raw, dict) else {}
            accounts = store.get("accounts") if isinstance(store.get("accounts"), dict) else {}
            next_accounts = copy.deepcopy(accounts)
            existing = next_accounts.get(account_id) if isinstance(next_accounts.get(account_id), dict) else {}
            existing_refresh = str(existing.get("refresh_token") or "")
            existing_email = str(existing.get("email") or "")
            action = "created" if not existing else ("updated" if existing_refresh != refresh_token or (email and email != existing_email) else "unchanged")
            authenticated_at = existing.get("authenticated_at") if existing else None
            if action != "unchanged":
                authenticated_at = int(time.time())
            merged = dict(existing)
            if source:
                merged["source"] = source
            next_accounts[account_id] = {
                **merged,
                "account_id": account_id,
                "email": email or existing_email,
                "refresh_token": refresh_token,
                "authenticated_at": authenticated_at,
            }
            default_account_id = str(store.get("default_account_id") or "")
            if set_default or not default_account_id:
                default_account_id = account_id
            next_store = {
                "version": 1,
                "accounts": next_accounts,
                "default_account_id": default_account_id,
            }
            before = json.dumps(store, ensure_ascii=False, sort_keys=True)
            after = json.dumps(next_store, ensure_ascii=False, sort_keys=True)
            if before != after:
                self._backup_file(self.paths.auth_store, f"{source}-oauth")
                dump_json(self.paths.auth_store, next_store)
        return {
            "account_id": account_id,
            "email": email or existing_email,
            "action": action,
            "refresh_sha12": sha12(refresh_token),
        }

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

    def _installed_claude_plugins(self) -> dict[str, bool]:
        raw = load_json(DEFAULT_CLAUDE_INSTALLED_PLUGINS_PATH, {})
        if not isinstance(raw, dict):
            return {}
        plugins = raw.get("plugins")
        if not isinstance(plugins, dict):
            return {}
        result: dict[str, bool] = {}
        for plugin_id, entries in plugins.items():
            if not isinstance(plugin_id, str) or "@" not in plugin_id:
                continue
            if isinstance(entries, list) and len(entries) > 0:
                result[plugin_id] = True
        return result

    def _enabled_plugins_from(self, payload: dict[str, Any]) -> dict[str, bool]:
        raw = payload.get("enabledPlugins")
        if not isinstance(raw, dict):
            return {}
        return {str(key): bool(value) for key, value in raw.items() if isinstance(key, str)}

    def extract_safe_claude_common_config(self) -> dict[str, Any]:
        settings = load_json(DEFAULT_CLAUDE_SETTINGS_PATH, {})
        settings = settings if isinstance(settings, dict) else {}

        extracted_keys: list[str] = [key for key in SAFE_COMMON_CONFIG_KEYS if key in settings]
        settings_env = settings.get("env")
        safe_env: dict[str, Any] = {
            key: copy.deepcopy(settings_env[key])
            for key in SAFE_COMMON_ENV_KEYS
            if isinstance(settings_env, dict) and key in settings_env
        }
        ensure_claude_attribution_default(safe_env)

        def build_next_common(existing: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
            next_common = copy.deepcopy(existing)
            removed_keys: list[str] = []
            for key in SAFE_COMMON_CONFIG_KEYS:
                if key in settings:
                    next_common[key] = copy.deepcopy(settings[key])
                elif key in next_common:
                    next_common.pop(key, None)
                    removed_keys.append(key)

            existing_env = next_common.get("env")
            existing_env_keys = set(existing_env.keys()) if isinstance(existing_env, dict) else set()
            unsafe_removed = sorted(str(key) for key in existing_env_keys if key not in SAFE_COMMON_ENV_KEYS)
            if safe_env:
                next_common["env"] = safe_env
            else:
                next_common.pop("env", None)
            return next_common, removed_keys, unsafe_removed

        common = load_json(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, {})
        common = common if isinstance(common, dict) else {}
        next_common, removed_keys, unsafe_removed = build_next_common(common)

        before = json.dumps(common, ensure_ascii=False, sort_keys=True)
        after = json.dumps(next_common, ensure_ascii=False, sort_keys=True)
        backups: list[str] = []
        changed = before != after
        if changed:
            backup = self._backup_file(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, "safe-common-extract")
            if backup:
                backups.append(backup)
            dump_json(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, next_common)

        db_changed = False
        if self.paths.db.exists():
            with self._lock:
                conn = self._connect()
                try:
                    has_settings = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings'"
                    ).fetchone()
                    if has_settings:
                        row = conn.execute(
                            "SELECT value FROM settings WHERE key = 'common_config_claude'"
                        ).fetchone()
                        db_common = self._extract_json(row["value"]) if row else {}
                        next_db_common, db_removed_keys, db_unsafe_removed = build_next_common(db_common)
                        removed_keys = sorted(set(removed_keys + db_removed_keys))
                        unsafe_removed = sorted(set(unsafe_removed + db_unsafe_removed))
                        db_before = json.dumps(db_common, ensure_ascii=False, sort_keys=True)
                        db_after = json.dumps(next_db_common, ensure_ascii=False, sort_keys=True)
                        if db_before != db_after:
                            db_backup = self._backup_file(self.paths.db, "safe-common-extract")
                            if db_backup:
                                backups.append(db_backup)
                            conn.execute(
                                """
                                INSERT INTO settings (key, value)
                                VALUES ('common_config_claude', ?)
                                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                                """,
                                (json.dumps(next_db_common, ensure_ascii=False),),
                            )
                            conn.commit()
                            db_changed = True
                finally:
                    conn.close()

        return {
            "ok": True,
            "changed": changed or db_changed,
            "message": "安全通用配置已提取",
            "keys": extracted_keys,
            "env_keys": sorted(safe_env.keys()),
            "removed_keys": removed_keys,
            "removed_env_keys": unsafe_removed,
            "backups": backups,
        }

    def sync_claude_enabled_plugins(self) -> dict[str, Any]:
        installed = self._installed_claude_plugins()
        if not installed:
            return {
                "ok": True,
                "changed": False,
                "installed_count": 0,
                "enabled_count": 0,
                "added": [],
                "backups": [],
            }

        common = load_json(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, {})
        settings = load_json(DEFAULT_CLAUDE_SETTINGS_PATH, {})
        common = common if isinstance(common, dict) else {}
        settings = settings if isinstance(settings, dict) else {}
        common_enabled = self._enabled_plugins_from(common)
        settings_enabled = self._enabled_plugins_from(settings)

        merged = dict(common_enabled)
        merged.update(settings_enabled)
        added: list[str] = []
        for plugin_id in sorted(installed):
            explicitly_disabled = common_enabled.get(plugin_id) is False or settings_enabled.get(plugin_id) is False
            if plugin_id not in merged and not explicitly_disabled:
                merged[plugin_id] = True
                added.append(plugin_id)

        common_changed = common_enabled != merged
        settings_changed = settings_enabled != merged
        backups: list[str] = []
        if common_changed:
            backup = self._backup_file(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, "sync-enabled-plugins")
            if backup:
                backups.append(backup)
            common["enabledPlugins"] = merged
            dump_json(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, common)
        if settings_changed:
            backup = self._backup_file(DEFAULT_CLAUDE_SETTINGS_PATH, "sync-enabled-plugins")
            if backup:
                backups.append(backup)
            settings["enabledPlugins"] = merged
            dump_json(DEFAULT_CLAUDE_SETTINGS_PATH, settings)

        return {
            "ok": True,
            "changed": common_changed or settings_changed,
            "installed_count": len(installed),
            "enabled_count": len([value for value in merged.values() if value]),
            "added": added,
            "backups": backups,
        }

    def claude_plugin_sync_status(self) -> dict[str, Any]:
        installed = self._installed_claude_plugins()
        common = load_json(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH, {})
        settings = load_json(DEFAULT_CLAUDE_SETTINGS_PATH, {})
        common = common if isinstance(common, dict) else {}
        settings = settings if isinstance(settings, dict) else {}
        common_enabled = self._enabled_plugins_from(common)
        settings_enabled = self._enabled_plugins_from(settings)
        missing_from_common = sorted(plugin_id for plugin_id in installed if plugin_id not in common_enabled)
        missing_from_settings = sorted(plugin_id for plugin_id in installed if plugin_id not in settings_enabled)
        disabled = sorted(
            plugin_id
            for plugin_id in installed
            if common_enabled.get(plugin_id) is False or settings_enabled.get(plugin_id) is False
        )
        return {
            "ok": True,
            "installed_count": len(installed),
            "common_enabled_count": len(common_enabled),
            "settings_enabled_count": len(settings_enabled),
            "missing_from_common": missing_from_common,
            "missing_from_settings": missing_from_settings,
            "disabled": disabled,
            "needs_sync": bool(missing_from_common or missing_from_settings),
        }

    def _load_auto_switch_config(self) -> dict[str, Any]:
        raw = load_json(DEFAULT_AUTO_SWITCH_PATH, {})
        config = raw if isinstance(raw, dict) else {}
        return {
            "enabled": bool(config.get("enabled", False)),
            "claude": bool(config.get("claude", True)),
            "default_codex": bool(config.get("default_codex", False)),
            "priority": ["pro20x", "pro5x", "plus"],
            "last_result": config.get("last_result") if isinstance(config.get("last_result"), dict) else {},
        }

    def _save_auto_switch_config(self, config: dict[str, Any]) -> None:
        current = self._load_auto_switch_config()
        current.update(
            {
                "enabled": bool(config.get("enabled", current["enabled"])),
                "claude": bool(config.get("claude", current["claude"])),
                "default_codex": bool(config.get("default_codex", current["default_codex"])),
                "priority": ["pro20x", "pro5x", "plus"],
                "last_result": config.get("last_result", current.get("last_result", {})),
            }
        )
        dump_json(DEFAULT_AUTO_SWITCH_PATH, current)

    def _load_aimami_follow_config(self) -> dict[str, Any]:
        raw = load_json(DEFAULT_AIMAMI_FOLLOW_PATH, {})
        config = raw if isinstance(raw, dict) else {}
        return {
            "enabled": bool(config.get("enabled", False)),
            "last_result": config.get("last_result") if isinstance(config.get("last_result"), dict) else {},
            "last_seen_active_account_key": str(config.get("last_seen_active_account_key") or ""),
            "last_synced_account_id": str(config.get("last_synced_account_id") or ""),
        }

    def _save_aimami_follow_config(self, config: dict[str, Any]) -> None:
        current = self._load_aimami_follow_config()
        current.update(
            {
                "enabled": bool(config.get("enabled", current["enabled"])),
                "last_result": config.get("last_result", current.get("last_result", {})),
                "last_seen_active_account_key": str(config.get("last_seen_active_account_key", current.get("last_seen_active_account_key", "")) or ""),
                "last_synced_account_id": str(config.get("last_synced_account_id", current.get("last_synced_account_id", "")) or ""),
            }
        )
        dump_json(DEFAULT_AIMAMI_FOLLOW_PATH, current)

    def update_aimami_follow_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._save_aimami_follow_config({"enabled": bool(payload.get("enabled", False))})
        return {"ok": True, "aimami_follow": self._load_aimami_follow_config()}

    def _load_api_keys(self) -> dict[str, Any]:
        raw = load_json(DEFAULT_API_KEYS_PATH, {})
        return raw if isinstance(raw, dict) else {}

    def _save_api_keys(self, keys: dict[str, Any]) -> None:
        dump_json(DEFAULT_API_KEYS_PATH, keys)
        try:
            os.chmod(DEFAULT_API_KEYS_PATH, 0o600)
        except OSError:
            pass

    def create_api_key(self, label: str = "") -> dict[str, Any]:
        import secrets
        key = f"sk-bridgedeck-{secrets.token_urlsafe(32)}"
        keys = self._load_api_keys()
        keys[key] = {
            "label": label or f"key-{len(keys) + 1}",
            "created_at": int(time.time()),
            "revoked": False,
        }
        self._save_api_keys(keys)
        return {"ok": True, "key": key, "label": keys[key]["label"]}

    def revoke_api_key(self, key: str) -> dict[str, Any]:
        keys = self._load_api_keys()
        if key not in keys:
            raise ValueError("API key not found")
        keys[key]["revoked"] = True
        self._save_api_keys(keys)
        return {"ok": True, "key": key}

    def list_api_keys(self) -> dict[str, Any]:
        keys = self._load_api_keys()
        result = []
        for k, v in keys.items():
            result.append({
                "key_prefix": k[:20] + "...",
                "label": str(v.get("label") or ""),
                "created_at": v.get("created_at"),
                "revoked": bool(v.get("revoked")),
            })
        return {"ok": True, "keys": result}

    def validate_api_key(self, key: str) -> bool:
        keys = self._load_api_keys()
        entry = keys.get(key)
        return bool(entry and not entry.get("revoked"))

    def account_pool(self) -> dict[str, Any]:
        accounts = self._load_accounts()
        auth_raw = self._load_auth_store_raw()
        default_id = str(auth_raw.get("default_account_id") or "") if isinstance(auth_raw, dict) else ""
        pool = []
        for acct in accounts:
            pool.append({
                "account_id": acct["account_id"],
                "email": acct.get("email", ""),
                "is_default": acct["account_id"] == default_id,
                "source": acct.get("source", ""),
            })
        return {"ok": True, "default_account_id": default_id, "pool": pool}

    def launchd_status(self) -> dict[str, Any]:
        import subprocess
        try:
            result = subprocess.run(
                ["launchctl", "list", "com.jinjungao.bridgedeck-ui"],
                capture_output=True, text=True, timeout=5
            )
            loaded = result.returncode == 0
            pid = None
            if loaded:
                for line in result.stdout.splitlines():
                    if line.startswith("PID"):
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            pid = parts[2]
            return {"ok": True, "loaded": loaded, "pid": pid}
        except Exception as e:
            return {"ok": True, "loaded": False, "error": str(e)}

    def service_control(self, action: str) -> dict[str, Any]:
        import subprocess
        try:
            if action == "stop":
                subprocess.run(["pkill", "-f", "bridgedeck"], capture_output=True, timeout=5)
                return {"ok": True, "message": "服务停止信号已发送"}
            elif action == "start":
                return {"ok": False, "message": "请通过 launchd 或手动启动服务"}
            elif action == "restart":
                subprocess.run(["pkill", "-f", "bridgedeck"], capture_output=True, timeout=5)
                return {"ok": True, "message": "重启信号已发送"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Unknown action"}

    def launchd_control(self, action: str) -> dict[str, Any]:
        import subprocess
        plist_path = Path.home() / "Library/LaunchAgents/com.jinjungao.bridgedeck-ui.plist"
        try:
            if action == "unload":
                subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, timeout=10)
                return {"ok": True, "message": "Launchd 已卸载"}
            elif action == "load":
                subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, timeout=10)
                return {"ok": True, "message": "Launchd 已加载"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Unknown action"}

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

    def _aimami_snapshot_path(self, value: str) -> tuple[Path | None, str]:
        if not value.strip():
            return None, "missing_snapshot_path"
        raw_path = Path(value).expanduser()
        path = raw_path if raw_path.is_absolute() else DEFAULT_AIMAMI_SNAPSHOTS_DIR / raw_path
        if not path_inside_dir(path, DEFAULT_AIMAMI_SNAPSHOTS_DIR):
            return path, "snapshot_path_outside_dir"
        return path, ""

    def _aimami_candidate_from_item(self, item: dict[str, Any]) -> dict[str, Any]:
        snapshot_path, path_error = self._aimami_snapshot_path(str(item.get("snapshotPath") or ""))
        account_key = str(item.get("accountKey") or "")
        candidate: dict[str, Any] = {
            "account_key": account_key,
            "account_id": account_id_from_aimami_key(account_key),
            "email": str(item.get("email") or ""),
            "plan": str(item.get("plan") or ""),
            "snapshot_path": str(snapshot_path or ""),
            "status": "skipped",
            "reason": path_error,
            "refresh_sha12": "",
        }
        if path_error:
            return candidate
        if not snapshot_path or not snapshot_path.exists():
            candidate["reason"] = "snapshot_missing"
            return candidate
        try:
            snapshot = load_json(snapshot_path, {})
        except Exception as exc:  # noqa: BLE001
            candidate["reason"] = f"snapshot_parse_error: {exc}"
            return candidate
        if not isinstance(snapshot, dict):
            candidate["reason"] = "snapshot_invalid"
            return candidate
        if str(snapshot.get("auth_mode") or "") != "chatgpt":
            candidate["reason"] = "not_chatgpt_auth"
            return candidate
        tokens = snapshot.get("tokens") if isinstance(snapshot.get("tokens"), dict) else {}
        refresh_token = str(tokens.get("refresh_token") or "")
        account_id = str(tokens.get("account_id") or candidate["account_id"] or "")
        identity = jwt_identity(str(tokens.get("id_token") or tokens.get("access_token") or ""))
        email = str(item.get("email") or identity.get("email") or "")
        if not account_id:
            candidate.update({"reason": "missing_account_id", "account_id": ""})
            return candidate
        if not refresh_token:
            candidate.update({"reason": "missing_refresh_token", "account_id": account_id, "email": email})
            return candidate
        existing = self._account_map().get(account_id)
        refresh_hash = sha12(refresh_token)
        existing_hash = str((existing or {}).get("refresh_sha12") or "")
        if not existing:
            status = "new"
            reason = ""
        elif existing_hash == refresh_hash:
            status = "unchanged"
            reason = ""
        else:
            status = "updated"
            reason = "refresh_token_changed"
        candidate.update(
            {
                "account_id": account_id,
                "email": email,
                "status": status,
                "reason": reason,
                "refresh_sha12": refresh_hash,
                "_refresh_token": refresh_token,
            }
        )
        return candidate

    def aimami_import_preview(self) -> dict[str, Any]:
        registry_path = DEFAULT_AIMAMI_REGISTRY_PATH
        if not registry_path.exists():
            return {
                "ok": True,
                "detected": False,
                "registry_path": str(registry_path),
                "snapshots_dir": str(DEFAULT_AIMAMI_SNAPSHOTS_DIR),
                "active_account_id": "",
                "candidates": [],
                "summary": {"new": 0, "updated": 0, "unchanged": 0, "skipped": 0, "importable": 0},
            }
        registry = load_json(registry_path, {})
        if not isinstance(registry, dict):
            raise RuntimeError("AiMaMi registry is not a JSON object")
        items = registry.get("items") if isinstance(registry.get("items"), list) else []
        candidates = [self._aimami_candidate_from_item(item) for item in items if isinstance(item, dict)]
        for candidate in candidates:
            candidate.pop("_refresh_token", None)
        summary = self._aimami_import_summary(candidates)
        return {
            "ok": True,
            "detected": True,
            "registry_path": str(registry_path),
            "snapshots_dir": str(DEFAULT_AIMAMI_SNAPSHOTS_DIR),
            "active_account_key": str(registry.get("activeAccountKey") or ""),
            "active_account_id": account_id_from_aimami_key(str(registry.get("activeAccountKey") or "")),
            "candidates": candidates,
            "summary": summary,
        }

    def _aimami_import_summary(self, candidates: list[dict[str, Any]]) -> dict[str, int]:
        summary = {"new": 0, "updated": 0, "unchanged": 0, "skipped": 0, "importable": 0}
        for candidate in candidates:
            status = str(candidate.get("status") or "skipped")
            if status in summary:
                summary[status] += 1
            else:
                summary["skipped"] += 1
            if status in {"new", "updated", "unchanged"}:
                summary["importable"] += 1
        return summary

    def import_aimami_accounts(self, *, create_missing: bool = False) -> dict[str, Any]:
        registry = load_json(DEFAULT_AIMAMI_REGISTRY_PATH, {})
        if not isinstance(registry, dict):
            raise RuntimeError("AiMaMi registry is not a JSON object")
        items = registry.get("items") if isinstance(registry.get("items"), list) else []
        raw_candidates = [self._aimami_candidate_from_item(item) for item in items if isinstance(item, dict)]
        imported: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            status = str(candidate.get("status") or "skipped")
            if status not in {"new", "updated", "unchanged"}:
                skipped.append({k: v for k, v in candidate.items() if not k.startswith("_")})
                continue
            if status == "unchanged":
                imported.append({k: v for k, v in candidate.items() if not k.startswith("_")})
                continue
            result = self._upsert_oauth_account_record(
                account_id=str(candidate.get("account_id") or ""),
                email=str(candidate.get("email") or ""),
                refresh_token=str(candidate.get("_refresh_token") or ""),
                set_default=False,
                source="aimami",
            )
            imported.append({**{k: v for k, v in candidate.items() if not k.startswith("_")}, "action": result.get("action")})
        created_payload = {"created": [], "skipped": [], "missing": []}
        if create_missing:
            created_payload = self.create_missing_bridge_providers()
        preview_candidates = [{k: v for k, v in candidate.items() if not k.startswith("_")} for candidate in raw_candidates]
        return {
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "summary": self._aimami_import_summary(preview_candidates),
            "bridge_providers": created_payload,
        }

    def _aimami_active_candidate(self) -> dict[str, Any]:
        registry = load_json(DEFAULT_AIMAMI_REGISTRY_PATH, {})
        if not isinstance(registry, dict):
            return {"status": "skipped", "reason": "registry_invalid", "account_id": "", "account_key": ""}
        active_key = str(registry.get("activeAccountKey") or "")
        active_account_id = account_id_from_aimami_key(active_key)
        items = registry.get("items") if isinstance(registry.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            account_key = str(item.get("accountKey") or "")
            if account_key == active_key or account_id_from_aimami_key(account_key) == active_account_id:
                return self._aimami_candidate_from_item(item)
        return {
            "status": "skipped",
            "reason": "active_account_not_in_registry",
            "account_id": active_account_id,
            "account_key": active_key,
        }

    def _local_bridge_has_active_clients(self) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
        active_connections = port_active_connections(LOCAL_BRIDGE_PORT)
        bridge_state = read_local_bridge_state()
        active_stream = bridge_state.get("active_stream") if isinstance(bridge_state, dict) else {}
        active_stream = active_stream if isinstance(active_stream, dict) else {}
        return bool(active_connections or active_stream), active_connections, active_stream

    def _bridge_provider_for_account(self, snapshot: dict[str, Any], account_id: str) -> dict[str, Any] | None:
        providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
        return next((p for p in providers if p.get("account_id") == account_id and self._is_bridge_provider(p)), None)

    def run_aimami_follow(self, *, force: bool = False) -> dict[str, Any]:
        config = self._load_aimami_follow_config()
        now = int(time.time())
        if not force and not config["enabled"]:
            result = {
                "ok": True,
                "enabled": False,
                "action": "noop",
                "reason": "follow_disabled",
                "selected_account_id": "",
                "timestamp": now,
            }
            self._save_aimami_follow_config({**config, "last_result": result})
            return result

        preview = self.aimami_import_preview()
        active_key = str(preview.get("active_account_key") or "")
        active_account_id = str(preview.get("active_account_id") or "")
        if not active_account_id:
            result = {
                "ok": False,
                "enabled": config["enabled"],
                "action": "noop",
                "reason": "missing_active_account",
                "selected_account_id": "",
                "timestamp": now,
            }
            self._save_aimami_follow_config({**config, "last_result": result, "last_seen_active_account_key": active_key})
            return result

        if active_account_id not in self._account_map():
            candidate = self._aimami_active_candidate()
            status = str(candidate.get("status") or "skipped")
            if status not in {"new", "updated", "unchanged"}:
                result = {
                    "ok": False,
                    "enabled": config["enabled"],
                    "action": "noop",
                    "reason": str(candidate.get("reason") or "active_account_not_importable"),
                    "selected_account_id": active_account_id,
                    "timestamp": now,
                }
                self._save_aimami_follow_config({**config, "last_result": result, "last_seen_active_account_key": active_key})
                return result
            imported = self.import_aimami_accounts(create_missing=False)
            if active_account_id not in self._account_map():
                result = {
                    "ok": False,
                    "enabled": config["enabled"],
                    "action": "import_failed",
                    "reason": "active_account_missing_after_import",
                    "selected_account_id": active_account_id,
                    "imported": imported,
                    "timestamp": now,
                }
                self._save_aimami_follow_config({**config, "last_result": result, "last_seen_active_account_key": active_key})
                return result

        snapshot = self.snapshot(include_secrets=False)
        current_provider = self._current_claude_provider(snapshot)
        if not self._is_bridge_provider(current_provider):
            result = {
                "ok": True,
                "enabled": config["enabled"],
                "action": "noop",
                "reason": "current_provider_is_not_local_bridge",
                "selected_account_id": active_account_id,
                "timestamp": now,
            }
            self._save_aimami_follow_config({**config, "last_result": result, "last_seen_active_account_key": active_key})
            return result

        busy, active_connections, active_stream = self._local_bridge_has_active_clients()
        if busy:
            result = {
                "ok": True,
                "enabled": config["enabled"],
                "action": "deferred",
                "reason": "deferred_active_clients",
                "selected_account_id": active_account_id,
                "active_connection_count": len(active_connections),
                "active_stream": active_stream,
                "timestamp": now,
            }
            self._save_aimami_follow_config({**config, "last_result": result, "last_seen_active_account_key": active_key})
            return result

        target_provider = self._bridge_provider_for_account(snapshot, active_account_id)
        provider_created = None
        if not target_provider:
            providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
            existing_names = {str(p.get("name") or "") for p in providers}
            account = self._account_for_id(active_account_id) or {"account_id": active_account_id, "email": ""}
            provider_name = self._default_provider_name(account, existing_names)
            provider_created = self.create_or_update_provider(active_account_id, provider_name, False)
            snapshot = self.snapshot(include_secrets=False)
            target_provider = self._bridge_provider_for_account(snapshot, active_account_id)

        if not target_provider:
            result = {
                "ok": False,
                "enabled": config["enabled"],
                "action": "noop",
                "reason": "missing_provider_after_create",
                "selected_account_id": active_account_id,
                "created_provider": provider_created,
                "timestamp": now,
            }
            self._save_aimami_follow_config({**config, "last_result": result, "last_seen_active_account_key": active_key})
            return result

        target_provider_id = str(target_provider.get("id") or "")
        current_provider_id = str((current_provider or {}).get("id") or "")
        if target_provider_id and target_provider_id != current_provider_id:
            changed = self.set_current_provider(target_provider_id)
            result = {
                "ok": True,
                "enabled": config["enabled"],
                "action": "switched",
                "reason": "followed_active_account",
                "selected_account_id": active_account_id,
                "provider_id": target_provider_id,
                "created_provider": provider_created,
                "result": changed,
                "timestamp": now,
            }
        else:
            result = {
                "ok": True,
                "enabled": config["enabled"],
                "action": "unchanged",
                "reason": "already_following_active_account",
                "selected_account_id": active_account_id,
                "provider_id": target_provider_id,
                "timestamp": now,
            }
        self._save_aimami_follow_config(
            {
                **config,
                "last_result": result,
                "last_seen_active_account_key": active_key,
                "last_synced_account_id": active_account_id if result.get("ok") else config.get("last_synced_account_id", ""),
            }
        )
        return result

    def _load_auth_store_raw(self) -> dict[str, Any]:
        store = load_json(self.paths.auth_store, {})
        return store if isinstance(store, dict) else {}

    def aimami_export_preview(self) -> dict[str, Any]:
        aimami = self.aimami_import_preview()
        aimami_accounts = {
            str(item.get("account_id") or ""): item
            for item in aimami.get("candidates", [])
            if isinstance(item, dict) and item.get("account_id")
        }
        missing: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        for account in self._load_accounts():
            account_id = str(account.get("account_id") or "")
            if not account_id:
                continue
            existing = aimami_accounts.get(account_id)
            row = {
                "account_id": account_id,
                "email": account.get("email") or "",
                "refresh_sha12": account.get("refresh_sha12") or "",
            }
            if not existing:
                missing.append(row)
                continue
            aimami_hash = str(existing.get("refresh_sha12") or "")
            bridge_hash = str(account.get("refresh_sha12") or "")
            if aimami_hash and bridge_hash and aimami_hash != bridge_hash:
                conflicts.append({**row, "aimami_refresh_sha12": aimami_hash})
        return {
            "ok": True,
            "detected": bool(aimami.get("detected")),
            "missing_in_aimami": missing,
            "conflicts": conflicts,
            "recommendation": "export_file",
        }

    def _export_account_token_payload(self, account_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        store = self._load_auth_store_raw()
        accounts = store.get("accounts") if isinstance(store.get("accounts"), dict) else {}
        record = accounts.get(account_id) if isinstance(accounts.get(account_id), dict) else None
        if not record:
            raise ValueError(f"未找到账号: {account_id}")
        refresh_token = str(record.get("refresh_token") or "")
        if not refresh_token:
            raise ValueError(f"账号缺少 refresh_token: {account_id}")
        token_payload = refresh_codex_oauth_token(refresh_token)
        refreshed_access = str(token_payload.get("access_token") or "")
        refreshed_refresh = str(token_payload.get("refresh_token") or "")
        identity = jwt_identity(refreshed_access)
        token_account_id = str(
            token_payload.get("account_id")
            or identity.get("account_id")
            or account_id
        )
        if token_account_id != account_id:
            raise RuntimeError("OAuth refresh returned a different account_id")
        email = str(record.get("email") or identity.get("email") or "")
        user_id = str(identity.get("user_id") or "")
        plan = str(identity.get("plan") or "")
        if refreshed_refresh and refreshed_refresh != refresh_token:
            self._upsert_oauth_account_record(
                account_id=account_id,
                email=email,
                refresh_token=refreshed_refresh,
                set_default=False,
                source=str(record.get("source") or "bridgedeck"),
            )
        export_record = {
            "account_id": account_id,
            "email": email,
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "account_id": account_id,
                "access_token": refreshed_access,
                "refresh_token": refreshed_refresh,
            },
            "last_refresh": int(time.time()),
        }
        id_token = str(token_payload.get("id_token") or "")
        if id_token:
            export_record["tokens"]["id_token"] = id_token
        return export_record, {
            "account_id": account_id,
            "email": email,
            "user_id": user_id,
            "plan": plan,
            "refresh_sha12": sha12(refreshed_refresh),
        }

    def export_aimami_accounts(self, account_ids: list[str]) -> dict[str, Any]:
        selected = [str(item).strip() for item in account_ids if str(item).strip()]
        if not selected:
            raise ValueError("请选择至少一个账号")
        known = {account["account_id"] for account in self._load_accounts()}
        unknown = [account_id for account_id in selected if account_id not in known]
        if unknown:
            raise ValueError(f"未知账号: {', '.join(unknown)}")
        exported_accounts: list[dict[str, Any]] = []
        result_accounts: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for account_id in selected:
            account = self._account_for_id(account_id) or {"account_id": account_id, "email": ""}
            try:
                export_record, result_record = self._export_account_token_payload(account_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "account_id": account_id,
                        "email": account.get("email") or "",
                        "error": truncate_log_text(str(exc), limit=500),
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            exported_accounts.append(self._aimami_export_account_payload(export_record, result_record))
            result_accounts.append(result_record)
        if not exported_accounts:
            return {
                "ok": False,
                "mode": "export_file",
                "reason": "export_failed",
                "errors": errors,
                "exported": [],
                "count": 0,
                "message": "No AiMaMi export file was written.",
            }
        payload = {
            "schemaVersion": 1,
            "kind": "aimami-accounts-export",
            "appVersion": f"BridgeDeck {APP_VERSION}",
            "exportedAt": int(time.time()),
            "exportedHostname": socket.gethostname(),
            "accountCount": len(exported_accounts),
            "accounts": exported_accounts,
        }
        stamp = time.strftime("%Y%m%d-%H%M%S")
        export_path = DEFAULT_AIMAMI_EXPORT_DIR / f"bridgedeck-{stamp}.aimami-accounts.json"
        write_private_text_file(export_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return {
            "ok": not errors,
            "mode": "export_file",
            "path": str(export_path),
            "exported": result_accounts,
            "errors": errors,
            "count": len(result_accounts),
            "message": "AiMaMi-compatible export file written; no AiMaMi files were modified.",
        }

    def _load_aimami_inject_verification(self) -> dict[str, Any]:
        raw = load_json(DEFAULT_AIMAMI_INJECT_VERIFICATION_PATH, {})
        data = raw if isinstance(raw, dict) else {}
        reload_verified = bool(data.get("reload_verified"))
        private_state_not_required = bool(data.get("private_state_not_required"))
        verified = reload_verified and private_state_not_required
        return {
            "verified": verified,
            "reload_verified": reload_verified,
            "private_state_not_required": private_state_not_required,
            "path": str(DEFAULT_AIMAMI_INJECT_VERIFICATION_PATH),
            "message": "snapshot injection verified" if verified else "manual AiMaMi reload verification required",
        }

    def _aimami_registry(self) -> dict[str, Any]:
        if not DEFAULT_AIMAMI_REGISTRY_PATH.exists():
            return {"items": []}
        raw = load_json(DEFAULT_AIMAMI_REGISTRY_PATH, {})
        if not isinstance(raw, dict):
            raise RuntimeError("AiMaMi registry is not a JSON object")
        if not isinstance(raw.get("items"), list):
            raw["items"] = []
        return raw

    def _aimami_existing_by_account(self) -> dict[str, dict[str, Any]]:
        preview = self.aimami_import_preview()
        return {
            str(item.get("account_id") or ""): item
            for item in preview.get("candidates", [])
            if isinstance(item, dict) and item.get("account_id")
        }

    def aimami_schema_profile(self) -> dict[str, Any]:
        registry = self._aimami_registry()
        items = [item for item in registry.get("items", []) if isinstance(item, dict)]
        account_keys = [str(item.get("accountKey") or "") for item in items]
        snapshot_paths = [str(item.get("snapshotPath") or "") for item in items]
        user_prefix_keys = [key for key in account_keys if key.startswith("user-") and "::" in key]
        absolute_snapshots = [path for path in snapshot_paths if path and Path(path).expanduser().is_absolute()]
        expected_item_fields = {
            "accountKey",
            "email",
            "alias",
            "accountName",
            "workspaceName",
            "profileName",
            "plan",
            "authMode",
            "hasActiveSubscription",
            "subscriptionExpiresAt",
            "subscriptionWillRenew",
            "createdAt",
            "lastUsedAt",
            "lastUsageAt",
            "cachedPrimaryWindow",
            "cachedSecondaryWindow",
            "snapshotPath",
        }
        observed_fields = set().union(*(set(item.keys()) for item in items)) if items else set()
        missing_item_fields = sorted(expected_item_fields - observed_fields) if items else []
        sample_snapshot_ok = False
        sample_snapshot_keys: list[str] = []
        for path_text in snapshot_paths:
            path, path_error = self._aimami_snapshot_path(path_text)
            if path_error or not path or not path.exists():
                continue
            snapshot = load_json(path, {})
            if isinstance(snapshot, dict):
                sample_snapshot_keys = sorted(snapshot.keys())
                tokens = snapshot.get("tokens") if isinstance(snapshot.get("tokens"), dict) else {}
                sample_snapshot_ok = (
                    snapshot.get("auth_mode") == "chatgpt"
                    and "OPENAI_API_KEY" in snapshot
                    and all(tokens.get(key) for key in ("access_token", "refresh_token", "account_id"))
                )
                break
        return {
            "detected": bool(items),
            "registry_schema_version": registry.get("schemaVersion"),
            "item_count": len(items),
            "account_key_style": "user_prefix" if user_prefix_keys else ("unknown" if items else "none"),
            "snapshot_path_style": "absolute" if snapshot_paths and len(absolute_snapshots) == len(snapshot_paths) else ("mixed" if absolute_snapshots else ("relative" if snapshot_paths else "none")),
            "required_item_fields_present": not missing_item_fields,
            "missing_item_fields": missing_item_fields,
            "sample_snapshot_keys": sample_snapshot_keys,
            "sample_snapshot_valid": sample_snapshot_ok,
            "expected_injected_account_key_style": "user_prefix",
            "expected_injected_snapshot_path_style": "absolute",
            "compatible_with_injection": bool(
                (not items or user_prefix_keys)
                and (not snapshot_paths or absolute_snapshots)
                and (not items or not missing_item_fields)
                and (not snapshot_paths or sample_snapshot_ok)
            ),
        }

    def aimami_inject_preview(self) -> dict[str, Any]:
        export_preview = self.aimami_export_preview()
        verification = self._load_aimami_inject_verification()
        processes = aimami_processes()
        return {
            "ok": True,
            "mode": "codex_snapshot",
            "verification": verification,
            "can_apply": bool(verification.get("verified")),
            "missing_in_aimami": export_preview.get("missing_in_aimami", []),
            "conflicts": export_preview.get("conflicts", []),
            "schema_profile": self.aimami_schema_profile(),
            "aimami_running": bool(processes),
            "aimami_processes": processes,
            "warning": "AiMaMi is running; reload/restart AiMaMi after injection." if processes else "",
        }

    def _aimami_snapshot_filename(self, account_id: str) -> str:
        return f"bridgedeck-{safe_slug(account_id)}.json"

    def _aimami_account_key(self, account_id: str, user_id: str) -> str:
        prefix = user_id.strip() or f"bridgedeck-{safe_slug(account_id)}"
        return f"{prefix}::{account_id}"

    def _aimami_export_account_payload(self, export_record: dict[str, Any], result_record: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        account_id = str(result_record.get("account_id") or export_record.get("account_id") or "")
        email = str(result_record.get("email") or export_record.get("email") or "")
        plan = str(result_record.get("plan") or "")
        account_key = self._aimami_account_key(account_id, str(result_record.get("user_id") or ""))
        return {
            "accountKey": account_key,
            "email": email,
            "alias": email,
            "accountName": email,
            "workspaceName": "",
            "profileName": "",
            "plan": plan,
            "authMode": "chatgpt",
            "hasActiveSubscription": bool(plan and plan.lower() != "free"),
            "subscriptionExpiresAt": 0,
            "subscriptionWillRenew": None,
            "createdAt": now,
            "lastUsedAt": now,
            "auth": {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": export_record["tokens"],
                "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        }

    def _aimami_native_snapshot_path(self, account_id: str, user_id: str) -> Path:
        prefix = (user_id.strip() or f"bridgedeck-{safe_slug(account_id)}").replace("/", "-")
        return DEFAULT_AIMAMI_SNAPSHOTS_DIR / f"{prefix}__{account_id}.json"

    def _write_aimami_snapshot(self, account_id: str, export_record: dict[str, Any], *, user_id: str = "") -> str:
        snapshot_path = self._aimami_native_snapshot_path(account_id, user_id)
        if not path_inside_dir(snapshot_path, DEFAULT_AIMAMI_SNAPSHOTS_DIR):
            raise ValueError("snapshot path outside AiMaMi snapshots directory")
        payload = {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": export_record["tokens"],
            "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        write_private_text_file(snapshot_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return str(snapshot_path)

    def _update_aimami_registry_for_injected(
        self,
        *,
        account_id: str,
        email: str,
        user_id: str,
        plan: str,
        snapshot_path: str,
        set_active: bool,
        overwrite: bool,
    ) -> str | None:
        registry = self._aimami_registry()
        backup = self._backup_file(DEFAULT_AIMAMI_REGISTRY_PATH, "aimami-inject")
        items = registry.get("items") if isinstance(registry.get("items"), list) else []
        now = int(time.time())
        account_key = self._aimami_account_key(account_id, user_id)
        next_item = {
            "accountKey": account_key,
            "email": email,
            "alias": email,
            "accountName": email,
            "workspaceName": "",
            "profileName": "",
            "plan": plan,
            "authMode": "chatgpt",
            "hasActiveSubscription": bool(plan and plan.lower() != "free"),
            "subscriptionExpiresAt": 0,
            "subscriptionWillRenew": None,
            "createdAt": now,
            "lastUsedAt": now,
            "lastUsageAt": None,
            "cachedPrimaryWindow": None,
            "cachedSecondaryWindow": None,
            "snapshotPath": str(Path(snapshot_path).resolve(strict=False)),
        }
        replaced = False
        next_items: list[Any] = []
        for item in items:
            if not isinstance(item, dict):
                next_items.append(item)
                continue
            item_account_id = account_id_from_aimami_key(str(item.get("accountKey") or ""))
            if item_account_id == account_id:
                if not overwrite:
                    next_items.append(item)
                    continue
                merged = dict(item)
                next_item["createdAt"] = item.get("createdAt", now)
                merged.update(next_item)
                next_items.append(merged)
                replaced = True
            else:
                next_items.append(item)
        if not replaced:
            next_items.append(next_item)
        registry["items"] = next_items
        registry["schemaVersion"] = registry.get("schemaVersion") or 1
        registry["updatedAt"] = now
        if set_active:
            registry["activeAccountKey"] = account_key
        write_private_text_file(DEFAULT_AIMAMI_REGISTRY_PATH, json.dumps(registry, ensure_ascii=False, indent=2))
        return backup

    def inject_aimami_accounts(
        self,
        *,
        account_ids: list[str],
        mode: str = "codex_snapshot",
        set_active: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        if mode == "export_file":
            return self.export_aimami_accounts(account_ids)
        if mode != "codex_snapshot":
            raise ValueError("unsupported AiMaMi injection mode")
        verification = self._load_aimami_inject_verification()
        if not verification.get("verified"):
            return {
                "ok": False,
                "mode": mode,
                "reason": "injection_verification_required",
                "verification": verification,
                "message": "Manual AiMaMi reload verification is required before writing AiMaMi files.",
            }
        selected = [str(item).strip() for item in account_ids if str(item).strip()]
        if not selected:
            raise ValueError("请选择至少一个账号")
        existing = self._aimami_existing_by_account()
        conflicts = [item for item in selected if item in existing and str(existing[item].get("status") or "") == "updated"]
        if conflicts and not overwrite:
            return {
                "ok": False,
                "mode": mode,
                "reason": "conflict_requires_overwrite",
                "conflicts": [{"account_id": account_id} for account_id in conflicts],
            }
        written: list[dict[str, Any]] = []
        backups: list[str] = []
        for account_id in selected:
            export_record, result_record = self._export_account_token_payload(account_id)
            snapshot_path = self._write_aimami_snapshot(account_id, export_record, user_id=str(result_record.get("user_id") or ""))
            backup = self._update_aimami_registry_for_injected(
                account_id=account_id,
                email=str(result_record.get("email") or ""),
                user_id=str(result_record.get("user_id") or ""),
                plan=str(result_record.get("plan") or ""),
                snapshot_path=snapshot_path,
                set_active=set_active,
                overwrite=overwrite,
            )
            if backup:
                backups.append(backup)
            written.append({**result_record, "snapshot_path": snapshot_path})
        processes = aimami_processes()
        return {
            "ok": True,
            "mode": mode,
            "written": written,
            "backups": backups,
            "set_active": set_active,
            "aimami_running": bool(processes),
            "warning": "AiMaMi is running; reload/restart AiMaMi after injection." if processes else "",
        }

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
            is_current_launcher = item == current_codex_launcher_path()
            launchers.append(
                {
                    "path": str(item),
                    "name": item.stem.removeprefix("codex-"),
                    "account_id": account_match.group(1) if account_match else "",
                    "codex_home": next((v for v in (home_match.groups() if home_match else ()) if v), ""),
                    "launcher_only": "OPENAI_API_KEY" in body and "/accounts/" in body and "/v1" in body,
                    "is_current_launcher": is_current_launcher,
                    "launcher_role": "current" if is_current_launcher else "dedicated",
                }
            )
        return launchers

    def _current_codex_launcher_status(self) -> dict[str, Any]:
        launcher_path = current_codex_launcher_path()
        data = {
            "path": str(launcher_path),
            "exists": launcher_path.exists(),
            "account_id": "",
            "base_url": "",
            "launcher_only": False,
            "codex_home": "",
            "risk_flags": [],
        }
        if not launcher_path.exists():
            data["risk_flags"].append("missing_current_launcher")
            return data
        if launcher_path.is_symlink():
            data["risk_flags"].append("current_launcher_symlink")
            return data
        try:
            body = launcher_path.read_text(encoding="utf-8")
        except Exception as exc:
            data["risk_flags"].append(f"current_launcher_read_error:{exc}")
            return data
        base_match = re.search(r'base_url="([^"]+)"', body)
        if base_match:
            data["base_url"] = base_match.group(1)
        account_match = re.search(r"/accounts/([^/'\" ]+)/v1", body)
        if account_match:
            data["account_id"] = account_match.group(1)
        home_match = re.search(r"CODEX_HOME=(?:'([^']+)'|\"([^\"]+)\"|([^ \n]+))", body)
        data["codex_home"] = next((v for v in (home_match.groups() if home_match else ()) if v), "")
        data["launcher_only"] = "OPENAI_API_KEY" in body and bool(data["base_url"])
        if data["codex_home"]:
            data["risk_flags"].append("current_launcher_sets_codex_home")
        if not data["launcher_only"]:
            data["risk_flags"].append("current_launcher_not_local_bridge")
        return data

    def _omc_codex_shim_status(self) -> dict[str, Any]:
        shims: list[dict[str, Any]] = []
        active = False
        risk_flags: list[str] = []
        for path in DEFAULT_OMC_CODEX_SHIM_PATHS:
            exists = path.exists()
            managed = False
            target_current = False
            body = ""
            if exists and not path.is_symlink():
                try:
                    body = path.read_text(encoding="utf-8")
                except Exception:
                    body = ""
                managed = MANAGED_CODEX_SHIM_MARKER in body
                target_current = str(current_codex_launcher_path()) in body
            elif path.is_symlink():
                risk_flags.append("omc_codex_shim_symlink")
            if exists and not managed:
                risk_flags.append("omc_codex_shim_unmanaged")
            if managed and target_current:
                active = True
            shims.append(
                {
                    "path": str(path),
                    "exists": exists,
                    "managed": managed,
                    "target_current": target_current,
                }
            )
        if not active:
            risk_flags.append("omc_codex_shim_missing")
        return {"active": active, "shims": shims, "risk_flags": sorted(set(risk_flags))}

    def _codex_desktop_status(self) -> dict[str, Any]:
        config_path = DEFAULT_CODEX_HOME / "config.toml"
        data = {
            "detected": config_path.exists(),
            "config_path": str(config_path),
            "base_url": "",
            "account_id": "",
            "model_provider": "",
            "model": "",
            "model_reasoning_effort": "",
            "service_tier": "",
            "bridge_mode": "native",
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
        provider_match = re.search(r'^\s*model_provider\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if provider_match:
            data["model_provider"] = provider_match.group(1)
        model_match = re.search(r'^\s*model\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if model_match:
            data["model"] = model_match.group(1)
        effort_match = re.search(r'^\s*model_reasoning_effort\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if effort_match:
            data["model_reasoning_effort"] = effort_match.group(1)
        tier_match = re.search(r'^\s*service_tier\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if tier_match:
            data["service_tier"] = tier_match.group(1)
        provider_base_match = re.search(
            r'(?ms)^\s*\[model_providers\.bridgedeck\].*?^\s*base_url\s*=\s*["\']([^"\']+)["\']',
            text,
        )
        if provider_base_match and not data["base_url"]:
            data["base_url"] = provider_base_match.group(1)
        account_match = re.search(r"/accounts/([^/?#]+)/v1", data["base_url"])
        if account_match:
            data["account_id"] = account_match.group(1)
        if MANAGED_CODEX_DESKTOP_BRIDGE_START in text or data["model_provider"] == "bridgedeck":
            data["bridge_mode"] = "bridgedeck_provider"
            data["managed_by"] = "bridgedeck_provider"
            data["risk_flags"].append("desktop_bridgedeck_provider")
        elif CC_SWITCH_BASE_URL in data["base_url"]:
            data["managed_by"] = "cc_switch"
        elif LOCAL_BRIDGE_BASE_URL in data["base_url"]:
            data["managed_by"] = "bridgedeck_or_local_bridge"
            data["risk_flags"].append("desktop_local_bridge_route")
        elif data["base_url"]:
            data["managed_by"] = "custom"
        else:
            data["managed_by"] = "default"
        if data["model"]:
            data["risk_flags"].append("desktop_static_model")
        if data["model_reasoning_effort"]:
            data["risk_flags"].append("desktop_static_reasoning_effort")
        if data["service_tier"]:
            data["risk_flags"].append("desktop_static_service_tier")
        return data

    def _list_codex_providers(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        known_account_ids = {item["account_id"] for item in self._load_accounts()}
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
            embedded_token_account = tokens.get("account_id") if isinstance(tokens.get("account_id"), str) else ""
            uses_managed_auth_store = (
                binding.get("source") == "managed_account"
                and binding.get("authProvider") == "codex_oauth"
                and meta_account in known_account_ids
            )
            token_account = meta_account if uses_managed_auth_store else embedded_token_account
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
                    "embedded_token_account_id": embedded_token_account,
                    "uses_managed_auth_store": uses_managed_auth_store,
                    "embedded_token_stale": bool(
                        uses_managed_auth_store
                        and embedded_token_account
                        and meta_account
                        and embedded_token_account != meta_account
                    ),
                    "refresh_sha12": sha12(refresh_token),
                    "token_mismatch": bool(meta_account and token_account and meta_account != token_account),
                }
            )
        return providers

    def _provider_public_row(self, row: sqlite3.Row, *, include_secrets: bool = False) -> dict[str, Any]:
        app_type = str(row["app_type"] or "claude") if "app_type" in row.keys() else "claude"
        surface = provider_surface_for_app_type(app_type)
        meta = self._extract_json(row["meta"])
        settings = self._extract_json(row["settings_config"])
        env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        account_id = ""
        auth_binding = meta.get("authBinding")
        if isinstance(auth_binding, dict):
            value = auth_binding.get("accountId")
            if isinstance(value, str):
                account_id = value
        if not account_id:
            account_id = bridge_account_id_from_env(env)
        auth_token = env.get("ANTHROPIC_AUTH_TOKEN") if isinstance(env.get("ANTHROPIC_AUTH_TOKEN"), str) else ""
        forced_model = env.get("ANTHROPIC_MODEL") if isinstance(env.get("ANTHROPIC_MODEL"), str) else ""
        base_url = env.get("ANTHROPIC_BASE_URL") if isinstance(env.get("ANTHROPIC_BASE_URL"), str) else ""
        routes = meta.get("claudeDesktopModelRoutes") if isinstance(meta.get("claudeDesktopModelRoutes"), dict) else {}
        desktop_route_scope = "unmanaged"
        route_issues: list[dict[str, Any]] = []
        route_changed = False
        if app_type == "claude-desktop":
            managed_desktop_bridge = bool(
                account_id
                and (
                    base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/")
                    or meta.get("codexOauthTransport") == "local_bridge"
                )
            )
            if managed_desktop_bridge:
                desktop_route_scope = "local_bridge"
                _normalized_meta, route_issues, route_changed = normalize_claude_desktop_routes(meta, env)

        return {
            "id": row["id"],
            "name": row["name"],
            "surface": surface,
            "app_type": app_type,
            "provider_type": row["provider_type"] or "" if "provider_type" in row.keys() else "",
            "is_current": bool(row["is_current"]) if "is_current" in row.keys() else False,
            "sort_index": row["sort_index"] if "sort_index" in row.keys() else 0,
            "meta_provider_type": meta.get("providerType") if isinstance(meta.get("providerType"), str) else "",
            "api_format": meta.get("apiFormat") if isinstance(meta.get("apiFormat"), str) else "",
            "desktop_mode": meta.get("claudeDesktopMode") if isinstance(meta.get("claudeDesktopMode"), str) else "",
            "desktop_routes": routes,
            "desktop_route_scope": desktop_route_scope,
            "desktop_route_issues": route_issues if app_type == "claude-desktop" else [],
            "desktop_routes_ok": (not route_changed) if app_type == "claude-desktop" else True,
            "desktop_requires_local_routing": app_type == "claude-desktop" and meta.get("claudeDesktopMode") == "proxy",
            "account_id": account_id,
            "base_url": base_url,
            "model": forced_model,
            "routing_mode": "forced" if forced_model else "claude_auto",
            "model_is_legacy_default": forced_model == DEFAULT_BRIDGE_PROVIDER_MODEL,
            "haiku_model": env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") if isinstance(env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"), str) else "",
            "sonnet_model": env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") if isinstance(env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"), str) else "",
            "opus_model": env.get("ANTHROPIC_DEFAULT_OPUS_MODEL") if isinstance(env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"), str) else "",
            "max_context_tokens": env.get(MAX_CONTEXT_TOKENS_ENV) if isinstance(env.get(MAX_CONTEXT_TOKENS_ENV), str) else "",
            "auth_token": auth_token if include_secrets else "",
            "auth_token_masked": mask_token(auth_token),
            "compact_enabled": bool(str(env.get(COMPACT_WINDOW_ENV) or "").strip()),
            "compact_window_tokens": env.get(COMPACT_WINDOW_ENV) if isinstance(env.get(COMPACT_WINDOW_ENV), str) else "",
            "compact_threshold_percent": env.get(COMPACT_THRESHOLD_ENV) if isinstance(env.get(COMPACT_THRESHOLD_ENV), str) else "",
            "claude_attribution_header": env.get(CLAUDE_CODE_ATTRIBUTION_HEADER_ENV)
            if CLAUDE_CODE_ATTRIBUTION_HEADER_ENV in env
            else None,
            "claude_attribution_status": attribution_env_status(
                env.get(CLAUDE_CODE_ATTRIBUTION_HEADER_ENV),
                source_present=True,
            ),
        }

    def _list_surface_providers(
        self,
        conn: sqlite3.Connection,
        surface: str,
        *,
        include_secrets: bool = False,
    ) -> list[dict[str, Any]]:
        app_type = provider_surface_app_type(surface)
        rows = conn.execute(
            """
            SELECT id, app_type, name, provider_type, is_current, sort_index, meta, settings_config
            FROM providers
            WHERE app_type = ?
            ORDER BY sort_index ASC, name ASC
            """,
            (app_type,),
        ).fetchall()
        return [self._provider_public_row(row, include_secrets=include_secrets) for row in rows]

    def _ccswitch_315_status(
        self,
        providers: list[dict[str, Any]],
        desktop_providers: list[dict[str, Any]],
        codex_providers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for provider in desktop_providers:
            if provider.get("account_id") and not provider.get("desktop_routes_ok"):
                issues.append(
                    {
                        "severity": "warn",
                        "surface": "claude_desktop",
                        "provider_id": provider.get("id"),
                        "provider_name": provider.get("name"),
                        "message": "Claude Desktop 路由字段缺失或和 BridgeDeck 账号映射不一致",
                    }
                )
        return {
            "ok": not any(item.get("severity") == "error" for item in issues),
            "claude_provider_count": len(providers),
            "claude_desktop_provider_count": len(desktop_providers),
            "codex_provider_count": len(codex_providers),
            "desktop_route_issue_count": sum(1 for item in desktop_providers if item.get("desktop_route_issues")),
            "local_bridge_desktop_count": sum(1 for item in desktop_providers if item.get("account_id")),
            "issues": issues,
        }

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
            account_id = str(provider.get("account_id") or bridge_account_id_from_base_url(str(provider.get("base_url") or "")) or "")
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
            if launcher.get("is_current_launcher"):
                continue
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
        ccswitch_315 = snapshot.get("ccswitch_315") if isinstance(snapshot.get("ccswitch_315"), dict) else {}
        if ccswitch_315.get("desktop_route_issue_count"):
            risk_flags.append("claude_desktop_route_mismatch")
        codex_desktop = snapshot.get("codex_desktop", {}) if isinstance(snapshot.get("codex_desktop"), dict) else {}
        for flag in codex_desktop.get("risk_flags", []):
            if flag in {"desktop_static_model", "desktop_static_reasoning_effort", "desktop_static_service_tier"}:
                risk_flags.append(str(flag))
        stream_diag = snapshot.get("stream_diagnostics") if isinstance(snapshot.get("stream_diagnostics"), dict) else {}
        latest_stream = stream_diag.get("latest") if isinstance(stream_diag.get("latest"), dict) else {}
        if latest_stream.get("kind") == "client_disconnect":
            risk_flags.append("bridge_client_disconnect")
        elif latest_stream.get("kind") == "bridge_idle_timeout":
            risk_flags.append("bridge_idle_timeout")
        hook_risks = snapshot.get("claude_hook_risks") if isinstance(snapshot.get("claude_hook_risks"), dict) else {}
        if hook_risks.get("status") == "warning":
            risk_flags.append("claude_hook_stall_risk")
        status = "ok" if not risk_flags else str(risk_flags[0])
        return {
            "ok": True,
            "status": status,
            "risk_flags": sorted(set(risk_flags)),
            "account_matrix": snapshot.get("account_matrix", []),
            "codex_desktop": snapshot.get("codex_desktop", {}),
            "ccswitch_315": ccswitch_315,
            "claude_desktop_providers": snapshot.get("claude_desktop_providers", []),
            "stream_diagnostics": stream_diag,
            "claude_hook_risks": hook_risks,
        }

    def codex_stability_route_canary(
        self,
        *,
        desktop: dict[str, Any] | None = None,
        native_proxy: dict[str, Any] | None = None,
        app_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        desktop = desktop or self._codex_desktop_status()
        native_proxy = native_proxy or self.codex_native_proxy_status()
        app_state = app_state or codex_desktop_app_state()
        bridge_running = tcp_open("127.0.0.1", LOCAL_BRIDGE_PORT)
        route_active = desktop.get("bridge_mode") == "bridgedeck_provider"
        fresh_stale_stream = app_state.get("status") == "stale_stream_state" and bool(app_state.get("fresh"))
        native_status = str(native_proxy.get("status") or "unknown")
        account_id = str(desktop.get("account_id") or "")
        checks = [
            {
                "id": "fresh_app_state",
                "status": "ok" if fresh_stale_stream else "blocked",
                "detail": app_state.get("message", ""),
            },
            {
                "id": "local_bridge",
                "status": "ok" if bridge_running else "blocked",
                "detail": f"http://127.0.0.1:{LOCAL_BRIDGE_PORT}",
            },
            {
                "id": "native_proxy",
                "status": "ok" if native_status == "ok" else "blocked",
                "detail": native_proxy.get("message", ""),
            },
            {
                "id": "stability_route",
                "status": "blocked",
                "detail": desktop.get("managed_by", "unknown"),
            },
            {
                "id": "compact_route",
                "status": "blocked",
                "detail": "Local Bridge 当前未实现 /v1/responses/compact。",
            },
        ]
        pass_criteria = [
            "先补齐 Local Bridge /v1/responses/compact 兼容端点。",
            "确认不会写入 model/provider/model_reasoning_effort。",
            "再用真实 Codex Desktop 会话验证上下文压缩。",
        ]
        if route_active:
            status = "unsafe_active"
            action = "restore_native_mode"
            message = CODEX_DESKTOP_BRIDGE_DISABLED_MESSAGE
            eligible = False
        elif app_state.get("status") == "stale_stream_state_unfresh":
            status = "needs_fresh_evidence"
            action = "collect_fresh_app_state"
            message = "Sentry app-state 证据已过期；Stability Route 暂不启用。"
            eligible = False
        elif fresh_stale_stream and bridge_running and native_status == "ok":
            status = "disabled"
            action = "keep_native_mode"
            message = CODEX_DESKTOP_BRIDGE_DISABLED_MESSAGE
            eligible = False
        else:
            status = "disabled"
            action = "keep_native_mode"
            message = CODEX_DESKTOP_BRIDGE_DISABLED_MESSAGE
            eligible = False
        return {
            "ok": eligible,
            "status": status,
            "action": action,
            "message": message,
            "eligible": eligible,
            "route_active": route_active,
            "bridge_running": bridge_running,
            "account_id": account_id,
            "checks": checks,
            "pass_criteria": pass_criteria,
        }

    def codex_desktop_doctor(self) -> dict[str, Any]:
        config = codex_config_feature_state()
        desktop = self._codex_desktop_status()
        native_proxy = self.codex_native_proxy_status()
        process_state = codex_desktop_process_state(
            config_path=DEFAULT_CODEX_HOME / "config.toml",
            env_path=DEFAULT_CODEX_HOME / ".env",
        )
        versions = codex_cli_version_state()
        logs = codex_desktop_log_state()
        app_state = codex_desktop_app_state()
        dynamic_tools = codex_app_dynamic_tools_state()
        stability_route_canary = self.codex_stability_route_canary(
            desktop=desktop,
            native_proxy=native_proxy,
            app_state=app_state,
        )
        app_state_status = str(app_state.get("status") or "unknown")
        if app_state_status == "stale_stream_state":
            app_state_check_status = "failed"
        elif app_state_status == "stale_stream_state_unfresh":
            app_state_check_status = "warning"
        elif app_state_status in {"ok", "missing", "no_app_state"}:
            app_state_check_status = app_state_status
        else:
            app_state_check_status = "warning"

        checks: list[dict[str, Any]] = [
            {
                "id": "config_hooks",
                "label": "Codex hooks config",
                "status": "failed" if config.get("active_legacy_key_present") else ("ok" if config.get("hooks_effective_enabled") else "disabled"),
                "detail": (
                    "active config still contains codex_hooks"
                    if config.get("active_legacy_key_present")
                    else ("hooks enabled" if config.get("hooks_effective_enabled") else "hooks disabled")
                ),
            },
            {
                "id": "native_proxy",
                "label": "Codex native proxy env",
                "status": native_proxy.get("status", "unknown"),
                "detail": native_proxy.get("message", ""),
            },
            {
                "id": "desktop_process",
                "label": "Codex Desktop app-server",
                "status": "warning" if process_state.get("restart_required") else ("ok" if process_state.get("app_server_running") else "missing"),
                "detail": (
                    "app-server started before config/env changed"
                    if process_state.get("restart_required")
                    else ("app-server running" if process_state.get("app_server_running") else "app-server not detected")
                ),
            },
            {
                "id": "desktop_app_state",
                "label": "Codex Desktop app-state",
                "status": app_state_check_status,
                "detail": app_state.get("message", ""),
            },
            {
                "id": "codex_app_dynamic_tools",
                "label": "Codex App dynamic tools",
                "status": (
                    "ok"
                    if dynamic_tools.get("status") == "ok"
                    else ("failed" if not dynamic_tools.get("ok") else dynamic_tools.get("status", "unknown"))
                ),
                "detail": dynamic_tools.get("message", ""),
            },
            {
                "id": "desktop_logs",
                "label": "Codex Desktop logs",
                "status": logs.get("status", "unknown"),
                "detail": ", ".join(logs.get("signals", [])) if logs.get("signals") else "no warning signals in recent logs",
            },
            {
                "id": "desktop_route",
                "label": "Codex Desktop route",
                "status": "warning" if desktop.get("bridge_mode") == "bridgedeck_provider" else "ok",
                "detail": desktop.get("managed_by", "unknown"),
            },
        ]

        recommendations: list[str] = []
        status = "healthy"
        action = "no_action"
        message = "Codex Desktop config、proxy、进程和近期日志未发现明显异常。"

        native_status = str(native_proxy.get("status") or "unknown")
        log_counts = logs.get("counts") if isinstance(logs.get("counts"), dict) else {}
        clean_hooks_config = bool(
            config.get("hooks_effective_enabled")
            and not config.get("active_legacy_key_present")
        )
        has_deprecation_warning = bool(log_counts.get("codex_hooks_deprecation"))
        has_unknown_conversation = bool(log_counts.get("unknown_conversation"))
        has_slow_app_server_calls = bool(log_counts.get("slow_config_read") or log_counts.get("slow_skills_list"))
        has_stale_stream_state = app_state_status == "stale_stream_state"
        has_unfresh_stale_stream_state = app_state_status == "stale_stream_state_unfresh"
        has_dynamic_tools_failure = str(dynamic_tools.get("status") or "") in {
            "missing_dynamic_tools",
            "non_user_thread_source",
            "recent_missing_dynamic_tools",
            "remote_dynamic_tools_missing",
        }

        if config.get("active_legacy_key_present"):
            status = "active_config_legacy_key"
            action = "normalize_config"
            message = "活跃 ~/.codex/config.toml 仍包含 deprecated codex_hooks。"
            recommendations.append("删除 [features].codex_hooks，保留 [features].hooks = true。")
        elif desktop.get("bridge_mode") == "bridgedeck_provider":
            status = "bridge_mode_unsupported"
            action = "restore_native_mode"
            message = CODEX_DESKTOP_BRIDGE_DISABLED_MESSAGE
            recommendations.append("恢复 Codex Desktop 原生模式；只移除 BridgeDeck provider，不清理模型或思考等级。")
        elif native_status in {"missing", "incomplete", "proxy_down", "blocked"}:
            status = f"native_proxy_{native_status}"
            action = "repair_env" if native_status in {"missing", "incomplete"} else "start_proxy"
            message = str(native_proxy.get("message") or "Codex 原生代理 env 不完整。")
            recommendations.append("只修复 ~/.codex/.env；不要改 model/provider。")
            if native_status != "blocked":
                recommendations.append("修复后完全退出并重启 Codex Desktop。")
        elif has_dynamic_tools_failure:
            message = str(dynamic_tools.get("message") or "Codex 线程缺失 codex_app dynamic tools。")
            if dynamic_tools.get("status") == "remote_dynamic_tools_missing":
                status = "remote_thread_dynamic_tools_missing"
                action = "create_local_desktop_thread"
                recommendations.append("停止在该 remote/iOS 创建的线程里做 automation；直接用本机 Codex Desktop 新建普通用户会话。")
                recommendations.append("新线程必须验证 thread_source=user、dynamic_tools=3。")
            else:
                status = "desktop_dynamic_tools_missing"
                action = "new_user_thread_after_hard_restart"
                recommendations.append("不要继续重复改 config 或 BridgeDeck provider；该问题发生在线程启动注入阶段。")
                recommendations.append("完全退出 Codex Desktop 后新建普通用户会话，并验证 thread_source=user、dynamic_tools=3。")
        elif process_state.get("restart_required"):
            status = "desktop_state_stale"
            action = "hard_restart_codex"
            message = "Codex app-server 启动时间早于 config/env 修改时间，当前进程可能仍持有旧 features/config 状态。"
            recommendations.append("不要继续重复改 config；当前活跃 config 已清理时，必须完全退出 Codex Desktop 再重新打开。")
        elif has_stale_stream_state:
            status = "desktop_stream_state_stale"
            action = "keep_native_mode"
            message = str(app_state.get("message") or "Codex Desktop streaming 状态卡在无 runtime。")
            recommendations.append("保持 Codex Desktop 原生配置；不要启用 Stability Route。")
            recommendations.append("先补齐 Local Bridge /v1/responses/compact 兼容后，再评估是否恢复路由。")
        elif has_unfresh_stale_stream_state:
            status = "desktop_app_state_unfresh"
            action = "collect_fresh_app_state"
            message = str(app_state.get("message") or "Codex Desktop app-state 证据已过期。")
            recommendations.append("先重新采样 app-state；Stability Route 暂不启用。")
        elif has_deprecation_warning and clean_hooks_config:
            status = "upstream_hooks_warning_likely"
            action = "report_upstream"
            message = "活跃 config 已是 hooks=true，但日志仍出现 codex_hooks deprecated warning，符合上游 false-positive 类问题。"
            recommendations.append("不要继续重复改 config；记录版本和日志，等待/跟踪上游修复。")
        elif has_unknown_conversation:
            status = "desktop_event_session_unhealthy"
            action = "hard_restart_codex"
            message = "Codex Desktop 日志出现 unknown conversation 事件，问题在 Desktop 事件/会话层。"
            recommendations.append("完全退出 Codex Desktop，重新打开当前会话后重测。")
        elif has_slow_app_server_calls:
            status = "desktop_app_server_slow"
            action = "hard_restart_codex"
            message = "Codex Desktop app-server 出现慢 config/read 或 skills/list。"
            recommendations.append("先重启 Codex Desktop；若复现再收集日志。")

        if versions.get("version_split"):
            recommendations.append("注意：全局 codex CLI 与 Codex.app bundled CLI 版本不同，诊断以 Desktop bundled CLI 为准。")
        if not recommendations:
            recommendations.append("无需修复。")

        return {
            "ok": True,
            "status": status,
            "action": action,
            "message": message,
            "recommendations": recommendations,
            "restart_command": "osascript -e 'quit app \"Codex\"' && open -a Codex",
            "checks": checks,
            "config": config,
            "codex_native_proxy": native_proxy,
            "process": process_state,
            "versions": versions,
            "logs": logs,
            "app_state": app_state,
            "dynamic_tools": dynamic_tools,
            "stability_route_canary": stability_route_canary,
            "codex_desktop": desktop,
        }

    def normalize_codex_hooks_config(self) -> dict[str, Any]:
        config_path = DEFAULT_CODEX_HOME / "config.toml"
        if config_path.is_symlink():
            raise ValueError("~/.codex/config.toml 不能是符号链接")
        if not config_path.exists():
            return {
                "ok": True,
                "changed": False,
                "message": "~/.codex/config.toml 不存在，无需清理",
                "config_path": str(config_path),
                "backup": None,
            }
        original = config_path.read_text(encoding="utf-8")
        features = toml_section_bool_keys(original, "features")
        updated, removed = strip_toml_section_keys(original, "features", ("codex_hooks",))
        if removed and "hooks" not in features:
            updated = ensure_toml_section_bool_key(updated, "features", "hooks", True)
        if updated == original:
            return {
                "ok": True,
                "changed": False,
                "message": "活跃 config 未发现 codex_hooks",
                "config_path": str(config_path),
                "backup": None,
                "removed": [],
                "restart_required": False,
            }
        backup = self._backup_file(config_path, "codex-hooks-config")
        write_private_text_file(config_path, updated)
        return {
            "ok": True,
            "changed": True,
            "message": "已清理 [features].codex_hooks，并保留 hooks=true",
            "config_path": str(config_path),
            "backup": backup,
            "removed": removed,
            "restart_required": True,
        }

    def services(self, *, server_port: int = DEFAULT_PORT) -> dict[str, Any]:
        bridge_processes = port_processes(LOCAL_BRIDGE_PORT)
        bridge_script = find_local_bridge_script(bridge_processes)
        upstream_proxy = detect_upstream_proxy(bridge_processes)
        bridge_state = read_local_bridge_state()
        stream_diagnostics = self.stream_diagnostics()
        active_connections = port_active_connections(LOCAL_BRIDGE_PORT)
        return {
            "ok": True,
            "services": {
                "bridgedeck": {
                    "name": "BridgeDeck",
                    "running": tcp_open("127.0.0.1", server_port),
                    "port": server_port,
                },
                "local_bridge": {
                    "name": "Local Codex Bridge",
                    "running": tcp_open("127.0.0.1", LOCAL_BRIDGE_PORT),
                    "port": LOCAL_BRIDGE_PORT,
                    "processes": bridge_processes,
                    "script": str(bridge_script) if bridge_script else "",
                    "can_start": bool(bridge_script),
                    "active_connections": active_connections,
                    "active_connection_count": len(active_connections),
                    "restart_protected": bool(active_connections),
                    "upstream_proxy": mask_url_credentials(upstream_proxy),
                    "log_path": str(self.paths.db.parent / "bridgedeck-local-bridge.log"),
                    "active_stream": bridge_state.get("active_stream") or {},
                    "last_stream_error": bridge_state.get("last_stream_error") or {},
                    "stream_diagnostics": stream_diagnostics,
                },
                "cc_switch_proxy": {
                    "name": "CC Switch Proxy",
                    "running": tcp_open("127.0.0.1", 15721),
                    "port": 15721,
                    "processes": port_processes(15721),
                },
            },
        }

    def stream_diagnostics(self) -> dict[str, Any]:
        return bridge_stream_diagnostics([self.paths.db.parent / "bridgedeck-local-bridge.log"])

    def codex_native_proxy_status(self) -> dict[str, Any]:
        env_path = DEFAULT_CODEX_HOME / ".env"
        if env_path.is_symlink():
            return {
                "ok": False,
                "status": "blocked",
                "message": "~/.codex/.env 是符号链接，BridgeDeck 不会修改",
                "env_path": str(env_path),
                "proxy_url": "",
                "proxy_url_masked": "",
                "proxy_host": "",
                "proxy_port": 0,
                "proxy_running": False,
                "missing_keys": list(CODEX_NATIVE_PROXY_REQUIRED_KEYS),
                "mismatched_keys": [],
                "repair_available": False,
                "restart_required": False,
            }
        values = load_env_file(env_path)
        file_proxy_url = proxy_url_from_env_values(values)
        repair_proxy_url, repair_source = choose_codex_native_proxy_url()
        proxy_url = file_proxy_url or repair_proxy_url
        proxy_host, proxy_port = parse_proxy_target(proxy_url)
        proxy_running = bool(proxy_host and proxy_port and tcp_open(proxy_host, proxy_port))
        repair_host, repair_port = parse_proxy_target(repair_proxy_url)
        repair_running = bool(repair_host and repair_port and tcp_open(repair_host, repair_port))
        required_values = codex_native_proxy_required_values(proxy_url) if proxy_url else {}
        missing_keys = [key for key in CODEX_NATIVE_PROXY_REQUIRED_KEYS if not values.get(key)]
        mismatched_keys = [
            key
            for key in CODEX_NATIVE_PROXY_REQUIRED_KEYS
            if values.get(key) and required_values.get(key) and values.get(key) != required_values[key]
        ]
        if not env_path.exists():
            status = "missing"
            message = "未发现 ~/.codex/.env，Codex Desktop 可能拿不到显式代理"
        elif not proxy_url:
            status = "missing"
            message = "~/.codex/.env 未配置 Codex 代理"
        elif not proxy_running:
            status = "proxy_down"
            message = "Codex 原生代理端口不可达"
        elif missing_keys or mismatched_keys:
            status = "incomplete"
            message = "Codex 原生代理缺少 WS/WSS 或代理变量不一致"
        else:
            status = "ok"
            message = "Codex 原生代理变量已齐全"
        return {
            "ok": status == "ok",
            "status": status,
            "message": message,
            "env_path": str(env_path),
            "exists": env_path.exists(),
            "proxy_url": proxy_url,
            "proxy_url_masked": mask_url_credentials(proxy_url),
            "proxy_source": str(env_path) if file_proxy_url else repair_source,
            "proxy_host": proxy_host,
            "proxy_port": proxy_port,
            "proxy_running": proxy_running,
            "missing_keys": missing_keys,
            "mismatched_keys": mismatched_keys,
            "required_keys": list(CODEX_NATIVE_PROXY_REQUIRED_KEYS),
            "repair_proxy_url": repair_proxy_url,
            "repair_proxy_url_masked": mask_url_credentials(repair_proxy_url),
            "repair_available": repair_running,
            "restart_required": status in {"ok", "incomplete"},
        }

    def repair_codex_native_proxy(self) -> dict[str, Any]:
        env_path = DEFAULT_CODEX_HOME / ".env"
        if env_path.is_symlink():
            raise ValueError("~/.codex/.env 不能是符号链接")
        proxy_url, proxy_source = choose_codex_native_proxy_url()
        proxy_host, proxy_port = parse_proxy_target(proxy_url)
        if not proxy_url or not proxy_host or not proxy_port or not tcp_open(proxy_host, proxy_port):
            raise ValueError("未检测到可用代理端口，先启动本地代理后再修复")
        DEFAULT_CODEX_HOME.mkdir(parents=True, exist_ok=True)
        os.chmod(DEFAULT_CODEX_HOME, 0o700)
        original = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        updated = update_env_text_with_values(original, codex_native_proxy_required_values(proxy_url))
        mode_before = env_path.stat().st_mode & 0o777 if env_path.exists() else None
        changed = updated != original
        permission_changed = mode_before != 0o600
        backup = self._backup_file(env_path, "codex-native-proxy") if env_path.exists() and (changed or permission_changed) else None
        if changed:
            write_private_text_file(env_path, updated)
        elif env_path.exists() and permission_changed:
            os.chmod(env_path, 0o600)
        status = self.codex_native_proxy_status()
        return {
            "ok": True,
            "changed": changed or permission_changed,
            "message": "Codex 原生代理已修复" if changed or permission_changed else "Codex 原生代理已是最新",
            "env_path": str(env_path),
            "backup": backup,
            "proxy_url": proxy_url,
            "proxy_url_masked": mask_url_credentials(proxy_url),
            "proxy_source": proxy_source,
            "proxy_host": proxy_host,
            "proxy_port": proxy_port,
            "env_keys": list(CODEX_NATIVE_PROXY_REQUIRED_KEYS),
            "restart_required": True,
            "restart_message": "完全退出并重启 Codex Desktop 后，新的 ~/.codex/.env 才会被进程读取。",
            "status": status,
        }

    def proxy_diagnosis(self) -> dict[str, Any]:
        proxy_url, proxy_source = detect_codex_proxy_url()
        proxy_host, proxy_port = parse_proxy_target(proxy_url)
        proxy_running = bool(proxy_host and proxy_port and tcp_open(proxy_host, proxy_port))
        proxy_processes = proxy_port_processes(proxy_port) if proxy_port else []
        proxy_owner_detail = "未检测到端口占用进程"
        if proxy_processes:
            proxy_owner_detail = " / ".join(
                f"{item.get('label') or 'unknown'}(pid {item.get('pid') or '-'})"
                for item in proxy_processes
            )
        native_proxy_status = self.codex_native_proxy_status()

        checks: list[dict[str, Any]] = [
            {
                "id": "proxy_config",
                "label": "Codex 代理配置",
                "status": "ok" if proxy_url else "missing",
                "detail": mask_url_credentials(proxy_url) if proxy_url else "未检测到 .codex 代理配置",
                "source": proxy_source,
            },
            {
                "id": "proxy_tcp",
                "label": "本地代理监听",
                "status": "ok" if proxy_running else "failed",
                "detail": f"{proxy_host}:{proxy_port}" if proxy_running else (f"{proxy_host}:{proxy_port} 不可达" if proxy_host and proxy_port else "未解析到代理地址"),
            },
            {
                "id": "proxy_owner",
                "label": "代理端口占用者",
                "status": "warning" if any(item.get("legacy_conflict") for item in proxy_processes) else ("ok" if proxy_processes else "unknown"),
                "detail": proxy_owner_detail,
            },
            {
                "id": "codex_native_proxy_env",
                "label": "Codex 原生代理 env",
                "status": native_proxy_status["status"],
                "detail": native_proxy_status["message"],
                "missing_keys": native_proxy_status["missing_keys"],
            },
        ]

        openai_probe: dict[str, Any] | None = None
        direct_openai_probe: dict[str, Any] | None = None
        if proxy_url and proxy_running:
            openai_probe = probe_remote_url(
                PROXY_DIAG_OPENAI_URL,
                proxy_url=proxy_url,
                headers={"Accept": "application/json"},
            )
            checks.append(
                {
                    "id": "openai_api",
                    "label": "api.openai.com 基础探测",
                    "status": "ok" if openai_probe_is_healthy(openai_probe) else ("forbidden" if openai_probe.get("status_code") == 403 else "failed"),
                    "detail": openai_probe.get("error") or f"HTTP {openai_probe.get('status_code')}",
                    "body_excerpt": openai_probe.get("body_excerpt", ""),
                }
            )
        if not openai_probe_is_healthy(openai_probe):
            direct_openai_probe = probe_remote_url(
                PROXY_DIAG_OPENAI_URL,
                proxy_url="",
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            checks.append(
                {
                    "id": "openai_direct",
                    "label": "绕过本地 HTTP 代理探测",
                    "status": "ok" if openai_probe_is_healthy(direct_openai_probe) else ("forbidden" if direct_openai_probe.get("status_code") == 403 else "failed"),
                    "detail": direct_openai_probe.get("error") or f"HTTP {direct_openai_probe.get('status_code')}",
                    "body_excerpt": direct_openai_probe.get("body_excerpt", ""),
                }
            )

        auth_state = read_codex_auth_state()
        codex_probe: dict[str, Any] | None = None
        if proxy_url and proxy_running and auth_state.get("authenticated"):
            payload = json.dumps(
                {
                    "model": "gpt-5.5",
                    "stream": True,
                    "store": False,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                    "instructions": "You are Codex.",
                    "tools": [],
                    "include": ["reasoning.encrypted_content"],
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Reply with ok."}],
                        }
                    ],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            codex_probe = probe_remote_url(
                PROXY_DIAG_CODEX_URL,
                proxy_url=proxy_url,
                method="POST",
                headers={
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {auth_state['access_token']}",
                    "ChatGPT-Account-Id": str(auth_state.get("account_id") or ""),
                    "User-Agent": "bridgedeck-proxy-diagnose",
                    "Originator": "bridgedeck-proxy-diagnose",
                },
                body=payload,
                timeout=25.0,
            )
            codex_status = int(codex_probe.get("status_code") or 0)
            checks.append(
                {
                    "id": "codex_backend",
                    "label": "chatgpt.com Codex 流式探测",
                    "status": "ok" if codex_status == 200 else ("forbidden" if codex_status == 403 else "failed"),
                    "detail": codex_probe.get("error") or f"HTTP {codex_status}",
                    "body_excerpt": codex_probe.get("body_excerpt", ""),
                }
            )
        else:
            checks.append(
                {
                    "id": "codex_backend",
                    "label": "chatgpt.com Codex 流式探测",
                    "status": "skipped",
                    "detail": "缺少 ~/.codex/auth.json 登录态" if not auth_state.get("authenticated") else "代理未就绪",
                }
            )

        status = "healthy"
        message = "代理链路可用，问题更像 Codex.app 事件会话层重连"
        recommendations = [
            "完全退出并重启 Codex.app 后重测",
            "如果只在 App 内重连，优先排查旧会话状态或事件流请求头差异",
        ]
        if not proxy_url:
            status = "missing_proxy"
            message = "未检测到 Codex 代理配置"
            recommendations = ["检查 ~/.codex/.env 的 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY"]
        elif not proxy_running:
            status = "proxy_down"
            message = "本地代理端口不可达"
            recommendations = ["先启动本地代理，再重测"]
        elif openai_probe and not openai_probe_is_healthy(openai_probe) and openai_probe_is_healthy(direct_openai_probe):
            status = "proxy_unhealthy"
            error_text = probe_error_text(openai_probe)
            message = "本地网络可达，但配置的本地代理无法连接 OpenAI"
            if looks_like_tls_proxy_failure(error_text):
                status = "proxy_tls_failure"
                message = "检测到本地代理 TLS/SSL 握手失败"
            recommendations = [
                "检查当前代理端口是否被遗留代理软件抢占",
                "重启正在使用的代理工具后再重测",
                "若已开启系统级 TUN/VPN，可临时清除显式 HTTP 代理后验证直连链路",
            ]
            legacy_labels = sorted(
                {
                    str(item.get("label") or "")
                    for item in proxy_processes
                    if item.get("legacy_conflict") and item.get("label")
                }
            )
            if legacy_labels:
                recommendations.insert(0, f"当前端口占用者包含 {' / '.join(legacy_labels)}，优先关闭该遗留后台进程")
        elif any(check.get("status") == "forbidden" for check in checks):
            status = "upstream_forbidden"
            message = "代理链路对 OpenAI/Codex 请求返回 403"
            recommendations = [
                "更换代理节点后重测",
                "检查分流规则，确认 OpenAI/Codex 实时流量未被特殊处理",
                "确认节点支持 websocket / SSE / 长连接",
            ]
        elif openai_probe and openai_probe.get("status_code") != 401:
            status = "api_unhealthy"
            message = "api.openai.com 基础探测异常"
            recommendations = [
                "优先更换节点",
                "检查是否存在 TLS 拦截或中间层返回非预期状态码",
            ]
        elif codex_probe and int(codex_probe.get("status_code") or 0) != 200:
            status = "codex_backend_unhealthy"
            message = "Codex 上游接口异常，问题不在本地 env"
            recommendations = [
                "更换节点后重测 chatgpt.com/backend-api/codex",
                "检查该节点是否只允许基础 API，不兼容 Codex 后端事件流",
            ]
        elif native_proxy_status.get("status") == "incomplete":
            status = "native_proxy_incomplete"
            message = "Codex 原生代理缺少 WS/WSS，WebSocket 可能仍会断链"
            recommendations = [
                "点击“修复 Codex 原生代理”补齐 ~/.codex/.env",
                "完全退出并重启 Codex.app 后重测",
            ]

        return {
            "ok": True,
            "status": status,
            "message": message,
            "codex_native_proxy": native_proxy_status,
            "proxy": {
                "source": proxy_source,
                "url": mask_url_credentials(proxy_url),
                "host": proxy_host,
                "port": proxy_port,
                "running": proxy_running,
                "processes": proxy_processes,
            },
            "direct_openai_probe": direct_openai_probe or {},
            "codex_auth": {
                "present": bool(auth_state.get("present")),
                "authenticated": bool(auth_state.get("authenticated")),
                "plan": str(auth_state.get("plan") or ""),
                "email_masked": mask_email_value(auth_state.get("email")),
            },
            "checks": checks,
            "recommendations": recommendations,
        }

    def _start_local_bridge(self) -> dict[str, Any]:
        if tcp_open("127.0.0.1", LOCAL_BRIDGE_PORT):
            return {**self.services(), "ok": True, "message": "Local Codex Bridge 已在运行"}

        bridge_processes = port_processes(LOCAL_BRIDGE_PORT)
        script = find_local_bridge_script(bridge_processes)
        if not script:
            return {"ok": False, "error": "未找到 local_codex_bridge.py"}

        env = os.environ.copy()
        env["CODEX_BRIDGE_HOST"] = "127.0.0.1"
        env["CODEX_BRIDGE_PORT"] = str(LOCAL_BRIDGE_PORT)
        no_proxy = "127.0.0.1,localhost,::1"
        env["NO_PROXY"] = ",".join(filter(None, [env.get("NO_PROXY", ""), no_proxy]))
        env["no_proxy"] = ",".join(filter(None, [env.get("no_proxy", ""), no_proxy]))
        upstream_proxy = detect_upstream_proxy(bridge_processes)
        if upstream_proxy:
            env["CODEX_BRIDGE_UPSTREAM_PROXY"] = upstream_proxy

        log_path = self.paths.db.parent / "bridgedeck-local-bridge.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        python_bin = find_local_bridge_python()
        if not python_bin:
            return {
                **self.services(),
                "ok": False,
                "error": "未找到可运行 Local Codex Bridge 的 Python（缺少 httpx）",
            }
        with log_path.open("ab") as log:
            subprocess.Popen(
                [python_bin, str(script)],
                cwd=str(script.parent),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        for _ in range(30):
            if tcp_open("127.0.0.1", LOCAL_BRIDGE_PORT):
                return {**self.services(), "ok": True, "message": "Local Codex Bridge 已启动"}
            time.sleep(0.2)
        return {**self.services(), "ok": False, "error": f"Local Codex Bridge 启动超时，日志：{log_path}"}

    def _stop_local_bridge(self, *, force: bool = False) -> dict[str, Any]:
        processes = port_processes(LOCAL_BRIDGE_PORT)
        targets = [
            proc
            for proc in processes
            if "local_codex_bridge.py" in str(proc.get("command") or "")
        ]
        if not processes:
            return {**self.services(), "ok": True, "message": "Local Codex Bridge 未运行"}
        if not targets:
            return {**self.services(), "ok": False, "error": f"{LOCAL_BRIDGE_PORT} 端口被其它进程占用，未停止"}
        active_connections = port_active_connections(LOCAL_BRIDGE_PORT)
        if active_connections and not force:
            message = "检测到 8876 正在被客户端使用，未停止 Local Bridge"
            return {
                **self.services(),
                "ok": False,
                "requires_force": True,
                "message": message,
                "error": message,
                "active_connections": active_connections,
            }

        for proc in targets:
            try:
                os.kill(int(proc["pid"]), 15)
            except OSError:
                pass
        for _ in range(20):
            if not tcp_open("127.0.0.1", LOCAL_BRIDGE_PORT):
                return {**self.services(), "ok": True, "message": "Local Codex Bridge 已停止"}
            time.sleep(0.2)
        for proc in targets:
            try:
                os.kill(int(proc["pid"]), 9)
            except OSError:
                pass
        return {**self.services(), "ok": True, "message": "Local Codex Bridge 已强制停止"}

    def control_local_bridge(self, action: str, *, force: bool = False) -> dict[str, Any]:
        if action == "start":
            return self._start_local_bridge()
        if action == "stop":
            return self._stop_local_bridge(force=force)
        if action == "restart":
            stopped = self._stop_local_bridge(force=force)
            if not stopped.get("ok"):
                return stopped
            return self._start_local_bridge()
        raise ValueError("unknown local bridge action")

    def repair_quota_query(self) -> dict[str, Any]:
        actions: list[str] = []
        if not tcp_open("127.0.0.1", LOCAL_BRIDGE_PORT):
            started = self._start_local_bridge()
            actions.append(str(started.get("message") or started.get("error") or "start_local_bridge"))
            if not started.get("ok"):
                return {"ok": False, "actions": actions, "error": str(started.get("error") or "bridge start failed")}

        payload = self.quotas()
        quota_rows = payload.get("quotas", [])
        rows = quota_rows if isinstance(quota_rows, list) else []
        statuses = {str(item.get("quota_status") or "") for item in rows if isinstance(item, dict)}
        if rows and statuses and statuses <= {"network_error", "bridge_down", "unknown"}:
            actions.append("额度查询失败，未重启 Local Bridge")

        payload["actions"] = actions
        payload["services"] = self.services().get("services", {})
        return payload

    def _fetch_quota(self, account: dict[str, Any]) -> dict[str, Any]:
        account_id = str(account.get("account_id") or "")
        result: dict[str, Any] = {
            "account_id": account_id,
            "email": account.get("email") or "",
            "label": account.get("label") or "",
            "quota_status": "unknown",
            "plan_type": "",
            "allowed": False,
            "limit_reached": False,
            "windows": [],
            "error": "",
        }
        if not account_id:
            result["quota_status"] = "network_error"
            result["error"] = "missing account id"
            return result
        if not tcp_open("127.0.0.1", 8876):
            result["quota_status"] = "bridge_down"
            result["error"] = "local bridge is not running"
            return result

        url = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{urllib.parse.quote(account_id, safe='')}/quota"
        try:
            raw = read_local_url(url, timeout=18, max_bytes=512 * 1024)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", "replace")
            result["quota_status"] = classify_error_text(detail or str(exc))
            result["error"] = detail or str(exc)
            return result
        except Exception as exc:  # noqa: BLE001
            result["quota_status"] = classify_error_text(str(exc))
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

        try:
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("quota response is not an object")
        except Exception as exc:  # noqa: BLE001
            result["quota_status"] = "network_error"
            result["error"] = f"parse error: {exc}"
            return result

        result.update(summarize_quota_payload(payload))
        if isinstance(payload.get("email"), str) and payload.get("email"):
            result["email"] = payload["email"]
        return result

    def quotas(self) -> dict[str, Any]:
        accounts = self._load_accounts()
        return {"ok": True, "quotas": [self._fetch_quota(account) for account in accounts]}

    def missing_bridge_accounts(self, quotas: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        snapshot = self.snapshot(include_secrets=False)
        providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
        bridge_account_ids = {
            str(provider.get("account_id") or "")
            for provider in providers
            if self._is_bridge_provider(provider) and provider.get("account_id")
        }
        quota_rows = quotas if isinstance(quotas, list) else self.quotas().get("quotas", [])
        quota_by_account = {
            str(quota.get("account_id") or ""): quota
            for quota in quota_rows
            if isinstance(quota, dict) and quota.get("account_id")
        }
        missing: list[dict[str, Any]] = []
        for account in self._load_accounts():
            account_id = str(account.get("account_id") or "")
            if not account_id or account_id in bridge_account_ids:
                continue
            quota = quota_by_account.get(account_id, {})
            row = {
                "account_id": account_id,
                "email": quota.get("email") or account.get("email") or "",
                "label": account.get("label") or "",
                "plan_type": quota.get("plan_type") or "",
                "quota_status": quota.get("quota_status") or "unknown",
            }
            missing.append(row)
        missing.sort(key=lambda item: self._priority_rank(str(item.get("account_id") or ""), providers, item))
        return missing

    def create_missing_bridge_providers(self) -> dict[str, Any]:
        quotas_payload = self.quotas()
        quota_rows = quotas_payload.get("quotas", [])
        missing = self.missing_bridge_accounts(quota_rows if isinstance(quota_rows, list) else [])
        snapshot = self.snapshot(include_secrets=False)
        providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
        existing_names = {str(provider.get("name") or "") for provider in providers}
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        quota_by_account = {
            str(quota.get("account_id") or ""): quota
            for quota in (quota_rows if isinstance(quota_rows, list) else [])
            if isinstance(quota, dict) and quota.get("account_id")
        }
        for account in missing:
            account_id = str(account.get("account_id") or "")
            quota = quota_by_account.get(account_id, account)
            status = str(quota.get("quota_status") or "unknown")
            if status in {"refresh_token_reused", "unsupported_region", "bridge_down", "network_error"}:
                skipped.append({**account, "reason": status})
                continue
            provider_name = self._provider_name_for_quota(account_id, quota, existing_names)
            result = self.create_or_update_provider(account_id, provider_name, False)
            existing_names.add(provider_name)
            created.append({"account_id": account_id, "provider_name": provider_name, "result": result})
        return {"ok": True, "created": created, "skipped": skipped, "missing": missing}

    def update_auto_switch_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._save_auto_switch_config(payload)
        return {"ok": True, "auto_switch": self._load_auto_switch_config()}

    def _priority_rank(self, account_id: str, providers: list[dict[str, Any]], quota: dict[str, Any] | None = None) -> tuple[int, str]:
        names = " ".join(str(p.get("name") or "").lower() for p in providers if p.get("account_id") == account_id)
        plan_type = str((quota or {}).get("plan_type") or "").lower()
        # Provider names are user labels; prefer the quota payload plan whenever it exists.
        haystack = plan_type or names
        if "20x" in plan_type or "pro max" in plan_type or "promax" in plan_type or plan_type == "pro":
            return (0, haystack)
        if "pro_lite" in plan_type or "pro-lite" in plan_type or "pro lite" in plan_type or "prolite" in plan_type or "5x" in plan_type:
            return (1, haystack)
        if "plus" in plan_type:
            return (2, haystack)
        if "20x" in haystack or "pro max" in haystack or "promax" in haystack:
            return (0, haystack)
        if "5x" in haystack or "pro_lite" in haystack or "pro-lite" in haystack or "pro lite" in haystack or "prolite" in haystack:
            return (1, haystack)
        if "plus" in haystack:
            return (2, haystack)
        if "pro" in haystack:
            return (0, haystack)
        return (9, account_id)

    def _quota_capacity_factor(self, account_id: str, providers: list[dict[str, Any]], quota: dict[str, Any] | None = None) -> int:
        names = " ".join(str(p.get("name") or "").lower() for p in providers if p.get("account_id") == account_id)
        plan_type = str((quota or {}).get("plan_type") or "").lower()
        if plan_type:
            return quota_capacity_factor_from_text(plan_type)
        return quota_capacity_factor_from_text(names)

    def _quota_effective_remaining(self, account_id: str, providers: list[dict[str, Any]], quota: dict[str, Any]) -> float:
        return effective_remaining_units(
            quota.get("windows", []) if isinstance(quota.get("windows"), list) else [],
            self._quota_capacity_factor(account_id, providers, quota),
        )

    def _is_bridge_provider(self, provider: dict[str, Any] | None) -> bool:
        if not provider:
            return False
        base_url = str(provider.get("base_url") or "")
        return LOCAL_BRIDGE_BASE_URL in base_url and "/accounts/" in base_url

    def _provider_row_bridge_account_id(self, row: sqlite3.Row) -> str:
        settings = self._extract_json(row["settings_config"])
        env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        account_id = bridge_account_id_from_env(env)
        if account_id:
            return account_id
        meta = self._extract_json(row["meta"])
        binding = meta.get("authBinding")
        if isinstance(binding, dict) and isinstance(binding.get("accountId"), str):
            return binding["accountId"].strip()
        return ""

    def _select_existing_bridge_provider_for_account(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        *,
        app_type: str = "claude",
    ) -> sqlite3.Row | None:
        rows = conn.execute(
            """
            SELECT id, name, settings_config, meta, sort_index
            FROM providers
            WHERE app_type = ?
            ORDER BY
              CASE
                WHEN name = 'Local Codex Bridge - Plus' THEN 0
                WHEN name = 'Local Codex Bridge - Pro' THEN 1
                WHEN name = 'Local Codex Bridge - Pro 20x' THEN 2
                ELSE 9
              END,
              sort_index ASC,
              name ASC
            """,
            (app_type,),
        ).fetchall()
        for row in rows:
            if self._provider_row_bridge_account_id(row) == account_id:
                return row
        return None

    def _current_claude_provider(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        providers = snapshot.get("providers") if isinstance(snapshot.get("providers"), list) else []
        current_id = snapshot.get("current_provider_from_settings")
        for provider in providers:
            if isinstance(provider, dict) and current_id and provider.get("id") == current_id:
                return provider
        for provider in providers:
            if isinstance(provider, dict) and provider.get("is_current"):
                return provider
        return None

    def _best_quota_account(self, snapshot: dict[str, Any], quotas: list[dict[str, Any]]) -> dict[str, Any] | None:
        providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
        usable = [
            quota for quota in quotas
            if quota.get("quota_status") in {"ok", "near_limit"} and not quota.get("limit_reached")
        ]
        if not usable:
            return None
        usable.sort(
            key=lambda q: (
                -self._quota_effective_remaining(str(q.get("account_id") or ""), providers, q),
                self._priority_rank(str(q.get("account_id") or ""), providers, q),
            )
        )
        return usable[0]

    def _quota_is_still_usable(self, quota: dict[str, Any] | None) -> bool:
        if not quota:
            return False
        return quota.get("quota_status") in {"ok", "near_limit"} and not quota.get("limit_reached")

    def _account_for_id(self, account_id: str) -> dict[str, Any] | None:
        for account in self._load_accounts():
            if account.get("account_id") == account_id:
                return account
        return None

    def _provider_name_for_quota(self, account_id: str, quota: dict[str, Any], existing_names: set[str]) -> str:
        account = self._account_for_id(account_id) or {"account_id": account_id, "email": quota.get("email") or ""}
        plan = str(quota.get("plan_type") or "").strip().lower()
        suffix = ""
        if "20x" in plan or "pro max" in plan or "promax" in plan:
            suffix = "Pro 20x"
        elif "pro_lite" in plan or "pro-lite" in plan or "pro lite" in plan or "prolite" in plan or "5x" in plan:
            suffix = "Pro 5x"
        elif plan == "pro" or plan.startswith("pro_") or plan.startswith("pro-"):
            suffix = "Pro 20x"
        elif "plus" in plan:
            suffix = "Plus"
        if suffix:
            candidate = f"Local Codex Bridge - {suffix}"
            if candidate not in existing_names:
                return candidate
        return self._default_provider_name(account, existing_names)

    def run_auto_switch(self, *, force: bool = False) -> dict[str, Any]:
        config = self._load_auto_switch_config()
        if not force and not config["enabled"]:
            return {"ok": True, "enabled": False, "message": "自动切换未开启", "actions": []}

        snapshot = self.snapshot(include_secrets=False)
        quotas = self.quotas().get("quotas", [])
        quota_rows = quotas if isinstance(quotas, list) else []
        quota_by_account = {
            str(quota.get("account_id") or ""): quota
            for quota in quota_rows
            if isinstance(quota, dict) and quota.get("account_id")
        }
        best = self._best_quota_account(snapshot, quota_rows)
        actions: list[dict[str, Any]] = []
        if not best:
            result = {"ok": False, "enabled": config["enabled"], "message": "没有可用 OpenAI 账号", "actions": []}
            self._save_auto_switch_config({**config, "last_result": result})
            return result

        best_account_id = str(best.get("account_id") or "")
        providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
        target_provider = next((p for p in providers if p.get("account_id") == best_account_id and self._is_bridge_provider(p)), None)
        current_provider = self._current_claude_provider(snapshot)
        if config["claude"]:
            if self._is_bridge_provider(current_provider):
                current_account_id = str((current_provider or {}).get("account_id") or "")
                if current_account_id and self._quota_is_still_usable(quota_by_account.get(current_account_id)):
                    actions.append({"target": "claude", "changed": False, "reason": "current_account_still_usable"})
                elif not target_provider:
                    existing_names = {str(p.get("name") or "") for p in providers}
                    provider_name = self._provider_name_for_quota(best_account_id, best, existing_names)
                    created = self.create_or_update_provider(best_account_id, provider_name, False)
                    actions.append({"target": "claude_provider", "changed": True, "reason": "created_missing_provider", "result": created})
                    snapshot = self.snapshot(include_secrets=False)
                    providers = [p for p in snapshot.get("providers", []) if isinstance(p, dict)]
                    target_provider = next((p for p in providers if p.get("account_id") == best_account_id and self._is_bridge_provider(p)), None)
                    if target_provider and current_provider and target_provider.get("id") != current_provider.get("id"):
                        changed = self.set_current_provider(str(target_provider["id"]))
                        actions.append({"target": "claude", "changed": True, "provider_id": target_provider["id"], "result": changed})
                    else:
                        actions.append({"target": "claude", "changed": False, "reason": "missing_provider_after_create"})
                elif target_provider and current_provider and target_provider.get("id") != current_provider.get("id"):
                    changed = self.set_current_provider(str(target_provider["id"]))
                    actions.append({"target": "claude", "changed": True, "provider_id": target_provider["id"], "result": changed})
                else:
                    actions.append({"target": "claude", "changed": False, "reason": "already_best_or_missing_provider"})
            else:
                actions.append({"target": "claude", "changed": False, "reason": "current_provider_is_not_local_bridge"})

        desktop = snapshot.get("codex_desktop") if isinstance(snapshot.get("codex_desktop"), dict) else {}
        if config["default_codex"]:
            if desktop.get("managed_by") == "bridgedeck_or_local_bridge":
                current_codex_account_id = str(desktop.get("account_id") or "")
                if current_codex_account_id and self._quota_is_still_usable(quota_by_account.get(current_codex_account_id)):
                    actions.append({"target": "default_codex", "changed": False, "reason": "current_account_still_usable"})
                elif desktop.get("account_id") != best_account_id:
                    changed = self.set_default_codex_account(best_account_id)
                    actions.append({"target": "default_codex", "changed": True, "result": changed})
                else:
                    actions.append({"target": "default_codex", "changed": False, "reason": "already_best"})
            else:
                actions.append({"target": "default_codex", "changed": False, "reason": "default_codex_is_not_local_bridge"})

        result = {
            "ok": True,
            "enabled": config["enabled"],
            "selected_account_id": best_account_id,
            "selected_quota_status": best.get("quota_status"),
            "actions": actions,
        }
        self._save_auto_switch_config({**config, "last_result": result})
        return result

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

    def _build_usage_script(self, account_id: str) -> dict[str, Any]:
        quota_url = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{account_id}/quota"
        code = f"""({{
  request: {{
    url: "{quota_url}",
    method: "GET",
    headers: {{}}
  }},
  extractor: function(response) {{
    if (!response || response.error) {{
      return {{
        isValid: false,
        invalidMessage: response && (response.error || response.detail) || "quota query failed"
      }};
    }}
    var rate = response.rate_limit || {{}};
    var primary = rate.primary_window || {{}};
    var secondary = rate.secondary_window || {{}};
    var rows = [
      {{
        planName: "five_hour",
        used: Number(primary.used_percent || 0),
        total: 100,
        remaining: Math.max(0, 100 - Number(primary.used_percent || 0)),
        unit: "%",
        extra: primary.reset_after_seconds ? String(primary.reset_after_seconds) + "s" : undefined
      }},
      {{
        planName: "weekly_limit",
        used: Number(secondary.used_percent || 0),
        total: 100,
        remaining: Math.max(0, 100 - Number(secondary.used_percent || 0)),
        unit: "%",
        extra: secondary.reset_after_seconds ? String(secondary.reset_after_seconds) + "s" : undefined
      }}
    ];
    var extraLimits = Array.isArray(response.additional_rate_limits) ? response.additional_rate_limits : [];
    extraLimits.forEach(function(item) {{
      var limit = item && item.rate_limit || {{}};
      var win = limit.secondary_window || limit.primary_window || {{}};
      var used = Number(win.used_percent || 0);
      rows.push({{
        planName: item.limit_name || item.metered_feature || "extra_limit",
        used: used,
        total: 100,
        remaining: Math.max(0, 100 - used),
        unit: "%",
        extra: win.reset_after_seconds ? String(win.reset_after_seconds) + "s" : undefined
      }});
    }});
    return rows;
  }}
}})"""
        return {
            "enabled": True,
            "language": "javascript",
            "code": code,
            "timeout": 10,
            "templateType": "custom",
            "autoQueryInterval": 5,
            "bridgeDeckManaged": True,
        }

    def _build_provider_payload(
        self,
        account_id: str,
        *,
        settings_config: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        compact_config: dict[str, Any] | None = None,
        context_config: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
        clear_forced_model: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        settings = copy.deepcopy(settings_config) if isinstance(settings_config, dict) else {}
        if not isinstance(settings, dict):
            settings = {}
        env = settings.get("env")
        if not isinstance(env, dict):
            env = {}
        env["ANTHROPIC_BASE_URL"] = f"{LOCAL_BRIDGE_BASE_URL}/v1"
        env["ANTHROPIC_AUTH_TOKEN"] = "local-bridge"
        if clear_forced_model:
            clear_forced_bridge_model_from_env(env)
        if model_config is not None:
            apply_bridge_model_config_to_env(env, model_config)
        elif context_config is not None:
            apply_bridge_context_config_to_env(env, context_config)
        env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", "gpt-5.3-codex-spark")
        env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", "gpt-5.3-codex")
        env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "gpt-5.5")
        apply_bridge_safe_model_display_names(env)
        ensure_claude_attribution_default(env)
        normalize_provider_model_env(env)
        if compact_config is not None:
            apply_compact_config_to_env(env, compact_config)
        settings["env"] = env

        m = copy.deepcopy(meta) if isinstance(meta, dict) else {}
        if not isinstance(m, dict):
            m = {}
        # Keep Codex OAuth account binding so CC Switch can show quota for the card,
        # but do not mark the provider itself as codex_oauth. CC Switch routes that
        # provider type through its own ChatGPT transport and bypasses the local bridge.
        m.pop("providerType", None)
        m["apiFormat"] = "openai_responses"
        m["codexOauthTransport"] = "local_bridge"
        m["usage_script"] = self._build_usage_script(account_id)
        binding = m.get("authBinding")
        if not isinstance(binding, dict):
            binding = {}
        binding["source"] = "managed_account"
        binding["authProvider"] = "codex_oauth"
        binding["accountId"] = account_id
        m["authBinding"] = binding

        return settings, m

    def _build_desktop_provider_payload(
        self,
        account_id: str,
        *,
        settings_config: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        settings, m = self._build_provider_payload(
            account_id,
            settings_config=settings_config,
            meta=meta,
            clear_forced_model=False,
        )
        env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        normalized_meta, issues, _changed = normalize_claude_desktop_routes(m, env)
        return settings, normalized_meta, issues

    def _pick_template_provider(
        self,
        conn: sqlite3.Connection,
        *,
        app_type: str = "claude",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT settings_config, meta
            FROM providers
            WHERE app_type = ?
            ORDER BY
              CASE
                WHEN name = 'Local Codex Bridge - Pro' THEN 0
                WHEN name = 'Local Codex Bridge - Plus' THEN 1
                ELSE 9
              END,
              sort_index ASC
            LIMIT 1
            """,
            (app_type,),
        ).fetchall()
        if not rows:
            return {}, {}
        row = rows[0]
        return self._extract_json(row["settings_config"]), self._extract_json(row["meta"])

    def _attribution_source(
        self,
        *,
        source_id: str,
        label: str,
        path: str,
        value: Any,
        present: bool,
        scope: str,
        provider_id: str = "",
        provider_name: str = "",
    ) -> dict[str, Any]:
        status = attribution_env_status(value, source_present=present)
        return {
            "id": source_id,
            "label": label,
            "path": path,
            "scope": scope,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "present": present,
            "status": status,
            "value": "" if value is None else str(value),
        }

    def _json_env_file_attribution_source(self, path: Path, source_id: str, label: str) -> dict[str, Any]:
        if not path.exists():
            return self._attribution_source(
                source_id=source_id,
                label=label,
                path=str(path),
                value=None,
                present=False,
                scope="file",
            )
        if path.is_symlink():
            return {
                **self._attribution_source(
                    source_id=source_id,
                    label=label,
                    path=str(path),
                    value=None,
                    present=False,
                    scope="file",
                ),
                "error": "symlink_not_allowed",
            }
        try:
            payload = load_json(path, {})
            env = env_from_json_payload(payload)
            value = env.get(CLAUDE_CODE_ATTRIBUTION_HEADER_ENV)
            return self._attribution_source(
                source_id=source_id,
                label=label,
                path=str(path),
                value=value,
                present=True,
                scope="file",
            )
        except Exception as exc:  # noqa: BLE001
            return {
                **self._attribution_source(
                    source_id=source_id,
                    label=label,
                    path=str(path),
                    value=None,
                    present=False,
                    scope="file",
                ),
                "error": f"{type(exc).__name__}: {truncate_log_text(str(exc))}",
            }

    def claude_attribution_header_status(self) -> dict[str, Any]:
        sources: list[dict[str, Any]] = [
            self._json_env_file_attribution_source(
                DEFAULT_CLAUDE_SETTINGS_PATH,
                "claude_settings",
                "~/.claude/settings.json",
            ),
            self._json_env_file_attribution_source(
                DEFAULT_CCSWITCH_COMMON_CONFIG_PATH,
                "ccswitch_common_file",
                "~/.ccswitch-common-config.json",
            ),
        ]
        skipped_providers: list[dict[str, Any]] = []

        if self.paths.db.exists():
            try:
                with self._connect() as conn:
                    has_settings = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings'"
                    ).fetchone()
                    if has_settings:
                        row = conn.execute(
                            "SELECT value FROM settings WHERE key = 'common_config_claude'"
                        ).fetchone()
                        if row:
                            common = self._extract_json(row["value"])
                            env = env_from_json_payload(common)
                            sources.append(
                                self._attribution_source(
                                    source_id="ccswitch_common_db",
                                    label="CC Switch common_config_claude",
                                    path=str(self.paths.db),
                                    value=env.get(CLAUDE_CODE_ATTRIBUTION_HEADER_ENV),
                                    present=True,
                                    scope="db_common",
                                )
                            )
                        else:
                            sources.append(
                                self._attribution_source(
                                    source_id="ccswitch_common_db",
                                    label="CC Switch common_config_claude",
                                    path=str(self.paths.db),
                                    value=None,
                                    present=False,
                                    scope="db_common",
                                )
                            )

                    has_providers = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'providers'"
                    ).fetchone()
                    if has_providers:
                        rows = conn.execute(
                            """
                            SELECT id, name, settings_config, meta, app_type
                            FROM providers
                            WHERE app_type IN ('claude', 'claude-desktop')
                            ORDER BY sort_index ASC, name ASC
                            """
                        ).fetchall()
                        for row in rows:
                            settings = self._extract_json(row["settings_config"])
                            meta = self._extract_json(row["meta"])
                            env = env_from_json_payload(settings)
                            base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                            managed = base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/") or meta.get(
                                "codexOauthTransport"
                            ) == "local_bridge"
                            if not managed:
                                skipped_providers.append({
                                    "id": row["id"],
                                    "name": row["name"],
                                    "app_type": row["app_type"],
                                    "reason": "not_local_bridge",
                                })
                                continue
                            sources.append(
                                self._attribution_source(
                                    source_id=f"provider:{row['id']}",
                                    label=f"Provider: {row['name']}",
                                    path=str(self.paths.db),
                                    value=env.get(CLAUDE_CODE_ATTRIBUTION_HEADER_ENV),
                                    present=True,
                                    scope=f"provider:{row['app_type']}",
                                    provider_id=str(row["id"]),
                                    provider_name=str(row["name"]),
                                )
                            )
            except Exception as exc:  # noqa: BLE001
                sources.append(
                    {
                        **self._attribution_source(
                            source_id="ccswitch_db",
                            label="CC Switch DB",
                            path=str(self.paths.db),
                            value=None,
                            present=False,
                            scope="db",
                        ),
                        "error": f"{type(exc).__name__}: {truncate_log_text(str(exc))}",
                    }
                )
        else:
            sources.append(
                self._attribution_source(
                    source_id="ccswitch_db",
                    label="CC Switch DB",
                    path=str(self.paths.db),
                    value=None,
                    present=False,
                    scope="db",
                )
            )

        known = [item for item in sources if item.get("status") != "unknown"]
        has_disabled = any(item.get("status") == "disabled" for item in known)
        has_enabled = any(item.get("status") == "enabled" for item in known)
        if not known:
            status = "unknown"
            message = "未检测到 Claude Code 配置。"
        elif has_disabled and has_enabled:
            status = "inconsistent"
            message = "不同配置源对 CLAUDE_CODE_ATTRIBUTION_HEADER 设置不一致。"
        elif has_enabled:
            status = "enabled"
            message = "Claude Code billing attribution header 未关闭。"
        else:
            status = "disabled"
            message = "已关闭 Claude Code billing attribution header。"

        return {
            "ok": True,
            "status": status,
            "message": message,
            "env_key": CLAUDE_CODE_ATTRIBUTION_HEADER_ENV,
            "disabled_value": CLAUDE_CODE_ATTRIBUTION_DISABLED_VALUE,
            "sources": sources,
            "skipped_providers": skipped_providers,
            "disabled_count": sum(1 for item in sources if item.get("status") == "disabled"),
            "enabled_count": sum(1 for item in sources if item.get("status") == "enabled"),
            "unknown_count": sum(1 for item in sources if item.get("status") == "unknown"),
        }

    def snapshot(self, include_secrets: bool = False) -> dict[str, Any]:
        try:
            plugin_sync = self.sync_claude_enabled_plugins()
        except Exception as exc:  # noqa: BLE001
            plugin_sync = {"ok": False, "changed": False, "error": str(exc)}
        try:
            plugin_status = self.claude_plugin_sync_status()
        except Exception as exc:  # noqa: BLE001
            plugin_status = {"ok": False, "error": str(exc)}
        local_bridge_state = read_local_bridge_state()
        stream_diagnostics = self.stream_diagnostics()
        hook_risks = claude_hook_risk_status()
        data: dict[str, Any] = {
            "version": APP_VERSION,
            "paths": {
                "db": str(self.paths.db),
                "settings": str(self.paths.settings),
                "auth_store": str(self.paths.auth_store),
                "auto_switch": str(DEFAULT_AUTO_SWITCH_PATH),
                "aimami_follow": str(DEFAULT_AIMAMI_FOLLOW_PATH),
                "ccswitch_common_config": str(DEFAULT_CCSWITCH_COMMON_CONFIG_PATH),
                "claude_settings": str(DEFAULT_CLAUDE_SETTINGS_PATH),
                "claude_installed_plugins": str(DEFAULT_CLAUDE_INSTALLED_PLUGINS_PATH),
            },
            "exists": {
                "db": self.paths.db.exists(),
                "settings": self.paths.settings.exists(),
                "auth_store": self.paths.auth_store.exists(),
            },
            "accounts": self._load_accounts(),
            "providers": [],
            "claude_desktop_providers": [],
            "codex_providers": [],
            "cli_homes": self._known_cli_homes(),
            "cli_launchers": self._known_cli_launchers(),
            "codex_desktop": self._codex_desktop_status(),
            "current_codex_launcher": self._current_codex_launcher_status(),
            "omc_codex_shim": self._omc_codex_shim_status(),
            "usage_metrics": local_bridge_state.get("usage_metrics", {}),
            "usage_events": local_bridge_state.get("usage_events", []),
            "active_stream": local_bridge_state.get("active_stream", {}),
            "stream_diagnostics": stream_diagnostics,
            "claude_hook_risks": hook_risks,
            "account_matrix": [],
            "current_provider_from_settings": self._current_provider_from_settings(),
            "auto_switch": self._load_auto_switch_config(),
            "aimami_sync": self.aimami_import_preview(),
            "aimami_follow": self._load_aimami_follow_config(),
            "plugin_sync": plugin_sync,
            "plugin_status": plugin_status,
            "claude_attribution_header": self.claude_attribution_header_status(),
            "ccswitch_315": {},
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
            data["providers"] = self._list_surface_providers(conn, "claude_code", include_secrets=include_secrets)
            data["claude_desktop_providers"] = self._list_surface_providers(
                conn,
                "claude_desktop",
                include_secrets=include_secrets,
            )
            data["codex_providers"] = self._list_codex_providers(conn)
            data["ccswitch_315"] = self._ccswitch_315_status(
                data["providers"],
                data["claude_desktop_providers"],
                data["codex_providers"],
            )

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
        compact_config: dict[str, Any] | None = None,
        context_config: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
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
                existing = self._select_existing_bridge_provider_for_account(conn, account_id)
                if not existing:
                    existing = conn.execute(
                        "SELECT id, name, settings_config, meta FROM providers WHERE app_type = 'claude' AND name = ? LIMIT 1",
                        (provider_name,),
                    ).fetchone()
                if existing:
                    provider_id = str(existing["id"])
                    provider_name = str(existing["name"])
                    current_settings = self._extract_json(existing["settings_config"])
                    current_meta = self._extract_json(existing["meta"])
                else:
                    provider_id = str(uuid.uuid4())
                    template_settings, template_meta = self._pick_template_provider(conn)
                    current_settings = template_settings
                    current_meta = template_meta
                clear_forced_model = not existing and model_config is None

                new_settings, new_meta = self._build_provider_payload(
                    account_id,
                    settings_config=current_settings,
                    meta=current_meta,
                    compact_config=compact_config,
                    context_config=context_config,
                    model_config=model_config,
                    clear_forced_model=clear_forced_model,
                )
                settings_text = json.dumps(new_settings, ensure_ascii=False)
                meta_text = json.dumps(new_meta, ensure_ascii=False)

                if existing:
                    updates = {
                        "settings_config": settings_text,
                        "meta": meta_text,
                        "provider_type": None,
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
                        "provider_type": None,
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

    def create_or_update_desktop_provider(
        self,
        account_id: str,
        provider_name: str,
        set_current: bool = False,
    ) -> dict[str, Any]:
        if not account_id.strip():
            raise ValueError("account_id 不能为空")
        if not provider_name.strip():
            raise ValueError("provider_name 不能为空")

        account_ids = {item["account_id"] for item in self._load_accounts()}
        if account_id not in account_ids:
            raise ValueError(f"未找到账号: {account_id}")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "create-desktop-provider")
            with self._connect() as conn:
                columns = self._provider_columns(conn)
                existing = self._select_existing_bridge_provider_for_account(
                    conn,
                    account_id,
                    app_type="claude-desktop",
                )
                if not existing:
                    existing = conn.execute(
                        """
                        SELECT id, name, settings_config, meta, sort_index
                        FROM providers
                        WHERE app_type = 'claude-desktop' AND name = ? LIMIT 1
                        """,
                        (provider_name,),
                    ).fetchone()
                if existing:
                    provider_id = str(existing["id"])
                    provider_name = str(existing["name"])
                    current_settings = self._extract_json(existing["settings_config"])
                    current_meta = self._extract_json(existing["meta"])
                else:
                    provider_id = str(uuid.uuid4())
                    current_settings, current_meta = self._pick_template_provider(conn, app_type="claude-desktop")

                new_settings, new_meta, route_issues = self._build_desktop_provider_payload(
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
                        "provider_type": None,
                    }
                    assignments = []
                    values: list[Any] = []
                    for key, value in updates.items():
                        if key in columns:
                            assignments.append(f"{key} = ?")
                            values.append(value)
                    values.extend([provider_id, "claude-desktop"])
                    conn.execute(
                        f"UPDATE providers SET {', '.join(assignments)} WHERE id = ? AND app_type = ?",
                        values,
                    )
                else:
                    row = {
                        "id": provider_id,
                        "app_type": "claude-desktop",
                        "name": provider_name,
                        "settings_config": settings_text,
                        "meta": meta_text,
                        "provider_type": None,
                        "created_at": int(time.time()),
                        "sort_index": conn.execute(
                            "SELECT COALESCE(MAX(sort_index), 0) + 1 FROM providers WHERE app_type = 'claude-desktop'"
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
                if set_current and "is_current" in columns:
                    conn.execute("UPDATE providers SET is_current = 0 WHERE app_type = 'claude-desktop'")
                    conn.execute(
                        "UPDATE providers SET is_current = 1 WHERE app_type = 'claude-desktop' AND id = ?",
                        (provider_id,),
                    )
                conn.commit()

            return {
                "ok": True,
                "message": "Claude Desktop provider 已创建/更新",
                "provider_id": provider_id,
                "provider_name": provider_name,
                "set_current": set_current,
                "route_issues_fixed": route_issues,
                "backups": [db_bak],
            }

    def repair_ccswitch_315_desktop_routes(self, *, apply: bool = False) -> dict[str, Any]:
        with self._lock:
            if not self.paths.db.exists():
                return {"ok": True, "apply": apply, "plan": [], "updated": [], "backups": [], "message": "cc-switch 数据库不存在"}
            db_bak = self._backup_file(self.paths.db, "ccswitch-315-desktop-routes") if apply else None
            updated: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            conn = self._connect()
            try:
                columns = self._provider_columns(conn)
                if "settings_config" not in columns or "meta" not in columns:
                    raise RuntimeError("providers 表缺少 settings_config/meta 字段")
                rows = conn.execute(
                    """
                    SELECT id, app_type, name, provider_type, is_current, sort_index, settings_config, meta
                    FROM providers
                    WHERE app_type = 'claude-desktop'
                    ORDER BY sort_index ASC, name ASC
                    """
                ).fetchall()
                plan: list[dict[str, Any]] = []
                for row in rows:
                    settings = self._extract_json(row["settings_config"])
                    meta = self._extract_json(row["meta"])
                    env = env_from_json_payload(settings)
                    base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                    account_id = self._provider_row_bridge_account_id(row)
                    managed = base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/") or meta.get(
                        "codexOauthTransport"
                    ) == "local_bridge"
                    if not managed or not account_id:
                        skipped.append({"id": row["id"], "name": row["name"], "reason": "not_local_bridge"})
                        continue
                    next_settings, next_meta, issues = self._build_desktop_provider_payload(
                        account_id,
                        settings_config=settings,
                        meta=meta,
                    )
                    before = json.dumps({"settings": settings, "meta": meta}, ensure_ascii=False, sort_keys=True)
                    after = json.dumps({"settings": next_settings, "meta": next_meta}, ensure_ascii=False, sort_keys=True)
                    changed = before != after
                    item = {
                        "id": row["id"],
                        "name": row["name"],
                        "account_id": account_id,
                        "changed": changed,
                        "issues": issues,
                        "expected_routes": next_meta.get("claudeDesktopModelRoutes", {}),
                    }
                    plan.append(item)
                    if apply and changed:
                        conn.execute(
                            "UPDATE providers SET settings_config = ?, meta = ? WHERE id = ? AND app_type = ?",
                            (
                                json.dumps(next_settings, ensure_ascii=False),
                                json.dumps(next_meta, ensure_ascii=False),
                                row["id"],
                                "claude-desktop",
                            ),
                        )
                        updated.append({"id": row["id"], "name": row["name"]})
                if apply and updated:
                    conn.commit()
            finally:
                conn.close()

            return {
                "ok": True,
                "apply": apply,
                "message": "Claude Desktop 3.15 路由修复完成" if apply else "Claude Desktop 3.15 路由修复预览",
                "plan": plan,
                "updated": updated,
                "skipped": skipped,
                "backups": [db_bak] if db_bak else [],
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
                    "provider_type": None,
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

    def update_provider_compact(
        self,
        provider_id: str,
        compact_config: dict[str, Any] | None,
        context_config: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not provider_id.strip():
            raise ValueError("provider_id 不能为空")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "provider-compact")
            with self._connect() as conn:
                columns = self._provider_columns(conn)
                row = conn.execute(
                    "SELECT id, settings_config FROM providers WHERE app_type = 'claude' AND id = ? LIMIT 1",
                    (provider_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"provider 不存在: {provider_id}")
                if "settings_config" not in columns:
                    raise RuntimeError("providers 表缺少 settings_config 字段")

                settings = self._extract_json(row["settings_config"])
                env = settings.get("env")
                if not isinstance(env, dict):
                    env = {}
                base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                if not base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/"):
                    raise ValueError("仅支持 Local Codex Bridge provider")
                normalized_context = (
                    apply_bridge_context_config_to_env(env, context_config)
                    if context_config is not None
                    else None
                )
                normalized = apply_compact_config_to_env(env, compact_config)
                settings["env"] = env
                conn.execute(
                    "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = ?",
                    (json.dumps(settings, ensure_ascii=False), provider_id, "claude"),
                )
                conn.commit()

            return {
                "ok": True,
                "message": "上下文配置已保存",
                "provider_id": provider_id,
                "compact_config": normalized,
                "context_config": normalized_context,
                "backups": [db_bak],
            }

    def update_provider_forced_model(
        self,
        provider_id: str,
        model_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not provider_id.strip():
            raise ValueError("provider_id 不能为空")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "provider-model")
            with self._connect() as conn:
                columns = self._provider_columns(conn)
                row = conn.execute(
                    "SELECT id, settings_config FROM providers WHERE app_type = 'claude' AND id = ? LIMIT 1",
                    (provider_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"provider 不存在: {provider_id}")
                if "settings_config" not in columns:
                    raise RuntimeError("providers 表缺少 settings_config 字段")

                settings = self._extract_json(row["settings_config"])
                env = settings.get("env")
                if not isinstance(env, dict):
                    env = {}
                base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                if not base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/"):
                    raise ValueError("仅支持 Local Codex Bridge provider")
                normalized_model = apply_bridge_model_config_to_env(env, model_config)
                settings["env"] = env
                conn.execute(
                    "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = ?",
                    (json.dumps(settings, ensure_ascii=False), provider_id, "claude"),
                )
                conn.commit()

            return {
                "ok": True,
                "message": "强制主模型已保存",
                "provider_id": provider_id,
                "model_config": normalized_model,
                "backups": [db_bak],
            }

    def clear_provider_forced_model(self, provider_id: str, *, apply: bool = False) -> dict[str, Any]:
        if not provider_id.strip():
            raise ValueError("provider_id 不能为空")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "provider-routing") if apply else None
            with self._connect() as conn:
                columns = self._provider_columns(conn)
                row = conn.execute(
                    "SELECT id, settings_config FROM providers WHERE app_type = 'claude' AND id = ? LIMIT 1",
                    (provider_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"provider 不存在: {provider_id}")
                if "settings_config" not in columns:
                    raise RuntimeError("providers 表缺少 settings_config 字段")

                settings = self._extract_json(row["settings_config"])
                env = settings.get("env")
                if not isinstance(env, dict):
                    env = {}
                base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                if not base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/"):
                    raise ValueError("仅支持 Local Codex Bridge provider")
                removed_model = env.get("ANTHROPIC_MODEL") if isinstance(env.get("ANTHROPIC_MODEL"), str) else ""
                changed = bool(removed_model)
                if apply and changed:
                    clear_forced_bridge_model_from_env(env)
                    settings["env"] = env
                    conn.execute(
                        "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = ?",
                        (json.dumps(settings, ensure_ascii=False), provider_id, "claude"),
                    )
                    conn.commit()

            return {
                "ok": True,
                "message": "已改为 Claude 自动路由" if apply and changed else "Claude 自动路由预览",
                "provider_id": provider_id,
                "apply": apply,
                "changed": changed,
                "removed_model": removed_model,
                "backups": [db_bak] if db_bak else [],
            }

    def sync_common_env_to_bridge_providers(self, provider_id: str) -> dict[str, Any]:
        if not provider_id.strip():
            raise ValueError("provider_id 不能为空")

        with self._lock:
            db_bak = self._backup_file(self.paths.db, "sync-common-env")
            conn = self._connect()
            try:
                columns = self._provider_columns(conn)
                if "settings_config" not in columns:
                    raise RuntimeError("providers 表缺少 settings_config 字段")

                source = conn.execute(
                    """
                    SELECT id, name, settings_config
                    FROM providers
                    WHERE app_type = 'claude' AND id = ? LIMIT 1
                    """,
                    (provider_id,),
                ).fetchone()
                if not source:
                    raise ValueError(f"provider 不存在: {provider_id}")

                source_settings = self._extract_json(source["settings_config"])
                source_env = source_settings.get("env")
                if not isinstance(source_env, dict):
                    source_env = {}
                source_base_url = str(source_env.get("ANTHROPIC_BASE_URL") or "")
                if not source_base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/"):
                    raise ValueError("仅支持 Local Codex Bridge provider")

                common_env = common_provider_env(source_env)
                rows = conn.execute(
                    """
                    SELECT id, name, settings_config
                    FROM providers
                    WHERE app_type = 'claude'
                    ORDER BY sort_index ASC, name ASC
                    """
                ).fetchall()

                updated: list[dict[str, Any]] = []
                skipped: list[dict[str, Any]] = []
                for row in rows:
                    settings = self._extract_json(row["settings_config"])
                    env = settings.get("env")
                    if not isinstance(env, dict):
                        env = {}
                    base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                    if not base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/"):
                        skipped.append({"id": row["id"], "name": row["name"], "reason": "not_local_bridge"})
                        continue

                    auth_token = env.get("ANTHROPIC_AUTH_TOKEN")
                    before = json.dumps(settings, ensure_ascii=False, sort_keys=True)
                    merged = copy.deepcopy(env)
                    merged.update(copy.deepcopy(common_env))
                    merged["ANTHROPIC_BASE_URL"] = base_url
                    if isinstance(auth_token, str):
                        merged["ANTHROPIC_AUTH_TOKEN"] = auth_token
                    normalize_provider_model_env(merged)
                    settings["env"] = merged
                    after = json.dumps(settings, ensure_ascii=False, sort_keys=True)
                    if after == before:
                        skipped.append({"id": row["id"], "name": row["name"], "reason": "unchanged"})
                        continue

                    conn.execute(
                        "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = ?",
                        (json.dumps(settings, ensure_ascii=False), row["id"], "claude"),
                    )
                    updated.append({"id": row["id"], "name": row["name"]})

                conn.commit()
            finally:
                conn.close()

            return {
                "ok": True,
                "message": "通用 env 已同步",
                "source_provider_id": provider_id,
                "env_keys": sorted(common_env.keys()),
                "updated": updated,
                "skipped": skipped,
                "backups": [db_bak],
            }

    def _canonical_bridge_name_rank(self, name: str) -> int:
        try:
            return CANONICAL_BRIDGE_NAMES.index(name)
        except ValueError:
            return len(CANONICAL_BRIDGE_NAMES) + 1

    def _bridge_provider_duplicate_plan(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, name, is_current, sort_index, settings_config, meta
            FROM providers
            WHERE app_type = 'claude'
            ORDER BY sort_index ASC, name ASC
            """
        ).fetchall()
        current_id = self._current_provider_from_settings()
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            settings = self._extract_json(row["settings_config"])
            env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
            account_id = bridge_account_id_from_env(env)
            if not account_id:
                continue
            groups.setdefault(account_id, []).append(
                {
                    "id": str(row["id"]),
                    "name": str(row["name"] or ""),
                    "account_id": account_id,
                    "is_current": bool(row["is_current"]),
                    "sort_index": int(row["sort_index"] or 0),
                    "settings": settings,
                    "env": env,
                }
            )

        plan: list[dict[str, Any]] = []
        for account_id, group in groups.items():
            if len(group) < 2:
                continue
            canonical = [item for item in group if item["name"] in CANONICAL_BRIDGE_NAMES]
            if canonical:
                current_canonical = [item for item in canonical if item["id"] == current_id or item["is_current"]]
                keep = (current_canonical or sorted(canonical, key=lambda item: (self._canonical_bridge_name_rank(item["name"]), item["sort_index"], item["name"])))[0]
            else:
                current = [item for item in group if item["id"] == current_id or item["is_current"]]
                keep = (current or sorted(group, key=lambda item: (item["sort_index"], item["name"])))[0]
            to_delete = [item for item in group if item["id"] != keep["id"]]
            if not to_delete:
                continue
            active_deleted = [item for item in to_delete if item["id"] == current_id or item["is_current"]]
            plan.append(
                {
                    "account_id": account_id,
                    "keep": {"id": keep["id"], "name": keep["name"]},
                    "delete": [{"id": item["id"], "name": item["name"]} for item in to_delete],
                    "switch_current_to": keep["id"] if active_deleted else "",
                    "_keep": keep,
                    "_delete": to_delete,
                }
            )
        return plan

    def dedupe_bridge_providers(self, *, apply: bool = False) -> dict[str, Any]:
        with self._lock:
            if not self.paths.db.exists():
                return {"ok": True, "message": "cc-switch 数据库不存在", "apply": apply, "plan": [], "deleted": [], "backups": []}

            db_bak = self._backup_file(self.paths.db, "dedupe-bridge-providers") if apply else None
            settings_bak = self._backup_file(self.paths.settings, "dedupe-bridge-providers") if apply else None
            switch_current_to = ""
            deleted: list[dict[str, Any]] = []
            updated: list[dict[str, Any]] = []
            conn = self._connect()
            try:
                columns = self._provider_columns(conn)
                if "settings_config" not in columns:
                    raise RuntimeError("providers 表缺少 settings_config 字段")
                plan = self._bridge_provider_duplicate_plan(conn)
                public_plan = [
                    {
                        "account_id": item["account_id"],
                        "keep": item["keep"],
                        "delete": item["delete"],
                        "switch_current_to": item["switch_current_to"],
                    }
                    for item in plan
                ]
                if not apply:
                    return {"ok": True, "message": "重复 provider 预览", "apply": False, "plan": public_plan, "deleted": [], "backups": []}

                for item in plan:
                    keep = item["_keep"]
                    to_delete = item["_delete"]
                    keep_env = keep["env"]
                    keep_base_url = keep_env.get("ANTHROPIC_BASE_URL")
                    keep_auth_token = keep_env.get("ANTHROPIC_AUTH_TOKEN")
                    merged_common = common_provider_env(keep_env)
                    for duplicate in to_delete:
                        for key, value in common_provider_env(duplicate["env"]).items():
                            merged_common.setdefault(key, value)
                    for duplicate in to_delete:
                        if duplicate["id"] == self._current_provider_from_settings() or duplicate["is_current"]:
                            merged_common.update(common_provider_env(duplicate["env"]))
                            for key in (
                                *MODEL_ENV_KEYS,
                                COMPACT_WINDOW_ENV,
                                COMPACT_THRESHOLD_ENV,
                                MAX_CONTEXT_TOKENS_ENV,
                            ):
                                if key in duplicate["env"]:
                                    merged_common[key] = copy.deepcopy(duplicate["env"][key])

                    merged_env = copy.deepcopy(keep_env)
                    merged_env.update(merged_common)
                    if isinstance(keep_base_url, str):
                        merged_env["ANTHROPIC_BASE_URL"] = keep_base_url
                    if isinstance(keep_auth_token, str):
                        merged_env["ANTHROPIC_AUTH_TOKEN"] = keep_auth_token
                    normalize_provider_model_env(merged_env)
                    keep_settings = copy.deepcopy(keep["settings"])
                    keep_settings["env"] = merged_env
                    conn.execute(
                        "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = ?",
                        (json.dumps(keep_settings, ensure_ascii=False), keep["id"], "claude"),
                    )
                    updated.append(item["keep"])

                    delete_ids = [duplicate["id"] for duplicate in to_delete]
                    placeholders = ", ".join(["?"] * len(delete_ids))
                    conn.execute(
                        f"DELETE FROM providers WHERE app_type = ? AND id IN ({placeholders})",
                        ["claude", *delete_ids],
                    )
                    deleted.extend(item["delete"])
                    if item["switch_current_to"]:
                        switch_current_to = str(item["switch_current_to"])

                if switch_current_to and "is_current" in columns:
                    conn.execute("UPDATE providers SET is_current = 0 WHERE app_type = 'claude'")
                    conn.execute(
                        "UPDATE providers SET is_current = 1 WHERE app_type = 'claude' AND id = ?",
                        (switch_current_to,),
                    )
                conn.commit()
            finally:
                conn.close()

            if switch_current_to:
                self._set_current_provider_in_settings(switch_current_to)

            return {
                "ok": True,
                "message": "重复 Local Bridge provider 已清理",
                "apply": True,
                "plan": public_plan,
                "deleted": deleted,
                "updated": updated,
                "switch_current_to": switch_current_to,
                "backups": [db_bak, settings_bak],
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
                        "provider_type": None,
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
            codex_bin = codex_binary_path()
            base_url = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{account_id}/v1"
            config_arg = f'base_url="{base_url}"'
            write_executable_file(
                launcher_path,
                "#!/bin/zsh\n"
                f"export CODEX_HOME={json.dumps(str(target))}\n"
                'export OPENAI_API_KEY="local-bridge"\n'
                f"exec {json.dumps(codex_bin)} -c '{config_arg}' \"$@\"\n",
            )

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

    def write_current_codex_launcher(self, account_id: str) -> dict[str, Any]:
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("account_id 不能为空")
        store = self._load_auth_store_raw()
        accounts = store.get("accounts")
        if not isinstance(accounts, dict):
            raise ValueError("auth store 缺少 accounts")
        account_payload = accounts.get(account_id)
        if not isinstance(account_payload, dict):
            raise ValueError(f"未找到账号: {account_id}")

        launcher_path = current_codex_launcher_path()
        base_url = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{account_id}/v1"
        config_arg = f'base_url="{base_url}"'
        write_executable_file(
            launcher_path,
            "#!/bin/zsh\n"
            'export OPENAI_API_KEY="local-bridge"\n'
            f"exec {json.dumps(codex_binary_path())} -c '{config_arg}' \"$@\"\n",
        )
        return {
            "ok": True,
            "account_id": account_id,
            "email": account_payload.get("email", ""),
            "launcher": str(launcher_path),
            "run_command": str(launcher_path),
            "base_url": base_url,
            "launcher_only": True,
        }

    def write_omc_codex_shims(self) -> dict[str, Any]:
        current_launcher = current_codex_launcher_path()
        if not current_launcher.exists():
            raise ValueError("codex-current.command 不存在")
        body = (
            "#!/bin/zsh\n"
            f"# {MANAGED_CODEX_SHIM_MARKER}\n"
            f"exec {json.dumps(str(current_launcher))} \"$@\"\n"
        )
        written: list[str] = []
        for shim_path in DEFAULT_OMC_CODEX_SHIM_PATHS:
            if shim_path.exists() or shim_path.is_symlink():
                try:
                    existing = shim_path.read_text(encoding="utf-8") if shim_path.is_file() and not shim_path.is_symlink() else ""
                except Exception:
                    existing = ""
                if MANAGED_CODEX_SHIM_MARKER not in existing:
                    raise ValueError(f"OMC/tmux codex 包装器已存在且不是 BridgeDeck 管理: {shim_path}")
            write_executable_file(shim_path, body)
            written.append(str(shim_path))
        return {"ok": True, "paths": written, "target": str(current_launcher)}

    def ensure_omc_codex_path(self) -> dict[str, Any]:
        profile = DEFAULT_ZPROFILE_PATH
        if profile.is_symlink():
            raise ValueError("~/.zprofile 不能是符号链接")
        shim_dir = DEFAULT_CLI_LAUNCHER_DIR / "bin"
        block = (
            f"{MANAGED_CODEX_PATH_START}\n"
            f'export PATH="{shim_dir}:$PATH"\n'
            f"{MANAGED_CODEX_PATH_END}"
        )
        original = profile.read_text(encoding="utf-8") if profile.exists() else ""
        pattern = re.compile(
            rf"{re.escape(MANAGED_CODEX_PATH_START)}.*?{re.escape(MANAGED_CODEX_PATH_END)}",
            re.DOTALL,
        )
        if pattern.search(original):
            updated = pattern.sub(block, original, count=1)
        else:
            updated = f"{original.rstrip()}\n\n{block}\n" if original.strip() else f"{block}\n"
        backup = None
        if updated != original:
            backup = self._backup_file(profile, "codex-shim-path") if profile.exists() else None
            write_private_text_file(profile, updated)
        return {
            "ok": True,
            "profile": str(profile),
            "shim_dir": str(shim_dir),
            "changed": updated != original,
            "backup": backup,
        }

    def set_default_codex_account(self, account_id: str) -> dict[str, Any]:
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("account_id 不能为空")
        with self._lock:
            store = self._load_auth_store_raw()
            accounts = store.get("accounts")
            if not isinstance(accounts, dict):
                raise ValueError("auth store 缺少 accounts")
            account_payload = accounts.get(account_id)
            if not isinstance(account_payload, dict):
                raise ValueError(f"未找到账号: {account_id}")

            current_launcher = self.write_current_codex_launcher(account_id)
            omc_shims = self.write_omc_codex_shims()
            omc_path = self.ensure_omc_codex_path()
            return {
                "ok": True,
                "message": "全局 Codex CLI 固定入口已设置",
                "account_id": account_id,
                "email": account_payload.get("email", ""),
                "config_path": str(DEFAULT_CODEX_HOME / "config.toml"),
                "current_launcher": current_launcher["launcher"],
                "omc_codex_shims": omc_shims["paths"],
                "omc_codex_path": omc_path,
                "base_url": current_launcher["base_url"],
                "affected": ["codex-current.command", "OMC/tmux codex"],
                "desktop_affected": False,
                "removed_env_keys": [],
                "backups": [item for item in (omc_path.get("backup"),) if item],
            }

    def enable_codex_desktop_bridge_mode(self, account_id: str) -> dict[str, Any]:
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("account_id 不能为空")
        return {
            "ok": False,
            "changed": False,
            "message": CODEX_DESKTOP_BRIDGE_DISABLED_MESSAGE,
            "blocked_reason": CODEX_DESKTOP_BRIDGE_DISABLED_REASON,
            "account_id": account_id,
            "config_path": str(DEFAULT_CODEX_HOME / "config.toml"),
            "restart_required": False,
        }

    def restore_codex_desktop_native_mode(self) -> dict[str, Any]:
        with self._lock:
            config_path = DEFAULT_CODEX_HOME / "config.toml"
            if config_path.is_symlink():
                raise ValueError("~/.codex/config.toml 不能是符号链接")
            if not config_path.exists():
                return {
                    "ok": True,
                    "changed": False,
                    "message": "Codex Desktop 已是原生配置",
                    "config_path": str(config_path),
                    "backup": None,
                    "removed": [],
                }
            original = config_path.read_text(encoding="utf-8")
            updated, stripped_managed = strip_managed_codex_desktop_bridge(original)
            updated, stripped_legacy_keys = strip_legacy_bridgedeck_provider_config(updated, remove_static_keys=False)
            removed = [*stripped_legacy_keys]
            if stripped_managed:
                removed.append("managed_bridge_block")
            if updated == original:
                return {
                    "ok": True,
                    "changed": False,
                    "message": "Codex Desktop 已是原生配置",
                    "config_path": str(config_path),
                    "backup": None,
                    "removed": [],
                }
            backup = self._backup_file(config_path, "codex-desktop-native-mode")
            write_private_text_file(config_path, updated)
            return {
                "ok": True,
                "changed": True,
                "message": "已恢复 Codex Desktop 原生配置",
                "config_path": str(config_path),
                "backup": backup,
                "removed": sorted(set(removed)),
                "restart_required": True,
            }

    def _repair_attribution_json_file(self, path: Path, label: str) -> dict[str, Any]:
        result: dict[str, Any] = {"label": label, "path": str(path), "changed": False, "backup": None}
        try:
            if path.is_symlink():
                result.update({"ok": False, "error": "symlink_not_allowed"})
                return result
            payload = load_json(path, {}) if path.exists() else {}
            if not isinstance(payload, dict):
                payload = {}
            env = payload.get("env")
            if not isinstance(env, dict):
                env = {}
            before = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            ensure_claude_attribution_default(env, force=True)
            payload["env"] = env
            after = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if before == after:
                result["ok"] = True
                result["already_correct"] = True
                return result
            backup = self._backup_file(path, "claude-attribution-header") if path.exists() else None
            dump_json(path, payload)
            result.update({"ok": True, "changed": True, "backup": backup})
            return result
        except Exception as exc:  # noqa: BLE001
            result.update({"ok": False, "error": f"{type(exc).__name__}: {truncate_log_text(str(exc))}"})
            return result

    def repair_claude_attribution_header(self) -> dict[str, Any]:
        with self._lock:
            file_results = [
                self._repair_attribution_json_file(DEFAULT_CLAUDE_SETTINGS_PATH, "~/.claude/settings.json"),
                self._repair_attribution_json_file(
                    DEFAULT_CCSWITCH_COMMON_CONFIG_PATH,
                    "~/.ccswitch-common-config.json",
                ),
            ]
            db_backup: str | None = None
            db_changed = False
            updated_providers: list[dict[str, Any]] = []
            already_correct_providers: list[dict[str, Any]] = []
            skipped_providers: list[dict[str, Any]] = []
            db_common_changed = False
            db_common_already_correct = False
            db_errors: list[str] = []

            if self.paths.db.exists():
                try:
                    conn = self._connect()
                    try:
                        has_settings = conn.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings'"
                        ).fetchone()
                        if has_settings:
                            row = conn.execute(
                                "SELECT value FROM settings WHERE key = 'common_config_claude'"
                            ).fetchone()
                            common = self._extract_json(row["value"]) if row else {}
                            if not isinstance(common, dict):
                                common = {}
                            env = common.get("env")
                            if not isinstance(env, dict):
                                env = {}
                            before = json.dumps(common, ensure_ascii=False, sort_keys=True)
                            ensure_claude_attribution_default(env, force=True)
                            common["env"] = env
                            after = json.dumps(common, ensure_ascii=False, sort_keys=True)
                            if before == after:
                                db_common_already_correct = True
                            else:
                                if not db_backup:
                                    db_backup = self._backup_file(self.paths.db, "claude-attribution-header")
                                conn.execute(
                                    """
                                    INSERT INTO settings (key, value)
                                    VALUES ('common_config_claude', ?)
                                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                                    """,
                                    (json.dumps(common, ensure_ascii=False),),
                                )
                                db_changed = True
                                db_common_changed = True

                        has_providers = conn.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'providers'"
                        ).fetchone()
                        if has_providers:
                            columns = self._provider_columns(conn)
                            if "settings_config" in columns:
                                rows = conn.execute(
                                    """
                                    SELECT id, name, settings_config, meta, app_type
                                    FROM providers
                                    WHERE app_type IN ('claude', 'claude-desktop')
                                    ORDER BY sort_index ASC, name ASC
                                    """
                                ).fetchall()
                                for row in rows:
                                    settings = self._extract_json(row["settings_config"])
                                    meta = self._extract_json(row["meta"])
                                    env = env_from_json_payload(settings)
                                    base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
                                    managed = base_url.startswith(f"{LOCAL_BRIDGE_BASE_URL}/accounts/") or meta.get(
                                        "codexOauthTransport"
                                    ) == "local_bridge"
                                    if not managed:
                                        skipped_providers.append({
                                            "id": row["id"],
                                            "name": row["name"],
                                            "app_type": row["app_type"],
                                            "reason": "not_local_bridge",
                                        })
                                        continue
                                    before = json.dumps(settings, ensure_ascii=False, sort_keys=True)
                                    env = copy.deepcopy(env)
                                    ensure_claude_attribution_default(env, force=True)
                                    settings["env"] = env
                                    after = json.dumps(settings, ensure_ascii=False, sort_keys=True)
                                    if before == after:
                                        already_correct_providers.append({"id": row["id"], "name": row["name"]})
                                        continue
                                    if not db_backup:
                                        db_backup = self._backup_file(self.paths.db, "claude-attribution-header")
                                    conn.execute(
                                        "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = ?",
                                        (json.dumps(settings, ensure_ascii=False), row["id"], row["app_type"]),
                                    )
                                    updated_providers.append({"id": row["id"], "name": row["name"], "app_type": row["app_type"]})
                                    db_changed = True
                        if db_changed:
                            conn.commit()
                    finally:
                        conn.close()
                except Exception as exc:  # noqa: BLE001
                    db_errors.append(f"{type(exc).__name__}: {truncate_log_text(str(exc))}")

            status = self.claude_attribution_header_status()
            return {
                "ok": not db_errors and all(item.get("ok", True) for item in file_results),
                "message": "Claude Code Attribution Header 修复完成",
                "changed": any(item.get("changed") for item in file_results) or db_changed,
                "files": file_results,
                "db_common": {
                    "changed": db_common_changed,
                    "already_correct": db_common_already_correct,
                    "path": str(self.paths.db),
                },
                "updated_providers": updated_providers,
                "already_correct_providers": already_correct_providers,
                "skipped_providers": skipped_providers,
                "errors": db_errors + [str(item.get("error")) for item in file_results if item.get("error")],
                "backups": [item for item in [*(r.get("backup") for r in file_results), db_backup] if item],
                "restart_required": True,
                "restart_message": "重新打开 Claude Code 或新终端后，所有启动路径会读取新的 env。",
                "status": status,
            }

    def repair_codex_environment_conflicts(self) -> dict[str, Any]:
        config_path = DEFAULT_CODEX_HOME / "config.toml"
        if config_path.is_symlink():
            raise ValueError("~/.codex/config.toml 不能是符号链接")
        if not config_path.exists():
            return {
                "ok": True,
                "changed": False,
                "message": "未发现 Codex 环境冲突",
                "config_path": str(config_path),
                "removed_env_keys": [],
                "backup": None,
            }
        original = config_path.read_text(encoding="utf-8")
        updated, removed_env_keys = strip_toml_section_keys(
            original,
            "shell_environment_policy.set",
            CODEX_GLOBAL_ENV_CONFLICT_KEYS,
        )
        if updated == original:
            return {
                "ok": True,
                "changed": False,
                "message": "未发现 Codex 环境冲突",
                "config_path": str(config_path),
                "removed_env_keys": [],
                "backup": None,
            }
        backup = self._backup_file(config_path, "codex-env-conflict")
        write_private_text_file(config_path, updated)
        return {
            "ok": True,
            "changed": True,
            "message": "已清理 Codex 环境冲突",
            "config_path": str(config_path),
            "removed_env_keys": removed_env_keys,
            "backup": backup,
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


def quota_window_name(seconds: Any) -> str:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return "unknown"
    if value == 18_000:
        return "5小时"
    if value == 604_800:
        return "7天"
    if value % 86_400 == 0:
        return f"{value // 86_400}天"
    if value % 3_600 == 0:
        return f"{value // 3_600}小时"
    return f"{value}s"


def summarize_rate_limit_windows(rate_limit: dict[str, Any]) -> tuple[list[dict[str, Any]], float, bool]:
    windows: list[dict[str, Any]] = []
    max_used = 0.0
    for key in ("primary_window", "secondary_window"):
        window = rate_limit.get(key) if isinstance(rate_limit.get(key), dict) else {}
        used_raw = window.get("used_percent")
        try:
            used = float(used_raw)
        except (TypeError, ValueError):
            continue
        max_used = max(max_used, used)
        window_seconds = window.get("limit_window_seconds")
        windows.append(
            {
                "name": quota_window_name(window_seconds),
                "used_percent": int(used) if used.is_integer() else round(used, 1),
                "reset_after_seconds": window.get("reset_after_seconds"),
                "reset_at": window.get("reset_at"),
            }
        )
    return windows, max_used, bool(rate_limit.get("limit_reached"))


def quota_capacity_factor_from_text(*values: Any) -> int:
    parts = [str(value or "").lower().strip() for value in values if str(value or "").strip()]
    plan_type = parts[0] if parts else ""
    haystack = " ".join(parts)
    if "20x" in plan_type or "pro max" in plan_type or "promax" in plan_type:
        return 20
    if "pro_lite" in plan_type or "pro-lite" in plan_type or "pro lite" in plan_type or "prolite" in plan_type or "5x" in plan_type:
        return 5
    if "plus" in haystack:
        return 1
    if plan_type == "pro" or plan_type.startswith("pro_") or plan_type.startswith("pro-"):
        return 20
    if "20x" in haystack or "pro max" in haystack or "promax" in haystack:
        return 20
    if "pro_lite" in haystack or "pro-lite" in haystack or "pro lite" in haystack or "prolite" in haystack or "5x" in haystack:
        return 5
    if "pro" in haystack:
        return 20
    return 1


def effective_remaining_units(windows: list[dict[str, Any]], capacity_factor: int) -> float:
    remaining_values: list[float] = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        try:
            used = float(window.get("used_percent"))
        except (TypeError, ValueError):
            continue
        remaining_values.append(max(0.0, 100.0 - used))
    remaining_percent = min(remaining_values) if remaining_values else 0.0
    return round(remaining_percent * max(1, capacity_factor), 1)


def summarize_quota_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rate_limit = payload.get("rate_limit") if isinstance(payload.get("rate_limit"), dict) else {}
    windows, max_used, rate_limit_reached = summarize_rate_limit_windows(rate_limit)
    plan_type = payload.get("plan_type") if isinstance(payload.get("plan_type"), str) else ""
    capacity_factor = quota_capacity_factor_from_text(plan_type)
    limit_reached = bool(rate_limit_reached or payload.get("rate_limit_reached_type"))
    if limit_reached or max_used >= 100:
        status = "limit_reached"
    elif max_used >= 80:
        status = "near_limit"
    else:
        status = "ok"

    additional_limits: list[dict[str, Any]] = []
    raw_additional = payload.get("additional_rate_limits")
    if isinstance(raw_additional, list):
        for item in raw_additional:
            if not isinstance(item, dict):
                continue
            item_rate_limit = item.get("rate_limit") if isinstance(item.get("rate_limit"), dict) else {}
            item_windows, item_max_used, item_limit_reached = summarize_rate_limit_windows(item_rate_limit)
            item_status = "limit_reached" if item_limit_reached or item_max_used >= 100 else ("near_limit" if item_max_used >= 80 else "ok")
            additional_limits.append(
                {
                    "limit_name": item.get("limit_name") if isinstance(item.get("limit_name"), str) else "",
                    "metered_feature": item.get("metered_feature") if isinstance(item.get("metered_feature"), str) else "",
                    "quota_status": item_status,
                    "allowed": bool(item_rate_limit.get("allowed", True)),
                    "limit_reached": item_limit_reached,
                    "windows": item_windows,
                }
            )

    return {
        "plan_type": plan_type,
        "allowed": bool(rate_limit.get("allowed", True)),
        "limit_reached": limit_reached,
        "quota_status": status,
        "windows": windows,
        "capacity_factor": capacity_factor,
        "effective_remaining_units": effective_remaining_units(windows, capacity_factor),
        "additional_limits": additional_limits,
        "queried_at": int(time.time()),
    }


def redact_path_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    home = str(Path.home())
    if value == home:
        return "~"
    if value.startswith(f"{home}/"):
        return f"~/{value[len(home) + 1:]}"
    value = re.sub(r"^/Users/[^/]+(?=/|$)", "~", value)
    return value


def _redact_stream_diagnostics(stream_diagnostics: dict[str, Any]) -> None:
    stream_diagnostics["log_paths"] = [
        redact_path_value(item) for item in stream_diagnostics.get("log_paths", []) if isinstance(item, str)
    ]
    latest = stream_diagnostics.get("latest")
    if isinstance(latest, dict):
        latest["account_id"] = mask_id_value(latest.get("account_id"))
        latest["log_path"] = redact_path_value(latest.get("log_path"))
    for item in stream_diagnostics.get("events", []):
        if isinstance(item, dict):
            item["account_id"] = mask_id_value(item.get("account_id"))
            item["log_path"] = redact_path_value(item.get("log_path"))


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
    for provider in redacted.get("claude_desktop_providers", []):
        if isinstance(provider, dict):
            provider["account_id"] = mask_id_value(provider.get("account_id"))
            provider["base_url"] = re.sub(r"/accounts/[^/?#]+", "/accounts/<redacted>", str(provider.get("base_url") or ""))
            provider["auth_token"] = ""
            provider["auth_token_masked"] = mask_token(provider.get("auth_token_masked"))
    for provider in redacted.get("codex_providers", []):
        if isinstance(provider, dict):
            provider["meta_account_id"] = mask_id_value(provider.get("meta_account_id"))
            provider["token_account_id"] = mask_id_value(provider.get("token_account_id"))
            provider["embedded_token_account_id"] = mask_id_value(provider.get("embedded_token_account_id"))
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
    current_launcher = redacted.get("current_codex_launcher")
    if isinstance(current_launcher, dict):
        current_launcher["path"] = redact_path_value(current_launcher.get("path"))
        current_launcher["base_url"] = re.sub(
            r"/accounts/[^/?#]+",
            "/accounts/<redacted>",
            str(current_launcher.get("base_url") or ""),
        )
        current_launcher["account_id"] = mask_id_value(current_launcher.get("account_id"))
        current_launcher["codex_home"] = redact_path_value(current_launcher.get("codex_home"))
    omc_shim = redacted.get("omc_codex_shim")
    if isinstance(omc_shim, dict):
        for shim in omc_shim.get("shims", []):
            if isinstance(shim, dict):
                shim["path"] = redact_path_value(shim.get("path"))
    plugin_sync = redacted.get("plugin_sync")
    if isinstance(plugin_sync, dict):
        plugin_sync["backups"] = [
            redact_path_value(item) for item in plugin_sync.get("backups", []) if isinstance(item, str)
        ]
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
            for home in row.get("codex_cli_homes", []):
                if isinstance(home, dict):
                    home["path"] = redact_path_value(home.get("path"))
                    home["run_command"] = redact_path_value(home.get("run_command"))
                    home["token_account_id"] = mask_id_value(home.get("token_account_id"))
                    home["access_account_id"] = mask_id_value(home.get("access_account_id"))
                    home["email"] = mask_email_value(home.get("email"))
    for quota in redacted.get("quotas", []):
        if isinstance(quota, dict):
            quota["account_id"] = mask_id_value(quota.get("account_id"))
            quota["email"] = mask_email_value(quota.get("email"))
    for key in ("missing", "created", "skipped"):
        for item in redacted.get(key, []):
            if isinstance(item, dict):
                item["account_id"] = mask_id_value(item.get("account_id"))
                item["email"] = mask_email_value(item.get("email"))
    for key in ("missing_in_aimami", "conflicts", "exported"):
        for item in redacted.get(key, []):
            if isinstance(item, dict):
                item["account_id"] = mask_id_value(item.get("account_id"))
                item["user_id"] = mask_id_value(item.get("user_id"))
                item["email"] = mask_email_value(item.get("email"))
                if item.get("refresh_sha12"):
                    item["refresh_sha12"] = mask_token_value(str(item.get("refresh_sha12") or ""))
                if item.get("aimami_refresh_sha12"):
                    item["aimami_refresh_sha12"] = mask_token_value(str(item.get("aimami_refresh_sha12") or ""))
    for item in redacted.get("errors", []):
        if isinstance(item, dict):
            item["account_id"] = mask_id_value(item.get("account_id"))
            item["email"] = mask_email_value(item.get("email"))
    for item in redacted.get("written", []):
        if isinstance(item, dict):
            item["account_id"] = mask_id_value(item.get("account_id"))
            item["user_id"] = mask_id_value(item.get("user_id"))
            item["email"] = mask_email_value(item.get("email"))
            item["snapshot_path"] = redact_path_value(item.get("snapshot_path"))
            if item.get("refresh_sha12"):
                item["refresh_sha12"] = mask_token_value(str(item.get("refresh_sha12") or ""))
    if isinstance(redacted.get("verification"), dict):
        redacted["verification"]["path"] = redact_path_value(redacted["verification"].get("path"))
    if "path" in redacted:
        redacted["path"] = redact_path_value(redacted.get("path"))
    if isinstance(redacted.get("backups"), list):
        redacted["backups"] = [redact_path_value(item) for item in redacted["backups"] if isinstance(item, str)]
    aimami = redacted.get("aimami_sync")
    if isinstance(aimami, dict):
        aimami["registry_path"] = redact_path_value(aimami.get("registry_path"))
        aimami["snapshots_dir"] = redact_path_value(aimami.get("snapshots_dir"))
        aimami["active_account_id"] = mask_id_value(aimami.get("active_account_id"))
        if aimami.get("active_account_key"):
            active_id = account_id_from_aimami_key(str(aimami.get("active_account_key") or ""))
            aimami["active_account_key"] = f"<redacted>::{mask_id_value(active_id)}" if active_id else "<redacted>"
        for item in aimami.get("candidates", []):
            if isinstance(item, dict):
                item["account_id"] = mask_id_value(item.get("account_id"))
                item["email"] = mask_email_value(item.get("email"))
                item["snapshot_path"] = redact_path_value(item.get("snapshot_path"))
                if item.get("account_key"):
                    account_id = account_id_from_aimami_key(str(item.get("account_key") or ""))
                    item["account_key"] = f"<redacted>::{mask_id_value(account_id)}" if account_id else "<redacted>"
    aimami_follow = redacted.get("aimami_follow")
    if isinstance(aimami_follow, dict):
        aimami_follow["last_synced_account_id"] = mask_id_value(aimami_follow.get("last_synced_account_id"))
        if aimami_follow.get("last_seen_active_account_key"):
            active_id = account_id_from_aimami_key(str(aimami_follow.get("last_seen_active_account_key") or ""))
            aimami_follow["last_seen_active_account_key"] = f"<redacted>::{mask_id_value(active_id)}" if active_id else "<redacted>"
        last_result = aimami_follow.get("last_result")
        if isinstance(last_result, dict):
            last_result["selected_account_id"] = mask_id_value(last_result.get("selected_account_id"))
            active_stream = last_result.get("active_stream")
            if isinstance(active_stream, dict):
                active_stream["account_id"] = mask_id_value(active_stream.get("account_id"))
    if "selected_account_id" in redacted:
        redacted["selected_account_id"] = mask_id_value(redacted.get("selected_account_id"))
    for key in ("imported", "bridge_providers"):
        value = redacted.get(key)
        if isinstance(value, dict):
            redacted[key] = redact_snapshot(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item["account_id"] = mask_id_value(item.get("account_id"))
                    item["email"] = mask_email_value(item.get("email"))
    services = redacted.get("services")
    if isinstance(services, dict):
        for service in services.values():
            if not isinstance(service, dict):
                continue
            service.pop("processes", None)
            service.pop("script", None)
            service.pop("log_path", None)
            if service.get("upstream_proxy"):
                service["upstream_proxy"] = "<redacted>"
            stream_error = service.get("last_stream_error")
            if isinstance(stream_error, dict):
                stream_error["account_id"] = mask_id_value(stream_error.get("account_id"))
            active_stream = service.get("active_stream")
            if isinstance(active_stream, dict):
                active_stream["account_id"] = mask_id_value(active_stream.get("account_id"))
            stream_diagnostics = service.get("stream_diagnostics")
            if isinstance(stream_diagnostics, dict):
                _redact_stream_diagnostics(stream_diagnostics)
    usage_metrics = redacted.get("usage_metrics")
    if isinstance(usage_metrics, dict):
        usage_metrics["last_account_id"] = mask_id_value(usage_metrics.get("last_account_id"))
    for event in redacted.get("usage_events", []):
        if isinstance(event, dict):
            event["account_id"] = mask_id_value(event.get("account_id"))
    stream_diagnostics = redacted.get("stream_diagnostics")
    if isinstance(stream_diagnostics, dict):
        _redact_stream_diagnostics(stream_diagnostics)
    active_stream = redacted.get("active_stream")
    if isinstance(active_stream, dict):
        active_stream["account_id"] = mask_id_value(active_stream.get("account_id"))
    hook_risks = redacted.get("claude_hook_risks")
    if isinstance(hook_risks, dict):
        hook_risks["settings_path"] = redact_path_value(hook_risks.get("settings_path"))
    codex_auth = redacted.get("codex_auth")
    if isinstance(codex_auth, dict):
        codex_auth.pop("path", None)
        codex_auth["email_masked"] = mask_email_value(codex_auth.get("email_masked"))
    proxy = redacted.get("proxy")
    if isinstance(proxy, dict):
        if proxy.get("url"):
            proxy["url"] = "<redacted>"
        for process in proxy.get("processes", []):
            if isinstance(process, dict):
                process.pop("command", None)
    native_proxy = redacted.get("codex_native_proxy")
    if isinstance(native_proxy, dict):
        native_proxy["env_path"] = redact_path_value(native_proxy.get("env_path"))
        if native_proxy.get("proxy_url"):
            native_proxy["proxy_url"] = "<redacted>"
        if native_proxy.get("proxy_url_masked"):
            native_proxy["proxy_url_masked"] = "<redacted>"
        if native_proxy.get("repair_proxy_url"):
            native_proxy["repair_proxy_url"] = "<redacted>"
        if native_proxy.get("repair_proxy_url_masked"):
            native_proxy["repair_proxy_url_masked"] = "<redacted>"
        for process in native_proxy.get("proxy_processes", []):
            if isinstance(process, dict):
                process.pop("command", None)
    doctor = redacted.get("codex_desktop_doctor")
    if isinstance(doctor, dict):
        config = doctor.get("config")
        if isinstance(config, dict):
            config["config_path"] = redact_path_value(config.get("config_path"))
            config["backup_legacy_refs"] = [redact_path_value(item) for item in config.get("backup_legacy_refs", []) if isinstance(item, str)]
        native = doctor.get("codex_native_proxy")
        if isinstance(native, dict):
            native["env_path"] = redact_path_value(native.get("env_path"))
            for key in ("proxy_url", "proxy_url_masked", "repair_proxy_url", "repair_proxy_url_masked"):
                if native.get(key):
                    native[key] = "<redacted>"
        logs = doctor.get("logs")
        if isinstance(logs, dict):
            logs["log_root"] = redact_path_value(logs.get("log_root"))
            logs["paths"] = [redact_path_value(item) for item in logs.get("paths", []) if isinstance(item, str)]
        app_state = doctor.get("app_state")
        if isinstance(app_state, dict):
            app_state["scope_path"] = redact_path_value(app_state.get("scope_path"))
        dynamic_tools = doctor.get("dynamic_tools")
        if isinstance(dynamic_tools, dict):
            dynamic_tools["state_db_path"] = redact_path_value(dynamic_tools.get("state_db_path"))
            latest = dynamic_tools.get("latest")
            if isinstance(latest, dict):
                latest["cwd"] = redact_path_value(latest.get("cwd"))
                thread_start_log = latest.get("thread_start_log")
                if isinstance(thread_start_log, dict):
                    thread_start_log["logs_db_path"] = redact_path_value(thread_start_log.get("logs_db_path"))
            for item in dynamic_tools.get("suspect_threads", []):
                if isinstance(item, dict):
                    item["cwd"] = redact_path_value(item.get("cwd"))
                    thread_start_log = item.get("thread_start_log")
                    if isinstance(thread_start_log, dict):
                        thread_start_log["logs_db_path"] = redact_path_value(thread_start_log.get("logs_db_path"))
        desktop_doctor = doctor.get("codex_desktop")
        if isinstance(desktop_doctor, dict):
            desktop_doctor["config_path"] = redact_path_value(desktop_doctor.get("config_path"))
            desktop_doctor["base_url"] = re.sub(r"/accounts/[^/?#]+", "/accounts/<redacted>", str(desktop_doctor.get("base_url") or ""))
            desktop_doctor["account_id"] = mask_id_value(desktop_doctor.get("account_id"))
        versions = doctor.get("versions")
        if isinstance(versions, dict):
            versions["global_cli_path"] = redact_path_value(versions.get("global_cli_path"))
            versions["bundled_cli_path"] = redact_path_value(versions.get("bundled_cli_path"))
        process = doctor.get("process")
        if isinstance(process, dict):
            for item in process.get("processes", []):
                if isinstance(item, dict):
                    item.pop("command", None)
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
    :root {
      /* Open Props inspired design tokens - BridgeDeck dark theme */
      /* Grays - cool blue-tinted dark palette */
      --gray-0: #f8f9fa;
      --gray-1: #f1f3f5;
      --gray-2: #e9ecef;
      --gray-3: #dee2e6;
      --gray-4: #ced4da;
      --gray-5: #adb5bd;
      --gray-6: #868e96;
      --gray-7: #495057;
      --gray-8: #343a40;
      --gray-9: #212529;
      --gray-10: #16191d;
      --gray-11: #0d0f12;
      --gray-12: #030507;

      /* Brand colors - BridgeDeck signature blue */
      --blue-0: #e7f5ff;
      --blue-1: #d0ebff;
      --blue-2: #a5d8ff;
      --blue-3: #74c0fc;
      --blue-4: #4dabf7;
      --blue-5: #339af0;
      --blue-6: #228be6;
      --blue-7: #1c7ed6;
      --blue-8: #1971c2;
      --blue-9: #1864ab;
      --blue-10: #145591;
      --blue-11: #114678;
      --blue-12: #0d375e;

      /* Status colors */
      --green-5: #51cf66;
      --green-6: #40c057;
      --green-7: #37b24d;
      --yellow-5: #fcc419;
      --yellow-6: #fab005;
      --yellow-7: #f59f00;
      --red-5: #ff6b6b;
      --red-6: #fa5252;
      --red-7: #f03e3e;

      /* Semantic tokens */
      --bg: var(--gray-12);
      --surface: #111722;
      --panel: #151c29;
      --panel2: #101621;
      --line: #263244;
      --text: var(--gray-0);
      --muted: var(--gray-5);
      --soft: var(--gray-3);
      --ok: var(--green-6);
      --warn: var(--yellow-6);
      --bad: var(--red-6);
      --brand: var(--blue-5);
      --brand2: var(--blue-3);
      --focus: var(--blue-9);
    }
    * { box-sizing:border-box; }
    body { margin:0; font-family:ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }
    .wrap { min-height:100vh; }
    .appShell { display:grid; grid-template-columns:260px minmax(0, 1fr); min-height:100vh; }
    .appSidebar { position:sticky; top:0; height:100vh; padding:18px 14px; border-right:1px solid var(--line); background:#0a0d12; display:flex; flex-direction:column; gap:14px; }
    .brand { display:grid; gap:4px; padding:4px 6px 12px; border-bottom:1px solid var(--line); }
    .brandName { font-size:19px; font-weight:850; }
    .brandSub { color:var(--muted); font-size:12px; }
    .sideNav { display:grid; gap:6px; }
    .navItem { width:100%; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 12px; border:1px solid transparent; border-radius:8px; background:transparent; color:var(--soft); text-align:left; font-weight:700; }
    .navItem:hover, .navItem.active { background:var(--focus); border-color:#315077; color:var(--text); }
    .navHint { color:var(--muted); font-size:11px; font-weight:600; }
    .sidePanel { margin-top:auto; border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--panel2); }
    .workspace { width:100%; min-width:0; box-sizing:border-box; padding:20px; display:grid; grid-template-columns:minmax(0, 1fr) 300px; gap:16px; align-items:start; align-content:start; }
    .topBar { grid-column:1 / -1; grid-row:1; justify-self:stretch; width:100%; display:flex; justify-content:space-between; gap:16px; align-items:flex-start; padding:16px; border:1px solid var(--line); border-radius:8px; background:var(--surface); }
    .topBar h1 { margin:0; font-size:24px; }
    .topBar p { margin:6px 0 0; color:var(--muted); font-size:13px; }
    .topActions { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
    .pageStack { grid-column:1; grid-row:2; justify-self:stretch; width:100%; min-width:0; }
    .deckPage { display:none; }
    .deckPage.active { display:block; }
    .guideDock { grid-column:2; grid-row:2; justify-self:stretch; width:100%; position:sticky; top:20px; }
    body.usageMode .workspace { grid-template-columns:minmax(0, 1fr); }
    body.usageMode .guideDock { display:none; }
    .card, .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:14px; }
    .panel.subtle { background:var(--panel2); }
    .pageHeader { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:14px; }
    .pageTitle { margin:0; font-size:21px; font-weight:850; }
    .pageDesc { margin:5px 0 0; color:var(--muted); font-size:13px; line-height:1.5; }
    h1, h2 { margin:0 0 10px; }
    h2 { font-size:16px; }
    .sectionHint { color:var(--muted); font-size:12px; margin:-2px 0 12px; line-height:1.5; }
    .muted { color:var(--muted); font-size:12px; }
    .row, .toggleLine, .apiEnvActions { display:flex; gap:9px; flex-wrap:wrap; align-items:center; margin-top:10px; }
    input, select, button, textarea { border-radius:8px; border:1px solid var(--line); background:#0d1320; color:var(--text); padding:8px 10px; font:inherit; }
    input, select { min-width:220px; }
    input[type="checkbox"], input[type="radio"] { min-width:0; }
    button { cursor:pointer; background:#1a2332; }
    button:hover { border-color:#3f5676; }
    button:disabled { opacity:.55; cursor:default; }
    button.primary { background:var(--brand); border-color:#3d8ce0; color:#041122; font-weight:800; }
    button.warn { background:#36260e; border-color:#745018; color:#ffd98f; }
    .miniBtn { padding:6px 9px; font-size:12px; }
    .mt10 { margin-top:10px; }
    .ok { color:var(--ok); }
    .bad { color:var(--bad); }
    .warnText { color:var(--warn); }
    .cmd, .mono, .paths, .apiEnvValue { font-family:ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap:anywhere; word-break:break-word; }
    .paths { color:var(--muted); font-size:11px; line-height:1.45; white-space:pre-wrap; }
    .mono, .cmd { color:#b7d8ff; }
    .topGrid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:10px; }
    .tile { border:1px solid var(--line); border-radius:8px; padding:12px; background:var(--panel2); min-height:76px; }
    .tileLabel { color:var(--muted); font-size:12px; margin-bottom:6px; }
    .tileValue { font-size:24px; font-weight:850; }
    .metricGrid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; margin-top:12px; }
    .metricCard { border:1px solid var(--line); border-radius:8px; padding:16px; min-height:148px; background:linear-gradient(180deg, #171a21 0%, #121722 100%); display:grid; align-content:space-between; gap:12px; }
    .metricHead { display:flex; align-items:center; justify-content:space-between; gap:10px; color:var(--muted); font-size:15px; font-weight:850; }
    .metricIcon { width:34px; height:34px; border-radius:12px; display:grid; place-items:center; font-size:18px; background:#18263a; color:var(--brand2); }
    .metricIcon.ok { background:#132b21; color:#53e5a0; }
    .metricIcon.warn { background:#352711; color:#ffd070; }
    .metricIcon.bad { background:#351717; color:#ff8e8e; }
    .metricValue { font-size:32px; line-height:1; font-weight:900; letter-spacing:0; }
    .metricSub { border-top:1px solid var(--line); padding-top:10px; display:grid; gap:5px; color:var(--muted); font-size:12px; }
    .metricLine { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
    .metricLine span { flex:0 0 auto; white-space:nowrap; }
    .metricLine strong { flex:1 1 auto; min-width:0; text-align:right; overflow-wrap:anywhere; }
    .metricEllipsis { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; overflow-wrap:normal; }
    .hudPanel { border:1px solid var(--line); border-radius:8px; padding:16px; background:#101720; display:grid; grid-template-columns:340px minmax(0, 1fr); gap:16px; align-items:center; }
    .hudDial { position:relative; min-height:230px; display:grid; place-items:center; }
    .hudDial::before { content:""; width:220px; height:220px; border-radius:50%; background:
      conic-gradient(from 225deg, var(--ok) 0 var(--hit-angle, 0deg), #2b3545 var(--hit-angle, 0deg) 270deg, transparent 270deg 360deg);
      mask:radial-gradient(circle, transparent 0 63px, #000 64px 100px, transparent 101px);
      -webkit-mask:radial-gradient(circle, transparent 0 63px, #000 64px 100px, transparent 101px);
      transform:rotate(45deg);
    }
    .hudDial::after { content:""; position:absolute; width:156px; height:156px; border-radius:50%; border:1px solid var(--line); background:#0d121b; }
    .hudCenter { position:absolute; z-index:1; text-align:center; display:grid; gap:6px; }
    .hudValue { font-size:44px; line-height:1; font-weight:900; }
    .hudLabel { color:var(--muted); font-size:12px; font-weight:850; }
    .hudGrid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; }
    .hudStat { border:1px solid var(--line); border-radius:8px; padding:12px; background:var(--panel2); min-height:82px; display:grid; align-content:space-between; gap:8px; }
    .hudStatLabel { color:var(--muted); font-size:12px; font-weight:850; }
    .hudStatValue { font-size:22px; font-weight:900; overflow-wrap:anywhere; }
    .usageControls { display:flex; gap:8px; flex-wrap:wrap; justify-content:space-between; align-items:center; margin:12px 0; }
    .usageTable table { min-width:0; }
    .usageTimeCol { width:9%; }
    .usageEntryCol { width:15%; }
    .usageProviderCol { width:15%; }
    .usageModelCol { width:17%; }
    .usageNumCol { width:6.2%; }
    .usageStatusCol { width:7%; }
    .usageEntryMain, .usageModelMain { display:block; color:var(--text); font-weight:850; line-height:1.25; }
    .usageMeta { display:block; color:var(--muted); font-size:11px; line-height:1.35; margin-top:3px; overflow-wrap:anywhere; }
    .usageTag { display:inline-flex; align-items:center; width:max-content; max-width:100%; border:1px solid var(--line); border-radius:999px; padding:2px 6px; margin-top:5px; color:var(--soft); background:#111827; font-size:10px; font-weight:850; line-height:1; }
    .usageTag.desktop { border-color:#2f5f8f; background:#102033; color:#b9dcff; }
    .usageTag.chat { border-color:#255c43; background:#0f2018; color:#a6f3c6; }
    .overviewGrid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-top:12px; }
    .overviewCard { border:1px solid var(--line); border-radius:8px; padding:13px; background:var(--panel2); min-height:122px; display:grid; gap:8px; align-content:start; }
    .overviewLabel { color:var(--muted); font-size:12px; font-weight:850; }
    .overviewMain { font-size:16px; font-weight:850; overflow-wrap:anywhere; }
    .overviewMeta { color:var(--muted); font-size:12px; line-height:1.45; overflow-wrap:anywhere; }
    .taskList { display:grid; gap:8px; }
    .taskItem { border:1px solid var(--line); border-radius:8px; padding:9px 10px; background:#0d1320; color:var(--soft); font-size:12px; line-height:1.45; }
    .taskItem.bad { border-color:#743333; background:#241313; color:#ffc0c0; }
    .taskItem.warn { border-color:#73551c; background:#21190d; color:#ffe0a3; }
    .taskItem.ok { border-color:#245f43; background:#102318; color:#a6f3c6; }
    .quickActions { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; }
    .quickActions button { min-height:38px; font-weight:800; }
    .summaryGrid, .splitGrid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
    .recommend { margin-top:10px; padding:12px; border:1px solid var(--line); border-radius:8px; background:var(--panel2); line-height:1.55; }
    .recommend.okState { border-color:#255c43; background:#0f2018; }
    .recommend.warnState { border-color:#77571c; background:#21190d; }
    .recommend.badState, .recommend.fail { border-color:#7a3030; background:#241313; }
    .toolGrid, .apiMatrix, .apiExampleGrid { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:12px; }
    .toolCard, .apiCard, .apiExample, .compactPanel, .serviceItem, .apiEnvLine { border:1px solid var(--line); border-radius:8px; background:var(--panel2); padding:12px; }
    .toolCard { min-height:176px; display:flex; flex-direction:column; justify-content:space-between; gap:12px; }
    .toolName, .apiCardTitle, .apiExampleTitle, .compactTitle, .serviceName { font-weight:850; }
    .toolName { font-size:16px; margin-bottom:6px; }
    .toolText, .apiCardMeta, .actualLine, .serviceMeta { color:var(--muted); font-size:12px; line-height:1.5; }
    .toolSelect { display:grid; gap:6px; margin-top:10px; }
    .toolSelect label, .apiEnvLabel { color:var(--muted); font-size:11px; }
    .toolSelect select { width:100%; min-width:0; }
    .oauthPanel { display:grid; gap:10px; }
    .oauthActions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .oauthLinkBox { border:1px solid var(--line); border-radius:8px; background:#0d1320; padding:10px; display:grid; gap:8px; }
    .oauthLinkBox a { color:#9fd0ff; overflow-wrap:anywhere; }
    #oauthUserCode { width:max-content; max-width:100%; border:1px solid #2f4160; border-radius:8px; padding:8px 12px; font-size:22px; letter-spacing:0; color:#f6f8ff; background:#111b2e; }
    #oauthExpiresAt { color:var(--muted); font-size:12px; }
    .oauthPaste { width:100%; min-height:72px; }
    .hidden { display:none !important; }
    .actualRow { display:flex; gap:8px; align-items:flex-start; margin-top:8px; }
    .actualLine { flex:1 1 auto; min-width:0; }
    .actualLine strong { color:var(--text); }
    .toolCard button { min-height:40px; font-weight:800; }
    .toolCard .actualRow button { min-height:0; flex:0 0 auto; }
    .apiEnvBox { margin-top:10px; display:grid; gap:8px; }
    .apiEnvValue { color:#b7d8ff; font-size:12px; }
    .simpleResult { margin-top:12px; padding:12px; border:1px solid var(--line); border-radius:8px; background:#0d1320; min-height:44px; color:var(--muted); font-size:13px; line-height:1.5; }
    .quotaBar { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin:12px 0; align-items:stretch; }
    .quotaPill { border:1px solid var(--line); border-radius:8px; padding:13px; background:var(--panel2); display:grid; gap:10px; }
    .quotaPill.current { border-color:#4c91d9; background:#102033; }
    .quotaHead { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
    .quotaTitle { font-weight:850; font-size:14px; overflow-wrap:anywhere; }
    .quotaMeta { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }
    .badge { display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:3px 7px; font-size:11px; font-weight:800; line-height:1; }
    .badge.ok { border-color:#245f43; background:#102318; color:#7ff0b5; }
    .badge.warn { border-color:#75551a; background:#241a0d; color:#ffd680; }
    .badge.bad { border-color:#733333; background:#261313; color:#ff9b9b; }
    .quotaMeter { display:grid; gap:5px; }
    .quotaMeterMeta { display:grid; grid-template-columns:1fr auto auto; gap:8px; align-items:center; font-size:12px; color:var(--muted); }
    .quotaMeterMeta strong { color:var(--text); }
    .quotaReset { color:#7f8ca0; }
    .quotaProgress { width:100%; height:8px; appearance:none; border:0; border-radius:999px; overflow:hidden; background:#222a36; }
    .quotaProgress::-webkit-progress-bar { background:#222a36; border-radius:999px; }
    .quotaProgress::-webkit-progress-value { border-radius:999px; }
    .quotaProgress.ok::-webkit-progress-value { background:var(--ok); }
    .quotaProgress.warn::-webkit-progress-value { background:var(--warn); }
    .quotaProgress.bad::-webkit-progress-value { background:var(--bad); }
    .quotaProgress::-moz-progress-bar { border-radius:999px; background:var(--ok); }
    .quotaWindows { color:var(--muted); font-size:12px; line-height:1.5; }
    .servicePanel { border-top:1px solid var(--line); margin-top:12px; padding-top:12px; }
    .serviceGrid { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:10px; margin-top:8px; }
    .serviceItem { min-height:84px; }
    .serviceMeta { overflow-wrap:anywhere; }
    .formGrid { display:grid; grid-template-columns:repeat(2, minmax(240px, 1fr)); gap:12px; align-items:end; }
    .formGrid label { display:grid; gap:6px; color:var(--muted); font-size:12px; font-weight:700; }
    .formGrid input, .formGrid select { width:100%; min-width:0; }
    .tableWrap { width:100%; overflow:auto; border-radius:8px; border:1px solid var(--line); }
    table { width:100%; min-width:min(760px, 100%); border-collapse:collapse; table-layout:fixed; font-size:12px; }
    th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; overflow-wrap:anywhere; word-break:break-word; }
    th { color:var(--muted); background:#111827; font-weight:800; }
    tr:last-child td { border-bottom:0; }
    .nameCol { width:20%; }
    .smallCol { width:10%; }
    .accountCol { width:16%; }
    .urlCol { width:30%; }
    .tokenCol { width:12%; }
    .providerNameCell { display:flex; gap:8px; align-items:flex-start; min-width:0; }
    .providerNameText { min-width:0; }
    details.card { padding:0; }
    details.card > summary { padding:14px; list-style:none; cursor:pointer; font-weight:850; }
    details.card > summary::-webkit-details-marker { display:none; }
    details.card > .detailsBody { padding:0 14px 14px; }
    .steps { margin:0; padding-left:18px; color:var(--soft); font-size:12px; line-height:1.65; }
    .guideTarget { color:var(--muted); font-size:12px; margin-bottom:10px; }
    textarea { width:100%; min-height:220px; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px; }
    @media (max-width: 1180px) {
      .workspace { grid-template-columns:minmax(0, 1fr); }
      .topBar, .pageStack, .guideDock { grid-column:1; }
      .topBar, .pageStack { grid-row:auto; }
      .guideDock { grid-row:auto; position:static; }
      .hudPanel { grid-template-columns:1fr; }
    }
    @media (max-width: 900px) {
      .appShell { grid-template-columns:1fr; }
      .appSidebar { position:static; height:auto; }
      .sideNav { grid-template-columns:repeat(2, minmax(0, 1fr)); }
      .topGrid, .metricGrid, .overviewGrid, .summaryGrid, .splitGrid, .formGrid, .quickActions { grid-template-columns:1fr; }
      .hudGrid { grid-template-columns:1fr; }
      .usageTable table { min-width:920px; }
      .topBar { flex-direction:column; }
      input, select { min-width:0; width:100%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="appShell">
      <aside class="appSidebar">
        <div class="brand">
          <div class="brandName">BridgeDeck</div>
          <div class="brandSub">Local Codex / Claude 控制台</div>
        </div>
        <nav class="sideNav" aria-label="BridgeDeck sections">
          <button class="navItem active" data-page="overview">总览 <span class="navHint">状态</span></button>
          <button class="navItem" data-page="usage">使用详情 <span class="navHint">Token</span></button>
          <button class="navItem" data-page="switching">入口切换 <span class="navHint">账号</span></button>
          <button class="navItem" data-page="quota">额度与自动切换 <span class="navHint">OpenAI</span></button>
          <button class="navItem" data-page="claude">Claude Code <span class="navHint">桥接</span></button>
          <button class="navItem" data-page="codex">Codex CLI <span class="navHint">启动器</span></button>
          <button class="navItem" data-page="api">通用 API <span class="navHint">复制</span></button>
          <button class="navItem" data-page="services">本地服务 <span class="navHint">8876</span></button>
          <button class="navItem" data-page="diagnostics">诊断日志 <span class="navHint">排查</span></button>
          <button class="navItem" data-page="account-pool">账户池 <span class="navHint">轮换</span></button>
          <button class="navItem" data-page="api-keys">API Keys <span class="navHint">统一入口</span></button>
          <button class="navItem" data-page="service-control">服务控制 <span class="navHint">launchd</span></button>
        </nav>
        <div class="sidePanel">
          <div id="status" class="muted">加载中...</div>
          <details class="mt10">
            <summary>技术信息</summary>
            <div class="paths mt10" id="paths"></div>
          </details>
        </div>
      </aside>

      <main class="workspace">
        <header class="topBar">
          <div>
            <h1>BridgeDeck 控制台</h1>
            <p>把账户、额度、Claude、Codex CLI、API 接入和本地服务拆开管理。</p>
          </div>
          <div class="topActions">
            <button data-action="refresh">刷新状态</button>
            <button data-page="services">本地服务</button>
            <button class="warn" data-action="stop-bridgedeck-ui">关闭 UI</button>
          </div>
        </header>

        <div class="pageStack">
          <section class="deckPage active" id="page-overview">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">总览</h2>
                <p class="pageDesc">只显示当前能否用、哪里不一致、下一步该点哪个入口。</p>
              </div>
              <button class="primary" data-page="switching">选择账号入口</button>
            </div>
            <div class="topGrid">
              <div class="tile"><div class="tileLabel">账号</div><div id="tileAccounts" class="tileValue">-</div></div>
              <div class="tile"><div class="tileLabel">Claude 配置</div><div id="tileProviders" class="tileValue">-</div></div>
              <div class="tile"><div class="tileLabel">账号不一致</div><div id="tileMismatches" class="tileValue">-</div></div>
              <div class="tile"><div class="tileLabel">CLI 配置</div><div id="tileCliHomes" class="tileValue">-</div></div>
            </div>
            <div class="metricGrid">
              <div class="metricCard">
                <div class="metricHead"><span>Provider 匹配</span><span id="metricAccountIcon" class="metricIcon ok">✓</span></div>
                <div id="metricAccountValue" class="metricValue">-</div>
                <div class="metricSub">
                  <div class="metricLine"><span>匹配</span><strong id="metricAccountOk">-</strong></div>
                  <div class="metricLine"><span>错配</span><strong id="metricAccountRisk">-</strong></div>
                </div>
              </div>
              <div class="metricCard">
                <div class="metricHead"><span>额度消耗</span><span id="metricQuotaIcon" class="metricIcon">▣</span></div>
                <div id="metricQuotaValue" class="metricValue">-</div>
                <div class="metricSub">
                  <div class="metricLine"><span>账号</span><strong id="metricQuotaAccount" class="metricEllipsis">-</strong></div>
                  <div class="metricLine"><span>剩余</span><strong id="metricQuotaRemaining">-</strong></div>
                </div>
              </div>
              <div class="metricCard">
                <div class="metricHead"><span>Token 用量</span><span class="metricIcon">◇</span></div>
                <div id="metricTokenValue" class="metricValue">等待请求</div>
                <div class="metricSub">
                  <div class="metricLine"><span>Input</span><strong id="metricTokenInput">-</strong></div>
                  <div class="metricLine"><span>Output</span><strong id="metricTokenOutput">-</strong></div>
                </div>
              </div>
              <div class="metricCard">
                <div class="metricHead"><span>缓存 Token</span><span class="metricIcon warn">◎</span></div>
                <div id="metricCacheValue" class="metricValue">等待请求</div>
                <div class="metricSub">
                  <div class="metricLine"><span>创建</span><strong id="metricCacheCreate">-</strong></div>
                  <div class="metricLine"><span>命中</span><strong id="metricCacheHit">-</strong></div>
                </div>
              </div>
            </div>
            <div class="overviewGrid">
              <div class="overviewCard">
                <div class="overviewLabel">Claude Code</div>
                <div id="overviewClaudeMain" class="overviewMain">检测中...</div>
                <div id="overviewClaudeMeta" class="overviewMeta">-</div>
              </div>
              <div class="overviewCard">
                <div class="overviewLabel">Codex Desktop / 全局 CLI</div>
                <div id="overviewDesktopMain" class="overviewMain">检测中...</div>
                <div id="overviewDesktopMeta" class="overviewMeta">-</div>
              </div>
              <div class="overviewCard">
                <div class="overviewLabel">OMC / tmux 固定入口</div>
                <div id="overviewOmniMain" class="overviewMain">检测中...</div>
                <div id="overviewOmniMeta" class="overviewMeta">-</div>
              </div>
            </div>
            <div id="recommendation" class="recommend">加载中...</div>
            <div class="summaryGrid mt10">
              <div class="panel">
                <h2>待处理事项</h2>
                <div id="overviewTasks" class="taskList"><div class="taskItem">检测中...</div></div>
              </div>
              <div class="panel">
                <h2>快捷动作</h2>
                <div class="quickActions">
                  <button class="miniBtn" data-page="switching">入口切换</button>
                  <button class="miniBtn" data-page="quota">额度详情</button>
                  <button class="miniBtn" data-page="diagnostics">账号矩阵</button>
                  <button class="miniBtn" data-page="services">服务状态</button>
                </div>
              </div>
            </div>
            <div class="summaryGrid mt10">
              <div class="panel guideSection" data-guide="simpleFlow">
                <h2>当前实际使用</h2>
                <div id="actualCurrentAccounts" class="actualLine">实际当前使用：检测中...</div>
                <div class="row">
                  <button class="miniBtn" data-page="switching">入口切换</button>
                  <button class="miniBtn" data-page="quota">查看额度</button>
                  <button class="miniBtn" data-page="diagnostics">状态矩阵</button>
                </div>
              </div>
              <div class="panel">
                <h2>Claude 插件启用态</h2>
                <div id="pluginSyncStatus" class="sectionHint">插件同步检测中...</div>
                <div class="row">
                  <button class="miniBtn" data-action="extract-safe-common-config">安全提取通用配置</button>
                  <button class="miniBtn" data-action="sync-claude-plugins">一键同步插件启用态</button>
                </div>
              </div>
              <div class="panel">
                <h2>Claude Code Attribution Header</h2>
                <div id="attributionHeaderStatus" class="sectionHint">检测中...</div>
                <div class="muted mt10">关闭动态 billing attribution header，不影响 Claude Code 正常功能、模型质量或 git commit attribution。</div>
                <div id="attributionHeaderPaths" class="muted mt10">-</div>
                <div class="row">
                  <button class="miniBtn" data-action="repair-claude-attribution-header">一键修复</button>
                  <button class="miniBtn" data-action="show-attribution-header-paths">查看配置位置</button>
                  <button class="miniBtn" data-action="keep-attribution-header">保持当前设置</button>
                </div>
              </div>
            </div>
          </section>

          <section class="deckPage" id="page-usage">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">使用详情</h2>
                <p class="pageDesc">查看 Local Codex Bridge 请求、Token、缓存写入、缓存命中和未命中。</p>
              </div>
              <button data-action="refresh">刷新使用详情</button>
            </div>
            <div class="hudPanel guideSection" data-guide="usage">
              <div id="usageHudDial" class="hudDial">
                <div class="hudCenter">
                  <div id="usageHudHitRate" class="hudValue">-</div>
                  <div class="hudLabel">缓存命中率</div>
                </div>
              </div>
              <div class="hudGrid">
                <div class="hudStat"><div class="hudStatLabel">总请求数</div><div id="usageHudRequests" class="hudStatValue">-</div></div>
                <div class="hudStat"><div class="hudStatLabel">总 Token</div><div id="usageHudTokens" class="hudStatValue">-</div></div>
                <div class="hudStat"><div class="hudStatLabel">输入 / 输出</div><div id="usageHudInOut" class="hudStatValue">-</div></div>
                <div class="hudStat"><div class="hudStatLabel">缓存写入</div><div id="usageHudCacheWrite" class="hudStatValue">-</div></div>
                <div class="hudStat"><div class="hudStatLabel">命中缓存</div><div id="usageHudCacheRead" class="hudStatValue">-</div></div>
                <div class="hudStat"><div class="hudStatLabel">未命中缓存</div><div id="usageHudCacheMiss" class="hudStatValue">-</div></div>
              </div>
            </div>
            <div class="usageControls">
              <div class="sectionHint">明细只保留最近 200 条；采集从新版 8876 Local Codex Bridge 启动后的下一次 LLM 请求开始，历史请求不会回填。</div>
              <div class="row">
                <button class="miniBtn" data-page="services">服务状态</button>
                <button class="miniBtn" data-page="diagnostics">诊断日志</button>
              </div>
            </div>
            <div class="tableWrap usageTable">
              <table>
                <thead>
                  <tr>
                    <th class="usageTimeCol">时间</th>
                    <th class="usageEntryCol">入口</th>
                    <th class="usageProviderCol">供应商</th>
                    <th class="usageModelCol">模型</th>
                    <th class="usageNumCol">输入</th>
                    <th class="usageNumCol">输出</th>
                    <th class="usageNumCol">缓存写入</th>
                    <th class="usageNumCol">命中缓存</th>
                    <th class="usageNumCol">未命中</th>
                    <th class="usageNumCol">命中率</th>
                    <th class="usageStatusCol">状态</th>
                  </tr>
                </thead>
                <tbody id="usageRows">
                  <tr><td colspan="11">加载中...</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="deckPage" id="page-switching">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">入口切换</h2>
                <p class="pageDesc">Claude Code、单独 Codex CLI、全局 Codex CLI 分开选，避免一个操作影响全部。</p>
              </div>
              <button data-action="refresh">刷新状态</button>
            </div>
            <div class="panel guideSection oauthPanel" data-guide="oauth">
              <div>
                <h2>ChatGPT 授权</h2>
                <div class="sectionHint">在 BridgeDeck 内新增或重新授权 ChatGPT 账号；完成后写入 CC Switch 使用的 OAuth 账号池。</div>
              </div>
              <div class="oauthActions">
                <button class="primary" data-action="start-codex-oauth">生成授权验证码</button>
                <label><input type="checkbox" id="oauthSetDefault"> 授权后设为默认账号</label>
                <button class="miniBtn" data-action="refresh">刷新账号列表</button>
              </div>
              <div id="oauthResult" class="simpleResult">未开始授权。</div>
              <div id="oauthUrlBox" class="oauthLinkBox hidden">
                <div class="muted">打开 OpenAI 设备授权页，输入下方验证码。</div>
                <div id="oauthUserCode" class="mono strong">-</div>
                <div id="oauthExpiresAt">有效期：-</div>
                <a id="oauthAuthLink" href="#" target="_blank" rel="noopener noreferrer">OpenAI 设备授权页</a>
                <div class="oauthActions">
                  <button class="miniBtn" data-action="check-codex-oauth">检查授权状态</button>
                  <button class="miniBtn hidden" id="oauthApplyBridgeBtn" data-action="apply-codex-oauth-bridge">加入 CC Switch</button>
                  <button class="miniBtn" data-action="hide-codex-oauth">隐藏验证码</button>
                </div>
              </div>
            </div>
            <div class="card guideSection" id="simpleFlowCard" data-guide="simpleFlow">
              <div class="toolGrid">
                <div class="toolCard">
                  <div>
                    <div class="toolName">Claude Code</div>
                    <div class="toolText">切换 Claude Code 当前使用的账号。</div>
                    <div class="toolSelect">
                      <label for="simpleClaudeAccount">Claude Code 用哪个账号</label>
                      <select id="simpleClaudeAccount"></select>
                    </div>
                    <div class="actualRow">
                      <div class="actualLine" id="simpleClaudeActual">当前实际：检测中...</div>
                      <button class="miniBtn" data-action="refresh">刷新</button>
                    </div>
                  </div>
                  <button class="primary" data-action="simple-claude">应用到 Claude Code</button>
                </div>
                <div class="toolCard">
                  <div>
                    <div class="toolName">单独 Codex CLI</div>
                    <div class="toolText">准备独立启动器，不改变全局默认。</div>
                    <div class="toolSelect">
                      <label for="simpleCliAccount">单独 Codex CLI 用哪个账号</label>
                      <select id="simpleCliAccount"></select>
                    </div>
                    <div class="actualRow">
                      <div class="actualLine" id="simpleCliActual">当前实际：检测中...</div>
                      <button class="miniBtn" data-action="refresh">刷新</button>
                    </div>
                  </div>
                  <button class="primary" data-action="simple-cli">准备单独 Codex CLI</button>
                </div>
                <div class="toolCard">
                  <div>
                    <div class="toolName">全局 Codex CLI</div>
                    <div class="toolText">只给 codex-current.command 和 OMC/tmux 使用，不改 Codex Desktop。</div>
                    <div class="toolSelect">
                      <label for="simpleDefaultAccount">全局 Codex CLI 用哪个账号</label>
                      <select id="simpleDefaultAccount"></select>
                    </div>
                    <div class="actualRow">
                      <div class="actualLine" id="simpleDefaultActual">当前实际：检测中...</div>
                      <button class="miniBtn" data-action="refresh">刷新</button>
                    </div>
                  </div>
                  <button class="warn" data-action="simple-default-codex">设为全局 Codex CLI 固定入口</button>
                </div>
                <div class="toolCard">
                  <div>
                    <div class="toolName">Codex Desktop</div>
                    <div class="toolText">默认保持原生。Stability Route 已禁用；恢复原生只移除 BridgeDeck provider，代理修复只写 .env。</div>
                    <div class="actualRow">
                      <div class="actualLine" id="simpleDesktopActual">当前实际：检测中...</div>
                      <button class="miniBtn" data-action="refresh">刷新</button>
                    </div>
                  </div>
                  <div class="apiEnvActions">
                    <button class="miniBtn warn" data-action="enable-desktop-bridge-mode" disabled title="Local Bridge 不支持 /v1/responses/compact">Stability Route 已禁用</button>
                    <button class="miniBtn" data-action="restore-desktop-native-mode">恢复原生</button>
                    <button class="miniBtn" data-action="scroll" data-target="statusCard">查看状态</button>
                  </div>
                </div>
              </div>
              <div class="simpleResult" id="simpleResult">三种入口可以选择不同账号。</div>
            </div>
          </section>

          <section class="deckPage" id="page-quota">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">额度与自动切换</h2>
                <p class="pageDesc">只接管 Local Codex Bridge。切到 MiniMax、Nvidia、SSSAiCode 时不会自动改回 OpenAI。</p>
              </div>
              <button class="primary" data-action="run-auto-switch">立即检查并切换</button>
            </div>
            <div class="card guideSection" data-guide="quota">
              <div id="quotaBoard" class="quotaBar">额度加载中...</div>
              <div class="toggleLine">
                <label><input type="checkbox" id="autoSwitchEnabled"> OpenAI 自动切换</label>
                <label><input type="checkbox" id="autoSwitchClaude" checked> 自动切 Claude Code</label>
                <label><input type="checkbox" id="autoSwitchDefaultCodex"> 自动切全局 Codex CLI</label>
              </div>
              <div class="row">
                <button class="miniBtn" data-action="save-auto-switch">保存</button>
                <button class="miniBtn" data-action="run-auto-switch">立即检查并切换</button>
                <button class="miniBtn" data-action="create-missing-bridges">为新账号创建 Local Codex Bridge</button>
                <button class="miniBtn" data-action="preview-bridge-dedupe">预览重复 Local Bridge</button>
                <button class="miniBtn warn" data-action="apply-bridge-dedupe">清理重复 Local Bridge</button>
              </div>
              <div id="missingBridgeStatus" class="muted mt10">新账号检测中...</div>
              <div id="autoSwitchStatus" class="muted mt10">未运行</div>
            </div>
            <div class="card guideSection" id="aimamiSyncPanel" data-guide="aimamiSync">
              <h2>AiMaMi 同步</h2>
              <div class="sectionHint">只读取 AiMaMi 本机账号快照，导入到 BridgeDeck 自己的 OAuth 存储；不写 AiMaMi 文件。</div>
              <div class="row">
                <button class="miniBtn" data-action="preview-aimami-import">预览 AiMaMi 导入</button>
                <button class="primary" data-action="import-aimami-accounts">导入账号</button>
                <button class="miniBtn" data-action="import-aimami-and-bridges">导入并创建 Local Bridge</button>
              </div>
              <div id="aimamiSyncStatus" class="muted mt10">AiMaMi 账号检测中...</div>
              <div class="toggleLine mt10">
                <label><input type="checkbox" id="aimamiFollowEnabled"> Follow AiMaMi active account</label>
              </div>
              <div class="row">
                <button class="miniBtn" data-action="save-aimami-follow">保存 Follow 设置</button>
                <button class="miniBtn" data-action="run-aimami-follow">立即同步 AiMaMi 当前账号</button>
              </div>
              <div id="aimamiFollowStatus" class="muted mt10">Follow 未运行</div>
              <div class="row mt10">
                <button class="miniBtn" data-action="preview-aimami-export">预览 BridgeDeck 导出</button>
                <button class="miniBtn" data-action="export-aimami-accounts">导出选中账号给 AiMaMi</button>
                <button class="miniBtn warn" data-action="preview-aimami-inject">预览 Snapshot Injection</button>
                <button class="miniBtn warn" data-action="inject-aimami-accounts">写入 AiMaMi Snapshots</button>
              </div>
              <div id="aimamiExportStatus" class="muted mt10">导出未运行</div>
            </div>
          </section>

          <section class="deckPage" id="page-claude">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">Claude Code</h2>
                <p class="pageDesc">创建、切换和修复 Claude Provider，同时配置模型上下文和自动压缩。</p>
              </div>
              <button data-action="refresh">刷新</button>
            </div>
            <div class="card guideSection" id="providerCreateCard" data-guide="providerCreate">
              <h2>Claude 桥接账号</h2>
              <div class="sectionHint">默认使用 Claude 自动路由，只写 Haiku/Sonnet/Opus slot；只有选择“强制主模型”才写 ANTHROPIC_MODEL。</div>
              <div class="formGrid">
                <label>ChatGPT 账号<select id="account"></select></label>
                <label>显示名称<input id="providerName" placeholder="Local Codex Bridge - xxx" /></label>
                <label>路由模式<select id="modelRoutingMode"><option value="auto">Claude 自动路由</option><option value="forced">强制主模型</option></select></label>
                <label>模型 / 上下文<select id="bridgeModel"></select></label>
                <label>上下文 tokens<input id="modelContextTokens" type="number" min="10000" max="2000000" step="1000" value="272000" readonly /></label>
              </div>
              <div class="muted" id="selectedProviderMeta">当前账号 provider：未检测。</div>
              <div class="row">
                <label><input type="checkbox" id="setCurrent" checked /> 设为当前</label>
                <button class="primary" data-action="create-provider">创建/更新 Claude 桥接</button>
              </div>
              <div class="compactPanel">
                <div class="compactTitle">Claude Code 自动压缩</div>
                <div class="row">
                  <label><input type="checkbox" id="compactEnabled" checked /> 启用</label>
                  <label>窗口 tokens <input id="compactWindow" type="number" min="10000" max="2000000" step="1000" value="272000" /></label>
                  <label>阈值 % <input id="compactPct" type="number" min="1" max="100" step="1" value="80" /></label>
                  <button class="miniBtn" data-action="compact-preset-model">模型上下文</button>
                  <button class="miniBtn" data-action="compact-preset-220k">220k</button>
                  <button class="miniBtn" data-action="compact-preset-1m">1m</button>
                  <button class="miniBtn" data-action="compact-off">关闭</button>
                  <button class="miniBtn" data-action="save-compact-selected">保存上下文/压缩到选中 provider</button>
                  <button class="miniBtn" data-action="save-forced-model-selected">保存强制主模型</button>
                  <button class="miniBtn warn" data-action="clear-forced-model-selected">改为 Claude 自动路由</button>
                  <button class="miniBtn" data-action="sync-common-env-selected">同步通用 env 到全部</button>
                </div>
                <div class="muted" id="bridgeModelMeta">gpt-5.5 = 272000 context tokens / 128000 max output。</div>
              </div>
            </div>
            <div class="card guideSection" id="providerManageCard" data-guide="providerManage">
              <h2>Claude Provider 管理</h2>
              <div class="sectionHint">排查 token、当前项和 base_url。默认隐藏真实 token。</div>
              <div class="row">
                <button data-action="refresh">刷新</button>
                <button class="miniBtn" id="tokenToggle" data-action="toggle-tokens">显示 token</button>
                <button data-action="set-current-selected">设选中为当前</button>
                <button data-action="patch-selected">修复选中桥接</button>
                <button class="warn" data-action="repair-plus-pro">修复 Plus/Pro</button>
              </div>
              <div class="tableWrap">
                <table id="providersTable">
                  <thead>
                    <tr>
                      <th class="nameCol">name</th>
                      <th class="smallCol">当前</th>
                      <th class="accountCol">account</th>
                      <th class="urlCol">base_url</th>
                      <th class="smallCol">路由/模型</th>
                      <th class="smallCol">压缩</th>
                      <th class="tokenCol">token</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
            </div>
          </section>

          <section class="deckPage" id="page-codex">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">Codex CLI</h2>
                <p class="pageDesc">生成 launcher-only 启动器，不复制 OpenAI token，不改默认 ~/.codex。</p>
              </div>
              <button data-action="refresh">刷新</button>
            </div>
            <div class="card guideSection" id="cliHomeCard" data-guide="cliHome">
              <h2>单独 Codex CLI 启动器</h2>
              <div class="formGrid">
                <label>账号<select id="cliAccount"></select></label>
                <label>保存目录<input id="cliHome" placeholder="~/.codex-cli-pro20x" /></label>
                <label>启动器名称<input id="cliProfileName" placeholder="pro20x" /></label>
              </div>
              <div class="row">
                <button class="primary" data-action="create-cli-home">生成启动器</button>
                <button data-action="migrate-cli-home">迁移旧 CLI 目录</button>
              </div>
              <div class="paths" id="cliCommand"></div>
              <div class="muted mt10">可用账号：点“选用”自动填入推荐目录。</div>
              <div class="tableWrap mt10">
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
          </section>

          <section class="deckPage" id="page-api">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">通用 API 接入</h2>
                <p class="pageDesc">复制 OpenAI Base URL 或 Claude/Anthropic 环境变量；API key 是占位符，不显示真实 OAuth token。</p>
              </div>
            </div>
            <div class="card guideSection" id="apiAccessCard" data-guide="apiAccess">
              <div class="toolGrid">
                <div class="toolCard">
                  <div>
                    <div class="toolName">本地 API 配置</div>
                    <div class="toolText">选择要暴露给外部工具的 ChatGPT 账号。</div>
                    <div class="toolSelect">
                      <label for="simpleApiAccount">API 用哪个账号</label>
                      <select id="simpleApiAccount"></select>
                    </div>
                    <div class="apiEnvBox">
                      <div class="apiEnvLine">
                        <div class="apiEnvLabel">OPENAI_API_KEY</div>
                        <div class="apiEnvValue" id="apiAccessKey">sk-bridgedeck-local-placeholder</div>
                      </div>
                      <div class="apiEnvLine">
                        <div class="apiEnvLabel">OPENAI_BASE_URL</div>
                        <div class="apiEnvValue" id="apiAccessBaseUrl">选择账号后生成</div>
                      </div>
                      <div class="apiEnvLine">
                        <div class="apiEnvLabel">ANTHROPIC_AUTH_TOKEN</div>
                        <div class="apiEnvValue" id="anthropicAccessToken">local-bridge</div>
                      </div>
                      <div class="apiEnvLine">
                        <div class="apiEnvLabel">ANTHROPIC_BASE_URL</div>
                        <div class="apiEnvValue" id="anthropicAccessBaseUrl">选择账号后生成</div>
                      </div>
                    </div>
                  </div>
                  <div class="apiEnvActions">
                    <button class="miniBtn" data-action="copy-api-key">复制 API key</button>
                    <button class="miniBtn" data-action="copy-api-base-url">复制 Base URL</button>
                    <button class="miniBtn" data-action="copy-api-env">复制 .env</button>
                    <button class="miniBtn" data-action="copy-anthropic-token">复制 Anthropic token</button>
                    <button class="miniBtn" data-action="copy-anthropic-base-url">复制 Anthropic URL</button>
                    <button class="miniBtn" data-action="copy-anthropic-env">复制 Anthropic .env</button>
                    <button class="miniBtn" data-action="copy-anthropic-forced-env">复制强制主模型 env</button>
                  </div>
                  <div class="actualLine mt10" id="simpleApiActual">当前实际：选择账号后可用。</div>
                </div>
                <div class="toolCard">
                  <div>
                    <div class="toolName">复制指南</div>
                    <div class="toolText" id="apiAccessGuideAccount">沿用左侧 API 账号选择</div>
                    <div class="paths mt10" id="apiAccessGuideBaseUrl"></div>
                  </div>
                  <div class="apiEnvActions">
                    <button class="miniBtn" data-action="copy-api-base-url">复制 BASE_URL</button>
                    <button class="miniBtn" data-action="copy-api-env">复制 OpenAI env</button>
                    <button class="miniBtn" data-action="copy-claude-env">复制 Desktop Gateway</button>
                  </div>
                </div>
              </div>
              <div class="apiMatrix">
                <div class="apiCard ok">
                  <div class="apiCardTitle">OpenAI Responses</div>
                  <div class="apiCardMeta"><span class="mono">POST /v1/responses</span><br />Codex bridge 主路径，支持流式 reasoning keepalive。</div>
                </div>
                <div class="apiCard ok">
                  <div class="apiCardTitle">Anthropic Messages</div>
                  <div class="apiCardMeta"><span class="mono">POST /v1/messages</span><br />Claude Desktop 3P 使用 Claude-safe 路由名，BridgeDeck 映射到 GPT。</div>
                </div>
                <div class="apiCard ok">
                  <div class="apiCardTitle">Chat Completions</div>
                  <div class="apiCardMeta"><span class="mono">POST /v1/chat/completions</span><br />OpenAI 旧式工具接入路径，非流式和 SSE 都走 Responses。</div>
                </div>
                <div class="apiCard ok">
                  <div class="apiCardTitle">Scoped Models</div>
                  <div class="apiCardMeta"><span class="mono">GET /v1/models</span><br />同时返回 gpt-* 和 claude-* Desktop 路由；gpt-5.5 为 272k context / 128k max output。</div>
                </div>
              </div>
              <div class="apiExampleGrid">
                <div class="apiExample">
                  <div class="apiExampleTitle">OpenAI-compatible</div>
                  <div class="paths" id="apiOpenAiExample"></div>
                </div>
                <div class="apiExample">
                  <div class="apiExampleTitle">Claude Desktop 3P</div>
                  <div class="paths" id="apiClaudeExample"></div>
                </div>
              </div>
              <div class="muted mt10">gpt-5.5 thinking levels: low / medium / high / xhigh。minimal 不作为可选级别展示。</div>
            </div>
          </section>

          <section class="deckPage" id="page-services">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">本地服务</h2>
                <p class="pageDesc">UI 8899 和 Local Bridge 8876 分开控制；关闭 UI 不影响 8876。</p>
              </div>
              <button class="primary" data-action="refresh-services">刷新服务</button>
            </div>
            <div class="card guideSection" data-guide="services">
              <h2>服务状态</h2>
              <div id="serviceStatus" class="serviceGrid">服务状态加载中...</div>
              <div class="row">
                <button class="miniBtn" data-action="refresh-services">刷新服务</button>
                <button class="miniBtn" data-action="install-scan">安装扫描</button>
                <button class="miniBtn" data-action="proxy-diagnosis">一键网络检测</button>
                <button class="miniBtn" data-action="codex-desktop-doctor">Codex Desktop Doctor</button>
                <button class="miniBtn" data-action="codex-native-proxy-status">诊断 Codex 原生代理</button>
                <button class="miniBtn" data-action="repair-codex-native-proxy">修复 Codex 原生代理</button>
                <button class="miniBtn" data-action="normalize-codex-hooks-config">清理 hooks legacy key</button>
                <button class="miniBtn" data-action="repair-quota-query">一键修复额度查询</button>
                <button class="miniBtn" data-action="repair-codex-env-conflicts">清理环境冲突</button>
                <button class="miniBtn" data-action="start-local-bridge">启动 Local Bridge</button>
                <button class="miniBtn" data-action="restart-local-bridge">重启 Local Bridge</button>
                <button class="miniBtn warn" data-action="stop-local-bridge">停止 Local Bridge</button>
                <button class="miniBtn warn" data-action="stop-bridgedeck-ui">关闭 BridgeDeck UI</button>
              </div>
              <div id="serviceMessage" class="muted mt10">关闭 BridgeDeck UI 只停 8899，不影响 8876 Local Bridge。Codex 原生代理修复只改 ~/.codex/.env，不改模型、provider 或 config.toml。</div>
              <div id="installScan" class="recommend mt10">安装扫描未运行</div>
              <div id="codexDesktopDoctor" class="recommend mt10">Codex Desktop Doctor 未运行</div>
              <div id="proxyDiagnosis" class="recommend">未诊断</div>
            </div>
          </section>

          <section class="deckPage" id="page-diagnostics">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">诊断日志</h2>
                <p class="pageDesc">账号矩阵、Codex Provider、CLI Home 和执行日志集中排查。</p>
              </div>
              <button data-action="refresh">刷新</button>
            </div>
            <div class="card guideSection" id="statusCard" data-guide="status">
              <h2>账号状态检查</h2>
              <div class="sectionHint">自动检测 Claude Code、单独 Codex CLI、全局 Codex CLI 当前状态。Codex Desktop 默认保持原生。</div>
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
              <div class="muted mt10">CC Switch Codex OAuth Provider：用于授权和额度检查；BridgeDeck 全局入口以上面 Desktop 列为准。</div>
              <div class="tableWrap mt10">
                <table id="codexProvidersTable">
                  <thead>
                    <tr>
                      <th class="nameCol">名称</th><th class="smallCol">当前</th><th class="accountCol">绑定账号</th><th class="accountCol">实际账号</th><th class="smallCol">状态</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
              <div class="row mt10">
                <button class="miniBtn" data-action="preview-ccswitch-315-desktop-routes">预览 Claude Desktop 3.15 路由修复</button>
                <button class="miniBtn warn" data-action="apply-ccswitch-315-desktop-routes">应用 Claude Desktop 3.15 路由修复</button>
              </div>
              <div class="tableWrap mt10">
                <table id="claudeDesktopProvidersTable">
                  <thead>
                    <tr>
                      <th class="nameCol">Claude Desktop Provider</th><th class="smallCol">当前</th><th class="accountCol">账号</th><th class="urlCol">路由</th><th class="smallCol">状态</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
              <div id="ccswitch315Status" class="recommend mt10"></div>
              <div id="diagnosis" class="recommend"></div>
              <div class="muted mt10">已配置 CLI 目录：这里只显示已经存在的 CODEX_HOME。</div>
              <div class="tableWrap mt10">
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
            <div class="card guideSection" data-guide="diagnostics">
              <h2>Claude Code 停顿诊断</h2>
              <div class="sectionHint">只读分析 Local Bridge 流式日志和 Claude hooks；不会修改 settings.json 或 Codex config。</div>
              <div id="streamDiagnostics" class="recommend">流式诊断加载中...</div>
              <div id="hookRiskDiagnostics" class="recommend mt10">Hook 诊断加载中...</div>
            </div>
            <div class="card guideSection" data-guide="log">
              <h2>执行日志</h2>
              <textarea id="log" readonly></textarea>
            </div>
          </section>

          <section class="deckPage" id="page-account-pool">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">账户池</h2>
                <p class="pageDesc">管理默认账户、账户轮换策略。切换账户不影响已配置的工具地址。</p>
              </div>
              <button data-action="refresh">刷新</button>
            </div>
            <div class="card">
              <h2>当前默认账户</h2>
              <div id="defaultAccountDisplay" class="recommend">加载中...</div>
              <div class="row mt10">
                <label>切换默认账户</label>
                <select id="accountPoolSelect"></select>
                <button class="primary" data-action="set-default-account">切换</button>
              </div>
            </div>
            <div class="card">
              <h2>账户列表</h2>
              <div class="tableWrap">
                <table id="accountPoolTable">
                  <thead>
                    <tr>
                      <th class="accountCol">Account ID</th>
                      <th class="accountCol">邮箱</th>
                      <th class="smallCol">默认</th>
                      <th class="smallCol">来源</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
            </div>
          </section>

          <section class="deckPage" id="page-api-keys">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">API Keys</h2>
                <p class="pageDesc">生成统一入口 API Key，所有工具使用同一地址 <code>http://127.0.0.1:8876/v1</code></p>
              </div>
              <button data-action="refresh">刷新</button>
            </div>
            <div class="card">
              <h2>创建新 Key</h2>
              <div class="row">
                <input type="text" id="newKeyName" placeholder="Key 名称 (可选)" />
                <button class="primary" data-action="create-api-key">创建 API Key</button>
              </div>
              <div id="newKeyResult" class="recommend hidden"></div>
            </div>
            <div class="card">
              <h2>已创建的 Keys</h2>
              <div class="tableWrap">
                <table id="apiKeysTable">
                  <thead>
                    <tr>
                      <th class="nameCol">名称</th>
                      <th class="urlCol">Key</th>
                      <th class="smallCol">状态</th>
                      <th class="smallCol">操作</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
            </div>
          </section>

          <section class="deckPage" id="page-service-control">
            <div class="pageHeader">
              <div>
                <h2 class="pageTitle">服务控制</h2>
                <p class="pageDesc">管理 BridgeDeck 服务、launchd 守护进程。</p>
              </div>
              <button data-action="refresh">刷新</button>
            </div>
            <div class="card">
              <h2>当前服务状态</h2>
              <div id="serviceStatusDisplay" class="recommend">加载中...</div>
              <div class="row mt10">
                <button class="primary" data-action="service-start">启动服务</button>
                <button class="warn" data-action="service-stop">停止服务</button>
                <button data-action="service-restart">重启服务</button>
              </div>
            </div>
            <div class="card">
              <h2>Launchd 守护进程</h2>
              <div id="launchdStatus" class="recommend">加载中...</div>
              <div class="row mt10">
                <button data-action="launchd-unload">卸载 launchd</button>
                <button class="primary" data-action="launchd-load">加载 launchd</button>
              </div>
            </div>
          </section>
        </div>

        <aside class="guideDock">
          <div class="card">
            <h2 id="guideTitle">当前操作</h2>
            <div id="guideTarget" class="guideTarget">随当前版面自动切换</div>
            <ol id="guideSteps" class="steps"></ol>
          </div>
        </aside>
      </main>
    </div>
  </div>

  <script nonce="__CSP_NONCE__">
    const CSRF_TOKEN = "__CSRF_TOKEN__";
    let lastData = null;
    let tokenVisible = false;
    let lastAccounts = [];
    let activeOAuthFlowId = '';
    let oauthPollTimer = null;
    let oauthExpiryTimer = null;
    let activeOAuthExpiresAt = '';
    const BRIDGE_MODELS = __BRIDGE_MODELS_JSON__;
    const DEFAULT_BRIDGE_MODEL = 'gpt-5.5';
    const DEFAULT_COMPACT_WINDOW = '272000';
    const CONSERVATIVE_COMPACT_WINDOW = '220000';
    const DEFAULT_COMPACT_PCT = '80';
    const LOCAL_BRIDGE_BASE_URL = "__LOCAL_BRIDGE_BASE_URL__";
    const LOCAL_API_KEY_PLACEHOLDER = 'sk-bridgedeck-local-placeholder';
    const LOCAL_ANTHROPIC_AUTH_TOKEN = 'local-bridge';
    const CLAUDE_DESKTOP_ROUTES = [
      ['claude-haiku-4-5', 'Haiku 4.5'],
      ['claude-sonnet-4-6', 'Sonnet 4.6'],
      ['claude-opus-4-7', 'Opus 4.7']
    ];
    const GUIDES = {
      oauth: {
        title: 'ChatGPT 授权',
        target: '入口切换：新增或重新授权账号',
        steps: [
          '点击“生成授权验证码”。',
          '在打开的 OpenAI 设备授权页输入验证码。',
          '确认授权后回到 BridgeDeck 检查状态。',
          '授权完成后刷新账号列表，再选择入口使用。'
        ]
      },
      simpleFlow: {
        title: '日常模式',
        target: '上方板块：每个入口单独选账号',
        steps: [
          'Claude Code、单独 Codex CLI、全局 Codex CLI 各自选账号。',
          'Claude Code 卡片只影响 Claude Code 当前账号。',
          '“当前实际”显示 CC Switch 当前 Claude Provider。',
          '单独 Codex CLI 只生成独立启动器，不改变全局默认。',
          '全局 Codex CLI 只生成固定入口和 OMC/tmux shim，不改 Codex Desktop。',
          'Codex Desktop Stability Route 已禁用，保留原生配置。',
          '三个入口可以同号，也可以不同号。',
          '下方高级区只在排查时使用。'
        ]
      },
      apiAccess: {
        title: '通用 API 接入',
        target: '上方板块：API endpoint 和 copy-safe 配置',
        steps: [
          '选择要暴露给工具的 ChatGPT 账号。',
          'BASE_URL 使用账号级路径，不暴露真实 OAuth token。',
          'OpenAI-compatible 工具使用 placeholder API key。',
          'Claude Desktop 3P 使用账号级 gateway，模型列表只暴露 claude-* 路由。',
          '这里只复制配置，不写入 provider，也不改变当前运行工具。'
        ]
      },
      quota: {
        title: '额度与自动切换',
        target: '额度版面：OpenAI 账号额度和自动切换',
        steps: [
          '先看当前账号卡片是否标记“当前使用”。',
          '5 小时和周额度任意一项接近阈值时，自动切换才有意义。',
          '只勾选你希望 BridgeDeck 接管的入口。',
          '保存后再点“立即检查并切换”。',
          '新授权账号没有 Local Bridge 时，先创建桥接。'
        ]
      },
      services: {
        title: '本地服务',
        target: '服务版面：8899 UI 和 8876 Local Bridge',
        steps: [
          '8876 Local Bridge 是 API 实际入口。',
          '8899 BridgeDeck UI 只负责管理界面。',
          '代理异常时先点“诊断代理链路”。',
          '额度查询异常时点“一键修复额度查询”。',
          '关闭 UI 不会停止 8876 Local Bridge。'
        ]
      },
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
        title: '单独 Codex CLI',
        target: '右侧板块：单独 Codex CLI',
        steps: [
          '在可用账号表点“选用”。',
          '保存目录保持 ~/.codex-cli-xxx。',
          '点击“生成启动器”。',
          '用页面输出的 launcher 启动该账号。',
          '这不会改变全局 Codex CLI 默认账号。'
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
          '~/.codex/auth.json 只代表本机 token；Desktop/全局入口看实际状态。',
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
      },
      usage: {
        title: '使用详情',
        target: '使用详情版面：HUD 仪表盘和请求列表',
        steps: [
          '上方 HUD 看缓存命中率和总 Token。',
          '输入/输出、缓存写入、命中缓存、未命中缓存分开显示。',
          '下方列表按最近请求倒序展示。',
          '状态不是 200 时，切到本地服务或诊断日志排查。',
          '这里只读本地 bridge 状态，不会切换账号或重启服务。'
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
    function accountLabel(item) {
      if (!item) return '';
      return maskEmail(item.email || item.label || maskId(item.account_id || ''));
    }
    function accountSlug(item) {
      if (!item) return '';
      const fallback = String(item.account_id || '').slice(0, 8);
      const label = item.email && item.email.includes('@') ? item.email.split('@')[0] : fallback;
      return label || fallback;
    }
    function findAccount(accountId) {
      return lastAccounts.find((a) => a.account_id === accountId);
    }
    function currentClaudeProvider(data) {
      if (!data) return null;
      const fromSettings = data.providers.find((p) => p.id === data.current_provider_from_settings);
      if (fromSettings) return fromSettings;
      return data.providers.find((p) => p.is_current) || null;
    }
    function isBridgeClaudeProvider(provider) {
      return Boolean(provider && provider.base_url && provider.base_url.includes('/accounts/'));
    }
    function providerDisplayName(provider) {
      if (!provider) return '未检测到';
      const account = provider.account_id ? findAccount(provider.account_id) : null;
      if (account) return `${provider.name} / ${accountLabel(account)}`;
      return provider.name || maskId(provider.id || '');
    }
    function accountDisplay(accountId) {
      const account = findAccount(accountId);
      if (account) return accountLabel(account);
      return maskId(accountId || '');
    }
    function desktopUnmappedText(desktop) {
      const mode = statusText(desktop.managed_by || 'unknown');
      if (!desktop.detected) return '未检测';
      if (desktop.managed_by === 'default') return '默认配置 / 账号未映射';
      return `${mode || '未知配置'} / 账号未映射`;
    }
    function desktopAccountText(data) {
      const desktop = data.codex_desktop || {};
      if (desktop.account_id) return accountDisplay(desktop.account_id);
      return desktopUnmappedText(desktop);
    }
    function desktopModeText(data) {
      const desktop = data.codex_desktop || {};
      const mode = statusText(desktop.managed_by || 'unknown');
      return desktop.base_url ? `${mode} / ${humanPath(desktop.config_path || '')}` : mode;
    }
    function currentLauncherAccountText(data) {
      const launcher = data.current_codex_launcher || {};
      if (launcher.account_id) return accountDisplay(launcher.account_id);
      return launcher.exists ? '未识别' : '未生成';
    }
    function currentLauncherModeText(data) {
      const launcher = data.current_codex_launcher || {};
      if (!launcher.exists) return 'codex-current.command 未生成';
      const desktop = data.codex_desktop || {};
      const mismatch = desktop.account_id && launcher.account_id && desktop.account_id !== launcher.account_id;
      const state = mismatch ? '账号不一致' : '固定入口';
      return `${state} / ${humanPath(launcher.path || '')}`;
    }
    function omcShimText(data) {
      const shim = data.omc_codex_shim || {};
      return shim.active ? 'OMC/tmux 已接管 codex' : 'OMC/tmux 未接管 codex';
    }
    function fmtMetricNumber(value) {
      const num = Number(value);
      if (!Number.isFinite(num)) return '-';
      return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(num);
    }
    function fmtPercent(value) {
      const num = Number(value);
      if (!Number.isFinite(num)) return '-';
      return `${Math.round(num * 100)}%`;
    }
    function fmtDuration(value) {
      const ms = Number(value);
      if (!Number.isFinite(ms) || ms <= 0) return '-';
      return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
    }
    function fmtDateTime(value) {
      const seconds = Number(value);
      if (!Number.isFinite(seconds) || seconds <= 0) return '-';
      const date = new Date(seconds * 1000);
      return date.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }
    function providerNameForUsage(event, data) {
      const accountId = event && event.account_id ? String(event.account_id) : '';
      const providers = data.providers || [];
      const codexProviders = data.codex_providers || [];
      const current = providers.find((p) => p.is_current && p.account_id === accountId);
      if (current) return current.name || 'Local Codex Bridge';
      const provider = providers.find((p) => p.account_id === accountId);
      if (provider) return provider.name || 'Local Codex Bridge';
      const codex = codexProviders.find((p) => p.token_account_id === accountId || p.meta_account_id === accountId);
      if (codex) return codex.name || 'Local Codex Bridge';
      return accountId ? `Local Codex Bridge - ${maskId(accountId)}` : 'Local Codex Bridge';
    }
    function usageModelCell(event) {
      const requested = String(event.requested_model || event.model || '').trim();
      const actual = String(event.actual_model || event.model || requested || '').trim();
      if (requested && actual && requested !== actual) {
        const routeLabel = event.desktop_route ? 'Desktop 路由' : '映射到实际模型';
        return `<span class="usageModelMain">${esc(requested)}</span><span class="usageMeta">-> ${esc(actual)}</span><span class="usageTag desktop">${esc(routeLabel)}</span>`;
      }
      return `<span class="usageModelMain">${esc(actual || '-')}</span><span class="usageTag chat">实际模型</span>`;
    }
    function usageEntryCell(event) {
      const client = String(event.client_label || event.request_type || '未知入口').trim();
      const port = Number(event.bridge_port || 0);
      const route = String(event.request_type || event.route_path || '-').trim();
      const source = String(event.source || 'proxy').trim();
      const portText = port > 0 ? `:${port}` : '-';
      const cacheKey = event.prompt_cache_key_present ? 'cache key: on' : `cache key: ${event.cache_key_source || 'none'}`;
      return `<span class="usageEntryMain">${esc(client)}</span><span class="usageMeta">${esc(portText)} / ${esc(route)} / ${esc(cacheKey)}</span><span class="usageTag">${esc(source)}</span>`;
    }
    function setMetricIcon(id, state) {
      const el = document.getElementById(id);
      if (!el) return;
      el.className = `metricIcon ${state || ''}`.trim();
    }
    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }
    function renderOverviewDashboard(data) {
      const codexProviders = data.codex_providers || [];
      const mismatchedProviders = codexProviders.filter((provider) => provider.token_mismatch);
      const matchedProviders = codexProviders.length - mismatchedProviders.length;
      setText('metricAccountValue', codexProviders.length ? `${matchedProviders}/${codexProviders.length}` : '-');
      setText('metricAccountOk', matchedProviders);
      setText('metricAccountRisk', mismatchedProviders.length);
      setMetricIcon('metricAccountIcon', mismatchedProviders.length ? 'bad' : 'ok');

      const usage = data.usage_metrics || {};
      const hasUsageRequests = Number(usage.request_count || 0) > 0;
      const totalTokens = Number(usage.total_tokens);
      const inputTokens = Number(usage.input_tokens);
      const outputTokens = Number(usage.output_tokens);
      const cachedTokens = Number(usage.cached_tokens);
      const cacheCreationTokens = Number(usage.cache_creation_tokens);
      setText('metricTokenValue', hasUsageRequests && Number.isFinite(totalTokens) ? fmtMetricNumber(totalTokens) : '等待请求');
      setText('metricTokenInput', hasUsageRequests && Number.isFinite(inputTokens) ? fmtMetricNumber(inputTokens) : '-');
      setText('metricTokenOutput', hasUsageRequests && Number.isFinite(outputTokens) ? fmtMetricNumber(outputTokens) : '-');
      setText('metricCacheValue', hasUsageRequests && Number.isFinite(cachedTokens) ? fmtMetricNumber(cachedTokens) : '等待请求');
      setText('metricCacheCreate', hasUsageRequests && Number.isFinite(cacheCreationTokens) ? fmtMetricNumber(cacheCreationTokens) : '-');
      setText('metricCacheHit', hasUsageRequests && Number.isFinite(cachedTokens) ? fmtMetricNumber(cachedTokens) : '-');

      const provider = currentClaudeProvider(data);
      const claudeAccount = provider && provider.account_id ? accountDisplay(provider.account_id) : '外部供应商/未检测到';
      setText('overviewClaudeMain', claudeAccount);
      setText('overviewClaudeMeta', provider ? `${provider.name || 'Claude Provider'} / ${provider.model || '未指定模型'}` : '未检测到当前 Claude Provider');
      setText('overviewDesktopMain', desktopAccountText(data));
      setText('overviewDesktopMeta', desktopModeText(data));
      setText('overviewOmniMain', currentLauncherAccountText(data));
      setText('overviewOmniMeta', `${currentLauncherModeText(data)}；${omcShimText(data)}`);

      const tasks = [];
      const mismatches = data.codex_providers.filter((p) => p.token_mismatch);
      mismatches.forEach((p) => {
        tasks.push({ cls: 'bad', text: `${p.name}: 绑定 ${maskId(p.meta_account_id || '')}，实际 ${maskId(p.token_account_id || '')}` });
      });
      const desktop = data.codex_desktop || {};
      if (desktop.detected && !desktop.account_id) {
        tasks.push({ cls: 'warn', text: `Desktop/默认 CLI：${desktopUnmappedText(desktop)}，固定入口仍可走 ${currentLauncherAccountText(data)}` });
      }
      if (!tasks.length) {
        tasks.push({ cls: 'ok', text: '账号、入口和 provider 绑定未发现阻断项。' });
      }
      const taskBox = document.getElementById('overviewTasks');
      if (taskBox) {
        taskBox.innerHTML = tasks.map((item) => `<div class="taskItem ${item.cls}">${esc(item.text)}</div>`).join('');
      }
    }
    function renderUsageDashboard(data) {
      const usage = data.usage_metrics || {};
      const events = Array.isArray(data.usage_events) ? [...data.usage_events].reverse() : [];
      const hitRate = Number(usage.cache_hit_rate);
      const hitRateValue = Number.isFinite(hitRate) ? Math.max(0, Math.min(1, hitRate)) : 0;
      const dial = document.getElementById('usageHudDial');
      if (dial) dial.style.setProperty('--hit-angle', `${hitRateValue * 270}deg`);
      setText('usageHudHitRate', Number.isFinite(hitRate) ? fmtPercent(hitRate) : '-');
      setText('usageHudRequests', fmtMetricNumber(usage.request_count || 0));
      setText('usageHudTokens', fmtMetricNumber(usage.total_tokens || 0));
      setText('usageHudInOut', `${fmtMetricNumber(usage.input_tokens || 0)} / ${fmtMetricNumber(usage.output_tokens || 0)}`);
      setText('usageHudCacheWrite', fmtMetricNumber(usage.cache_creation_tokens || 0));
      setText('usageHudCacheRead', fmtMetricNumber(usage.cached_tokens || 0));
      setText('usageHudCacheMiss', `${fmtMetricNumber(usage.cache_miss_tokens || 0)} · ${fmtPercent(usage.cache_miss_rate || 0)}`);

      const body = document.getElementById('usageRows');
      if (!body) return;
      if (!events.length) {
        body.innerHTML = '<tr><td colspan="11">采集已启用，等待下一次通过 8876 Local Codex Bridge 的 LLM 请求；升级前的历史请求不会回填。</td></tr>';
        return;
      }
      body.innerHTML = events.map((event) => {
        const status = Number(event.status_code || 0);
        const statusClass = status >= 200 && status < 300 ? 'ok' : (status ? 'bad' : 'muted');
        return `<tr>
          <td>${esc(fmtDateTime(event.at))}</td>
          <td>${usageEntryCell(event)}</td>
          <td>${esc(providerNameForUsage(event, data))}</td>
          <td class="mono">${usageModelCell(event)}</td>
          <td>${esc(fmtMetricNumber(event.input_tokens || 0))}</td>
          <td>${esc(fmtMetricNumber(event.output_tokens || 0))}</td>
          <td>${esc(fmtMetricNumber(event.cache_creation_tokens || 0))}</td>
          <td>${esc(fmtMetricNumber(event.cached_tokens || 0))}</td>
          <td>${esc(fmtMetricNumber(event.cache_miss_tokens || 0))}</td>
          <td>${esc(fmtPercent(event.cache_hit_rate || 0))}</td>
          <td><span class="${statusClass}">${esc(status || '-')}</span><br><span class="muted">${esc(fmtDuration(event.duration_ms))}</span></td>
        </tr>`;
      }).join('');
    }
    function renderOverviewQuotaMetrics(payload) {
      const quotas = payload && Array.isArray(payload.quotas) ? payload.quotas : [];
      if (!quotas.length) {
        setText('metricQuotaValue', '未返回');
        setText('metricQuotaAccount', '-');
        setText('metricQuotaRemaining', '-');
        setMetricIcon('metricQuotaIcon', 'warn');
        return;
      }
      const current = currentClaudeProvider(lastData || {});
      const currentQuota = quotas.find((q) => current && q.account_id === current.account_id) || quotas[0];
      const usedValues = (currentQuota.windows || [])
        .map((w) => Number(w.used_percent))
        .filter((value) => Number.isFinite(value));
      const maxUsed = usedValues.length ? Math.max(...usedValues) : NaN;
      setText('metricQuotaValue', Number.isFinite(maxUsed) ? `${fmtMetricNumber(maxUsed)}%` : '未返回');
      setText('metricQuotaAccount', maskEmail(currentQuota.email || currentQuota.label || maskId(currentQuota.account_id || '')));
      const remaining = Number(currentQuota.effective_remaining_units);
      setText('metricQuotaRemaining', Number.isFinite(remaining) ? fmtMetricNumber(remaining) : '-');
      setMetricIcon('metricQuotaIcon', currentQuota.quota_status === 'limit_reached' ? 'bad' : (currentQuota.quota_status === 'near_limit' ? 'warn' : 'ok'));
    }
    function renderActualCurrentAccounts(data) {
      const box = document.getElementById('actualCurrentAccounts');
      if (!box) return;
      const provider = currentClaudeProvider(data);
      const claudeAccount = provider && provider.account_id ? accountDisplay(provider.account_id) : '外部供应商/未检测到';
      const codexAccount = desktopAccountText(data);
      const launcherAccount = currentLauncherAccountText(data);
      box.innerHTML = `实际当前使用：Claude Code <strong>${esc(claudeAccount)}</strong>；全局 Codex CLI <strong>${esc(codexAccount)}</strong>；OMC/tmux <strong>${esc(launcherAccount)}</strong>`;
    }
    function renderPluginSync(data) {
      const box = document.getElementById('pluginSyncStatus');
      if (!box) return;
      const status = data.plugin_status || {};
      const sync = data.plugin_sync || {};
      if (status.ok === false || sync.ok === false) {
        box.innerHTML = `<span class="bad">插件同步检查失败：${esc(status.error || sync.error || 'unknown')}</span>`;
        return;
      }
      const missing = [...(status.missing_from_common || []), ...(status.missing_from_settings || [])];
      const added = sync.added || [];
      const changed = Boolean(sync.changed);
      if (changed && added.length) {
        box.innerHTML = `<span class="ok">已自动同步 ${esc(added.length)} 个插件</span>：${esc(added.join(', '))}`;
        return;
      }
      if (missing.length) {
        box.innerHTML = `<span class="warnText">发现 ${esc(missing.length)} 个插件未写入通用配置，点击一键同步。</span>`;
        return;
      }
      box.innerHTML = `<span class="ok">已同步</span>：已安装 ${esc(status.installed_count || 0)} 个；common ${esc(status.common_enabled_count || 0)} 个；当前 settings ${esc(status.settings_enabled_count || 0)} 个`;
    }
    function renderAttributionHeader(data) {
      const box = document.getElementById('attributionHeaderStatus');
      const paths = document.getElementById('attributionHeaderPaths');
      if (!box || !paths) return;
      const payload = data.claude_attribution_header || {};
      const status = payload.status || 'unknown';
      const cls = status === 'disabled' ? 'ok' : (status === 'unknown' ? 'muted' : 'warnText');
      let text = '未检测到 Claude Code 配置。';
      if (status === 'disabled') {
        text = '已关闭 Claude Code billing attribution header。第三方/本地模型更容易命中 prompt cache。';
      } else if (status === 'enabled') {
        text = 'Claude Code 可能注入动态 x-anthropic-billing-header，建议关闭以减少 cache 失效、token 增加和推理变慢。';
      } else if (status === 'inconsistent') {
        text = '不同配置源设置不一致，某些启动方式仍可能注入动态 header。建议一键修复。';
      }
      box.innerHTML = `<span class="${cls}">${esc(status)}</span> · ${esc(text)}`;
      const sources = Array.isArray(payload.sources) ? payload.sources : [];
      paths.innerHTML = sources.length
        ? sources.map((item) => `${esc(item.label || item.id || '')}: <span class="${item.status === 'disabled' ? 'ok' : (item.status === 'unknown' ? 'muted' : 'warnText')}">${esc(item.status || '')}</span> · ${esc(humanPath(item.path || ''))}`).join('<br>')
        : '-';
      paths.classList.add('hidden');
    }
    function renderSimpleActuals(data) {
      const box = document.getElementById('simpleClaudeActual');
      const provider = currentClaudeProvider(data);
      if (box) {
        if (!provider) {
          box.innerHTML = '当前实际：<strong class="warnText">未检测到</strong>';
        } else {
          const mode = isBridgeClaudeProvider(provider) ? 'BridgeDeck 同步' : '外部供应商';
          const cls = isBridgeClaudeProvider(provider) ? 'ok' : 'warnText';
          box.innerHTML = `当前实际：<strong>${esc(providerDisplayName(provider))}</strong><br><span class="${cls}">${esc(mode)}</span>`;
        }
      }
      const cliBox = document.getElementById('simpleCliActual');
      if (cliBox) {
        const selected = selectedAccount('simpleCliAccount');
        const launcher = selected ? (data.cli_launchers || []).find((item) => item.account_id === selected.account_id && !item.is_current_launcher) : null;
        const launcherText = launcher ? `launcher 已生成：${humanPath(launcher.path || '')}` : 'launcher 未生成';
        cliBox.innerHTML = selected
          ? `当前实际：<strong>${esc(accountLabel(selected))}</strong><br><span class="${launcher ? 'ok' : 'warnText'}">${esc(launcherText)}</span>`
          : '当前实际：<strong class="warnText">未选择</strong>';
      }
      const defaultBox = document.getElementById('simpleDefaultActual');
      if (defaultBox) {
        const launcher = data.current_codex_launcher || {};
        const desktop = data.codex_desktop || {};
        const mismatch = desktop.account_id && launcher.account_id && desktop.account_id !== launcher.account_id;
        const shimOk = Boolean((data.omc_codex_shim || {}).active);
        defaultBox.innerHTML = `当前实际：<strong>${esc(desktopAccountText(data))}</strong><br><span class="${mismatch ? 'bad' : 'ok'}">${esc(desktopModeText(data))}</span><br><span class="${mismatch ? 'bad' : 'ok'}">固定入口：${esc(currentLauncherAccountText(data))} / ${esc(currentLauncherModeText(data))}</span><br><span class="${shimOk ? 'ok' : 'warnText'}">${esc(omcShimText(data))}</span>`;
      }
      const desktopBox = document.getElementById('simpleDesktopActual');
      if (desktopBox) {
        const desktop = data.codex_desktop || {};
        const risk = (desktop.risk_flags || []).includes('desktop_bridgedeck_provider');
        const staticFlags = (desktop.risk_flags || []).filter((flag) => String(flag).startsWith('desktop_static_'));
        const extras = staticFlags.length ? `<br><span class="warnText">检测到静态项：${esc(staticFlags.join(', '))}</span>` : '';
        desktopBox.innerHTML = `当前实际：<strong>${esc(desktopAccountText(data))}</strong><br><span class="${risk ? 'warnText' : 'ok'}">${esc(desktopModeText(data))}</span>${extras}`;
      }
      renderApiAccess();
    }
    function renderAutoSwitchConfig(data) {
      const config = data.auto_switch || {};
      document.getElementById('autoSwitchEnabled').checked = Boolean(config.enabled);
      document.getElementById('autoSwitchClaude').checked = config.claude !== false;
      document.getElementById('autoSwitchDefaultCodex').checked = Boolean(config.default_codex);
      const last = config.last_result || {};
      if (last.message || last.selected_account_id) {
        document.getElementById('autoSwitchStatus').textContent = last.selected_account_id
          ? `上次选择：${accountDisplay(last.selected_account_id)}，${quotaStatusText(last.selected_quota_status)}`
          : `上次结果：${last.message || '无'}`;
      }
    }
    function quotaStatusText(value) {
      const map = {
        ok: '可用',
        near_limit: '接近限额',
        limit_reached: '已达限',
        refresh_token_reused: '需重新授权',
        unsupported_region: '地区受限',
        bridge_down: 'bridge 断开',
        proxy_down: '代理失败',
        network_error: '查询失败'
      };
      return map[value] || value || '未知';
    }
    function quotaStatusClass(value) {
      return value === 'ok' ? 'ok' : (value === 'near_limit' ? 'warn' : 'bad');
    }
    function quotaPercentClass(value) {
      const used = Number(value);
      if (!Number.isFinite(used)) return 'bad';
      return used >= 100 ? 'bad' : (used >= 80 ? 'warn' : 'ok');
    }
    function quotaWindowLabel(windowInfo) {
      const seconds = Number(windowInfo?.window_seconds || windowInfo?.limit_window_seconds || 0);
      if (seconds >= 600000) return '周限额';
      if (seconds >= 17000 && seconds <= 19000) return '5 小时限额';
      return windowInfo?.name || '额度';
    }
    function quotaResetText(windowInfo) {
      const raw = Number(windowInfo?.reset_at || 0);
      if (!Number.isFinite(raw) || raw <= 0) return '';
      const date = new Date(raw > 1000000000000 ? raw : raw * 1000);
      if (Number.isNaN(date.getTime())) return '';
      return date.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }
    function quotaMeter(windowInfo, labelPrefix='') {
      const used = Math.max(0, Math.min(100, Number(windowInfo?.used_percent ?? 0)));
      const cls = quotaPercentClass(used);
      const label = `${labelPrefix}${quotaWindowLabel(windowInfo)}`;
      const reset = quotaResetText(windowInfo);
      return `<div class="quotaMeter">
        <div class="quotaMeterMeta"><span>${esc(label)}</span><strong>${esc(used)}%</strong><span class="quotaReset">${esc(reset)}</span></div>
        <progress class="quotaProgress ${cls}" value="${esc(used)}" max="100"></progress>
      </div>`;
    }
    function quotaPlanLabel(q) {
      const plan = String(q.plan_type || '').trim();
      const factor = Number(q.capacity_factor || 0);
      if (factor >= 20) return 'Pro 20x';
      if (factor >= 5) return 'Pro 5x';
      if (plan) return plan.charAt(0).toUpperCase() + plan.slice(1);
      return '未知套餐';
    }
    function renderQuotaBoard(payload) {
      const board = document.getElementById('quotaBoard');
      const quotas = payload.quotas || [];
      if (!quotas.length) {
        board.textContent = '没有可显示的 OpenAI 账号额度。';
        return;
      }
      const current = currentClaudeProvider(lastData || {});
      board.innerHTML = quotas.map((q) => {
        const status = q.quota_status || 'unknown';
        const cls = quotaStatusClass(status);
        const currentCls = current && current.account_id === q.account_id ? ' current' : '';
        const windows = (q.windows || []).map((w) => quotaMeter(w)).join('');
        const spark = (q.additional_limits || []).find((item) => {
          const label = `${item.limit_name || ''} ${item.metered_feature || ''}`.toLowerCase();
          return label.includes('spark') || label.includes('bengalfox') || label.includes('gpt-5.3-codex');
        });
        const sparkWindows = spark
          ? (spark.windows || []).map((w) => quotaMeter(w, 'GPT-5.3-Codex-Spark ')).join('')
          : '';
        const remaining = Number(q.effective_remaining_units);
        const remainingText = Number.isFinite(remaining)
          ? `<span class="badge ok">剩余 ${esc(remaining)} 单位</span>`
          : '';
        return `<div class="quotaPill${currentCls}">
          <div class="quotaHead">
            <div>
              <div class="quotaTitle">${esc(maskEmail(q.email || q.label || maskId(q.account_id || '')))}</div>
              <div class="quotaMeta">
                <span class="badge warn">${esc(quotaPlanLabel(q))}</span>
                <span class="badge ${cls}">${esc(quotaStatusText(status))}</span>
                ${currentCls ? '<span class="badge ok">当前使用</span>' : ''}
                ${remainingText}
              </div>
            </div>
            <span class="muted">x${esc(q.capacity_factor || 1)}</span>
          </div>
          <div>${windows || '<div class="quotaWindows">主额度未返回</div>'}</div>
          <div>${spark ? `${sparkWindows || '<div class="quotaWindows">Spark 额度未返回</div>'}` : '<div class="quotaWindows">Spark：未返回</div>'}</div>
        </div>`;
      }).join('');
    }
    function renderMissingBridgeStatus(payload) {
      const box = document.getElementById('missingBridgeStatus');
      if (!box) return;
      const missing = payload.missing || [];
      if (!missing.length) {
        box.innerHTML = '<span class="ok">所有已授权 OpenAI 账号都已经有 Local Codex Bridge。</span>';
        return;
      }
      box.innerHTML = `<span class="warnText">发现 ${missing.length} 个已授权但未桥接的新账号：</span> ${missing.map((item) => esc(maskEmail(item.email || item.label || maskId(item.account_id || '')))).join('，')}`;
    }
    function renderAimamiSync(payload) {
      const box = document.getElementById('aimamiSyncStatus');
      if (!box) return;
      const data = payload || {};
      const summary = data.summary || {};
      if (!data.detected) {
        box.innerHTML = `<span class="muted">未检测到 AiMaMi registry。</span>`;
        return;
      }
      const candidates = data.candidates || [];
      const lines = candidates.slice(0, 8).map((item) => {
        const label = maskEmail(item.email || '') || maskId(item.account_id || '');
        const status = item.status || 'skipped';
        const cls = status === 'skipped' ? 'warnText' : (status === 'unchanged' ? 'muted' : 'ok');
        const reason = item.reason ? ` / ${item.reason}` : '';
        return `<div><span class="${cls}">${esc(status)}</span> ${esc(label)}${esc(reason)}</div>`;
      }).join('');
      const more = candidates.length > 8 ? `<div class="muted">另有 ${candidates.length - 8} 个未显示。</div>` : '';
      box.innerHTML = `
        <div>可导入 ${esc(summary.importable || 0)} 个：new ${esc(summary.new || 0)}，updated ${esc(summary.updated || 0)}，unchanged ${esc(summary.unchanged || 0)}，skipped ${esc(summary.skipped || 0)}。</div>
        ${lines || '<div class="muted">没有账号快照。</div>'}
        ${more}
      `;
    }
    function renderAimamiFollow(payload) {
      const data = payload || {};
      const enabled = Boolean(data.enabled);
      const checkbox = document.getElementById('aimamiFollowEnabled');
      if (checkbox) checkbox.checked = enabled;
      const box = document.getElementById('aimamiFollowStatus');
      if (!box) return;
      const result = data.last_result || {};
      const reason = result.reason || (enabled ? '等待同步' : 'follow_disabled');
      const action = result.action || 'noop';
      const account = result.selected_account_id ? accountDisplay(result.selected_account_id) : '-';
      const cls = action === 'switched' || action === 'unchanged' ? 'ok' : (action === 'deferred' ? 'warnText' : 'muted');
      box.innerHTML = `<span class="${cls}">${esc(enabled ? 'on' : 'off')}</span> · ${esc(action)} / ${esc(reason)} · ${esc(account)}`;
    }
    function renderAimamiExport(payload) {
      const box = document.getElementById('aimamiExportStatus');
      if (!box) return;
      const data = payload || {};
      if (data.verification) {
        const verification = data.verification || {};
        const missing = data.missing_in_aimami || [];
        const gate = verification.verified ? '<span class="ok">verified</span>' : '<span class="bad">verification required</span>';
        const running = data.aimami_running ? '<span class="warnText">AiMaMi running: reload after injection</span>' : '<span class="muted">AiMaMi not detected running</span>';
        const profile = data.schema_profile || {};
        const compatible = profile.compatible_with_injection ? '<span class="ok">native schema matched</span>' : '<span class="warnText">schema not verified</span>';
        const reason = data.reason ? `<div class="warnText">${esc(data.reason)}</div>` : '';
        const rows = missing.map((item) => {
          const label = maskEmail(item.email || '') || maskId(item.account_id || '');
          return `<label class="toggleLine"><input type="checkbox" class="aimamiExportAccount" value="${esc(item.account_id || '')}" checked> ${esc(label)}</label>`;
        }).join('');
        box.innerHTML = `<div>Snapshot injection: ${gate} · ${compatible} · ${running}</div><div class="muted">推荐优先导出 .aimami-accounts.json 后在 AiMaMi 导入；直接写 snapshots 只在验证门禁通过后启用。</div>${reason}${rows || '<div class="muted">没有可注入的缺失账号。</div>'}`;
        return;
      }
      if (data.path) {
        const errors = data.errors || [];
        const errorRows = errors.map((item) => `<div class="warnText">${esc(maskEmail(item.email || '') || maskId(item.account_id || ''))}: ${esc(item.error || item.error_type || 'export failed')}</div>`).join('');
        box.innerHTML = `<span class="${errors.length ? 'warnText' : 'ok'}">已导出 ${esc(data.count || 0)} 个账号</span> · ${esc(humanPath(data.path))}<div class="muted">这是 AiMaMi 原生导入文件；BridgeDeck 未写入 AiMaMi registry/snapshots。</div>${errorRows}`;
        return;
      }
      if (data.reason === 'export_failed' || (data.errors || []).length) {
        const errors = data.errors || [];
        const errorRows = errors.map((item) => `<div class="warnText">${esc(maskEmail(item.email || '') || maskId(item.account_id || ''))}: ${esc(item.error || item.error_type || 'export failed')}</div>`).join('');
        box.innerHTML = `<span class="bad">导出失败</span>${errorRows || `<div class="warnText">${esc(data.message || data.reason || 'export failed')}</div>`}`;
        return;
      }
      const missing = data.missing_in_aimami || [];
      const conflicts = data.conflicts || [];
      const rows = missing.map((item) => {
        const label = maskEmail(item.email || '') || maskId(item.account_id || '');
        return `<label class="toggleLine"><input type="checkbox" class="aimamiExportAccount" value="${esc(item.account_id || '')}" checked> ${esc(label)}</label>`;
      }).join('');
      box.innerHTML = `
        <div>BridgeDeck 有 ${esc(missing.length)} 个账号未在 AiMaMi registry 中；冲突 ${esc(conflicts.length)} 个。</div>
        <div class="muted">推荐导出 .aimami-accounts.json 后在 AiMaMi 导入，避免直接改 AiMaMi 私有状态。</div>
        ${rows || '<div class="muted">没有可导出的缺失账号。</div>'}
      `;
    }
    async function refreshQuotas() {
      try {
        const payload = await api('/api/quotas');
        renderQuotaBoard(payload);
        renderMissingBridgeStatus(payload);
        renderOverviewQuotaMetrics(payload);
        return payload;
      } catch (e) {
        document.getElementById('quotaBoard').textContent = `额度查询失败: ${e.message}`;
        setText('metricQuotaValue', '查询失败');
        setText('metricQuotaAccount', '-');
        setText('metricQuotaRemaining', '-');
        setMetricIcon('metricQuotaIcon', 'bad');
        return null;
      }
    }
    async function saveAutoSwitch() {
      const payload = {
        enabled: document.getElementById('autoSwitchEnabled').checked,
        claude: document.getElementById('autoSwitchClaude').checked,
        default_codex: document.getElementById('autoSwitchDefaultCodex').checked
      };
      const res = await api('/api/auto-switch-config', 'POST', payload);
      document.getElementById('autoSwitchStatus').textContent = payload.enabled
        ? '已开启：只在当前是 Local Codex Bridge 时自动切换。'
        : '已关闭自动切换。';
      if (res.auto_switch?.enabled) await runAutoSwitch(false, false);
      await refreshData();
    }
    async function runAutoSwitch(force=true, refresh=true) {
      const res = await api('/api/auto-switch-run', 'POST', { force });
      const actions = (res.actions || []).map((a) => `${a.target}:${a.changed ? '已切换' : (a.reason || '未变')}`).join('，');
      document.getElementById('autoSwitchStatus').textContent = res.selected_account_id
        ? `当前优先账号：${accountDisplay(res.selected_account_id)}，${quotaStatusText(res.selected_quota_status)}。${actions}`
        : (res.message || '未切换');
      log(`自动切换检查: ${document.getElementById('autoSwitchStatus').textContent}`);
      if (refresh) await refreshData();
      return res;
    }
    async function createMissingBridges() {
      const res = await api('/api/create-missing-bridges', 'POST', {});
      const created = res.created || [];
      const skipped = res.skipped || [];
      document.getElementById('missingBridgeStatus').innerHTML = created.length
        ? `<span class="ok">已创建 ${created.length} 个 Local Codex Bridge。</span>`
        : '<span class="muted">没有需要创建的 Local Codex Bridge。</span>';
      if (skipped.length) {
        document.getElementById('missingBridgeStatus').innerHTML += ` <span class="warnText">跳过 ${skipped.length} 个异常账号。</span>`;
      }
      log(`新账号桥接创建: created=${created.length}, skipped=${skipped.length}`);
      await refreshData();
      return res;
    }
    async function previewAimamiImport() {
      const res = await api('/api/aimami-sync/status');
      renderAimamiSync(res);
      const summary = res.summary || {};
      log(`AiMaMi 导入预览: importable=${summary.importable || 0}, skipped=${summary.skipped || 0}`);
      return res;
    }
    async function importAimamiAccounts(createMissing=false) {
      const res = await api('/api/aimami-sync/import', 'POST', { create_missing: createMissing });
      renderAimamiSync({ detected: true, candidates: [...(res.imported || []), ...(res.skipped || [])], summary: res.summary || {} });
      const created = res.bridge_providers ? (res.bridge_providers.created || []).length : 0;
      log(`AiMaMi 导入完成: imported=${(res.imported || []).length}, skipped=${(res.skipped || []).length}, bridges=${created}`);
      await refreshData();
      return res;
    }
    async function saveAimamiFollow() {
      const enabled = Boolean(document.getElementById('aimamiFollowEnabled')?.checked);
      const res = await api('/api/aimami-follow-config', 'POST', { enabled });
      renderAimamiFollow(res.aimami_follow || {});
      log(`AiMaMi follow: ${enabled ? 'enabled' : 'disabled'}`);
      if (enabled) await runAimamiFollow(true, true);
      return res;
    }
    async function runAimamiFollow(force=true, refresh=true) {
      const res = await api('/api/aimami-follow-run', 'POST', { force });
      renderAimamiFollow({ enabled: res.enabled, last_result: res });
      log(`AiMaMi follow: ${res.action || 'noop'} / ${res.reason || '-'} / ${res.selected_account_id ? maskId(res.selected_account_id) : '-'}`);
      if (refresh) await refreshData();
      return res;
    }
    async function previewAimamiExport() {
      const res = await api('/api/aimami-sync/export-preview');
      renderAimamiExport(res);
      log(`AiMaMi export preview: missing=${(res.missing_in_aimami || []).length}, conflicts=${(res.conflicts || []).length}`);
      return res;
    }
    async function exportAimamiAccounts() {
      let accountIds = Array.from(document.querySelectorAll('.aimamiExportAccount:checked')).map((item) => item.value).filter(Boolean);
      if (!accountIds.length) {
        const preview = await previewAimamiExport();
        accountIds = (preview.missing_in_aimami || []).map((item) => item.account_id).filter(Boolean);
      }
      if (!accountIds.length) return log('没有可导出的 BridgeDeck 账号。');
      const res = await api('/api/aimami-sync/export', 'POST', { account_ids: accountIds });
      renderAimamiExport(res);
      log(res.ok === false ? `AiMaMi export failed: ${(res.errors || []).length} errors` : `AiMaMi export written: count=${res.count || 0}, path=${humanPath(res.path || '')}`);
      return res;
    }
    async function previewAimamiInject() {
      const res = await api('/api/aimami-sync/inject-preview');
      renderAimamiExport(res);
      log(`AiMaMi inject preview: can_apply=${Boolean(res.can_apply)}, missing=${(res.missing_in_aimami || []).length}`);
      return res;
    }
    async function injectAimamiAccounts() {
      let accountIds = Array.from(document.querySelectorAll('.aimamiExportAccount:checked')).map((item) => item.value).filter(Boolean);
      if (!accountIds.length) {
        const preview = await previewAimamiInject();
        accountIds = (preview.missing_in_aimami || []).map((item) => item.account_id).filter(Boolean);
      }
      if (!accountIds.length) return log('没有可注入的 BridgeDeck 账号。');
      try {
        const res = await api('/api/aimami-sync/inject', 'POST', { mode: 'codex_snapshot', account_ids: accountIds, set_active: false, overwrite: false });
        renderAimamiExport({ verification: { verified: Boolean(res.ok) }, missing_in_aimami: [], aimami_running: res.aimami_running });
        log(`AiMaMi inject: ok=${Boolean(res.ok)}, reason=${res.reason || '-'}, written=${(res.written || []).length}`);
        return res;
      } catch (e) {
        const payload = e.payload || {};
        if (e.status === 409 && payload) {
          renderAimamiExport({
            verification: payload.verification || { verified: false },
            reason: payload.reason || payload.error || e.message,
            missing_in_aimami: payload.missing_in_aimami || [],
            conflicts: payload.conflicts || [],
            aimami_running: payload.aimami_running
          });
          log(`AiMaMi inject blocked: ${payload.reason || e.message}`);
          return payload;
        }
        throw e;
      }
    }
    function renderServices(payload) {
      const box = document.getElementById('serviceStatus');
      if (!box) return;
      const services = payload.services || {};
      const local = services.local_bridge || {};
      const items = [
        services.bridgedeck || { name: 'BridgeDeck', running: true, port: 8899 },
        local,
        services.cc_switch_proxy || { name: 'CC Switch Proxy', running: false, port: 15721 }
      ];
      box.innerHTML = items.map((item) => {
        const running = !!item.running;
        const cls = running ? 'ok' : 'bad';
        const script = item.script ? `<br>${esc(humanPath(item.script))}` : '';
        const proxy = item.upstream_proxy ? `<br>proxy: ${esc(item.upstream_proxy)}` : '';
        const err = item.last_stream_error || {};
        const streamError = err.error_type
          ? `<br><span class="warnText">stream error: ${esc(err.error_type)}${err.model ? ' / ' + esc(err.model) : ''}</span>`
          : '';
        const active = item.active_stream || {};
        const activeLine = active.request_id
          ? `<br><span class="warnText">active stream: ${esc(active.status || 'streaming')} · ${esc(active.model || '-')} · ${esc(active.duration_s || 0)}s · effort ${esc(active.requested_effort || '-')}/${esc(active.actual_effort || active.effort || '-')} · guard ${esc(active.guard_mode || 'off')}/${esc(active.guard_seconds || 0)}s · args ${esc(active.tool_args_mode || '-')} ${esc(active.tool_arg_delta_events || 0)}片/${esc(active.tool_arg_buffer_chars || 0)}字 · ping ${esc(active.tool_arg_ping_events || 0)}</span>`
          : '';
        const streamDiag = item.stream_diagnostics && item.stream_diagnostics.message
          ? `<br><span class="muted">stream diagnosis: ${esc(item.stream_diagnostics.message)}</span>`
          : '';
        return `<div class="serviceItem">
          <div class="serviceName">${esc(item.name || '')}</div>
          <div class="serviceMeta"><span class="${cls}">${running ? '运行中' : '未运行'}</span> · ${esc(item.port || '')}${script}${proxy}${streamError}${activeLine}${streamDiag}</div>
        </div>`;
      }).join('');
      const message = document.getElementById('serviceMessage');
      if (message && local.log_path) message.dataset.logPath = local.log_path;
    }
    function renderProxyDiagnosis(payload) {
      const box = document.getElementById('proxyDiagnosis');
      if (!box) return;
      const checks = Array.isArray(payload.checks) ? payload.checks : [];
      const lines = checks.map((item) => {
        const parts = [`${item.label}: ${item.status}`];
        if (item.detail) parts.push(item.detail);
        if (item.body_excerpt) parts.push(item.body_excerpt);
        return parts.join(' · ');
      });
      const owners = payload.proxy && Array.isArray(payload.proxy.processes) ? payload.proxy.processes : [];
      const ownerLines = owners.map((item) => `端口占用: ${item.label || 'unknown'}${item.pid ? ` pid ${item.pid}` : ''}${item.legacy_conflict ? ' · 可能是遗留代理' : ''}`);
      const recs = Array.isArray(payload.recommendations) ? payload.recommendations.slice(0, 4) : [];
      box.innerHTML = `<b>${esc(payload.message || '代理诊断完成')}</b>${lines.length ? `<br>${lines.map((line) => esc(line)).join('<br>')}` : ''}${ownerLines.length ? `<br>${ownerLines.map((line) => esc(line)).join('<br>')}` : ''}${recs.length ? `<br>${recs.map((line) => `- ${esc(line)}`).join('<br>')}` : ''}`;
    }
    function renderInstallScan(payload) {
      const box = document.getElementById('installScan');
      if (!box) return;
      const status = payload.status || 'unknown';
      const state = status === 'ok' ? 'okState' : (status === 'failed' ? 'badState' : 'warnState');
      box.className = `recommend mt10 ${state}`;
      const checks = Array.isArray(payload.checks) ? payload.checks : [];
      const lines = checks.map((item) => `${item.label || item.id}: ${item.status || '-'}${item.detail ? ` · ${item.detail}` : ''}`);
      const recs = Array.isArray(payload.recommendations) ? payload.recommendations.slice(0, 4) : [];
      box.innerHTML = `<b>安装扫描：${esc(status)}</b><br><span class="muted">version ${esc(payload.version || '-')}</span>${lines.length ? `<br>${lines.map((line) => esc(line)).join('<br>')}` : ''}${recs.length ? `<br>${recs.map((line) => `- ${esc(line)}`).join('<br>')}` : ''}`;
    }
    async function runInstallScan() {
      const payload = await api('/api/install-scan');
      renderInstallScan(payload);
      document.getElementById('serviceMessage').textContent = payload.status === 'failed' ? '安装扫描失败' : '安装扫描完成';
      log(`安装扫描: ${payload.status || 'unknown'}`);
      return payload;
    }
    function renderCodexDesktopDoctor(payload) {
      const box = document.getElementById('codexDesktopDoctor');
      if (!box) return;
      const status = payload.status || 'unknown';
      const state = status === 'healthy' ? 'okState'
        : (['active_config_legacy_key', 'native_proxy_missing', 'native_proxy_incomplete', 'native_proxy_proxy_down', 'native_proxy_blocked', 'desktop_dynamic_tools_missing', 'remote_thread_dynamic_tools_missing', 'desktop_state_stale', 'desktop_stream_state_stale', 'desktop_app_state_unfresh', 'desktop_event_session_unhealthy'].includes(status) ? 'badState' : 'warnState');
      box.className = `recommend mt10 ${state}`;
      const checks = Array.isArray(payload.checks) ? payload.checks : [];
      const checkLines = checks.map((item) => `${item.label || item.id}: ${item.status || '-'}${item.detail ? ` · ${item.detail}` : ''}`);
      const recs = Array.isArray(payload.recommendations) ? payload.recommendations.slice(0, 5) : [];
      const versions = payload.versions || {};
      const versionLine = versions.version_split ? `CLI 版本不同：global ${versions.global_cli_version || '-'} / app ${versions.bundled_cli_version || '-'}` : '';
      box.innerHTML = `<b>${esc(payload.message || 'Codex Desktop Doctor 完成')}</b><br><span class="muted">status ${esc(status)} · action ${esc(payload.action || '-')}</span>${versionLine ? `<br><span class="warnText">${esc(versionLine)}</span>` : ''}${checkLines.length ? `<br>${checkLines.map((line) => esc(line)).join('<br>')}` : ''}${recs.length ? `<br>${recs.map((line) => `- ${esc(line)}`).join('<br>')}` : ''}`;
    }
    async function refreshCodexDesktopDoctor() {
      const payload = await api('/api/codex-desktop-doctor');
      renderCodexDesktopDoctor(payload);
      document.getElementById('serviceMessage').textContent = payload.message || 'Codex Desktop Doctor 完成';
      log(`Codex Desktop Doctor: ${payload.status || 'unknown'} / ${payload.action || '-'}`);
      return payload;
    }
    function renderStreamDiagnostics(data) {
      const box = document.getElementById('streamDiagnostics');
      if (!box) return;
      const diag = data.stream_diagnostics || {};
      const active = data.active_stream || {};
      const latest = diag.latest || {};
      const counts = diag.counts || {};
      const state = active.request_id ? 'warn' : (diag.status === 'ok' ? 'ok' : (diag.status === 'unknown' ? '' : 'bad'));
      box.className = `recommend ${state}`;
      const activeLine = active.request_id
        ? `当前: ${active.status || 'streaming'} · ${active.model || '-'} · ${active.duration_s || 0}s · ${active.last_event_name || '-'} · 思考 ${active.requested_effort || '-'}/${active.actual_effort || active.effort || '-'} · tool ${active.tool_events || 0} · 参数 ${active.tool_args_mode || '-'} ${active.tool_arg_delta_events || 0}片/${active.tool_arg_buffer_chars || 0}字 · ping ${active.tool_arg_ping_events || 0} · 可见文本 ${active.visible_text_events || 0} · guard ${active.guard_mode || 'off'}/${active.guard_seconds || 0}s`
        : '当前: 无活跃 Local Bridge 流';
      const latestLine = latest.kind
        ? `最近: ${latest.timestamp || '-'} · ${latest.kind} · ${latest.model || '-'} · ${latest.duration_s ? `${latest.duration_s}s` : `${latest.duration_ms || 0}ms`}`
        : '最近: -';
      const detail = latest.kind === 'client_disconnect'
        ? `上游事件 ${latest.upstream_events || 0}，下游写入 ${latest.downstream_writes || 0}，终止事件 ${latest.terminal_event_seen ? '已看到' : '未看到'}，思考 ${latest.requested_effort || '-'}/${latest.actual_effort || '-'}，工具参数 ${latest.tool_args_mode || '-'} ${latest.tool_arg_delta_events || 0}片/${latest.tool_arg_buffer_chars || 0}字。`
        : `可见文本 ${latest.visible_text_events || 0}/${latest.visible_text_chars || 0}字，结尾 ${latest.answer_end_class || '-'}${latest.answer_incomplete_risk ? ' · 疑似半句' : ''}，reasoning ${latest.reasoning_events || 0}，tool ${latest.tool_events || 0}，terminal ${latest.terminal_events || 0}，思考 ${latest.requested_effort || '-'}/${latest.actual_effort || '-'}，工具参数 ${latest.tool_args_mode || '-'} ${latest.tool_arg_delta_events || 0}片。`;
      box.innerHTML = `<b>${esc(active.request_id ? '检测到活跃流。若长时间停在 tool_arguments_streaming，通常是上游持续生成工具参数，不是断网。' : (diag.message || '流式诊断未知'))}</b><br>${esc(activeLine)}<br>${esc(latestLine)}<br>${esc(detail)}<br><span class="muted">client_disconnect ${counts.client_disconnect || 0} · idle_timeout ${counts.bridge_idle_timeout || 0} · long_stream ${counts.long_stream || 0} · stream_end ${counts.stream_end || 0}</span>`;
    }
    function renderHookRiskDiagnostics(data) {
      const box = document.getElementById('hookRiskDiagnostics');
      if (!box) return;
      const diag = data.claude_hook_risks || {};
      const risks = Array.isArray(diag.risks) ? diag.risks : [];
      const state = diag.status === 'ok' ? 'ok' : (diag.status === 'unknown' ? '' : 'bad');
      box.className = `recommend ${state}`;
      const eventCounts = diag.events || {};
      const countLine = Object.keys(eventCounts).sort().map((key) => `${key}:${eventCounts[key]}`).join(' · ');
      const riskLines = risks.slice(0, 5).map((item) => `${item.event || '-'} · ${item.command_label || '-'} · ${item.reason || '-'}`);
      box.innerHTML = `<b>${esc(diag.message || 'Hook 诊断未知')}</b>${countLine ? `<br><span class="muted">${esc(countLine)}</span>` : ''}${riskLines.length ? `<br>${riskLines.map((line) => `- ${esc(line)}`).join('<br>')}` : ''}`;
    }
    async function refreshServices() {
      const payload = await api('/api/services');
      renderServices(payload);
      return payload;
    }

    // Account Pool functions
    async function refreshAccountPool() {
      try {
        const data = await api('/api/account-pool');
        renderAccountPool(data);
      } catch (e) {
        console.error('Account pool refresh failed:', e);
      }
    }

    function renderAccountPool(data) {
      const display = document.getElementById('defaultAccountDisplay');
      if (!data.ok) {
        display.className = 'recommend bad';
        display.textContent = data.error || '加载失败';
        return;
      }
      display.className = 'recommend ok';
      display.innerHTML = `当前默认账户: <b>${esc(data.default_account_id || '未设置')}</b>`;

      const select = document.getElementById('accountPoolSelect');
      select.innerHTML = '<option value="">选择账户...</option>';
      data.pool.forEach((acct) => {
        const opt = document.createElement('option');
        opt.value = acct.account_id;
        opt.textContent = `${esc(acct.email)} (${acct.account_id.substring(0, 8)}...)`;
        if (acct.is_default) opt.selected = true;
        select.appendChild(opt);
      });

      const tbody = document.querySelector('#accountPoolTable tbody');
      tbody.innerHTML = '';
      data.pool.forEach((acct) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="mono">${esc(acct.account_id.substring(0, 12))}...</td>
          <td>${esc(acct.email)}</td>
          <td>${acct.is_default ? '<span class="ok">✓ 默认</span>' : ''}</td>
          <td class="muted">${esc(acct.source || '')}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function setDefaultAccount() {
      const select = document.getElementById('accountPoolSelect');
      const accountId = select.value;
      if (!accountId) return log('请先选择一个账户');
      const res = await api('/api/set-default-account', 'POST', { account_id: accountId });
      if (res.ok) {
        log(`默认账户已切换为: ${accountId.substring(0, 12)}...`);
        await refreshAccountPool();
      } else {
        log(`切换失败: ${res.error}`);
      }
    }

    // API Keys functions
    async function refreshApiKeys() {
      try {
        const data = await api('/api/keys');
        renderApiKeys(data);
      } catch (e) {
        console.error('API keys refresh failed:', e);
      }
    }

    function renderApiKeys(data) {
      const tbody = document.querySelector('#apiKeysTable tbody');
      tbody.innerHTML = '';
      if (!data.ok || !data.keys) return;
      data.keys.forEach((key) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${esc(key.name || '未命名')}</td>
          <td class="mono">${esc(key.key_prefix || '****')}...</td>
          <td><span class="ok">有效</span></td>
          <td><button class="miniBtn warn" data-revoke-key="${esc(key.key_prefix)}">撤销</button></td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function createApiKey() {
      const nameInput = document.getElementById('newKeyName');
      const name = nameInput.value.trim() || 'default';
      const res = await api('/api/keys/create', 'POST', { name });
      const resultDiv = document.getElementById('newKeyResult');
      resultDiv.className = 'recommend ok';
      resultDiv.innerHTML = `API Key 已创建：<code class="mono">${esc(res.key)}</code><br><small>请复制保存，关闭后无法再次查看</small>`;
      resultDiv.classList.remove('hidden');
      nameInput.value = '';
      await refreshApiKeys();
    }

    async function revokeApiKey(keyPrefix) {
      if (!confirm(`确认撤销 Key ${keyPrefix}...？`)) return;
      const res = await api('/api/keys/revoke', 'POST', { key_prefix: keyPrefix });
      if (res.ok) {
        log(`Key ${keyPrefix}... 已撤销`);
        await refreshApiKeys();
      } else {
        log(`撤销失败: ${res.error}`);
      }
    }

    // Service Control functions
    async function refreshServiceControl() {
      try {
        const health = await api('/api/public-health');
        const display = document.getElementById('serviceStatusDisplay');
        display.className = health.ok ? 'recommend ok' : 'recommend bad';
        display.innerHTML = health.ok
          ? `服务运行中 · 状态: <b>${esc(health.status || 'ok')}</b>`
          : `服务异常: ${esc(health.error || '未知错误')}`;
      } catch (e) {
        document.getElementById('serviceStatusDisplay').className = 'recommend bad';
        document.getElementById('serviceStatusDisplay').textContent = '无法连接服务';
      }

      try {
        const launchd = await api('/api/launchd-status');
        const box = document.getElementById('launchdStatus');
        box.className = launchd.loaded ? 'recommend ok' : 'recommend warn';
        box.innerHTML = launchd.loaded
          ? `Launchd 已加载 · PID: ${esc(String(launchd.pid || 'N/A'))}`
          : 'Launchd 未加载';
      } catch (e) {
        document.getElementById('launchdStatus').textContent = '无法获取 launchd 状态';
      }
    }

    async function serviceControl(action) {
      const res = await api('/api/service-control', 'POST', { action });
      log(`服务${action}: ${res.message || res.error || '完成'}`);
      await refreshServiceControl();
    }

    async function launchdControl(action) {
      const res = await api('/api/launchd-control', 'POST', { action });
      log(`Launchd ${action}: ${res.message || res.error || '完成'}`);
      await refreshServiceControl();
    }
    async function runProxyDiagnosis() {
      const payload = await api('/api/proxy-diagnosis');
      renderProxyDiagnosis(payload);
      document.getElementById('serviceMessage').textContent = payload.message || '代理诊断完成';
      log(`代理诊断: ${payload.status || 'unknown'} / ${payload.message || ''}`);
      return payload;
    }
    function nativeProxyMessage(payload) {
      const missing = Array.isArray(payload.missing_keys) && payload.missing_keys.length
        ? `缺少 ${payload.missing_keys.join(', ')}`
        : '';
      const port = payload.proxy_port ? `端口 ${payload.proxy_port}` : '';
      const restart = payload.restart_required ? '；修复或变更后需完全重启 Codex Desktop' : '';
      return [payload.message || 'Codex 原生代理状态未知', port, missing].filter(Boolean).join(' · ') + restart;
    }
    async function runCodexNativeProxyStatus() {
      const payload = await api('/api/codex-native-proxy-status');
      const message = nativeProxyMessage(payload);
      document.getElementById('serviceMessage').textContent = message;
      const box = document.getElementById('proxyDiagnosis');
      if (box) box.innerHTML = `<b>Codex 原生代理：${esc(payload.status || 'unknown')}</b><br>${esc(message)}`;
      log(`Codex 原生代理: ${payload.status || 'unknown'} / ${message}`);
      return payload;
    }
    async function repairCodexNativeProxy() {
      const res = await api('/api/repair-codex-native-proxy', 'POST', {});
      const status = res.status || {};
      const message = `${res.message || 'Codex 原生代理修复完成'}。${res.restart_message || '完全重启 Codex Desktop 后生效。'}`;
      document.getElementById('serviceMessage').textContent = message;
      const box = document.getElementById('proxyDiagnosis');
      if (box) box.innerHTML = `<b>${esc(message)}</b><br>${esc(nativeProxyMessage(status))}`;
      log(`Codex 原生代理修复: ${message}`);
      return res;
    }
    async function normalizeCodexHooksConfig() {
      const res = await api('/api/normalize-codex-hooks-config', 'POST', {});
      const message = res.restart_required
        ? `${res.message || 'hooks config 已清理'}。完全重启 Codex Desktop 后生效。`
        : (res.message || 'hooks config 无需清理');
      document.getElementById('serviceMessage').textContent = message;
      const box = document.getElementById('codexDesktopDoctor');
      if (box) box.innerHTML = `<b>${esc(message)}</b>`;
      log(`hooks config 清理: ${message}`);
      await refreshCodexDesktopDoctor();
      return res;
    }
    async function controlLocalBridge(action) {
      let res;
      try {
        res = await api('/api/local-bridge-control', 'POST', { action });
      } catch (err) {
        const payload = err && err.payload ? err.payload : {};
        if ((action === 'stop' || action === 'restart') && payload.requires_force) {
          const count = Number((payload.active_connections || []).length || 0);
          const message = payload.message || '检测到 8876 正在被客户端使用，已取消操作';
          document.getElementById('serviceMessage').textContent = message;
          log(`Local Bridge ${action} 被保护拦截: ${message}`);
          if (!confirm(`${message}\\n\\n活动连接：${count}\\n继续会中断当前 Claude/CC Switch 请求。确认强制执行？`)) {
            await refreshServices();
            return payload;
          }
          res = await api('/api/local-bridge-control', 'POST', { action, force: true });
        } else {
          throw err;
        }
      }
      renderServices(res);
      document.getElementById('serviceMessage').textContent = res.message || 'Local Bridge 操作完成';
      log(`Local Bridge ${action}: ${res.message || 'done'}`);
      await refreshQuotas();
      return res;
    }
    async function stopBridgeDeckUi() {
      if (!confirm('只关闭 BridgeDeck UI (8899)，Local Bridge (8876) 会继续运行。继续？')) return;
      const res = await api('/api/ui-control', 'POST', { action: 'shutdown' });
      const message = res.message || 'BridgeDeck UI 正在关闭；Local Bridge 保持运行。';
      document.getElementById('serviceMessage').textContent = message;
      log(message);
      setTimeout(() => {
        document.body.innerHTML = '<main class="wrap"><div class="card"><h1>BridgeDeck UI 已关闭</h1><p class="muted">8876 Local Bridge 继续运行。重新打开 BridgeDeck.app 可恢复 UI。</p></div></main>';
      }, 250);
      return res;
    }
    async function repairQuotaQuery() {
      const res = await api('/api/repair-quota-query', 'POST', {});
      if (res.services) renderServices({ services: res.services });
      renderQuotaBoard(res);
      renderMissingBridgeStatus(res);
      const actions = (res.actions || []).filter(Boolean).join('，');
      const okCount = (res.quotas || []).filter((q) => ['ok', 'near_limit', 'limit_reached'].includes(q.quota_status)).length;
      document.getElementById('serviceMessage').textContent = actions || `额度查询已刷新，正常账号 ${okCount} 个`;
      log(`额度修复: ${document.getElementById('serviceMessage').textContent}`);
      await refreshData();
      return res;
    }
    async function repairCodexEnvConflicts() {
      const res = await api('/api/repair-codex-env-conflicts', 'POST', {});
      const keys = (res.removed_env_keys || []).join(', ');
      const message = res.changed ? `${res.message}: ${keys}` : res.message;
      document.getElementById('serviceMessage').textContent = message;
      log(`环境冲突清理: ${message}`);
      await refreshServices();
      return res;
    }
    async function repairClaudeAttributionHeader() {
      const res = await api('/api/repair-claude-attribution-header', 'POST', {});
      const changedFiles = (res.files || []).filter((item) => item.changed).length;
      const updatedProviders = (res.updated_providers || []).length;
      const message = `${res.message || '修复完成'}：文件 ${changedFiles} 个，provider ${updatedProviders} 个。${res.restart_message || ''}`;
      const box = document.getElementById('attributionHeaderStatus');
      if (box) box.innerHTML = `<span class="ok">${esc(message)}</span>`;
      log(`Attribution Header 修复: ${message}`);
      await refreshData();
      return res;
    }
    function showAttributionHeaderPaths() {
      const box = document.getElementById('attributionHeaderPaths');
      if (box) box.classList.toggle('hidden');
    }
    function keepAttributionHeader() {
      const box = document.getElementById('attributionHeaderStatus');
      const message = '已保留当前设置；BridgeDeck 不会在本次操作里改动 attribution header。';
      if (box) box.innerHTML = `<span class="warnText">${esc(message)}</span>`;
      log(message);
    }
    function setSimpleResult(message, level='') {
      const box = document.getElementById('simpleResult');
      const cls = level === 'ok' ? 'ok' : (level === 'warn' ? 'warnText' : (level === 'bad' ? 'bad' : ''));
      box.innerHTML = cls ? `<strong class="${cls}">${esc(message)}</strong>` : esc(message);
    }
    function setOAuthResult(message, level='') {
      const box = document.getElementById('oauthResult');
      if (!box) return;
      const cls = level === 'ok' ? 'ok' : (level === 'warn' ? 'warnText' : (level === 'bad' ? 'bad' : ''));
      box.innerHTML = cls ? `<strong class="${cls}">${esc(message)}</strong>` : esc(message);
    }
    function stopOAuthPolling() {
      if (oauthPollTimer) clearInterval(oauthPollTimer);
      oauthPollTimer = null;
    }
    function stopOAuthExpiryTimer() {
      if (oauthExpiryTimer) clearInterval(oauthExpiryTimer);
      oauthExpiryTimer = null;
    }
    function formatOAuthExpiry(expiresAt) {
      if (!expiresAt) return '有效期：-';
      const expires = new Date(expiresAt);
      const ms = expires.getTime() - Date.now();
      if (!Number.isFinite(expires.getTime())) return '有效期：-';
      if (ms <= 0) return '有效期：已过期';
      const totalSeconds = Math.ceil(ms / 1000);
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      const clock = expires.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      return `有效期至 ${clock}，剩余 ${minutes}:${String(seconds).padStart(2, '0')}`;
    }
    function updateOAuthExpiry() {
      const box = document.getElementById('oauthExpiresAt');
      if (!box) return;
      box.textContent = formatOAuthExpiry(activeOAuthExpiresAt);
      if (activeOAuthExpiresAt && Date.parse(activeOAuthExpiresAt) <= Date.now()) {
        stopOAuthPolling();
        stopOAuthExpiryTimer();
        setOAuthResult('验证码已过期，请重新生成。', 'warn');
      }
    }
    function setOAuthBridgeButton(result) {
      const button = document.getElementById('oauthApplyBridgeBtn');
      if (!button) return;
      if (result && result.status === 'completed') {
        button.classList.remove('hidden');
        button.textContent = result.bridge_provider_exists ? '更新 CC Switch' : '加入 CC Switch';
      } else {
        button.classList.add('hidden');
        button.textContent = '加入 CC Switch';
      }
    }
    function hideCodexOAuth() {
      stopOAuthPolling();
      stopOAuthExpiryTimer();
      activeOAuthFlowId = '';
      activeOAuthExpiresAt = '';
      const box = document.getElementById('oauthUrlBox');
      if (box) box.classList.add('hidden');
      setText('oauthUserCode', '-');
      setText('oauthExpiresAt', '有效期：-');
      setOAuthBridgeButton(null);
      setOAuthResult('验证码已隐藏。需要授权时重新生成。');
    }
    async function checkCodexOAuthStatus() {
      if (!activeOAuthFlowId) {
        setOAuthResult('还没有进行中的授权流程。', 'warn');
        return null;
      }
      const result = await api(`/api/codex-oauth/status?flow_id=${encodeURIComponent(activeOAuthFlowId)}`);
      if (result.expires_at) {
        activeOAuthExpiresAt = result.expires_at;
        updateOAuthExpiry();
      }
      setOAuthBridgeButton(result);
      if (result.status === 'completed') {
        stopOAuthPolling();
        stopOAuthExpiryTimer();
        setOAuthResult(`授权完成：${result.email || result.account_id || '新账号'}`, 'ok');
        await refreshData();
      } else if (result.status === 'error') {
        stopOAuthPolling();
        stopOAuthExpiryTimer();
        setOAuthResult(`授权失败：${result.error || '未知错误'}`, 'bad');
      } else if (result.status === 'exchanging') {
        setOAuthResult('已确认授权，正在交换 token...');
      } else {
        setOAuthResult('等待你在 OpenAI 页面输入验证码并确认...');
      }
      return result;
    }
    function startOAuthPolling() {
      stopOAuthPolling();
      oauthPollTimer = setInterval(() => {
        checkCodexOAuthStatus().catch((error) => {
          stopOAuthPolling();
          setOAuthResult(`授权状态检查失败：${error.message}`, 'bad');
        });
      }, 1800);
    }
    async function startCodexOAuth() {
      const setDefault = Boolean(document.getElementById('oauthSetDefault')?.checked);
      const popup = window.open('about:blank', '_blank');
      if (popup) popup.opener = null;
      stopOAuthPolling();
      stopOAuthExpiryTimer();
      setOAuthBridgeButton(null);
      const result = await api('/api/codex-oauth/start', 'POST', { set_default: setDefault });
      activeOAuthFlowId = result.flow_id || '';
      activeOAuthExpiresAt = result.expires_at || '';
      const link = document.getElementById('oauthAuthLink');
      const codeBox = document.getElementById('oauthUserCode');
      const box = document.getElementById('oauthUrlBox');
      if (link) {
        link.href = result.verification_url || result.auth_url || '#';
        link.textContent = result.verification_url || result.auth_url || '授权页生成失败';
      }
      if (codeBox) {
        codeBox.textContent = result.user_code || '-';
      }
      updateOAuthExpiry();
      if (box) box.classList.remove('hidden');
      if (result.user_code) {
        setOAuthResult(`验证码已生成：${result.user_code}。输入并确认后会自动写入账号池。`);
      } else {
        setOAuthResult(result.error || '验证码生成失败。', 'bad');
      }
      const authUrl = result.verification_url || result.auth_url || '';
      if (popup && authUrl) {
        popup.location.href = authUrl;
      } else if (authUrl) {
        window.open(authUrl, '_blank', 'noopener,noreferrer');
      }
      oauthExpiryTimer = setInterval(updateOAuthExpiry, 1000);
      startOAuthPolling();
    }
    async function applyCodexOAuthBridge() {
      if (!activeOAuthFlowId) {
        setOAuthResult('没有可加入的已授权账号。', 'warn');
        return null;
      }
      const result = await api('/api/codex-oauth/apply-bridge', 'POST', { flow_id: activeOAuthFlowId });
      setOAuthResult(result.message || 'CC Switch 已更新。', 'ok');
      const button = document.getElementById('oauthApplyBridgeBtn');
      if (button) button.textContent = '更新 CC Switch';
      await refreshData();
      return result;
    }
    async function finishCodexOAuth() {
      const input = document.getElementById('oauthManualInput');
      const code = input ? input.value.trim() : '';
      if (!activeOAuthFlowId || !code) {
        setOAuthResult('缺少授权流程或 code。', 'warn');
        return;
      }
      const result = await api('/api/codex-oauth/finish', 'POST', { flow_id: activeOAuthFlowId, code });
      if (result.status === 'completed') {
        stopOAuthPolling();
        setOAuthResult(`授权完成：${result.email || result.account_id || '新账号'}`, 'ok');
        await refreshData();
      } else {
        setOAuthResult(result.error || result.message || '授权未完成', result.ok === false ? 'bad' : '');
      }
    }
    function selectedProviderId() {
      const chosen = document.querySelector('input[name="providerPick"]:checked');
      return chosen ? chosen.value : '';
    }
    function providerById(providerId) {
      return providerId && lastData ? (lastData.providers || []).find((p) => p.id === providerId) || null : null;
    }
    function providerForClaudeAccount(accountId) {
      if (!lastData) return null;
      if (!accountId) return null;
      const matches = (lastData.providers || []).filter((p) => p.account_id === accountId && isBridgeClaudeProvider(p));
      return matches.find((p) => p.id === lastData.current_provider_from_settings)
        || matches.find((p) => p.is_current)
        || matches[0]
        || null;
    }
    function providerForSelectedClaudeAccount() {
      const item = selectedAccount('account') || selectedAccount('simpleClaudeAccount');
      return providerForClaudeAccount(item && item.account_id ? item.account_id : '');
    }
    function currentBridgeClaudeProvider() {
      const provider = currentClaudeProvider(lastData);
      return isBridgeClaudeProvider(provider) ? provider : null;
    }
    function markProviderPicked(providerId) {
      if (!providerId) return;
      const input = Array.from(document.querySelectorAll('input[name="providerPick"]')).find((item) => item.value === providerId);
      if (input) input.checked = true;
    }
    function selectedProviderActionTarget() {
      const explicitId = selectedProviderId();
      if (explicitId) return { provider: providerById(explicitId), source: '手动选中 provider' };
      const accountProvider = providerForSelectedClaudeAccount();
      if (accountProvider) return { provider: accountProvider, source: '上方账号对应 provider' };
      const currentProvider = currentBridgeClaudeProvider();
      if (currentProvider) return { provider: currentProvider, source: '当前 CC Switch provider' };
      return { provider: null, source: '' };
    }
    function selectedProviderActionId() {
      const target = selectedProviderActionTarget();
      if (!target.provider) return '';
      markProviderPicked(target.provider.id);
      if (target.source !== '手动选中 provider') {
        log(`未手动选中 provider，已使用${target.source}: ${providerDisplayName(target.provider)}`);
      }
      return target.provider.id || '';
    }
    function selectedProvider() {
      return providerById(selectedProviderId());
    }
    function pageIdForSection(section) {
      const page = section ? section.closest('.deckPage') : null;
      return page && page.id ? page.id.replace(/^page-/, '') : '';
    }
    function showPage(pageId, pushState=false) {
      const target = document.getElementById(`page-${pageId}`);
      if (!target) return;
      document.querySelectorAll('.deckPage').forEach((page) => {
        page.classList.toggle('active', page === target);
      });
      document.querySelectorAll('.navItem[data-page]').forEach((item) => {
        item.classList.toggle('active', item.dataset.page === pageId);
      });
      document.body.classList.toggle('usageMode', pageId === 'usage');
      if (pushState) sessionStorage.setItem('bridgedeckPage', pageId);
      const guideSection = target.querySelector('.guideSection');
      if (guideSection) setGuide(guideSection.dataset.guide || 'providerCreate');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function initPageNav() {
      const saved = sessionStorage.getItem('bridgedeckPage') || 'overview';
      showPage(saved, false);
      document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-page]');
        if (!button) return;
        showPage(button.dataset.page, true);
      });
    }
    function scrollToSection(id) {
      const section = document.getElementById(id);
      if (!section) return;
      const pageId = pageIdForSection(section);
      if (pageId) showPage(pageId, true);
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
      const activeSection = document.querySelector('.deckPage.active .guideSection') || sections[0];
      setGuide(activeSection.dataset.guide || 'providerCreate');
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
      const label = accountSlug(item);
      document.getElementById('cliHome').value = humanPath(item.default_cli_home || `~/.codex-cli-${label}`);
      document.getElementById('cliProfileName').value = label;
    }
    function setSelectValue(id, accountId) {
      const sel = document.getElementById(id);
      if (!sel) return;
      const idx = Array.from(sel.options).findIndex((opt) => opt.value === accountId);
      if (idx >= 0) sel.selectedIndex = idx;
    }
    function selectedAccount(selectId) {
      const sel = document.getElementById(selectId);
      return sel ? findAccount(sel.value) : null;
    }
    function apiAccessBaseUrl(item) {
      return item && item.account_id ? `${LOCAL_BRIDGE_BASE_URL}/accounts/${encodeURIComponent(item.account_id)}/v1` : '';
    }
    function anthropicAccessBaseUrl(item) {
      return apiAccessBaseUrl(item);
    }
    function claudeDesktopGatewayBaseUrl(item) {
      return item && item.account_id ? `${LOCAL_BRIDGE_BASE_URL}/accounts/${encodeURIComponent(item.account_id)}` : '';
    }
    function claudeDesktopRoutesText() {
      return CLAUDE_DESKTOP_ROUTES.map(([route, label]) => `${route} (${label})`).join('\\n');
    }
    function apiAccessEnv(item) {
      const baseUrl = apiAccessBaseUrl(item);
      return baseUrl ? `OPENAI_API_KEY=${LOCAL_API_KEY_PLACEHOLDER}\nOPENAI_BASE_URL=${baseUrl}` : '';
    }
    function anthropicAccessEnv(item) {
      const baseUrl = anthropicAccessBaseUrl(item);
      return baseUrl ? `ANTHROPIC_BASE_URL=${baseUrl}\nANTHROPIC_AUTH_TOKEN=${LOCAL_ANTHROPIC_AUTH_TOKEN}\nANTHROPIC_DEFAULT_HAIKU_MODEL=gpt-5.3-codex-spark\nANTHROPIC_DEFAULT_HAIKU_MODEL_NAME=Haiku 4.5\nANTHROPIC_DEFAULT_SONNET_MODEL=gpt-5.3-codex\nANTHROPIC_DEFAULT_SONNET_MODEL_NAME=Sonnet 4.6\nANTHROPIC_DEFAULT_OPUS_MODEL=gpt-5.5\nANTHROPIC_DEFAULT_OPUS_MODEL_NAME=Opus 4.7\nCLAUDE_CODE_ATTRIBUTION_HEADER=0\nCLAUDE_CODE_MAX_CONTEXT_TOKENS=272000` : '';
    }
    function anthropicForcedModelEnv(item) {
      const base = anthropicAccessEnv(item);
      return base ? `${base}\nANTHROPIC_MODEL=${selectedBridgeModel()}` : '';
    }
    function apiOpenAiEnv(item) {
      const baseUrl = apiAccessBaseUrl(item);
      return baseUrl ? `OPENAI_API_KEY=${LOCAL_API_KEY_PLACEHOLDER}\nOPENAI_BASE_URL=${baseUrl}\nMODEL=gpt-5.5` : '';
    }
    function apiClaudeEnv(item) {
      const gatewayBase = claudeDesktopGatewayBaseUrl(item);
      if (!gatewayBase) return '';
      return `inferenceGatewayBaseUrl=${gatewayBase}\ninferenceGatewayApiKey=${LOCAL_ANTHROPIC_AUTH_TOKEN}\ninferenceGatewayAuthScheme=bearer\ninferenceModels=${CLAUDE_DESKTOP_ROUTES.map(([route]) => route).join(',')}\n${claudeDesktopRoutesText()}`;
    }
    async function copyText(value, label) {
      const text = String(value || '');
      if (!text) {
        setSimpleResult(`${label} 为空，先选择账号。`, 'warn');
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
      }
      setSimpleResult(`已复制 ${label}。`, 'ok');
    }
    function renderApiAccess() {
      const item = selectedAccount('simpleApiAccount');
      const keyBox = document.getElementById('apiAccessKey');
      const baseBox = document.getElementById('apiAccessBaseUrl');
      const anthropicTokenBox = document.getElementById('anthropicAccessToken');
      const anthropicBaseBox = document.getElementById('anthropicAccessBaseUrl');
      const actual = document.getElementById('simpleApiActual');
      if (keyBox) keyBox.textContent = LOCAL_API_KEY_PLACEHOLDER;
      if (baseBox) baseBox.textContent = apiAccessBaseUrl(item) || '选择账号后生成';
      if (anthropicTokenBox) anthropicTokenBox.textContent = LOCAL_ANTHROPIC_AUTH_TOKEN;
      if (anthropicBaseBox) anthropicBaseBox.textContent = anthropicAccessBaseUrl(item) || '选择账号后生成';
      const guideBase = document.getElementById('apiAccessGuideBaseUrl');
      const guideAccount = document.getElementById('apiAccessGuideAccount');
      const openaiExample = document.getElementById('apiOpenAiExample');
      const claudeExample = document.getElementById('apiClaudeExample');
      if (guideBase) guideBase.textContent = apiAccessBaseUrl(item) ? `BASE_URL: ${apiAccessBaseUrl(item)}\nDesktop Gateway: ${claudeDesktopGatewayBaseUrl(item)}` : 'BASE_URL: 选择账号后生成';
      if (guideAccount) guideAccount.textContent = item ? accountLabel(item) : '沿用上方通用 API 接入选择';
      if (openaiExample) openaiExample.textContent = apiOpenAiEnv(item);
      if (claudeExample) claudeExample.textContent = apiClaudeEnv(item);
      if (actual) {
        actual.innerHTML = item
          ? `当前实际：<strong>${esc(accountLabel(item))}</strong><br><span class="warnText">只复制本地 fake key，不显示真实 OAuth token。</span>`
          : '当前实际：<strong class="warnText">未选择</strong>';
      }
    }
    function copyApiKey() {
      return copyText(LOCAL_API_KEY_PLACEHOLDER, 'OPENAI_API_KEY');
    }
    function copyApiBaseUrl() {
      return copyText(apiAccessBaseUrl(selectedAccount('simpleApiAccount')), 'OPENAI_BASE_URL');
    }
    function copyApiEnv() {
      const item = selectedAccount('simpleApiAccount');
      return copyText(item ? apiAccessEnv(item) : '', '.env');
    }
    function copyAnthropicToken() {
      return copyText(LOCAL_ANTHROPIC_AUTH_TOKEN, 'ANTHROPIC_AUTH_TOKEN');
    }
    function copyAnthropicBaseUrl() {
      return copyText(anthropicAccessBaseUrl(selectedAccount('simpleApiAccount')), 'ANTHROPIC_BASE_URL');
    }
    function copyAnthropicEnv() {
      const item = selectedAccount('simpleApiAccount');
      return copyText(item ? anthropicAccessEnv(item) : '', 'Anthropic .env');
    }
    function copyAnthropicForcedEnv() {
      const item = selectedAccount('simpleApiAccount');
      return copyText(item ? anthropicForcedModelEnv(item) : '', 'Anthropic forced model env');
    }
    function copyClaudeEnv() {
      return copyAnthropicEnv();
    }
    function bridgeModelOption(modelId) {
      const normalized = String(modelId || '').trim().toLowerCase();
      return BRIDGE_MODELS.find((item) => item.id === normalized) || BRIDGE_MODELS[0] || null;
    }
    function bridgeModelContext(modelId) {
      const option = bridgeModelOption(modelId);
      return option && option.context_tokens ? String(option.context_tokens) : '';
    }
    function bridgeModelMaxOutput(modelId) {
      const option = bridgeModelOption(modelId);
      return option && option.max_output_tokens ? String(option.max_output_tokens) : '';
    }
    function bridgeModelRecommendedCompact(modelId) {
      return bridgeModelContext(modelId) || CONSERVATIVE_COMPACT_WINDOW;
    }
    function selectedBridgeModel() {
      const sel = document.getElementById('bridgeModel');
      return sel && sel.value ? sel.value : DEFAULT_BRIDGE_MODEL;
    }
    function selectedRoutingMode() {
      const sel = document.getElementById('modelRoutingMode');
      return sel && sel.value ? sel.value : 'auto';
    }
    function setRoutingMode(mode) {
      const sel = document.getElementById('modelRoutingMode');
      if (sel) sel.value = mode === 'forced' ? 'forced' : 'auto';
      updateBridgeModelMeta();
    }
    function updateBridgeModelMeta() {
      const model = selectedBridgeModel();
      const context = bridgeModelContext(model);
      const maxOutput = bridgeModelMaxOutput(model);
      document.getElementById('modelContextTokens').value = context || '';
      const outputText = maxOutput ? ` / ${maxOutput} max output` : '';
      const routingText = selectedRoutingMode() === 'forced'
        ? `强制主模型：会写 ANTHROPIC_MODEL=${model}。`
        : 'Claude 自动路由：不写 ANTHROPIC_MODEL，只保留 Haiku/Sonnet/Opus slot。';
      const contextText = context
        ? `${model} = ${context} context tokens${outputText}。`
        : `${model} 未探测到真实 context；自动压缩使用保守 ${CONSERVATIVE_COMPACT_WINDOW}，不会写 CLAUDE_CODE_MAX_CONTEXT_TOKENS。`;
      document.getElementById('bridgeModelMeta').textContent = `${routingText} ${contextText}`;
    }
    function renderBridgeModels() {
      const sel = document.getElementById('bridgeModel');
      if (!sel) return;
      sel.innerHTML = '';
      BRIDGE_MODELS.forEach((item) => {
        const opt = document.createElement('option');
        opt.value = item.id;
        const context = item.context_tokens ? ` · ${item.context_tokens}` : ' · context unknown';
        opt.textContent = `${item.name || item.id}${context}`;
        sel.appendChild(opt);
      });
      sel.value = DEFAULT_BRIDGE_MODEL;
      sel.onchange = () => applyModelContextPreset();
      const routingSel = document.getElementById('modelRoutingMode');
      if (routingSel) routingSel.onchange = () => updateBridgeModelMeta();
      updateBridgeModelMeta();
    }
    function setBridgeModel(modelId, applyContext = false) {
      const sel = document.getElementById('bridgeModel');
      const option = bridgeModelOption(modelId || DEFAULT_BRIDGE_MODEL);
      if (sel && option) sel.value = option.id;
      updateBridgeModelMeta();
      if (applyContext) applyModelContextPreset();
    }
    function bridgeModelConfigPayload() {
      const model = selectedBridgeModel();
      return {
        model,
        context_tokens: bridgeModelContext(model),
        max_output_tokens: bridgeModelMaxOutput(model)
      };
    }
    function forcedModelConfigPayload() {
      return selectedRoutingMode() === 'forced' ? bridgeModelConfigPayload() : null;
    }
    function setCompactFields(enabled, windowTokens, pct) {
      document.getElementById('compactEnabled').checked = Boolean(enabled);
      document.getElementById('compactWindow').value = windowTokens || '';
      document.getElementById('compactPct').value = pct || DEFAULT_COMPACT_PCT;
    }
    function compactConfigPayload() {
      return {
        enabled: document.getElementById('compactEnabled').checked,
        window_tokens: document.getElementById('compactWindow').value.trim(),
        threshold_percent: document.getElementById('compactPct').value.trim() || DEFAULT_COMPACT_PCT
      };
    }
    function applyCompactPreset(windowTokens, pct = DEFAULT_COMPACT_PCT) {
      setCompactFields(Boolean(windowTokens), windowTokens, pct);
    }
    function applyModelContextPreset() {
      const context = bridgeModelRecommendedCompact(selectedBridgeModel());
      updateBridgeModelMeta();
      if (context) setCompactFields(true, context, DEFAULT_COMPACT_PCT);
    }
    function providerCompactText(provider) {
      if (!provider || !provider.compact_enabled) return '关闭';
      const pct = provider.compact_threshold_percent || DEFAULT_COMPACT_PCT;
      return `${provider.compact_window_tokens || ''} / ${pct}%`;
    }
    function providerRoutingText(provider) {
      if (!provider) return '';
      const slots = [
        provider.haiku_model ? `H:${provider.haiku_model}` : '',
        provider.sonnet_model ? `S:${provider.sonnet_model}` : '',
        provider.opus_model ? `O:${provider.opus_model}` : ''
      ].filter(Boolean).join(' ');
      const context = provider.max_context_tokens ? `\nctx ${provider.max_context_tokens}` : '';
      if (provider.routing_mode === 'forced' || provider.model) {
        const legacy = provider.model_is_legacy_default ? ' · 旧默认?' : '';
        return `强制 ${provider.model || '-'}${legacy}${context}${slots ? `\n${slots}` : ''}`;
      }
      return `Claude 自动路由${context}${slots ? `\n${slots}` : ''}`;
    }
    function setSelectedProviderMeta(provider) {
      const box = document.getElementById('selectedProviderMeta');
      if (!box) return;
      if (!provider) {
        box.textContent = '当前账号 provider：未检测到，下面显示的是创建新 provider 的默认值。';
        return;
      }
      const routing = providerRoutingText(provider).replace(/\\n/g, '；');
      box.innerHTML = `当前账号 provider：<strong>${esc(provider.name || maskId(provider.id || ''))}</strong>；实际路由：${esc(routing || '未检测')}`;
    }
    function applyDefaultProviderForm() {
      setBridgeModel(DEFAULT_BRIDGE_MODEL, false);
      setRoutingMode('auto');
      setCompactFields(true, bridgeModelRecommendedCompact(DEFAULT_BRIDGE_MODEL), DEFAULT_COMPACT_PCT);
      setSelectedProviderMeta(null);
    }
    function applyCompactFromProvider(provider) {
      if (!provider) return;
      const nameInput = document.getElementById('providerName');
      if (nameInput && provider.name) nameInput.value = provider.name;
      setBridgeModel(provider.model || DEFAULT_BRIDGE_MODEL, false);
      setRoutingMode(provider.model ? 'forced' : 'auto');
      if (provider.compact_enabled) {
        setCompactFields(true, provider.compact_window_tokens || DEFAULT_COMPACT_WINDOW, provider.compact_threshold_percent || DEFAULT_COMPACT_PCT);
      } else {
        setCompactFields(false, '', DEFAULT_COMPACT_PCT);
      }
      setSelectedProviderMeta(provider);
    }
    function syncClaudeProviderFormForSelectedAccount(markRadio = true) {
      const provider = providerForSelectedClaudeAccount();
      if (!provider) {
        applyDefaultProviderForm();
        return null;
      }
      applyCompactFromProvider(provider);
      if (markRadio) markProviderPicked(provider.id);
      return provider;
    }
    function applyClaudeAccount(item) {
      if (!item) return;
      setSelectValue('account', item.account_id);
      setSelectValue('simpleClaudeAccount', item.account_id);
      document.getElementById('providerName').value = `Local Codex Bridge - ${accountSlug(item)}`;
      syncClaudeProviderFormForSelectedAccount();
    }
    function applyCliAccount(item) {
      if (!item) return;
      setSelectValue('cliAccount', item.account_id);
      setSelectValue('simpleCliAccount', item.account_id);
      applyCliAccountDefaults(item);
    }
    function applyGlobalCodexAccount(item) {
      if (!item) return;
      setSelectValue('simpleDefaultAccount', item.account_id);
    }
    function selectCliAccount(accountId) {
      const item = findAccount(accountId);
      if (!item) return;
      applyCliAccount(item);
      setSimpleResult(`单独 Codex CLI 已选择 ${accountLabel(item)}。`);
      log(`单独 Codex CLI 账号已选中: ${maskId(accountId)}`);
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
        const err = new Error(data.error || data.message || `HTTP ${resp.status}`);
        err.status = resp.status;
        err.payload = data;
        throw err;
      }
      return data;
    }
    function setInitState(message, cls='muted') {
      const status = document.getElementById('status');
      if (status) status.innerHTML = `<span class="${cls}">${esc(message)}</span>`;
    }
    function handleInitError(error) {
      const message = error && error.message ? error.message : String(error || 'unknown');
      const statusCode = error && error.status ? Number(error.status) : 0;
      setInitState(`初始化失败：${message}`, 'bad');
      const recommendation = document.getElementById('recommendation');
      if (recommendation) {
        recommendation.className = 'recommend fail';
        recommendation.innerHTML = `<b>页面初始化失败</b><br>- ${esc(message)}<br>- 如果刚重启过 BridgeDeck，请刷新页面。`;
      }
      log(`初始化失败: ${message}`);
      if ((statusCode === 403 || message.toLowerCase().includes('csrf')) && !sessionStorage.getItem('bridgedeckCsrfReloaded')) {
        sessionStorage.setItem('bridgedeckCsrfReloaded', '1');
        const next = new URL(window.location.href);
        next.searchParams.set('t', String(Date.now()));
        window.location.replace(next.toString());
      }
    }
    function renderAccounts(data) {
      const accounts = data.accounts || [];
      const actualGlobalAccount = data.current_codex_launcher ? data.current_codex_launcher.account_id : '';
      lastAccounts = accounts;
      const sel = document.getElementById('account');
      const cliSel = document.getElementById('cliAccount');
      const simpleClaudeSel = document.getElementById('simpleClaudeAccount');
      const simpleCliSel = document.getElementById('simpleCliAccount');
      const simpleApiSel = document.getElementById('simpleApiAccount');
      const simpleDefaultSel = document.getElementById('simpleDefaultAccount');
      const previous = {
        claude: simpleClaudeSel.value || sel.value,
        cli: simpleCliSel.value || cliSel.value,
        api: simpleApiSel.value,
        global: actualGlobalAccount || simpleDefaultSel.value
      };
      sel.innerHTML = '';
      cliSel.innerHTML = '';
      simpleClaudeSel.innerHTML = '';
      simpleCliSel.innerHTML = '';
      simpleApiSel.innerHTML = '';
      simpleDefaultSel.innerHTML = '';
      accounts.forEach((a) => {
        const opt = document.createElement('option');
        opt.value = a.account_id;
        const mail = a.email ? ` (${maskEmail(a.email)})` : '';
        opt.textContent = `${maskId(a.account_id)}${mail}`;
        sel.appendChild(opt);
        cliSel.appendChild(opt.cloneNode(true));
        simpleClaudeSel.appendChild(opt.cloneNode(true));
        simpleCliSel.appendChild(opt.cloneNode(true));
        simpleApiSel.appendChild(opt.cloneNode(true));
        simpleDefaultSel.appendChild(opt.cloneNode(true));
      });
      if (accounts.length > 0) {
        const a = accounts[0];
        if (previous.claude) {
          setSelectValue('account', previous.claude);
          setSelectValue('simpleClaudeAccount', previous.claude);
        } else if (!document.getElementById('providerName').value.trim()) {
          applyClaudeAccount(a);
        }
        if (previous.cli) {
          setSelectValue('cliAccount', previous.cli);
          setSelectValue('simpleCliAccount', previous.cli);
        } else if (!document.getElementById('cliHome').value.trim()) {
          applyCliAccount(a);
        }
        applyGlobalCodexAccount(findAccount(previous.global) || a);
        setSelectValue('simpleApiAccount', previous.api || previous.claude || a.account_id);
        syncClaudeProviderFormForSelectedAccount(false);
      }
      sel.onchange = () => {
        const item = accounts[sel.selectedIndex];
        if (item) {
          applyClaudeAccount(item);
          setSimpleResult(`Claude Code 已选择 ${accountLabel(item)}。`);
        }
      };
      cliSel.onchange = () => {
        const item = accounts[cliSel.selectedIndex];
        if (item) {
          applyCliAccount(item);
          setSimpleResult(`单独 Codex CLI 已选择 ${accountLabel(item)}。`);
        }
      };
      simpleClaudeSel.onchange = () => {
        const item = accounts[simpleClaudeSel.selectedIndex];
        if (!item) return;
        applyClaudeAccount(item);
        setSimpleResult(`Claude Code 已选择 ${accountLabel(item)}。`);
      };
      simpleCliSel.onchange = () => {
        const item = accounts[simpleCliSel.selectedIndex];
        if (!item) return;
        applyCliAccount(item);
        if (lastData) renderSimpleActuals(lastData);
        setSimpleResult(`单独 Codex CLI 已选择 ${accountLabel(item)}。`);
      };
      simpleApiSel.onchange = () => {
        const item = accounts[simpleApiSel.selectedIndex];
        if (!item) return;
        renderApiAccess();
        setSimpleResult(`通用 API 接入已选择 ${accountLabel(item)}。可复制 OpenAI 或 Anthropic .env。`);
      };
      simpleDefaultSel.onchange = () => {
        const item = accounts[simpleDefaultSel.selectedIndex];
        if (!item) return;
        applyGlobalCodexAccount(item);
        setSimpleResult(`全局 Codex CLI 已选择 ${accountLabel(item)}。点击按钮后只写固定入口，不改 Codex Desktop。`);
      };
      renderApiAccess();
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
          <td><button class="miniBtn" data-action="select-cli-account" data-account-id="${esc(a.account_id)}">选用</button></td>
        `;
        body.appendChild(tr);
      });
    }
    function renderProviders(data) {
      const body = document.querySelector('#providersTable tbody');
      body.innerHTML = '';
      const selectedAccountProvider = providerForSelectedClaudeAccount();
      data.providers.forEach((p) => {
        const tr = document.createElement('tr');
        const currentBySettings = data.current_provider_from_settings === p.id;
        const checked = selectedAccountProvider && selectedAccountProvider.id === p.id ? ' checked' : '';
        tr.innerHTML = `
          <td><label class="providerNameCell"><input type="radio" name="providerPick" value="${esc(p.id)}"${checked}><span class="providerNameText">${esc(p.name)}</span></label></td>
          <td>${p.is_current ? '<span class="ok">当前</span>' : '<span class="muted">未选</span>'} ${currentBySettings ? '<span class="ok">设置同步</span>' : ''}</td>
          <td class="mono">${esc(maskId(p.account_id || ''))}</td>
          <td class="mono">${esc(p.base_url || '')}</td>
          <td class="mono">${esc(providerRoutingText(p)).replace(/\\n/g, '<br>')}</td>
          <td class="mono">${esc(providerCompactText(p))}</td>
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
          <td>${p.is_current ? '<span class="ok">CC Switch 当前</span>' : '<span class="muted">备用</span>'}</td>
          <td>${esc(maskId(p.meta_account_id || ''))}</td>
          <td>${esc(maskId(p.token_account_id || ''))}</td>
          <td>${status}</td>
        `;
        body.appendChild(tr);
      });
    }
    function renderClaudeDesktopProviders(data) {
      const body = document.querySelector('#claudeDesktopProvidersTable tbody');
      if (!body) return;
      body.innerHTML = '';
      const providers = data.claude_desktop_providers || [];
      providers.forEach((p) => {
        const routes = p.desktop_routes || {};
        const routeText = ['claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-4-7'].map((key) => {
          const item = routes[key] || {};
          const oneM = item.supports1m === true ? '1m' : 'std';
          return `${key} -> ${item.model || '-'} (${oneM})`;
        }).join('\\n');
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${esc(p.name || '')}<br><span class="muted">${esc(p.api_format || '-')} / ${esc(p.desktop_mode || '-')}</span></td>
          <td>${p.is_current ? '<span class="ok">当前</span>' : '<span class="muted">备用</span>'}</td>
          <td class="mono">${esc(maskId(p.account_id || ''))}</td>
          <td class="mono">${esc(routeText).split('\\n').join('<br>')}</td>
          <td>${p.desktop_routes_ok ? '<span class="ok">ok</span>' : '<span class="warnText">需修复</span>'}</td>
        `;
        body.appendChild(tr);
      });
      if (!providers.length) {
        body.innerHTML = '<tr><td colspan="5">未检测到 Claude Desktop provider。</td></tr>';
      }
      const status = data.ccswitch_315 || {};
      const box = document.getElementById('ccswitch315Status');
      if (box) {
        const issueCount = Number(status.desktop_route_issue_count || 0);
        box.className = `recommend ${issueCount ? 'warnState' : 'okState'}`;
        box.textContent = `CC Switch 3.15：Claude Code ${status.claude_provider_count || 0} 个，Claude Desktop ${status.claude_desktop_provider_count || 0} 个，Desktop 路由问题 ${issueCount} 个。`;
      }
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
        stale_launcher: '旧 CLI token',
        default: '默认配置',
        custom: '自定义配置',
        cc_switch: 'CC Switch',
        bridgedeck_provider: 'BridgeDeck Stability Route',
        bridgedeck_or_local_bridge: 'BridgeDeck 本地桥',
        unknown: '未知'
      };
      return map[value] || value || '';
    }
    function renderAccountMatrix(data) {
      const body = document.querySelector('#accountMatrixTable tbody');
      body.innerHTML = '';
      const desktop = data.codex_desktop || {};
      const desktopAccount = desktop.account_id || '';
      const desktopUnknown = desktopUnmappedText(desktop);
      (data.account_matrix || []).forEach((row) => {
        const status = row.account_status || 'ok';
        const cls = status === 'ok' ? 'ok' : (status === 'stale_launcher' ? 'warnText' : 'bad');
        const tr = document.createElement('tr');
        const desktopLabel = row.account_id && desktopAccount ? (row.account_id === desktopAccount ? '默认' : '备用') : desktopUnknown;
        tr.innerHTML = `
          <td>${esc(maskEmail(row.email || row.label || maskId(row.account_id || '')))}</td>
          <td>${row.claude_current ? '<span class="ok">当前</span>' : '<span class="muted">备用</span>'}</td>
          <td>${(row.cli_launchers || []).length ? '<span class="ok">launcher</span>' : '<span class="warnText">未生成</span>'}</td>
          <td>${esc(desktopLabel)}</td>
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
      const providerCount = data.providers.length + (data.claude_desktop_providers || []).length;
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
      let text = '状态正常。日常只需要用下面的“先选账号，再选工具”。';
      if (accountCount === 0) {
        state = 'warnState';
        text = '未发现 CC Switch Codex OAuth 账号。先在 CC Switch 登录目标 ChatGPT 账号，再回这里刷新。';
      } else if (staleCount > 0) {
        state = 'warnState';
        text = `发现 ${staleCount} 个旧 CLI tokenful profile。建议迁移为 launcher-only，避免 refresh_token 重复使用。`;
      } else if (mismatchCount > 0) {
        state = 'badState';
        text = `当前有 ${accountCount} 个账号；${mismatchCount} 个 Codex Provider 的绑定账号与实际 token 账号不一致。回 CC Switch 重新授权红色 provider。`;
      } else if (providerCount === 0) {
        state = 'warnState';
        text = '还没有 Claude 配置。选择账号后点“Claude Code 用这个账号”。';
      }
      box.className = `recommend ${state}`;
      box.textContent = text;
    }
    function renderDiagnosis(data) {
      const currentCodex = data.codex_providers.filter((p) => p.is_current);
      const mismatches = data.codex_providers.filter((p) => p.token_mismatch);
      const defaultCli = data.cli_homes.find((h) => humanPath(h.path) === '~/.codex');
      const desktop = data.codex_desktop || {};
      const launcher = data.current_codex_launcher || {};
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
      if (desktop.account_id || desktop.managed_by) {
        advice.push(`Codex Desktop：${desktopAccountText(data)}，${desktopModeText(data)}。`);
      } else {
        state = state === 'badState' ? state : 'warnState';
        advice.push('未检测到 Codex Desktop 配置状态。');
      }
      if (launcher.exists || launcher.account_id) {
        advice.push(`固定入口/OMC/tmux：${currentLauncherAccountText(data)}，${currentLauncherModeText(data)}；${omcShimText(data)}。`);
      }
      if (defaultCli) {
        const defaultToken = maskEmail(defaultCli.email || '') || maskId(defaultCli.token_account_id || defaultCli.access_account_id || '');
        advice.push(`~/.codex/auth.json token：${defaultToken || '无账号信息'}。`);
      } else {
        advice.push('未检测到 ~/.codex/auth.json token；全局入口以 Desktop/固定入口实际状态为准。');
      }
      const box = document.getElementById('diagnosis');
      box.className = `recommend ${state}`;
      box.innerHTML = `<b>自动检测意见</b><br>${advice.map((item) => `- ${esc(item)}`).join('<br>')}`;
    }
    async function refreshData(showFeedback=false) {
      if (showFeedback) {
        const result = document.getElementById('simpleResult');
        if (result) result.dataset.touched = '1';
        setSimpleResult('正在刷新状态...');
      }
      const data = await api(tokenVisible ? '/api/data?include_secrets=1' : '/api/data');
      lastData = data;
      const mismatches = data.codex_providers.filter((p) => p.token_mismatch).length;
      document.getElementById('status').innerHTML = `版本: <b>${esc(data.version || '')}</b> | 账号: <b>${data.accounts.length}</b> | Claude providers: <b>${data.providers.length}</b> | Codex mismatches: <b class="${mismatches ? 'bad' : 'ok'}">${mismatches}</b>`;
      document.getElementById('paths').textContent = `db: ${humanPath(data.paths.db)}\\nsettings: ${humanPath(data.paths.settings)}\\nauth_store: ${humanPath(data.paths.auth_store)}`;
      renderHealth(data);
      renderOverviewDashboard(data);
      renderUsageDashboard(data);
      renderAccounts(data);
      renderAccountMatrix(data);
      renderProviders(data);
      renderCodexProviders(data);
      renderClaudeDesktopProviders(data);
      renderCliHomes(data);
      renderDiagnosis(data);
      renderStreamDiagnostics(data);
      renderHookRiskDiagnostics(data);
      renderActualCurrentAccounts(data);
      renderPluginSync(data);
      renderAttributionHeader(data);
      renderSimpleActuals(data);
      renderAutoSwitchConfig(data);
      renderAimamiSync(data.aimami_sync || {});
      renderAimamiFollow(data.aimami_follow || {});
      refreshServices().catch((e) => {
        const box = document.getElementById('serviceStatus');
        if (box) box.textContent = `服务状态失败: ${e.message}`;
      });
      refreshCodexDesktopDoctor().catch((e) => {
        const box = document.getElementById('codexDesktopDoctor');
        if (box) box.textContent = `Codex Desktop Doctor 失败: ${e.message}`;
      });
      refreshQuotas();
      if (data.aimami_follow && data.aimami_follow.enabled) {
        runAimamiFollow(false, false).catch((e) => log(`AiMaMi follow 失败: ${e.message}`));
      }
      if (data.auto_switch && data.auto_switch.enabled) {
        runAutoSwitch(false, false).catch((e) => log(`自动切换失败: ${e.message}`));
      }
      if (data.accounts.length > 0 && !document.getElementById('simpleResult').dataset.touched) {
        setSimpleResult('已准备好。Claude Code、单独 Codex CLI、全局 Codex CLI 可以分别选不同账号。');
      }
      const refreshedAt = new Date().toLocaleTimeString();
      if (showFeedback) setSimpleResult(`已刷新：${refreshedAt}`, 'ok');
      log(`数据已刷新: ${refreshedAt}`);
      refreshAccountPool();
      refreshApiKeys();
      refreshServiceControl();
    }
    async function createProvider() {
      const accountId = document.getElementById('account').value;
      const providerName = document.getElementById('providerName').value.trim();
      const setCurrent = document.getElementById('setCurrent').checked;
      if (!accountId || !providerName) {
        log('请选择账号并填写 provider 名称');
        return;
      }
      const res = await api('/api/create-provider', 'POST', {
        account_id: accountId,
        provider_name: providerName,
        set_current: setCurrent,
        context_config: bridgeModelConfigPayload(),
        model_config: forcedModelConfigPayload(),
        compact_config: compactConfigPayload()
      });
      log(`${res.message}: ${res.provider_name} (${res.provider_id})`);
      await refreshData();
      return res;
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
      return res;
    }
    async function simpleClaude() {
      const item = selectedAccount('simpleClaudeAccount');
      if (!item) return setSimpleResult('先选择一个账号。', 'warn');
      applyClaudeAccount(item);
      document.getElementById('setCurrent').checked = true;
      document.getElementById('simpleResult').dataset.touched = '1';
      setSimpleResult(`正在让 Claude Code 使用 ${accountLabel(item)}...`);
      await createProvider();
      setSimpleResult(`完成：Claude Code 现在使用 ${accountLabel(item)}，CC Switch 当前 Claude Provider 已同步。`, 'ok');
    }
    async function simpleCli() {
      const item = selectedAccount('simpleCliAccount');
      if (!item) return setSimpleResult('先选择一个账号。', 'warn');
      applyCliAccount(item);
      document.getElementById('simpleResult').dataset.touched = '1';
      setSimpleResult(`正在准备 ${accountLabel(item)} 的单独 Codex CLI...`);
      const res = await createCliHome();
      setSimpleResult(`完成：单独 Codex CLI 已准备好。启动器：${humanPath(res.launcher)}。`, 'ok');
    }
    async function simpleDefaultCodex() {
      const item = selectedAccount('simpleDefaultAccount');
      if (!item) return setSimpleResult('先选择一个账号。', 'warn');
      applyGlobalCodexAccount(item);
      document.getElementById('simpleResult').dataset.touched = '1';
      setSimpleResult(`正在把全局 Codex CLI 固定入口设为 ${accountLabel(item)}...`);
      const res = await api('/api/set-default-codex', 'POST', { account_id: item.account_id });
      await refreshData();
      const currentLauncher = res.current_launcher ? `；固定入口：${humanPath(res.current_launcher)}` : '';
      const omcText = (res.omc_codex_shims || []).length ? '；OMC/tmux 已接管 codex' : '';
      setSimpleResult(`完成：全局 Codex CLI 固定入口已设为 ${accountLabel(item)}${currentLauncher}${omcText}；Codex Desktop 未改动。`, 'ok');
      log(`${res.message}: ${currentLauncher || humanPath(res.current_launcher || '')}`);
    }
    async function enableDesktopBridgeMode() {
      setSimpleResult('Codex Desktop Stability Route 已禁用：Local Bridge 不支持 /v1/responses/compact，不写入 ~/.codex/config.toml。', 'warn');
    }
    async function restoreDesktopNativeMode() {
      const res = await api('/api/codex-desktop-native-mode', 'POST', {});
      await refreshData();
      const backup = res.backup ? `；备份：${humanPath(res.backup)}` : '';
      setSimpleResult(`${res.message}${backup}。重启 Codex Desktop 后生效。`, res.changed ? 'ok' : '');
      log(`${res.message}: ${humanPath(res.config_path)}；removed=${(res.removed || []).join(', ') || '-'}`);
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
      return res;
    }
    async function setCurrentFromSelected() {
      const id = selectedProviderActionId();
      if (!id) return log('请先选账号或选中一个 provider');
      const res = await api('/api/set-current', 'POST', { provider_id: id });
      log(`${res.message}: ${id}`);
      await refreshData();
    }
    async function patchSelected() {
      const id = selectedProviderActionId();
      if (!id) return log('请先选账号或选中一个 provider');
      const res = await api('/api/patch-provider', 'POST', { provider_id: id });
      log(`${res.message}: ${id}`);
      await refreshData();
    }
    async function saveCompactSelected() {
      const id = selectedProviderActionId();
      if (!id) return log('请先选账号或选中一个 provider');
      const res = await api('/api/provider-compact', 'POST', { provider_id: id, context_config: bridgeModelConfigPayload(), compact_config: compactConfigPayload() });
      log(`${res.message}: ${providerCompactText({ compact_enabled: res.compact_config.enabled, compact_window_tokens: res.compact_config.window_tokens, compact_threshold_percent: res.compact_config.threshold_percent })}`);
      await refreshData();
    }
    async function saveForcedModelSelected() {
      const id = selectedProviderActionId();
      if (!id) return log('请先选账号或选中一个 provider');
      const res = await api('/api/provider-model', 'POST', { provider_id: id, model_config: bridgeModelConfigPayload() });
      setRoutingMode('forced');
      log(`${res.message}: ${res.model_config.model}`);
      await refreshData();
    }
    async function clearForcedModelSelected() {
      const id = selectedProviderActionId();
      if (!id) return log('请先选账号或选中一个 provider');
      const preview = await api('/api/provider-routing', 'POST', { provider_id: id, mode: 'auto', apply: false });
      if (!preview.changed) {
        log('该 provider 已经是 Claude 自动路由。');
        return;
      }
      const message = `将移除 ANTHROPIC_MODEL=${preview.removed_model}，保留 Haiku/Sonnet/Opus slot 映射。继续？`;
      if (!window.confirm(message)) {
        log('已取消改为 Claude 自动路由。');
        return;
      }
      const res = await api('/api/provider-routing', 'POST', { provider_id: id, mode: 'auto', apply: true });
      setRoutingMode('auto');
      log(`${res.message}: 已移除 ${res.removed_model || '-'}`);
      await refreshData();
    }
    async function syncCommonEnvSelected() {
      const id = selectedProviderActionId();
      if (!id) return log('请先选账号或选中一个 provider');
      const res = await api('/api/sync-common-env', 'POST', { provider_id: id });
      log(`${res.message}: 更新 ${res.updated.length} 个，跳过 ${res.skipped.length} 个；keys: ${res.env_keys.join(', ')}`);
      await refreshData();
    }
    async function copyApiBaseUrl() {
      return copyText(apiAccessBaseUrl(selectedAccount('simpleApiAccount')), 'BASE_URL');
    }
    async function copyApiEnv() {
      return copyText(apiOpenAiEnv(selectedAccount('simpleApiAccount')), 'OpenAI env');
    }
    async function copyClaudeEnv() {
      return copyText(apiClaudeEnv(selectedAccount('simpleApiAccount')), 'Desktop Gateway');
    }
    async function syncClaudePlugins() {
      const res = await api('/api/sync-claude-plugins', 'POST', {});
      const added = res.added && res.added.length ? `新增：${res.added.join(', ')}` : '没有新增';
      log(`插件启用态已同步：${added}`);
      await refreshData();
    }
    async function extractSafeCommonConfig() {
      const res = await api('/api/extract-safe-common-config', 'POST', {});
      const keys = [...(res.keys || []), ...(res.env_keys || []).map((key) => `env.${key}`)];
      log(`${res.message}: ${keys.length ? keys.join(', ') : '没有可提取项'}；移除 env ${res.removed_env_keys.length} 项`);
      await refreshData();
    }
    function dedupePlanText(plan) {
      if (!plan || !plan.length) return '没有重复 Local Bridge provider';
      return plan.map((item) => {
        const deleted = item.delete.map((p) => p.name).join(', ');
        const switchText = item.switch_current_to ? '，会切换当前项' : '';
        return `${item.keep.name} 保留；删除 ${deleted}${switchText}`;
      }).join(' | ');
    }
    async function dedupeBridgeProviders(apply=false) {
      if (apply && !confirm('只会删除同账号重复的 Local Bridge provider，并先备份。继续？')) return;
      const res = await api('/api/dedupe-bridge-providers', 'POST', { apply });
      log(apply ? `${res.message}: 删除 ${res.deleted.length} 个；${dedupePlanText(res.plan)}` : dedupePlanText(res.plan));
      await refreshData();
    }
    async function repairPlusPro() {
      const res = await api('/api/repair-plus-pro', 'POST', {});
      log(`${res.message}: ${JSON.stringify(res.patched)}`);
      await refreshData();
    }
    function desktopRoutePlanText(plan) {
      if (!plan || !plan.length) return '没有需要修复的 Claude Desktop Local Bridge provider';
      return plan.map((item) => {
        const issueCount = (item.issues || []).length;
        return `${item.name}: ${item.changed ? `修复 ${issueCount} 项` : '已正确'}`;
      }).join(' | ');
    }
    async function repairCcswitch315DesktopRoutes(apply=false) {
      if (apply && !confirm('只会修复 Claude Desktop Local Bridge provider 的 3.15 路由字段，并先备份。继续？')) return;
      const res = await api('/api/ccswitch-315-desktop-routes', 'POST', { apply });
      log(apply ? `${res.message}: 更新 ${res.updated.length} 个；${desktopRoutePlanText(res.plan)}` : desktopRoutePlanText(res.plan));
      await refreshData();
    }
    function bindActions() {
      document.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) return;
        const action = button.dataset.action;
        const run = async () => {
          if (action === 'scroll') return scrollToSection(button.dataset.target || '');
          if (action === 'refresh') return refreshData(true);
          if (action === 'start-codex-oauth') return startCodexOAuth();
          if (action === 'finish-codex-oauth') return finishCodexOAuth();
          if (action === 'check-codex-oauth') return checkCodexOAuthStatus();
          if (action === 'hide-codex-oauth') return hideCodexOAuth();
          if (action === 'apply-codex-oauth-bridge') return applyCodexOAuthBridge();
          if (action === 'create-provider') return createProvider();
          if (action === 'create-cli-home') return createCliHome();
          if (action === 'simple-claude') return simpleClaude();
          if (action === 'simple-cli') return simpleCli();
          if (action === 'simple-default-codex') return simpleDefaultCodex();
          if (action === 'enable-desktop-bridge-mode') return enableDesktopBridgeMode();
          if (action === 'restore-desktop-native-mode') return restoreDesktopNativeMode();
          if (action === 'copy-api-key') return copyApiKey();
          if (action === 'copy-api-base-url') return copyApiBaseUrl();
          if (action === 'copy-api-env') return copyApiEnv();
          if (action === 'copy-anthropic-token') return copyAnthropicToken();
          if (action === 'copy-anthropic-base-url') return copyAnthropicBaseUrl();
          if (action === 'copy-anthropic-env') return copyAnthropicEnv();
          if (action === 'copy-anthropic-forced-env') return copyAnthropicForcedEnv();
          if (action === 'migrate-cli-home') return migrateCliHome();
          if (action === 'toggle-tokens') return toggleTokens();
          if (action === 'set-current-selected') return setCurrentFromSelected();
          if (action === 'patch-selected') return patchSelected();
          if (action === 'repair-plus-pro') return repairPlusPro();
          if (action === 'compact-preset-model') return applyModelContextPreset();
          if (action === 'compact-preset-220k') return applyCompactPreset(CONSERVATIVE_COMPACT_WINDOW);
          if (action === 'compact-preset-1m') return applyCompactPreset('1000000');
          if (action === 'compact-off') return applyCompactPreset('');
          if (action === 'save-compact-selected') return saveCompactSelected();
          if (action === 'save-forced-model-selected') return saveForcedModelSelected();
          if (action === 'clear-forced-model-selected') return clearForcedModelSelected();
          if (action === 'sync-common-env-selected') return syncCommonEnvSelected();
          if (action === 'copy-api-base-url') return copyApiBaseUrl();
          if (action === 'copy-api-env') return copyApiEnv();
          if (action === 'copy-claude-env') return copyClaudeEnv();
          if (action === 'extract-safe-common-config') return extractSafeCommonConfig();
          if (action === 'sync-claude-plugins') return syncClaudePlugins();
          if (action === 'save-auto-switch') return saveAutoSwitch();
          if (action === 'run-auto-switch') return runAutoSwitch(true, true);
          if (action === 'create-missing-bridges') return createMissingBridges();
          if (action === 'preview-aimami-import') return previewAimamiImport();
          if (action === 'import-aimami-accounts') return importAimamiAccounts(false);
          if (action === 'import-aimami-and-bridges') return importAimamiAccounts(true);
          if (action === 'save-aimami-follow') return saveAimamiFollow();
          if (action === 'run-aimami-follow') return runAimamiFollow(true, true);
          if (action === 'preview-aimami-export') return previewAimamiExport();
          if (action === 'export-aimami-accounts') return exportAimamiAccounts();
          if (action === 'preview-aimami-inject') return previewAimamiInject();
          if (action === 'inject-aimami-accounts') return injectAimamiAccounts();
          if (action === 'preview-bridge-dedupe') return dedupeBridgeProviders(false);
          if (action === 'apply-bridge-dedupe') return dedupeBridgeProviders(true);
          if (action === 'preview-ccswitch-315-desktop-routes') return repairCcswitch315DesktopRoutes(false);
          if (action === 'apply-ccswitch-315-desktop-routes') return repairCcswitch315DesktopRoutes(true);
          if (action === 'refresh-services') return refreshServices();
          if (action === 'install-scan') return runInstallScan();
          if (action === 'proxy-diagnosis') return runProxyDiagnosis();
          if (action === 'codex-desktop-doctor') return refreshCodexDesktopDoctor();
          if (action === 'codex-native-proxy-status') return runCodexNativeProxyStatus();
          if (action === 'repair-codex-native-proxy') return repairCodexNativeProxy();
          if (action === 'normalize-codex-hooks-config') return normalizeCodexHooksConfig();
          if (action === 'repair-quota-query') return repairQuotaQuery();
          if (action === 'repair-codex-env-conflicts') return repairCodexEnvConflicts();
          if (action === 'repair-claude-attribution-header') return repairClaudeAttributionHeader();
          if (action === 'show-attribution-header-paths') return showAttributionHeaderPaths();
          if (action === 'keep-attribution-header') return keepAttributionHeader();
          if (action === 'start-local-bridge') return controlLocalBridge('start');
          if (action === 'stop-local-bridge') return controlLocalBridge('stop');
          if (action === 'restart-local-bridge') return controlLocalBridge('restart');
          if (action === 'stop-bridgedeck-ui') return stopBridgeDeckUi();
          if (action === 'select-cli-account') return selectCliAccount(button.dataset.accountId || '');
          // New Phase 4 actions
          if (action === 'set-default-account') return setDefaultAccount();
          if (action === 'create-api-key') return createApiKey();
          if (action === 'service-start') return serviceControl('start');
          if (action === 'service-stop') return serviceControl('stop');
          if (action === 'service-restart') return serviceControl('restart');
          if (action === 'launchd-load') return launchdControl('load');
          if (action === 'launchd-unload') return launchdControl('unload');
        };
        const originalText = button.textContent;
        const shouldShowBusy = action === 'refresh';
        if (shouldShowBusy) {
          button.disabled = true;
          button.textContent = '刷新中...';
        }
        Promise.resolve(run())
          .catch((e) => log(`操作失败: ${e.message}`))
          .finally(() => {
            if (shouldShowBusy) {
              button.disabled = false;
              button.textContent = originalText;
            }
          });
      });
      document.addEventListener('change', (event) => {
        const target = event.target;
        if (target && target.matches && target.matches('input[name="providerPick"]')) {
          applyCompactFromProvider(selectedProvider());
        }
      });
    }
    initPageNav();
    bindActions();
    renderBridgeModels();
    initGuideObserver();
    setInitState('正在连接本地 UI 服务...');
    refreshData().catch(handleInitError);
    setInterval(() => {
      if (document.getElementById('autoSwitchEnabled')?.checked) {
        runAutoSwitch(false, false).catch((e) => log(`自动切换失败: ${e.message}`));
        refreshQuotas();
      }
    }, 60000);
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

        def _shutdown_server_later(self) -> None:
            server = self.server

            def stop() -> None:
                time.sleep(0.2)
                server.shutdown()

            threading.Thread(target=stop, daemon=True).start()

        def do_GET(self) -> None:
            if not self._valid_host():
                json_response(self, 403, {"ok": False, "error": "Invalid Host header"})
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                body = (
                    INDEX_HTML.replace("__CSRF_TOKEN__", csrf_token)
                    .replace("__CSP_NONCE__", csp_nonce)
                    .replace("__LOCAL_BRIDGE_BASE_URL__", LOCAL_BRIDGE_BASE_URL)
                    .replace("__BRIDGE_MODELS_JSON__", json.dumps(BRIDGE_MODEL_OPTIONS, ensure_ascii=False))
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
            if parsed.path in {"/healthz", "/api/public-health"}:
                try:
                    host = host_from_header(self.headers.get("Host"))
                    if not is_loopback_host(host):
                        json_response(self, 403, {"ok": False, "error": "Loopback host required"})
                        return
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    payload = manager.health()
                    if hasattr(manager, "codex_desktop_doctor"):
                        payload["codex_desktop_doctor"] = manager.codex_desktop_doctor()
                    payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/install-scan":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = bridge_install_scan()
                    json_response(self, 200 if payload.get("ok") else 500, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/services":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.services(server_port=int(self.server.server_port))
                    if not allow_sensitive:
                        payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/codex-desktop-doctor":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.codex_desktop_doctor()
                    if not allow_sensitive:
                        payload = redact_snapshot({"codex_desktop_doctor": payload})["codex_desktop_doctor"]
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/proxy-diagnosis":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.proxy_diagnosis()
                    if not allow_sensitive:
                        payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/codex-native-proxy-status":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.codex_native_proxy_status()
                    if not allow_sensitive:
                        payload = redact_snapshot({"codex_native_proxy": payload})["codex_native_proxy"]
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/quotas":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.quotas()
                    payload["missing"] = manager.missing_bridge_accounts(payload.get("quotas"))
                    if not allow_sensitive:
                        payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/account-pool":
                try:
                    accounts = manager._load_accounts()
                    quotas = manager.quotas().get("quotas", [])
                    quota_map = {str(q.get("account_id") or ""): q for q in quotas if isinstance(q, dict)}
                    default_id = ""
                    auth_raw = manager._load_auth_store_raw()
                    if isinstance(auth_raw, dict):
                        default_id = str(auth_raw.get("default_account_id") or "")
                    pool = []
                    for acct in accounts:
                        aid = str(acct.get("account_id") or "")
                        q = quota_map.get(aid, {})
                        pool.append({
                            "account_id": aid,
                            "email": str(acct.get("email") or ""),
                            "is_default": aid == default_id,
                            "quota": q.get("quota"),
                            "usage": q.get("usage"),
                            "source": str(acct.get("source") or ""),
                        })
                    json_response(self, 200, {"ok": True, "default_account_id": default_id, "pool": pool})
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/codex-oauth/status":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    flow_id = (urllib.parse.parse_qs(parsed.query).get("flow_id") or [""])[0]
                    json_response(self, 200, manager.codex_oauth_status(flow_id))
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/aimami-sync/status":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.aimami_import_preview()
                    if not allow_sensitive:
                        payload = redact_snapshot({"aimami_sync": payload})["aimami_sync"]
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/aimami-sync/export-preview":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.aimami_export_preview()
                    if not allow_sensitive:
                        payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/aimami-sync/inject-preview":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    payload = manager.aimami_inject_preview()
                    if not allow_sensitive:
                        payload = redact_snapshot(payload)
                    json_response(self, 200, payload)
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/keys":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    json_response(self, 200, manager.list_api_keys())
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/account-pool":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    if not self._valid_csrf():
                        json_response(self, 403, {"ok": False, "error": "Invalid CSRF token"})
                        return
                    json_response(self, 200, manager.account_pool())
                except Exception as exc:  # noqa: BLE001
                    json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/launchd-status":
                try:
                    if not self._valid_fetch_metadata():
                        json_response(self, 403, {"ok": False, "error": "Invalid fetch metadata"})
                        return
                    json_response(self, 200, manager.launchd_status())
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
                    compact_config = payload.get("compact_config") if isinstance(payload.get("compact_config"), dict) else None
                    context_config = payload.get("context_config") if isinstance(payload.get("context_config"), dict) else None
                    model_config = payload.get("model_config") if isinstance(payload.get("model_config"), dict) else None
                    result = manager.create_or_update_provider(
                        account_id,
                        provider_name,
                        set_current,
                        compact_config=compact_config,
                        context_config=context_config,
                        model_config=model_config,
                    )
                    json_response(self, 200, result)
                    return
                if self.path == "/api/patch-provider":
                    provider_id = str(payload.get("provider_id") or "")
                    result = manager.patch_provider(provider_id)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/provider-compact":
                    provider_id = str(payload.get("provider_id") or "")
                    compact_config = payload.get("compact_config") if isinstance(payload.get("compact_config"), dict) else {}
                    context_config = payload.get("context_config") if isinstance(payload.get("context_config"), dict) else None
                    result = manager.update_provider_compact(provider_id, compact_config, context_config=context_config)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/provider-model":
                    provider_id = str(payload.get("provider_id") or "")
                    model_config = payload.get("model_config") if isinstance(payload.get("model_config"), dict) else None
                    result = manager.update_provider_forced_model(provider_id, model_config)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/provider-routing":
                    provider_id = str(payload.get("provider_id") or "")
                    mode = str(payload.get("mode") or "auto")
                    if mode != "auto":
                        raise ValueError("仅支持切换到 Claude 自动路由")
                    result = manager.clear_provider_forced_model(provider_id, apply=bool(payload.get("apply", False)))
                    json_response(self, 200, result)
                    return
                if self.path == "/api/sync-common-env":
                    provider_id = str(payload.get("provider_id") or "")
                    result = manager.sync_common_env_to_bridge_providers(provider_id)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/sync-claude-plugins":
                    result = manager.sync_claude_enabled_plugins()
                    json_response(self, 200, result)
                    return
                if self.path == "/api/extract-safe-common-config":
                    result = manager.extract_safe_claude_common_config()
                    json_response(self, 200, result)
                    return
                if self.path == "/api/dedupe-bridge-providers":
                    result = manager.dedupe_bridge_providers(apply=bool(payload.get("apply", False)))
                    json_response(self, 200, result)
                    return
                if self.path == "/api/repair-plus-pro":
                    result = manager.repair_plus_pro()
                    json_response(self, 200, result)
                    return
                if self.path == "/api/ccswitch-315-desktop-routes":
                    result = manager.repair_ccswitch_315_desktop_routes(apply=bool(payload.get("apply", False)))
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
                if self.path == "/api/set-default-codex":
                    account_id = str(payload.get("account_id") or "")
                    result = manager.set_default_codex_account(account_id)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/codex-desktop-bridge-mode":
                    account_id = str(payload.get("account_id") or "")
                    result = manager.enable_codex_desktop_bridge_mode(account_id)
                    json_response(self, 200 if result.get("ok", True) else 409, result)
                    return
                if self.path == "/api/codex-desktop-native-mode":
                    result = manager.restore_codex_desktop_native_mode()
                    json_response(self, 200, result)
                    return
                if self.path == "/api/migrate-cli-launcher":
                    account_id = str(payload.get("account_id") or "")
                    target_dir = str(payload.get("target_dir") or "")
                    profile_name = str(payload.get("profile_name") or "")
                    result = manager.migrate_cli_launcher(account_id, target_dir, profile_name)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/auto-switch-config":
                    result = manager.update_auto_switch_config(payload)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/auto-switch-run":
                    result = manager.run_auto_switch(force=bool(payload.get("force", False)))
                    json_response(self, 200, result)
                    return
                if self.path == "/api/aimami-follow-config":
                    result = manager.update_aimami_follow_config(payload)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/aimami-follow-run":
                    result = manager.run_aimami_follow(force=bool(payload.get("force", False)))
                    json_response(self, 200, result)
                    return
                if self.path == "/api/create-missing-bridges":
                    result = manager.create_missing_bridge_providers()
                    json_response(self, 200, result)
                    return
                if self.path == "/api/aimami-sync/import":
                    result = manager.import_aimami_accounts(create_missing=bool(payload.get("create_missing", False)))
                    json_response(self, 200, result)
                    return
                if self.path == "/api/aimami-sync/export":
                    account_ids = payload.get("account_ids") if isinstance(payload.get("account_ids"), list) else []
                    result = manager.export_aimami_accounts([str(item) for item in account_ids])
                    json_response(self, 200 if result.get("ok", True) else 409, result)
                    return
                if self.path == "/api/aimami-sync/inject":
                    account_ids = payload.get("account_ids") if isinstance(payload.get("account_ids"), list) else []
                    result = manager.inject_aimami_accounts(
                        account_ids=[str(item) for item in account_ids],
                        mode=str(payload.get("mode") or "codex_snapshot"),
                        set_active=bool(payload.get("set_active", False)),
                        overwrite=bool(payload.get("overwrite", False)),
                    )
                    json_response(self, 200 if result.get("ok", True) else 409, result)
                    return
                if self.path == "/api/codex-oauth/start":
                    result = manager.start_codex_oauth(set_default=bool(payload.get("set_default", False)))
                    json_response(self, 200, result)
                    return
                if self.path == "/api/codex-oauth/apply-bridge":
                    flow_id = str(payload.get("flow_id") or "")
                    result = manager.apply_codex_oauth_bridge(flow_id)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/codex-oauth/finish":
                    flow_id = str(payload.get("flow_id") or "")
                    code_input = str(payload.get("code") or payload.get("code_or_url") or "")
                    result = manager.complete_codex_oauth(flow_id, code_input)
                    json_response(self, 200 if result.get("ok", True) else 400, result)
                    return
                if self.path == "/api/local-bridge-control":
                    result = manager.control_local_bridge(
                        str(payload.get("action") or ""),
                        force=bool(payload.get("force")),
                    )
                    status = 200 if result.get("ok") else (409 if result.get("requires_force") else 400)
                    json_response(self, status, result)
                    return
                if self.path == "/api/ui-control":
                    action = str(payload.get("action") or "")
                    if action != "shutdown":
                        json_response(self, 400, {"ok": False, "error": "Unsupported UI action"})
                        return
                    json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "message": "BridgeDeck UI 正在关闭；Local Bridge 保持运行。重新打开 BridgeDeck.app 可恢复 UI。",
                        },
                    )
                    self._shutdown_server_later()
                    return
                if self.path == "/api/repair-quota-query":
                    result = manager.repair_quota_query()
                    json_response(self, 200 if result.get("ok", True) else 400, result)
                    return
                if self.path == "/api/repair-codex-env-conflicts":
                    result = manager.repair_codex_environment_conflicts()
                    json_response(self, 200 if result.get("ok", True) else 400, result)
                    return
                if self.path == "/api/repair-codex-native-proxy":
                    result = manager.repair_codex_native_proxy()
                    json_response(self, 200 if result.get("ok", True) else 400, result)
                    return
                if self.path == "/api/normalize-codex-hooks-config":
                    result = manager.normalize_codex_hooks_config()
                    json_response(self, 200 if result.get("ok", True) else 400, result)
                    return
                if self.path == "/api/repair-claude-attribution-header":
                    result = manager.repair_claude_attribution_header()
                    json_response(self, 200 if result.get("ok", True) else 400, result)
                    return
                if self.path == "/api/keys/create":
                    label = str(payload.get("label") or "")
                    result = manager.create_api_key(label)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/keys/revoke":
                    key = str(payload.get("key") or "")
                    result = manager.revoke_api_key(key)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/set-default-account":
                    account_id = str(payload.get("account_id") or "")
                    if not account_id:
                        json_response(self, 400, {"ok": False, "error": "Missing account_id"})
                        return
                    auth_raw = manager._load_auth_store_raw()
                    if not isinstance(auth_raw, dict):
                        auth_raw = {}
                    accounts = auth_raw.get("accounts") if isinstance(auth_raw.get("accounts"), dict) else {}
                    if account_id not in accounts:
                        json_response(self, 400, {"ok": False, "error": f"Account {account_id} not found"})
                        return
                    auth_raw["default_account_id"] = account_id
                    manager.paths.auth_store.write_text(json.dumps(auth_raw, ensure_ascii=False, indent=2), encoding="utf-8")
                    json_response(self, 200, {"ok": True, "default_account_id": account_id})
                    return
                if self.path == "/api/service-control":
                    action = str(payload.get("action") or "")
                    if action not in ("start", "stop", "restart"):
                        json_response(self, 400, {"ok": False, "error": "Invalid action"})
                        return
                    result = manager.service_control(action)
                    json_response(self, 200, result)
                    return
                if self.path == "/api/launchd-control":
                    action = str(payload.get("action") or "")
                    if action not in ("load", "unload"):
                        json_response(self, 400, {"ok": False, "error": "Invalid action"})
                        return
                    result = manager.launchd_control(action)
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
    parser.add_argument(
        "--local-bridge",
        choices=("start", "stop", "restart", "status"),
        help="Control the 8876 Local Codex Bridge without starting the 8899 UI.",
    )
    parser.add_argument(
        "--force-local-bridge",
        action="store_true",
        help="Allow stopping/restarting Local Bridge even when active client connections exist.",
    )
    parser.add_argument(
        "--install-scan",
        action="store_true",
        help="Run first-install compile/package scan and exit.",
    )
    parser.add_argument(
        "--write-install-state",
        action="store_true",
        help="Write install-state marker after --install-scan.",
    )
    parser.add_argument(
        "--install-scan-tests",
        action="store_true",
        help="Include unit tests in --install-scan.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.install_scan:
        scan = bridge_install_scan(include_tests=bool(args.install_scan_tests))
        if args.write_install_state:
            write_install_state(scan)
        print(json.dumps(scan, ensure_ascii=False))
        return 0 if scan.get("ok") else 2
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
    if args.local_bridge:
        if args.local_bridge == "status":
            print(json.dumps(manager.services().get("services", {}).get("local_bridge", {}), ensure_ascii=False))
        else:
            result = manager.control_local_bridge(args.local_bridge, force=bool(args.force_local_bridge))
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("ok") else 2
        return 0
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
