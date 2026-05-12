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
DEFAULT_CLI_LAUNCHER_DIR = Path.home() / ".cc-switch" / "codex-cli-launchers"
DEFAULT_LOCAL_BRIDGE_STATE_PATH = Path.home() / ".cc-switch" / "bridgedeck-local-bridge-state.json"
DEFAULT_OMC_CODEX_SHIM_PATHS = (
    DEFAULT_CLI_LAUNCHER_DIR / "bin" / "codex",
    Path.home() / ".codebuddy" / "bin" / "codex",
    Path.home() / ".workbuddy" / "bin" / "codex",
)
DEFAULT_ZPROFILE_PATH = Path.home() / ".zprofile"
DEFAULT_AUTO_SWITCH_PATH = Path.home() / ".cc-switch" / "bridgedeck-auto-switch.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8899
APP_VERSION = "0.2.18"
MAX_REQUEST_BYTES = 1024 * 1024
LOCAL_BRIDGE_BASE_URL = "http://127.0.0.1:8876"
CC_SWITCH_BASE_URL = "http://127.0.0.1:15721"
LOCAL_BRIDGE_PORT = 8876
COMMON_UPSTREAM_PROXY_PORTS = (1087, 7890, 6152, 8080)
COMPACT_WINDOW_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
COMPACT_THRESHOLD_ENV = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
MAX_CONTEXT_TOKENS_ENV = "CLAUDE_CODE_MAX_CONTEXT_TOKENS"
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
    {"id": "gpt-5.4", "name": "gpt-5.4", "thinking_levels": ("low", "medium", "high", "xhigh")},
    {"id": "gpt-5.4-mini", "name": "gpt-5.4 Mini", "thinking_levels": ("low", "medium", "high", "xhigh")},
    {"id": "gpt-5.3-codex", "name": "gpt-5.3-codex"},
    {"id": "gpt-5.3-codex-spark", "name": "gpt-5.3-codex-spark"},
)
MODEL_ENV_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
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
)
PROVIDER_SCOPED_ENV_KEYS = {
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    *MODEL_ENV_KEYS,
    COMPACT_WINDOW_ENV,
    COMPACT_THRESHOLD_ENV,
    MAX_CONTEXT_TOKENS_ENV,
}
CANONICAL_BRIDGE_NAMES = (
    "Local Codex Bridge - Plus",
    "Local Codex Bridge - Pro",
    "Local Codex Bridge - Pro 20x",
)
MANAGED_CODEX_SHIM_MARKER = "BridgeDeck managed codex-current shim"
MANAGED_CODEX_PATH_START = "# >>> BridgeDeck codex shim >>>"
MANAGED_CODEX_PATH_END = "# <<< BridgeDeck codex shim <<<"
PROXY_DIAG_OPENAI_URL = "https://api.openai.com/v1/models"
PROXY_DIAG_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"


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


def apply_bridge_model_config_to_env(env: dict[str, Any], model_config: dict[str, Any] | None) -> dict[str, str]:
    normalized = normalize_bridge_model_config(model_config)
    env["ANTHROPIC_MODEL"] = normalized["model"]
    if normalized["context_tokens"]:
        env[MAX_CONTEXT_TOKENS_ENV] = normalized["context_tokens"]
    else:
        env.pop(MAX_CONTEXT_TOKENS_ENV, None)
    normalize_provider_model_env(env)
    return normalized


def common_provider_env(env: dict[str, Any]) -> dict[str, Any]:
    common = {
        str(key): copy.deepcopy(value)
        for key, value in env.items()
        if isinstance(key, str) and key not in PROVIDER_SCOPED_ENV_KEYS
    }
    normalize_provider_model_env(common)
    return common


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


def detect_codex_proxy_url() -> tuple[str, str]:
    env_file = load_env_file(DEFAULT_CODEX_HOME / ".env")
    for key in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = str(env_file.get(key) or "").strip()
        if value:
            return value, str(DEFAULT_CODEX_HOME / ".env")
    for key in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value, f"env:{key}"
    return "", ""


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


def read_local_bridge_state(path: Path = DEFAULT_LOCAL_BRIDGE_STATE_PATH) -> dict[str, Any]:
    if not path.exists() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    error = payload.get("last_stream_error")
    if not isinstance(error, dict):
        return {}
    return {
        "updated_at": payload.get("updated_at"),
        "last_stream_error": {
            "account_id": str(error.get("account_id") or ""),
            "model": str(error.get("model") or ""),
            "request_id": str(error.get("request_id") or ""),
            "duration_ms": error.get("duration_ms"),
            "error_type": str(error.get("error_type") or ""),
            "error": str(error.get("error") or ""),
            "upstream_request_id": str(error.get("upstream_request_id") or ""),
        },
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


@dataclass
class ManagerPaths:
    db: Path
    settings: Path
    auth_store: Path


class BridgeManager:
    def __init__(self, paths: ManagerPaths) -> None:
        self.paths = paths
        self._lock = threading.RLock()

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
        account_match = re.search(r"/accounts/([^/?#]+)/v1", data["base_url"])
        if account_match:
            data["account_id"] = account_match.group(1)
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
        status = "ok" if not risk_flags else str(risk_flags[0])
        return {
            "ok": True,
            "status": status,
            "risk_flags": sorted(set(risk_flags)),
            "account_matrix": snapshot.get("account_matrix", []),
            "codex_desktop": snapshot.get("codex_desktop", {}),
        }

    def services(self, *, server_port: int = DEFAULT_PORT) -> dict[str, Any]:
        bridge_processes = port_processes(LOCAL_BRIDGE_PORT)
        bridge_script = find_local_bridge_script(bridge_processes)
        upstream_proxy = detect_upstream_proxy(bridge_processes)
        bridge_state = read_local_bridge_state()
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
                    "upstream_proxy": mask_url_credentials(upstream_proxy),
                    "log_path": str(self.paths.db.parent / "bridgedeck-local-bridge.log"),
                    "last_stream_error": bridge_state.get("last_stream_error") or {},
                },
                "cc_switch_proxy": {
                    "name": "CC Switch Proxy",
                    "running": tcp_open("127.0.0.1", 15721),
                    "port": 15721,
                    "processes": port_processes(15721),
                },
            },
        }

    def proxy_diagnosis(self) -> dict[str, Any]:
        proxy_url, proxy_source = detect_codex_proxy_url()
        proxy_host, proxy_port = parse_proxy_target(proxy_url)
        proxy_running = bool(proxy_host and proxy_port and tcp_open(proxy_host, proxy_port))

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
        ]

        openai_probe: dict[str, Any] | None = None
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
                    "status": "ok" if openai_probe.get("status_code") == 401 else ("forbidden" if openai_probe.get("status_code") == 403 else "failed"),
                    "detail": openai_probe.get("error") or f"HTTP {openai_probe.get('status_code')}",
                    "body_excerpt": openai_probe.get("body_excerpt", ""),
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

        return {
            "ok": True,
            "status": status,
            "message": message,
            "proxy": {
                "source": proxy_source,
                "url": mask_url_credentials(proxy_url),
                "host": proxy_host,
                "port": proxy_port,
                "running": proxy_running,
            },
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

    def _stop_local_bridge(self) -> dict[str, Any]:
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

    def control_local_bridge(self, action: str) -> dict[str, Any]:
        if action == "start":
            return self._start_local_bridge()
        if action == "stop":
            return self._stop_local_bridge()
        if action == "restart":
            stopped = self._stop_local_bridge()
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

    def _select_existing_bridge_provider_for_account(self, conn: sqlite3.Connection, account_id: str) -> sqlite3.Row | None:
        rows = conn.execute(
            """
            SELECT id, name, settings_config, meta, sort_index
            FROM providers
            WHERE app_type = 'claude'
            ORDER BY
              CASE
                WHEN name = 'Local Codex Bridge - Plus' THEN 0
                WHEN name = 'Local Codex Bridge - Pro' THEN 1
                WHEN name = 'Local Codex Bridge - Pro 20x' THEN 2
                ELSE 9
              END,
              sort_index ASC,
              name ASC
            """
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
        model_config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        settings = copy.deepcopy(settings_config) if isinstance(settings_config, dict) else {}
        if not isinstance(settings, dict):
            settings = {}
        env = settings.get("env")
        if not isinstance(env, dict):
            env = {}
        env["ANTHROPIC_BASE_URL"] = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{account_id}"
        env["ANTHROPIC_AUTH_TOKEN"] = "local-bridge"
        if model_config is not None:
            apply_bridge_model_config_to_env(env, model_config)
        else:
            env.setdefault("ANTHROPIC_MODEL", DEFAULT_BRIDGE_PROVIDER_MODEL)
        env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", "gpt-5.3-codex-spark")
        env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", "gpt-5.3-codex")
        env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "gpt-5.5")
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
        try:
            plugin_sync = self.sync_claude_enabled_plugins()
        except Exception as exc:  # noqa: BLE001
            plugin_sync = {"ok": False, "changed": False, "error": str(exc)}
        try:
            plugin_status = self.claude_plugin_sync_status()
        except Exception as exc:  # noqa: BLE001
            plugin_status = {"ok": False, "error": str(exc)}
        data: dict[str, Any] = {
            "version": APP_VERSION,
            "paths": {
                "db": str(self.paths.db),
                "settings": str(self.paths.settings),
                "auth_store": str(self.paths.auth_store),
                "auto_switch": str(DEFAULT_AUTO_SWITCH_PATH),
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
            "codex_providers": [],
            "cli_homes": self._known_cli_homes(),
            "cli_launchers": self._known_cli_launchers(),
            "codex_desktop": self._codex_desktop_status(),
            "current_codex_launcher": self._current_codex_launcher_status(),
            "omc_codex_shim": self._omc_codex_shim_status(),
            "account_matrix": [],
            "current_provider_from_settings": self._current_provider_from_settings(),
            "auto_switch": self._load_auto_switch_config(),
            "plugin_sync": plugin_sync,
            "plugin_status": plugin_status,
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
                if not account_id:
                    account_id = bridge_account_id_from_env(env)
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
                        "model": env.get("ANTHROPIC_MODEL") if isinstance(env.get("ANTHROPIC_MODEL"), str) else "",
                        "max_context_tokens": env.get(MAX_CONTEXT_TOKENS_ENV) if isinstance(env.get(MAX_CONTEXT_TOKENS_ENV), str) else "",
                        "auth_token": auth_token if include_secrets else "",
                        "auth_token_masked": mask_token(auth_token),
                        "compact_enabled": bool(str(env.get(COMPACT_WINDOW_ENV) or "").strip()),
                        "compact_window_tokens": env.get(COMPACT_WINDOW_ENV) if isinstance(env.get(COMPACT_WINDOW_ENV), str) else "",
                        "compact_threshold_percent": env.get(COMPACT_THRESHOLD_ENV) if isinstance(env.get(COMPACT_THRESHOLD_ENV), str) else "",
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
        compact_config: dict[str, Any] | None = None,
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

                new_settings, new_meta = self._build_provider_payload(
                    account_id,
                    settings_config=current_settings,
                    meta=current_meta,
                    compact_config=compact_config,
                    model_config=model_config,
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
                normalized_model = apply_bridge_model_config_to_env(env, model_config) if model_config is not None else None
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
                "model_config": normalized_model,
                "backups": [db_bak],
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

            config_path = DEFAULT_CODEX_HOME / "config.toml"
            if config_path.is_symlink():
                raise ValueError("~/.codex/config.toml 不能是符号链接")
            DEFAULT_CODEX_HOME.mkdir(parents=True, exist_ok=True)
            os.chmod(DEFAULT_CODEX_HOME, 0o700)
            backup = self._backup_file(config_path, "set-default-codex") if config_path.exists() else None
            original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
            base_url = f"{LOCAL_BRIDGE_BASE_URL}/accounts/{account_id}/v1"
            line = f'base_url = "{base_url}"'
            pattern = re.compile(r'(?m)^\s*base_url\s*=\s*["\'][^"\']*["\']\s*$')
            if pattern.search(original):
                updated = pattern.sub(line, original, count=1)
            else:
                updated = f"{line}\n{original}" if original else f"{line}\n"
            current_launcher = self.write_current_codex_launcher(account_id)
            omc_shims = self.write_omc_codex_shims()
            omc_path = self.ensure_omc_codex_path()
            write_private_text_file(config_path, updated)
            return {
                "ok": True,
                "message": "默认 Codex 账号已设置",
                "account_id": account_id,
                "email": account_payload.get("email", ""),
                "config_path": str(config_path),
                "current_launcher": current_launcher["launcher"],
                "omc_codex_shims": omc_shims["paths"],
                "omc_codex_path": omc_path,
                "base_url": base_url,
                "affected": ["Paperclip", "Codex Desktop", "default codex", "codex-current.command", "OMC/tmux codex"],
                "backups": [item for item in (backup, omc_path.get("backup")) if item],
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
    for quota in redacted.get("quotas", []):
        if isinstance(quota, dict):
            quota["account_id"] = mask_id_value(quota.get("account_id"))
            quota["email"] = mask_email_value(quota.get("email"))
    for key in ("missing", "created", "skipped"):
        for item in redacted.get(key, []):
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
    codex_auth = redacted.get("codex_auth")
    if isinstance(codex_auth, dict):
        codex_auth.pop("path", None)
        codex_auth["email_masked"] = mask_email_value(codex_auth.get("email_masked"))
    proxy = redacted.get("proxy")
    if isinstance(proxy, dict) and proxy.get("url"):
        proxy["url"] = "<redacted>"
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
      --bg:#0c0f14; --surface:#111722; --panel:#151c29; --panel2:#101621; --line:#263244;
      --text:#edf2fb; --muted:#9aa7ba; --soft:#c6d0df; --ok:#2ec27e; --warn:#f5b642;
      --bad:#ff6f6f; --brand:#59a7ff; --brand2:#8cc6ff; --focus:#213756;
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
    .workspace { min-width:0; padding:20px; display:grid; grid-template-columns:minmax(0, 1fr) 300px; gap:16px; align-items:start; align-content:start; }
    .topBar { grid-column:1 / -1; grid-row:1; display:flex; justify-content:space-between; gap:16px; align-items:flex-start; padding:16px; border:1px solid var(--line); border-radius:8px; background:var(--surface); }
    .topBar h1 { margin:0; font-size:24px; }
    .topBar p { margin:6px 0 0; color:var(--muted); font-size:13px; }
    .topActions { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
    .pageStack { grid-column:1; grid-row:2; min-width:0; }
    .deckPage { display:none; }
    .deckPage.active { display:block; }
    .guideDock { grid-column:2; grid-row:2; position:sticky; top:20px; }
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
    table { width:100%; min-width:760px; border-collapse:collapse; table-layout:fixed; font-size:12px; }
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
      .workspace { grid-template-columns:1fr; }
      .guideDock { position:static; }
    }
    @media (max-width: 900px) {
      .appShell { grid-template-columns:1fr; }
      .appSidebar { position:static; height:auto; }
      .sideNav { grid-template-columns:repeat(2, minmax(0, 1fr)); }
      .topGrid, .summaryGrid, .splitGrid, .formGrid { grid-template-columns:1fr; }
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
          <button class="navItem" data-page="switching">入口切换 <span class="navHint">账号</span></button>
          <button class="navItem" data-page="quota">额度与自动切换 <span class="navHint">OpenAI</span></button>
          <button class="navItem" data-page="claude">Claude Code <span class="navHint">桥接</span></button>
          <button class="navItem" data-page="codex">Codex CLI <span class="navHint">启动器</span></button>
          <button class="navItem" data-page="api">通用 API <span class="navHint">复制</span></button>
          <button class="navItem" data-page="services">本地服务 <span class="navHint">8876</span></button>
          <button class="navItem" data-page="diagnostics">诊断日志 <span class="navHint">排查</span></button>
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
            <div id="recommendation" class="recommend">加载中...</div>
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
                    <div class="toolText">给 Paperclip、Codex Desktop、OMC/tmux 和直接运行 codex 使用。</div>
                    <div class="toolSelect">
                      <label for="simpleDefaultAccount">全局 Codex CLI 用哪个账号</label>
                      <select id="simpleDefaultAccount"></select>
                    </div>
                    <div class="actualRow">
                      <div class="actualLine" id="simpleDefaultActual">当前实际：检测中...</div>
                      <button class="miniBtn" data-action="refresh">刷新</button>
                    </div>
                  </div>
                  <button class="warn" data-action="simple-default-codex">设为全局 Codex CLI</button>
                </div>
                <div class="toolCard">
                  <div>
                    <div class="toolName">Codex Desktop</div>
                    <div class="toolText">桌面版跟随全局 Codex CLI，这里只显示检测结果。</div>
                    <div class="actualRow">
                      <div class="actualLine" id="simpleDesktopActual">当前实际：检测中...</div>
                      <button class="miniBtn" data-action="refresh">刷新</button>
                    </div>
                  </div>
                  <button data-action="scroll" data-target="statusCard">查看桌面版状态</button>
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
              <div class="sectionHint">选择账号、模型和上下文后创建/更新；勾选“设为当前”会同步 CC Switch 当前 Claude Provider。</div>
              <div class="formGrid">
                <label>ChatGPT 账号<select id="account"></select></label>
                <label>显示名称<input id="providerName" placeholder="Local Codex Bridge - xxx" /></label>
                <label>模型<select id="bridgeModel"></select></label>
                <label>上下文 tokens<input id="modelContextTokens" type="number" min="10000" max="2000000" step="1000" value="272000" readonly /></label>
              </div>
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
                  <button class="miniBtn" data-action="save-compact-selected">保存模型/上下文到选中 provider</button>
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
                      <th class="smallCol">model</th>
                      <th class="smallCol">compact</th>
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
                <button class="miniBtn" data-action="proxy-diagnosis">诊断代理链路</button>
                <button class="miniBtn" data-action="repair-quota-query">一键修复额度查询</button>
                <button class="miniBtn" data-action="start-local-bridge">启动 Local Bridge</button>
                <button class="miniBtn" data-action="restart-local-bridge">重启 Local Bridge</button>
                <button class="miniBtn warn" data-action="stop-local-bridge">停止 Local Bridge</button>
                <button class="miniBtn warn" data-action="stop-bridgedeck-ui">关闭 BridgeDeck UI</button>
              </div>
              <div id="serviceMessage" class="muted mt10">关闭 BridgeDeck UI 只停 8899，不影响 8876 Local Bridge。</div>
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
              <div class="sectionHint">自动检测 Claude Code、单独 Codex CLI、全局 Codex CLI 当前状态。Desktop 跟随全局 Codex CLI。</div>
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
            <div class="card guideSection" data-guide="log">
              <h2>执行日志</h2>
              <textarea id="log" readonly></textarea>
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
    const BRIDGE_MODELS = __BRIDGE_MODELS_JSON__;
    const DEFAULT_BRIDGE_MODEL = 'gpt-5.5';
    const DEFAULT_COMPACT_WINDOW = '272000';
    const CONSERVATIVE_COMPACT_WINDOW = '220000';
    const DEFAULT_COMPACT_PCT = '80';
    const LOCAL_BRIDGE_BASE_URL = "__LOCAL_BRIDGE_BASE_URL__";
    const LOCAL_API_KEY_PLACEHOLDER = 'sk-bridgedeck-local-placeholder';
    const LOCAL_ANTHROPIC_AUTH_TOKEN = 'local-bridge';
    const CLAUDE_DESKTOP_ROUTES = [
      ['claude-haiku-4-5', 'gpt-5.3-codex-spark'],
      ['claude-sonnet-4-6', 'gpt-5.3-codex'],
      ['claude-opus-4-7', 'gpt-5.5']
    ];
    const GUIDES = {
      simpleFlow: {
        title: '日常模式',
        target: '上方板块：每个入口单独选账号',
        steps: [
          'Claude Code、单独 Codex CLI、全局 Codex CLI 各自选账号。',
          'Claude Code 卡片只影响 Claude Code 当前账号。',
          '“当前实际”显示 CC Switch 当前 Claude Provider。',
          '单独 Codex CLI 只生成独立启动器，不改变全局默认。',
          '全局 Codex CLI 给 Paperclip、Codex Desktop、直接运行 codex 用。',
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
    function desktopAccountText(data) {
      const desktop = data.codex_desktop || {};
      if (desktop.account_id) return accountDisplay(desktop.account_id);
      return statusText(desktop.managed_by || 'unknown');
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
        desktopBox.innerHTML = `当前实际：<strong>${esc(desktopAccountText(data))}</strong><br><span class="ok">${esc(desktopModeText(data))}</span>`;
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
    async function refreshQuotas() {
      try {
        const payload = await api('/api/quotas');
        renderQuotaBoard(payload);
        renderMissingBridgeStatus(payload);
        return payload;
      } catch (e) {
        document.getElementById('quotaBoard').textContent = `额度查询失败: ${e.message}`;
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
        return `<div class="serviceItem">
          <div class="serviceName">${esc(item.name || '')}</div>
          <div class="serviceMeta"><span class="${cls}">${running ? '运行中' : '未运行'}</span> · ${esc(item.port || '')}${script}${proxy}${streamError}</div>
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
      box.innerHTML = `<b>${esc(payload.message || '代理诊断完成')}</b>${lines.length ? `<br>${lines.map((line) => esc(line)).join('<br>')}` : ''}`;
    }
    async function refreshServices() {
      const payload = await api('/api/services');
      renderServices(payload);
      return payload;
    }
    async function runProxyDiagnosis() {
      const payload = await api('/api/proxy-diagnosis');
      renderProxyDiagnosis(payload);
      document.getElementById('serviceMessage').textContent = payload.message || '代理诊断完成';
      log(`代理诊断: ${payload.status || 'unknown'} / ${payload.message || ''}`);
      return payload;
    }
    async function controlLocalBridge(action) {
      const res = await api('/api/local-bridge-control', 'POST', { action });
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
    function setSimpleResult(message, level='') {
      const box = document.getElementById('simpleResult');
      const cls = level === 'ok' ? 'ok' : (level === 'warn' ? 'warnText' : (level === 'bad' ? 'bad' : ''));
      box.innerHTML = cls ? `<strong class="${cls}">${esc(message)}</strong>` : esc(message);
    }
    function selectedProviderId() {
      const chosen = document.querySelector('input[name="providerPick"]:checked');
      return chosen ? chosen.value : '';
    }
    function selectedProvider() {
      const id = selectedProviderId();
      return id && lastData ? (lastData.providers || []).find((p) => p.id === id) : null;
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
      return CLAUDE_DESKTOP_ROUTES.map(([route, target]) => `${route} -> ${target}`).join('\\n');
    }
    function apiAccessEnv(item) {
      const baseUrl = apiAccessBaseUrl(item);
      return baseUrl ? `OPENAI_API_KEY=${LOCAL_API_KEY_PLACEHOLDER}\nOPENAI_BASE_URL=${baseUrl}` : '';
    }
    function anthropicAccessEnv(item) {
      const baseUrl = anthropicAccessBaseUrl(item);
      return baseUrl ? `ANTHROPIC_BASE_URL=${baseUrl}\nANTHROPIC_AUTH_TOKEN=${LOCAL_ANTHROPIC_AUTH_TOKEN}\nANTHROPIC_MODEL=gpt-5.5\nANTHROPIC_DEFAULT_HAIKU_MODEL=gpt-5.3-codex-spark\nANTHROPIC_DEFAULT_SONNET_MODEL=gpt-5.3-codex\nANTHROPIC_DEFAULT_OPUS_MODEL=gpt-5.5\nCLAUDE_CODE_MAX_CONTEXT_TOKENS=272000` : '';
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
    function updateBridgeModelMeta() {
      const model = selectedBridgeModel();
      const context = bridgeModelContext(model);
      const maxOutput = bridgeModelMaxOutput(model);
      document.getElementById('modelContextTokens').value = context || '';
      const outputText = maxOutput ? ` / ${maxOutput} max output` : '';
      document.getElementById('bridgeModelMeta').textContent = context
        ? `${model} = ${context} context tokens${outputText}。`
        : `${model} 未探测到真实 context；自动压缩使用保守 ${CONSERVATIVE_COMPACT_WINDOW}，不会写 CLAUDE_CODE_MAX_CONTEXT_TOKENS。`;
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
    function applyCompactFromProvider(provider) {
      if (!provider) return;
      setBridgeModel(provider.model || DEFAULT_BRIDGE_MODEL, false);
      if (provider.compact_enabled) {
        setCompactFields(true, provider.compact_window_tokens || DEFAULT_COMPACT_WINDOW, provider.compact_threshold_percent || DEFAULT_COMPACT_PCT);
      } else {
        setCompactFields(false, '', DEFAULT_COMPACT_PCT);
      }
    }
    function applyClaudeAccount(item) {
      if (!item) return;
      setSelectValue('account', item.account_id);
      setSelectValue('simpleClaudeAccount', item.account_id);
      document.getElementById('providerName').value = `Local Codex Bridge - ${accountSlug(item)}`;
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
      const actualGlobalAccount = data.codex_desktop ? data.codex_desktop.account_id : '';
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
        setSimpleResult(`全局 Codex CLI 已选择 ${accountLabel(item)}。点击按钮后才会写入默认配置。`);
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
      data.providers.forEach((p) => {
        const tr = document.createElement('tr');
        const currentBySettings = data.current_provider_from_settings === p.id;
        tr.innerHTML = `
          <td><label class="providerNameCell"><input type="radio" name="providerPick" value="${esc(p.id)}"><span class="providerNameText">${esc(p.name)}</span></label></td>
          <td>${p.is_current ? '<span class="ok">当前</span>' : '<span class="muted">未选</span>'} ${currentBySettings ? '<span class="ok">设置同步</span>' : ''}</td>
          <td class="mono">${esc(maskId(p.account_id || ''))}</td>
          <td class="mono">${esc(p.base_url || '')}</td>
          <td class="mono">${esc(p.model || '')}${p.max_context_tokens ? '<br>' + esc(p.max_context_tokens) : ''}</td>
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
      const desktop = data.codex_desktop || {};
      const desktopAccount = desktop.account_id || '';
      const desktopUnknown = desktop.detected ? '未识别' : '未检测';
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
      let text = '状态正常。日常只需要用下面的“先选账号，再选工具”。';
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
        advice.push(`默认 Codex Desktop/CLI：${desktopAccountText(data)}，${desktopModeText(data)}。`);
      } else {
        state = state === 'badState' ? state : 'warnState';
        advice.push('未检测到 Codex Desktop/默认 CLI 接管状态。');
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
      renderAccounts(data);
      renderAccountMatrix(data);
      renderProviders(data);
      renderCodexProviders(data);
      renderCliHomes(data);
      renderDiagnosis(data);
      renderActualCurrentAccounts(data);
      renderPluginSync(data);
      renderSimpleActuals(data);
      renderAutoSwitchConfig(data);
      refreshServices().catch((e) => {
        const box = document.getElementById('serviceStatus');
        if (box) box.textContent = `服务状态失败: ${e.message}`;
      });
      refreshQuotas();
      if (data.auto_switch && data.auto_switch.enabled) {
        runAutoSwitch(false, false).catch((e) => log(`自动切换失败: ${e.message}`));
      }
      if (data.accounts.length > 0 && !document.getElementById('simpleResult').dataset.touched) {
        setSimpleResult('已准备好。Claude Code、单独 Codex CLI、全局 Codex CLI 可以分别选不同账号。');
      }
      const refreshedAt = new Date().toLocaleTimeString();
      if (showFeedback) setSimpleResult(`已刷新：${refreshedAt}`, 'ok');
      log(`数据已刷新: ${refreshedAt}`);
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
        model_config: bridgeModelConfigPayload(),
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
      setSimpleResult(`正在把全局 Codex CLI 设为 ${accountLabel(item)}...`);
      const res = await api('/api/set-default-codex', 'POST', { account_id: item.account_id });
      await refreshData();
      const currentLauncher = res.current_launcher ? `；固定入口：${humanPath(res.current_launcher)}` : '';
      const omcText = (res.omc_codex_shims || []).length ? '；OMC/tmux 已接管 codex' : '';
      setSimpleResult(`完成：全局 Codex 已设为 ${accountLabel(item)}${currentLauncher}${omcText}。`, 'ok');
      log(`${res.message}: ${humanPath(res.config_path)}${currentLauncher}`);
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
    async function saveCompactSelected() {
      const id = selectedProviderId();
      if (!id) return log('请先选中一个 provider');
      const res = await api('/api/provider-compact', 'POST', { provider_id: id, model_config: bridgeModelConfigPayload(), compact_config: compactConfigPayload() });
      log(`${res.message}: ${providerCompactText({ compact_enabled: res.compact_config.enabled, compact_window_tokens: res.compact_config.window_tokens, compact_threshold_percent: res.compact_config.threshold_percent })}`);
      await refreshData();
    }
    async function syncCommonEnvSelected() {
      const id = selectedProviderId();
      if (!id) return log('请先选中一个 provider');
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
    function bindActions() {
      document.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) return;
        const action = button.dataset.action;
        const run = async () => {
          if (action === 'scroll') return scrollToSection(button.dataset.target || '');
          if (action === 'refresh') return refreshData(true);
          if (action === 'create-provider') return createProvider();
          if (action === 'create-cli-home') return createCliHome();
          if (action === 'simple-claude') return simpleClaude();
          if (action === 'simple-cli') return simpleCli();
          if (action === 'simple-default-codex') return simpleDefaultCodex();
          if (action === 'copy-api-key') return copyApiKey();
          if (action === 'copy-api-base-url') return copyApiBaseUrl();
          if (action === 'copy-api-env') return copyApiEnv();
          if (action === 'copy-anthropic-token') return copyAnthropicToken();
          if (action === 'copy-anthropic-base-url') return copyAnthropicBaseUrl();
          if (action === 'copy-anthropic-env') return copyAnthropicEnv();
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
          if (action === 'sync-common-env-selected') return syncCommonEnvSelected();
          if (action === 'copy-api-base-url') return copyApiBaseUrl();
          if (action === 'copy-api-env') return copyApiEnv();
          if (action === 'copy-claude-env') return copyClaudeEnv();
          if (action === 'extract-safe-common-config') return extractSafeCommonConfig();
          if (action === 'sync-claude-plugins') return syncClaudePlugins();
          if (action === 'save-auto-switch') return saveAutoSwitch();
          if (action === 'run-auto-switch') return runAutoSwitch(true, true);
          if (action === 'create-missing-bridges') return createMissingBridges();
          if (action === 'preview-bridge-dedupe') return dedupeBridgeProviders(false);
          if (action === 'apply-bridge-dedupe') return dedupeBridgeProviders(true);
          if (action === 'refresh-services') return refreshServices();
          if (action === 'proxy-diagnosis') return runProxyDiagnosis();
          if (action === 'repair-quota-query') return repairQuotaQuery();
          if (action === 'start-local-bridge') return controlLocalBridge('start');
          if (action === 'stop-local-bridge') return controlLocalBridge('stop');
          if (action === 'restart-local-bridge') return controlLocalBridge('restart');
          if (action === 'stop-bridgedeck-ui') return stopBridgeDeckUi();
          if (action === 'select-cli-account') return selectCliAccount(button.dataset.accountId || '');
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
                    model_config = payload.get("model_config") if isinstance(payload.get("model_config"), dict) else None
                    result = manager.create_or_update_provider(
                        account_id,
                        provider_name,
                        set_current,
                        compact_config=compact_config,
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
                    model_config = payload.get("model_config") if isinstance(payload.get("model_config"), dict) else None
                    result = manager.update_provider_compact(provider_id, compact_config, model_config=model_config)
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
                if self.path == "/api/create-missing-bridges":
                    result = manager.create_missing_bridge_providers()
                    json_response(self, 200, result)
                    return
                if self.path == "/api/local-bridge-control":
                    result = manager.control_local_bridge(str(payload.get("action") or ""))
                    json_response(self, 200 if result.get("ok") else 400, result)
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
    if args.local_bridge:
        if args.local_bridge == "status":
            print(json.dumps(manager.services().get("services", {}).get("local_bridge", {}), ensure_ascii=False))
        else:
            print(json.dumps(manager.control_local_bridge(args.local_bridge), ensure_ascii=False))
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
