#!/usr/bin/env python3
from __future__ import annotations

import copy
import errno
import gzip
import hashlib
import io
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import fcntl
import urllib.parse
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

try:
    from compression import zstd
except Exception:  # noqa: BLE001
    zstd = None  # type: ignore[assignment]


AUTH_STORE_PATH = Path.home() / ".cc-switch" / "codex_oauth_auth.json"
CC_SWITCH_DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
DEFAULT_API_KEYS_PATH = Path.home() / ".cc-switch" / "bridgedeck-keys.json"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_USER_AGENT = "codex-local-bridge"
UPSTREAM_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TOKEN_REFRESH_BUFFER_SECS = 60
ACCOUNT_ROUTE_RE = re.compile(r"^/accounts/([^/]+)(/.*)?$")
MODELS_PATHS = {"/v1/models", "/models", "/v1/v1/models"}
RESPONSES_PATHS = {"/v1/responses", "/responses", "/v1/v1/responses"}
MESSAGES_PATHS = {"/v1/messages", "/messages", "/v1/v1/messages"}
CHAT_COMPLETIONS_PATHS = {"/v1/chat/completions", "/chat/completions", "/v1/v1/chat/completions"}
UPSTREAM_PROXY_ENV = "CODEX_BRIDGE_UPSTREAM_PROXY"
ALLOW_REMOTE_ENV = "CODEX_BRIDGE_ALLOW_REMOTE"
BIND_FAILURE_SLEEP_SECS_ENV = "CODEX_BRIDGE_BIND_FAILURE_SLEEP_SECS"
STREAM_MAX_RETRIES_ENV = "CODEX_BRIDGE_STREAM_MAX_RETRIES"
SESSION_AFFINITY_ENV = "CODEX_BRIDGE_SESSION_AFFINITY"
PROMPT_CACHE_KEY_MODE_ENV = "CODEX_BRIDGE_PROMPT_CACHE_KEY"
REASONING_PLACEHOLDER_HEARTBEAT_SECS = 8.0
REASONING_PLACEHOLDER_MODE_ENV = "CODEX_BRIDGE_REASONING_PLACEHOLDER_MODE"
STREAM_IDLE_LOG_SECS = float(os.environ.get("CODEX_BRIDGE_STREAM_IDLE_LOG_SECS", "20"))
STREAM_IDLE_FAIL_SECS = float(os.environ.get("CODEX_BRIDGE_STREAM_IDLE_FAIL_SECS", "300"))
STREAM_IDLE_PARTIAL_FAIL_SECS = float(os.environ.get("CODEX_BRIDGE_STREAM_IDLE_PARTIAL_FAIL_SECS", "900"))
STREAM_LONG_WARNING_SECS = float(os.environ.get("CODEX_BRIDGE_STREAM_LONG_WARNING_SECS", "240"))
STREAM_TOOL_CALL_GUARD_MODE_ENV = "CODEX_BRIDGE_STREAM_TOOL_CALL_GUARD"
STREAM_TOOL_CALL_WALL_FAIL_SECS = float(os.environ.get("CODEX_BRIDGE_STREAM_TOOL_CALL_WALL_FAIL_SECS", "240"))
INCOMPLETE_ANSWER_GUARD_ENV = "CODEX_BRIDGE_INCOMPLETE_ANSWER_GUARD"
ANTHROPIC_TOOL_ARGS_MODE_ENV = "CODEX_BRIDGE_ANTHROPIC_TOOL_ARGS_MODE"
ANTHROPIC_TOOL_ARG_PING_SECS = float(os.environ.get("CODEX_BRIDGE_ANTHROPIC_TOOL_ARG_PING_SECS", "5"))
STREAM_STATE_UPDATE_SECS = float(os.environ.get("CODEX_BRIDGE_STREAM_STATE_UPDATE_SECS", "5"))
STRIP_CLAUDE_ATTRIBUTION_HEADER_ENV = "CODEX_BRIDGE_STRIP_CLAUDE_CODE_ATTRIBUTION_HEADER"
CLAUDE_ATTRIBUTION_HEADER_RE = re.compile(
    r"^\s*x-anthropic-billing-header\s*:[^\r\n]*(?:\r?\n){0,2}",
    re.IGNORECASE,
)
RETRYABLE_HTTP_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024  # 50 MB – refuse before reading
MAX_DECOMPRESSED_BODY_BYTES = 10 * 1024 * 1024  # 10 MB – refuse after decompression
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "auth",
    "auth_token",
    "authorization",
    "client_secret",
    "key",
    "password",
    "refresh_token",
    "secret",
    "token",
}
BRIDGE_STATE_PATH = Path(
    os.environ.get(
        "CODEX_BRIDGE_STATE_PATH",
        str(Path.home() / ".cc-switch" / "bridgedeck-local-bridge-state.json"),
    )
)
MAX_USAGE_EVENTS = 200
_bridge_state_lock = threading.RLock()


@dataclass
class AccountRecord:
    account_id: str
    refresh_token: str
    email: str | None = None
    authenticated_at: int | None = None


@dataclass
class CachedToken:
    token: str
    expires_at: float

    def is_expiring_soon(self) -> bool:
        return (self.expires_at - time.time()) < TOKEN_REFRESH_BUFFER_SECS


@dataclass
class ReasoningPlaceholderState:
    active: bool = False
    completed: bool = False
    saw_text_delta: bool = False
    item_id: str | None = None
    output_index: int | None = None
    emitted_count: int = 0
    last_emitted_at: float = 0.0
    last_upstream_at: float = 0.0
    last_idle_logged_at: float = 0.0
    logged_terminal_error: bool = False


@dataclass
class BridgeStreamMetrics:
    upstream_events: int = 0
    downstream_writes: int = 0
    client_disconnected: bool = False
    terminal_event_seen: bool = False
    idle_timeout_seen: bool = False
    visible_text_events: int = 0
    reasoning_events: int = 0
    tool_events: int = 0
    terminal_events: int = 0
    first_visible_after_ms: int | None = None
    last_event_name: str = ""
    long_stream_warning_logged: bool = False
    tool_args_mode: str = ""
    tool_arg_delta_events: int = 0
    tool_arg_buffer_chars: int = 0
    tool_arg_ping_events: int = 0
    tool_arg_coalesced_calls: int = 0
    visible_text_chars: int = 0
    last_visible_text_tail: str = ""
    completed_response_status: str = ""
    completed_incomplete_reason: str = ""
    completed_output_tokens: int | None = None
    completed_total_tokens: int | None = None


@dataclass(frozen=True)
class BridgeModel:
    id: str
    display_name: str
    context_length: int | None = None
    max_completion_tokens: int | None = None
    thinking_levels: tuple[str, ...] = ()


class TerminalStreamError(Exception):
    pass


class BridgeIncompleteAnswer(TerminalStreamError):
    pass


class BridgeStreamIdleTimeout(Exception):
    pass


class BridgeClientDisconnect(Exception):
    pass


class BridgeToolCallRunaway(Exception):
    pass


class BridgeStreamRetryableError(Exception):
    pass


class RetryableStreamBootstrapError(Exception):
    pass


BRIDGE_MODELS: tuple[BridgeModel, ...] = (
    BridgeModel(
        id="gpt-5.5",
        display_name="GPT 5.5",
        context_length=272000,
        max_completion_tokens=128000,
        thinking_levels=("low", "medium", "high", "xhigh"),
    ),
    BridgeModel(id="gpt-5.4", display_name="GPT 5.4", context_length=220000, thinking_levels=("low", "medium", "high", "xhigh")),
    BridgeModel(id="gpt-5.4-mini", display_name="GPT 5.4 Mini", context_length=220000, thinking_levels=("low", "medium", "high", "xhigh")),
    BridgeModel(id="gpt-5.3-codex", display_name="GPT 5.3 Codex", context_length=220000),
    BridgeModel(id="gpt-5.3-codex-spark", display_name="GPT 5.3 Codex Spark", context_length=220000),
)

REASONING_LEVEL_DESCRIPTIONS = {
    "low": "Fast responses with lighter reasoning",
    "medium": "Balances speed and reasoning depth for everyday tasks",
    "high": "Greater reasoning depth for complex problems",
    "xhigh": "Extra high reasoning depth for complex problems",
}

CODEX_MODEL_BASE_INSTRUCTIONS = (
    "You are Codex, a coding agent. Follow the user's instructions and use the workspace safely."
)

CLAUDE_DESKTOP_MODEL_ROUTES: tuple[dict[str, Any], ...] = (
    {
        "id": "claude-haiku-4-5",
        "aliases": ("haiku",),
        "display_name": "Claude Haiku 4.5",
        "env": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "default": "gpt-5.3-codex-spark",
    },
    {
        "id": "claude-sonnet-4-6",
        "aliases": ("sonnet",),
        "display_name": "Claude Sonnet 4.6",
        "env": "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "default": "gpt-5.3-codex",
    },
    {
        "id": "claude-opus-4-7",
        "aliases": ("opus",),
        "display_name": "Claude Opus 4.7",
        "env": "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "default": "gpt-5.5",
    },
)


def parse_bool_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_non_negative_int_env(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def is_launchd_context() -> bool:
    return bool(os.environ.get("XPC_SERVICE_NAME"))


def bind_failure_sleep_seconds(exc: OSError) -> int:
    if not is_launchd_context():
        return 0
    default = 300 if exc.errno in {errno.EADDRNOTAVAIL, errno.EADDRINUSE} else 60
    return parse_non_negative_int_env(os.environ.get(BIND_FAILURE_SLEEP_SECS_ENV), default)


class _DecompressionBombReader:
    """Wraps a decompressor to read in chunks, aborting if the output exceeds a byte limit.

    This prevents decompression bombs from allocating excessive memory before
    the size check can execute.
    """

    def __init__(self, decompressor: Any, max_bytes: int) -> None:
        self._decompressor = decompressor
        self._max_bytes = max_bytes
        self._total = 0

    def read(self, size: int = -1) -> bytes:
        if size == -1 or size is None:
            # Read everything in bounded chunks
            chunks: list[bytes] = []
            while True:
                chunk = self._decompressor.read(65536)
                if not chunk:
                    break
                self._total += len(chunk)
                if self._total > self._max_bytes:
                    raise ValueError(
                        f"decompressed body too large: exceeds {self._max_bytes} bytes"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
        chunk = self._decompressor.read(size)
        if chunk:
            self._total += len(chunk)
            if self._total > self._max_bytes:
                raise ValueError(
                    f"decompressed body too large: exceeds {self._max_bytes} bytes"
                )
        return chunk


def decode_request_body(raw_body: bytes, content_encoding: str | None) -> bytes:
    encoding = str(content_encoding or "").strip().lower()
    if not raw_body:
        return raw_body
    if not encoding and raw_body.startswith(b"\x28\xb5\x2f\xfd"):
        encoding = "zstd"
    if encoding in {"", "identity"}:
        return raw_body
    max_bytes = MAX_DECOMPRESSED_BODY_BYTES
    if encoding == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as gz:
            guard = _DecompressionBombReader(gz, max_bytes)
            return guard.read()
    elif encoding == "deflate":
        decompressor = zlib.decompressobj()
        # Feed compressed input in small chunks so decompressor output is
        # produced incrementally rather than all at once.
        out_chunks: list[bytes] = []
        total = 0
        chunk_size = 65536
        for offset in range(0, len(raw_body), chunk_size):
            out = decompressor.decompress(raw_body[offset : offset + chunk_size])
            if out:
                total += len(out)
                if total > max_bytes:
                    raise ValueError(
                        f"decompressed body too large: exceeds {max_bytes} bytes"
                    )
                out_chunks.append(out)
        out = decompressor.flush()
        if out:
            total += len(out)
            if total > max_bytes:
                raise ValueError(
                    f"decompressed body too large: exceeds {max_bytes} bytes"
                )
            out_chunks.append(out)
        return b"".join(out_chunks)
    elif encoding in {"zstd", "zstandard"}:
        if zstd is None:
            raise ValueError("zstd request body is not supported by this Python runtime")
        decompressor = zstd.ZstdDecompressor()  # type: ignore[union-attr]
        out_chunks: list[bytes] = []
        total = 0
        chunk_size = 65536
        for offset in range(0, len(raw_body), chunk_size):
            out = decompressor.decompress(raw_body[offset : offset + chunk_size])
            if out:
                total += len(out)
                if total > max_bytes:
                    raise ValueError(
                        f"decompressed body too large: exceeds {max_bytes} bytes"
                    )
                out_chunks.append(out)
        return b"".join(out_chunks)
    else:
        raise ValueError(f"unsupported request content-encoding: {encoding}")


def strip_claude_attribution_mode() -> str:
    mode = str(os.environ.get(STRIP_CLAUDE_ATTRIBUTION_HEADER_ENV) or "auto").strip().lower()
    return mode if mode in {"auto", "always", "never"} else "auto"


def should_strip_claude_attribution_header(provider_kind: str, mode: str | None = None) -> tuple[bool, str]:
    normalized_mode = (mode or strip_claude_attribution_mode()).strip().lower()
    normalized_provider = (provider_kind or "proxy").strip().lower()
    if normalized_mode == "always":
        return True, "mode_always"
    if normalized_mode == "never":
        return False, "mode_never"
    if normalized_provider in {"official_anthropic", "anthropic_official", "official"}:
        return False, "official_anthropic"
    return True, "third_party_or_proxy"


def _prompt_sha12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""


def _strip_claude_attribution_text(value: str) -> tuple[str, bool]:
    updated = CLAUDE_ATTRIBUTION_HEADER_RE.sub("", value, count=1)
    return updated, updated != value


def _text_len(value: Any) -> int:
    return len(value) if isinstance(value, str) else 0


def _strip_text_block_value(value: Any) -> tuple[Any, bool, int, int, str, str]:
    if not isinstance(value, str):
        return value, False, 0, 0, "", ""
    before_len = len(value)
    before_hash = _prompt_sha12(value)
    updated, changed = _strip_claude_attribution_text(value)
    return updated, changed, before_len, len(updated), before_hash, _prompt_sha12(updated)


def _strip_from_content_first_text(content: Any) -> tuple[Any, bool, int, int, str, str]:
    if isinstance(content, str):
        return _strip_text_block_value(content)
    if not isinstance(content, list) or not content:
        return content, False, _text_len(content), _text_len(content), "", ""
    first = content[0]
    cloned = copy.deepcopy(content)
    if isinstance(first, str):
        updated, changed, before_len, after_len, before_hash, after_hash = _strip_text_block_value(first)
        if not changed:
            return content, False, before_len, after_len, before_hash, after_hash
        if updated:
            cloned[0] = updated
        else:
            cloned.pop(0)
        return cloned, True, before_len, after_len, before_hash, after_hash
    if isinstance(first, dict) and first.get("type") in {"text", "input_text"} and isinstance(first.get("text"), str):
        updated, changed, before_len, after_len, before_hash, after_hash = _strip_text_block_value(first["text"])
        if not changed:
            return content, False, before_len, after_len, before_hash, after_hash
        if updated:
            cloned[0]["text"] = updated
        else:
            cloned.pop(0)
        return cloned, True, before_len, after_len, before_hash, after_hash
    return content, False, 0, 0, "", ""


def _strip_from_anthropic_system(system: Any) -> tuple[Any, bool, int, int, str, str]:
    if isinstance(system, str):
        return _strip_text_block_value(system)
    return _strip_from_content_first_text(system)


def strip_claude_attribution_from_request(
    body: dict[str, Any],
    *,
    request_type: str,
    provider_kind: str = "proxy",
    mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    should_strip, reason = should_strip_claude_attribution_header(provider_kind, mode)
    result = {
        "stripped": False,
        "reason": reason,
        "provider_kind": provider_kind,
        "request_type": request_type,
        "before_len": 0,
        "after_len": 0,
        "before_hash": "",
        "after_hash": "",
    }
    if not should_strip:
        return body, result

    updated_body = copy.deepcopy(body)
    changed = False
    if isinstance(updated_body.get("system"), (str, list)):
        system, changed, before_len, after_len, before_hash, after_hash = _strip_from_anthropic_system(updated_body["system"])
        if changed:
            updated_body["system"] = system
            result.update(
                {
                    "stripped": True,
                    "field": "system",
                    "before_len": before_len,
                    "after_len": after_len,
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                }
            )
            return updated_body, result

    if isinstance(updated_body.get("instructions"), str):
        instructions, changed, before_len, after_len, before_hash, after_hash = _strip_text_block_value(updated_body["instructions"])
        if changed:
            updated_body["instructions"] = instructions
            result.update(
                {
                    "stripped": True,
                    "field": "instructions",
                    "before_len": before_len,
                    "after_len": after_len,
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                }
            )
            return updated_body, result

    messages = updated_body.get("messages")
    if isinstance(messages, list):
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            if role not in {"system", "developer"}:
                continue
            content, changed, before_len, after_len, before_hash, after_hash = _strip_from_content_first_text(message.get("content"))
            if changed:
                updated_body["messages"][index]["content"] = content
                result.update(
                    {
                        "stripped": True,
                        "field": f"messages[{index}].content",
                        "before_len": before_len,
                        "after_len": after_len,
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                    }
                )
            break

    input_items = updated_body.get("input")
    if isinstance(input_items, list):
        for index, item in enumerate(input_items):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            if role not in {"system", "developer"}:
                continue
            content, changed, before_len, after_len, before_hash, after_hash = _strip_from_content_first_text(item.get("content"))
            if changed:
                updated_body["input"][index]["content"] = content
                result.update(
                    {
                        "stripped": True,
                        "field": f"input[{index}].content",
                        "before_len": before_len,
                        "after_len": after_len,
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                    }
                )
            break

    return updated_body, result


def log_claude_attribution_strip(
    *,
    account_id: str | None,
    route_path: str,
    result: dict[str, Any],
) -> None:
    if not result.get("stripped"):
        return
    payload = {
        "account_id": account_id or "default",
        "route_path": route_path,
        "provider_kind": result.get("provider_kind") or "",
        "request_type": result.get("request_type") or "",
        "field": result.get("field") or "",
        "stripped": True,
        "reason": result.get("reason") or "",
        "before_len": result.get("before_len") or 0,
        "after_len": result.get("after_len") or 0,
        "before_hash": result.get("before_hash") or "",
        "after_hash": result.get("after_hash") or "",
    }
    print(
        f"{log_timestamp()} [claude-attribution-strip] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
        file=sys.stderr,
    )


def prompt_cache_key_mode() -> str:
    mode = str(os.environ.get(PROMPT_CACHE_KEY_MODE_ENV) or "auto").strip().lower()
    return mode if mode in {"auto", "never"} else "auto"


def prompt_cache_key_from_session(session_key: str | None) -> str:
    if not session_key or prompt_cache_key_mode() == "never":
        return ""
    return "bd:" + hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:32]


def _stable_json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonicalize_json_string(value: str) -> str:
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        parsed = json.loads(text)
    except Exception:
        return value
    if isinstance(parsed, (dict, list)):
        return _stable_json_string(parsed)
    return value


def canonicalize_for_cache(value: Any, *, key_hint: str = "") -> Any:
    if isinstance(value, dict):
        return {str(key): canonicalize_for_cache(value[key], key_hint=str(key)) for key in sorted(value.keys(), key=str)}
    if isinstance(value, list):
        return [canonicalize_for_cache(item, key_hint=key_hint) for item in value]
    if isinstance(value, str) and key_hint in {"arguments", "output"}:
        return _canonicalize_json_string(value)
    return value


def prepare_upstream_responses_body(
    body: dict[str, Any],
    *,
    session_key: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = canonicalize_for_cache(body)
    cache_key = prompt_cache_key_from_session(session_key)
    if cache_key:
        prepared["prompt_cache_key"] = cache_key
    return prepared, {
        "session_id": _prompt_sha12(session_key or ""),
        "prompt_cache_key_present": bool(cache_key),
        "cache_key_source": "session_identity" if cache_key else ("disabled" if prompt_cache_key_mode() == "never" else "none"),
    }


def stream_max_retries() -> int:
    raw = os.environ.get(STREAM_MAX_RETRIES_ENV, "2")
    try:
        return max(0, min(int(raw), 10))
    except ValueError:
        return 2


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in RETRYABLE_HTTP_STATUSES or 500 <= status_code < 600


def is_retryable_stream_exception(exc: BaseException) -> bool:
    retryable_types = (
        httpx.RemoteProtocolError,
        httpx.ReadError,
        httpx.ReadTimeout,
        httpx.WriteError,
    )
    if isinstance(exc, retryable_types):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "overloaded",
            "temporarily",
            "timeout",
            "timed out",
            "connection reset",
            "incomplete chunked read",
            "server disconnected",
        )
    )


def session_affinity_enabled() -> bool:
    return parse_bool_env(os.environ.get(SESSION_AFFINITY_ENV, "1"))


def is_loopback_host(host: str) -> bool:
    value = host.strip().strip("[]").lower()
    return value in {"localhost", "127.0.0.1", "::1"}


def resolve_listen_host(host: str, *, allow_remote: bool = False) -> str:
    value = (host or DEFAULT_HOST).strip()
    if is_loopback_host(value):
        return value
    if allow_remote:
        return value
    raise RuntimeError(
        f"Refusing non-loopback CODEX_BRIDGE_HOST={value!r}; set {ALLOW_REMOTE_ENV}=1 to allow remote access"
    )


def redact_sensitive_query(raw_query: str) -> str:
    if not raw_query:
        return raw_query
    pairs = urllib.parse.parse_qsl(raw_query, keep_blank_values=True)
    redacted: list[str] = []
    for key, value in pairs:
        if key.lower() in SENSITIVE_QUERY_KEYS:
            redacted.append(f"{urllib.parse.quote_plus(key)}=<redacted>")
        else:
            redacted.append(
                f"{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value)}"
            )
    return "&".join(redacted)


def redact_request_target(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc:
        query = redact_sensitive_query(parsed.query)
        redacted = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
    else:
        path, sep, query = value.partition("?")
        redacted = path + (sep + redact_sensitive_query(query) if sep else "")
    redacted = re.sub(r"/accounts/[^/?#\s]+", "/accounts/<redacted>", redacted)
    redacted = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", redacted)
    return redacted


def redact_log_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = re.sub(r"/accounts/[^/?#\s]+", "/accounts/<redacted>", value)
    key_pattern = "|".join(re.escape(key) for key in sorted(SENSITIVE_QUERY_KEYS, key=len, reverse=True))
    redacted = re.sub(
        rf"(?i)([?&](?:{key_pattern})=)[^&\s\"']+",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", redacted)
    return redacted


def normalize_bridge_model_id(value: Any) -> str:
    model = str(value or "").strip()
    if re.match(r"(?i)^gpt-", model):
        return model.lower()
    return model


def bridge_model_by_id(model_id: str | None) -> BridgeModel | None:
    normalized = normalize_bridge_model_id(model_id)
    for model in BRIDGE_MODELS:
        if model.id == normalized:
            return model
    return None


def claude_desktop_model_route_map() -> dict[str, str]:
    routes: dict[str, str] = {}
    for route in CLAUDE_DESKTOP_MODEL_ROUTES:
        source_model = normalize_bridge_model_id(os.environ.get(route["env"]) or route["default"])
        if source_model:
            routes[route["id"]] = source_model
            for alias in route.get("aliases", ()):
                routes[str(alias)] = source_model
    return routes


def map_claude_desktop_model(model_id: Any) -> Any:
    if not isinstance(model_id, str):
        return model_id
    requested = model_id.strip()
    if not requested:
        return model_id
    return claude_desktop_model_route_map().get(requested.lower(), model_id)


def model_payload_item(
    model: BridgeModel,
    *,
    model_id: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": model_id or model.id,
        "slug": model_id or model.id,
        "object": "model",
        "type": "model",
        "created": 0,
        "created_at": "2026-05-07T00:00:00Z",
        "owned_by": "openai",
        "display_name": display_name or model.display_name,
        "description": display_name or model.display_name,
        "shell_type": "shell_command",
        "visibility": "list",
        "supported_in_api": True,
        "minimal_client_version": "0.98.0",
        "availability_nux": None,
        "upgrade": None,
        "priority": 100,
        "base_instructions": CODEX_MODEL_BASE_INSTRUCTIONS,
        "model_messages": {
            "instructions_template": CODEX_MODEL_BASE_INSTRUCTIONS,
            "instructions_variables": {},
        },
        "support_verbosity": True,
        "default_verbosity": "medium",
        "apply_patch_tool_type": "freeform",
        "web_search_tool_type": "text_and_image",
        "truncation_policy": {"mode": "tokens", "limit": 10000},
        "supports_parallel_tool_calls": True,
        "supports_image_detail_original": False,
        "supports_reasoning_summaries": True,
        "default_reasoning_summary": "none",
        "experimental_supported_tools": [],
        "supports_search_tool": True,
        "additional_speed_tiers": ["fast"],
        "capabilities": {
            "responses": True,
            "messages": True,
            "streaming": True,
            "tools": True,
        },
    }
    if model.context_length is not None:
        item["context_length"] = model.context_length
        item["context_window"] = model.context_length
        item["max_context_window"] = model.context_length
        item["auto_compact_token_limit"] = None
    if model.max_completion_tokens is not None:
        item["max_completion_tokens"] = model.max_completion_tokens
    if model.thinking_levels:
        levels = list(model.thinking_levels)
        item["thinking"] = {"levels": levels}
        item["default_reasoning_level"] = "medium" if "medium" in levels else levels[0]
        item["supported_reasoning_levels"] = [
            {"effort": level, "description": REASONING_LEVEL_DESCRIPTIONS.get(level, level)}
            for level in levels
        ]
    else:
        item["supported_reasoning_levels"] = []
    return item


def build_models_payload() -> dict[str, Any]:
    data: list[dict[str, Any]] = []
    for model in BRIDGE_MODELS:
        data.append(model_payload_item(model))
    route_map = claude_desktop_model_route_map()
    for route in CLAUDE_DESKTOP_MODEL_ROUTES:
        route_id = route["id"]
        source_model = route_map.get(route_id)
        source = bridge_model_by_id(source_model) or BridgeModel(
            id=source_model or route["default"],
            display_name=source_model or route["default"],
        )
        item = model_payload_item(source, model_id=route_id, display_name=route["display_name"])
        item["owned_by"] = "anthropic"
        item["bridge_target_model"] = source.id
        item["capabilities"]["claude_desktop_gateway"] = True
        data.append(item)
    return {
        "object": "list",
        "data": data,
        "models": data,
        "has_more": False,
        "first_id": data[0]["id"] if data else None,
        "last_id": data[-1]["id"] if data else None,
    }


def mask_proxy_url(proxy_url: str | None) -> str:
    if not proxy_url:
        return "direct"
    match = re.match(r"^(https?://)(?:[^@/]+@)?([^/]+)$", proxy_url.strip())
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return proxy_url


def looks_like_proxy_tls_failure(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    ssl_markers = ("ssl", "tls", "handshake", "certificate", "wrong version number")
    eof_markers = ("unexpected_eof", "eof occurred", "connection reset", "remote end closed", "protocol violation")
    return any(marker in text for marker in ssl_markers) and any(marker in text for marker in eof_markers)


def upstream_exception_detail(exc: BaseException) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    proxy_url = os.environ.get(UPSTREAM_PROXY_ENV, "").strip()
    if proxy_url and looks_like_proxy_tls_failure(exc):
        detail += (
            f"; diagnosis=local_proxy_tls_failure proxy={mask_proxy_url(proxy_url)} "
            "action=run_bridgedeck_network_diagnosis"
        )
    return detail


def get_upstream_proxy_url() -> str | None:
    value = os.environ.get(UPSTREAM_PROXY_ENV, "").strip()
    if not value:
        return None
    parsed = httpx.URL(value)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError(
            f"{UPSTREAM_PROXY_ENV} only supports http:// or https:// proxies, got: {parsed.scheme}"
        )
    return value


def build_upstream_http_client(timeout: float) -> httpx.Client:
    proxy_url = get_upstream_proxy_url()
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "trust_env": False,
        "follow_redirects": True,
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)


def truncate_log_text(value: str | None, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    safe_value = value.replace("\n", " ").strip()
    if len(safe_value) > limit:
        return safe_value[:limit] + "..."
    return safe_value


def log_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def bridge_request_id() -> str:
    return f"bridge-{uuid.uuid4().hex[:12]}"


def reasoning_placeholder_mode() -> str:
    value = os.environ.get(REASONING_PLACEHOLDER_MODE_ENV, "comment").strip().lower()
    return value if value in {"visible", "comment", "off"} else "comment"


def reasoning_summary_mode() -> str:
    value = os.environ.get("BRIDGE_REASONING_SUMMARY", "concise").strip().lower()
    return value if value in {"auto", "concise", "detailed", "off"} else "concise"


def is_retryable_terminal_stream_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in ("overloaded", "temporarily", "timeout", "server error"))


def sse_block_commits_stream(event_name: str | None, payload: dict[str, Any] | None) -> bool:
    if event_name in {
        "response.completed",
        "response.failed",
        "response.cancelled",
        "response.incomplete",
        "error",
    }:
        return True
    if event_name in {
        "response.output_text.delta",
        "response.output_text.done",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.done",
    }:
        return True
    if event_name and ("tool" in event_name or "function_call" in event_name):
        return True
    if not isinstance(payload, dict):
        return False
    payload_type = payload.get("type")
    if isinstance(payload_type, str):
        if "tool" in payload_type or "function_call" in payload_type:
            return True
        if payload_type in {
            "response.output_text.delta",
            "response.output_text.done",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary_text.done",
        }:
            return True
    item = payload.get("item")
    if isinstance(item, dict):
        item_type = item.get("type")
        return isinstance(item_type, str) and item_type != "reasoning"
    return False


def log_upstream_result(
    request_type: str,
    account_id: str | None,
    success: bool,
    *,
    status_code: int | None = None,
    detail: str | None = None,
) -> None:
    proxy_mode = mask_proxy_url(os.environ.get(UPSTREAM_PROXY_ENV))
    account_label = account_id or "default"
    summary = (
        f"[upstream] type={request_type} account_id={account_label} proxy={proxy_mode} "
        f"success={str(success).lower()}"
    )
    if status_code is not None:
        summary += f" status={status_code}"
    if detail:
        safe_detail = truncate_log_text(redact_log_text(detail))
        summary += f" detail={safe_detail}"
    print(f"{log_timestamp()} {summary}", file=sys.stderr)


def log_bridge_stream_retry(
    *,
    request_id: str,
    account_id: str,
    requested_model: str | None,
    attempt: int,
    max_attempts: int,
    reason: str,
) -> None:
    print(
        f"{log_timestamp()} [bridge-stream-retry] request_id={request_id} account_id={account_id} "
        f"model={requested_model or 'unknown'} attempt={attempt}/{max_attempts} reason={truncate_log_text(reason)}",
        file=sys.stderr,
    )


def summarize_request_shape(body: dict[str, Any]) -> dict[str, Any]:
    shape: dict[str, Any] = {"keys": sorted(body.keys())}

    for key in ("stream", "store", "tool_choice", "parallel_tool_calls", "model"):
        if key in body:
            shape[key] = body.get(key)

    if "instructions" in body:
        instructions = body.get("instructions")
        shape["instructions_kind"] = type(instructions).__name__
        shape["has_instructions"] = bool(instructions)

    include = body.get("include")
    if isinstance(include, list):
        shape["include"] = sorted({item for item in include if isinstance(item, str)})

    tools = body.get("tools")
    if isinstance(tools, list):
        shape["tools_count"] = len(tools)

    input_items = body.get("input")
    if isinstance(input_items, list):
        item_types: set[str] = set()
        roles: set[str] = set()
        content_types: set[str] = set()
        for item in input_items:
            if isinstance(item, dict):
                item_type = item.get("type")
                if isinstance(item_type, str):
                    item_types.add(item_type)
                role = item.get("role")
                if isinstance(role, str):
                    roles.add(role)
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            part_type = part.get("type")
                            if isinstance(part_type, str):
                                content_types.add(part_type)
            else:
                item_types.add(type(item).__name__)
        shape["input_count"] = len(input_items)
        if item_types:
            shape["input_item_types"] = sorted(item_types)
        if roles:
            shape["input_roles"] = sorted(roles)
        if content_types:
            shape["input_content_types"] = sorted(content_types)
    elif "input" in body:
        shape["input_kind"] = type(input_items).__name__

    removed_fields = [key for key in ("max_output_tokens", "temperature", "top_p") if key in body]
    if removed_fields:
        shape["legacy_fields_present"] = sorted(removed_fields)

    return shape


def reasoning_has_visible_summary(item: dict[str, Any]) -> bool:
    summary = item.get("summary")
    if not isinstance(summary, list):
        return False
    for entry in summary:
        if isinstance(entry, dict):
            text = entry.get("text")
            if isinstance(text, str) and text.strip():
                return True
    return False


def extract_reasoning_effort(payload: dict[str, Any]) -> str | None:
    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, dict):
        return None
    effort = reasoning.get("effort")
    return effort if isinstance(effort, str) and effort else None


def build_visible_model_hint(
    actual_model: str | None,
    requested_model: str | None,
    actual_effort: str | None,
    requested_effort: str | None,
) -> str:
    effort = requested_effort or actual_effort or "unknown"
    model = requested_model or actual_model
    model_suffix = f"｜模型：{model}" if model else ""
    return f"【思考等级：{effort}{model_suffix}｜上游加密，无法展示明文】\n"


def lookup_bridge_provider_names(account_id: str | None) -> list[str]:
    if not account_id or not CC_SWITCH_DB_PATH.exists():
        return []

    query = """
        SELECT name
        FROM providers
        WHERE json_extract(meta, '$.authBinding.accountId') = ?
          AND json_extract(settings_config, '$.env.ANTHROPIC_AUTH_TOKEN') = 'local-bridge'
        ORDER BY name
    """
    try:
        with sqlite3.connect(CC_SWITCH_DB_PATH) as conn:
            rows = conn.execute(query, (account_id,)).fetchall()
    except sqlite3.Error:
        return []

    return [name for (name,) in rows if isinstance(name, str)]


def log_upstream_diagnostic(
    request_type: str,
    account_id: str | None,
    *,
    status_code: int,
    route_path: str,
    response_headers: httpx.Headers | None = None,
    request_shape: dict[str, Any] | None = None,
    normalized_shape: dict[str, Any] | None = None,
    error_detail: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": request_type,
        "account_id": account_id or "default",
        "route_path": route_path,
        "status": status_code,
    }
    provider_names = lookup_bridge_provider_names(account_id)
    if provider_names:
        payload["provider_names"] = provider_names
    if response_headers is not None:
        upstream_request_id = response_headers.get("x-request-id")
        if upstream_request_id:
            payload["x_request_id"] = upstream_request_id
        processing_ms = response_headers.get("openai-processing-ms")
        if processing_ms:
            payload["openai_processing_ms"] = processing_ms
        response_content_type = response_headers.get("content-type")
        if response_content_type:
            payload["content_type"] = response_content_type
    if request_shape:
        payload["request_shape"] = request_shape
    if normalized_shape:
        payload["normalized_shape"] = normalized_shape
    safe_error_detail = truncate_log_text(redact_log_text(error_detail), limit=800) if error_detail else None
    if safe_error_detail:
        payload["error_detail"] = safe_error_detail
    print(
        f"{log_timestamp()} [upstream-diagnostic] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
        file=sys.stderr,
    )


def response_failed_sse(
    *,
    request_id: str,
    requested_model: str | None,
    exc: BaseException,
    error_code: str = "upstream_stream_error",
    error_type: str | None = None,
) -> bytes:
    error_type = error_type or type(exc).__name__
    message = truncate_log_text(str(exc), limit=500) or error_type
    payload = {
        "type": "response.failed",
        "response": {
            "id": f"resp_{request_id}",
            "object": "response",
            "status": "failed",
            "model": requested_model or "unknown",
            "error": {
                "code": error_code,
                "message": message,
                "type": error_type,
            },
        },
    }
    return (
        "event: response.failed\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    ).encode("utf-8")


def stream_tool_call_guard_mode() -> str:
    raw = os.environ.get(STREAM_TOOL_CALL_GUARD_MODE_ENV, "off").strip().lower()
    aliases = {
        "": "off",
        "1": "auto",
        "true": "auto",
        "yes": "auto",
        "on": "auto",
        "0": "off",
        "false": "off",
        "no": "off",
        "never": "off",
        "passthrough": "off",
        "disabled": "off",
        "disable": "off",
    }
    raw = aliases.get(raw, raw)
    if raw not in {"auto", "protective", "off"}:
        return "off"
    return raw


def stream_tool_call_guard_seconds() -> float:
    if stream_tool_call_guard_mode() == "off":
        return 0.0
    return max(0.0, STREAM_TOOL_CALL_WALL_FAIL_SECS)


def incomplete_answer_guard_mode() -> str:
    raw = os.environ.get(INCOMPLETE_ANSWER_GUARD_ENV, "fail").strip().lower()
    aliases = {
        "": "fail",
        "0": "off",
        "false": "off",
        "no": "off",
        "never": "off",
        "disabled": "off",
        "disable": "off",
        "1": "fail",
        "true": "fail",
        "yes": "fail",
        "on": "fail",
        "error": "fail",
    }
    raw = aliases.get(raw, raw)
    if raw not in {"off", "warn", "fail"}:
        return "fail"
    return raw


def anthropic_tool_args_mode() -> str:
    raw = os.environ.get(ANTHROPIC_TOOL_ARGS_MODE_ENV, "coalesce").strip().lower()
    aliases = {
        "": "coalesce",
        "1": "coalesce",
        "true": "coalesce",
        "yes": "coalesce",
        "on": "coalesce",
        "buffer": "coalesce",
        "buffered": "coalesce",
        "collapse": "coalesce",
        "0": "stream",
        "false": "stream",
        "no": "stream",
        "off": "stream",
        "passthrough": "stream",
        "raw": "stream",
    }
    raw = aliases.get(raw, raw)
    if raw not in {"coalesce", "stream"}:
        return "coalesce"
    return raw


def anthropic_tool_arg_ping_seconds() -> float:
    return max(0.0, ANTHROPIC_TOOL_ARG_PING_SECS)


def _append_visible_text_metrics(metrics: BridgeStreamMetrics, text: str) -> None:
    if not text:
        return
    metrics.visible_text_chars += len(text)
    metrics.last_visible_text_tail = (metrics.last_visible_text_tail + text)[-160:]


def _visible_text_from_payload(event_key: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if event_key == "response.output_text.delta":
        value = payload.get("delta")
        return value if isinstance(value, str) else ""
    if event_key == "response.output_text.done":
        value = payload.get("text")
        return value if isinstance(value, str) else ""
    return ""


def _response_from_terminal_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    response = payload.get("response")
    if isinstance(response, dict):
        return response
    return payload


def _update_terminal_response_metrics(metrics: BridgeStreamMetrics, payload: Any) -> None:
    response = _response_from_terminal_payload(payload)
    if not response:
        return
    status = response.get("status")
    if isinstance(status, str):
        metrics.completed_response_status = status
    incomplete = response.get("incomplete_details")
    if isinstance(incomplete, dict):
        reason = incomplete.get("reason")
        if isinstance(reason, str):
            metrics.completed_incomplete_reason = reason
    usage = response.get("usage")
    if isinstance(usage, dict):
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        if isinstance(output_tokens, int):
            metrics.completed_output_tokens = output_tokens
        if isinstance(total_tokens, int):
            metrics.completed_total_tokens = total_tokens


def _answer_end_class(tail: str) -> str:
    text = tail.rstrip()
    if not text:
        return "empty"
    last = text[-1]
    if last in {":", "："}:
        return "open_colon"
    if last in {",", "，", ";", "；", "、"}:
        return "continuation_punctuation"
    if last in {".", "。", "!", "！", "?", "？", "…"}:
        return "sentence_terminal"
    if last in {")",
        "]",
        "}",
        ">",
        "）",
        "】",
        "」",
        "』",
        "》",
    }:
        return "closed_delimiter"
    return "other"


def _answer_incomplete_risk(metrics: BridgeStreamMetrics) -> bool:
    if metrics.completed_response_status == "incomplete" or metrics.completed_incomplete_reason:
        return True
    if metrics.client_disconnected or metrics.idle_timeout_seen:
        return True
    if metrics.visible_text_chars <= 0:
        return False
    return _answer_end_class(metrics.last_visible_text_tail) in {"open_colon", "continuation_punctuation"}


def _incomplete_answer_error(metrics: BridgeStreamMetrics) -> BridgeIncompleteAnswer:
    end_class = _answer_end_class(metrics.last_visible_text_tail)
    detail = metrics.completed_incomplete_reason or metrics.completed_response_status or "completed"
    return BridgeIncompleteAnswer(
        "upstream completed with a suspiciously unfinished visible answer "
        f"(end_class={end_class}, status={detail}, visible_text_chars={metrics.visible_text_chars})"
    )


def log_bridge_stream_summary(
    *,
    account_id: str,
    requested_model: str | None,
    requested_effort: str | None,
    actual_effort: str | None,
    request_id: str,
    started_at: float,
    upstream_request_id: str | None,
    state: ReasoningPlaceholderState,
    metrics: BridgeStreamMetrics,
) -> None:
    payload = {
        "account_id": account_id,
        "answer_end_class": _answer_end_class(metrics.last_visible_text_tail),
        "answer_incomplete_risk": _answer_incomplete_risk(metrics),
        "client_disconnected": metrics.client_disconnected,
        "completed_incomplete_reason": metrics.completed_incomplete_reason,
        "completed_output_tokens": metrics.completed_output_tokens,
        "completed_response_status": metrics.completed_response_status,
        "completed_total_tokens": metrics.completed_total_tokens,
        "downstream_writes": metrics.downstream_writes,
        "duration_s": round(time.monotonic() - started_at, 3),
        "actual_effort": actual_effort or requested_effort or "unknown",
        "effort": actual_effort or requested_effort or "unknown",
        "heartbeats": state.emitted_count,
        "idle_timeout_seen": metrics.idle_timeout_seen,
        "first_visible_after_ms": metrics.first_visible_after_ms,
        "last_event_name": metrics.last_event_name,
        "model": requested_model or "unknown",
        "reasoning_events": metrics.reasoning_events,
        "requested_effort": requested_effort or "unknown",
        "request_id": request_id,
        "terminal_event_seen": metrics.terminal_event_seen,
        "terminal_events": metrics.terminal_events,
        "tool_arg_buffer_chars": metrics.tool_arg_buffer_chars,
        "tool_arg_coalesced_calls": metrics.tool_arg_coalesced_calls,
        "tool_arg_delta_events": metrics.tool_arg_delta_events,
        "tool_arg_ping_events": metrics.tool_arg_ping_events,
        "tool_args_mode": metrics.tool_args_mode or anthropic_tool_args_mode(),
        "tool_events": metrics.tool_events,
        "upstream_events": metrics.upstream_events,
        "visible_text_chars": metrics.visible_text_chars,
        "visible_text_events": metrics.visible_text_events,
    }
    if metrics.last_visible_text_tail:
        payload["visible_text_tail_sha12"] = hashlib.sha256(
            metrics.last_visible_text_tail.encode("utf-8", "replace")
        ).hexdigest()[:12]
    if upstream_request_id:
        payload["upstream_request_id"] = upstream_request_id
    print(
        f"{log_timestamp()} [bridge-stream-end] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
        file=sys.stderr,
    )


def log_bridge_long_stream_warning(
    *,
    account_id: str,
    requested_model: str | None,
    requested_effort: str | None,
    actual_effort: str | None,
    request_id: str,
    started_at: float,
    upstream_request_id: str | None,
    metrics: BridgeStreamMetrics,
) -> None:
    payload = {
        "account_id": account_id,
        "duration_s": round(time.monotonic() - started_at, 3),
        "actual_effort": actual_effort or requested_effort or "unknown",
        "effort": actual_effort or requested_effort or "unknown",
        "first_visible_after_ms": metrics.first_visible_after_ms,
        "last_event_name": metrics.last_event_name,
        "model": requested_model or "unknown",
        "reasoning_events": metrics.reasoning_events,
        "requested_effort": requested_effort or "unknown",
        "request_id": request_id,
        "terminal_event_seen": metrics.terminal_event_seen,
        "tool_arg_buffer_chars": metrics.tool_arg_buffer_chars,
        "tool_arg_coalesced_calls": metrics.tool_arg_coalesced_calls,
        "tool_arg_delta_events": metrics.tool_arg_delta_events,
        "tool_arg_ping_events": metrics.tool_arg_ping_events,
        "tool_args_mode": metrics.tool_args_mode or anthropic_tool_args_mode(),
        "tool_events": metrics.tool_events,
        "upstream_events": metrics.upstream_events,
        "visible_text_events": metrics.visible_text_events,
    }
    if upstream_request_id:
        payload["upstream_request_id"] = upstream_request_id
    print(
        f"{log_timestamp()} [bridge-long-stream-warning] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
        file=sys.stderr,
    )


def terminal_stream_error_from_payload(event_name: str | None, payload: dict[str, Any] | None) -> TerminalStreamError | None:
    if event_name not in {"response.failed", "error"} or not isinstance(payload, dict):
        return None
    response_obj = payload.get("response")
    error_obj = response_obj.get("error") if isinstance(response_obj, dict) else payload.get("error")
    if isinstance(error_obj, dict):
        message = error_obj.get("message") or error_obj.get("code") or event_name
    else:
        message = payload.get("message") or str(error_obj or event_name)
    return TerminalStreamError(str(message))


def _read_bridge_state() -> dict[str, Any]:
    if not BRIDGE_STATE_PATH.exists() or BRIDGE_STATE_PATH.is_symlink():
        return {}
    try:
        payload = json.loads(BRIDGE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_bridge_state(state: dict[str, Any]) -> None:
    state["updated_at"] = int(time.time())
    try:
        BRIDGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = BRIDGE_STATE_PATH.with_name(
            f".{BRIDGE_STATE_PATH.name}.tmp-{os.getpid()}-{time.time_ns()}"
        )
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, BRIDGE_STATE_PATH)
        finally:
            if tmp.exists():
                tmp.unlink()
    except Exception as exc:  # noqa: BLE001
        print(
            f"{log_timestamp()} [bridge-state-error] type={type(exc).__name__} detail={truncate_log_text(str(exc))}",
            file=sys.stderr,
        )


def record_bridge_stream_error(payload: dict[str, Any]) -> None:
    state = _read_bridge_state()
    state["last_stream_error"] = payload
    _write_bridge_state(state)


def record_bridge_active_stream(payload: dict[str, Any] | None) -> None:
    state = _read_bridge_state()
    if payload is None:
        state.pop("active_stream", None)
    else:
        state["active_stream"] = payload
    _write_bridge_state(state)


def _usage_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def _extract_usage_counts(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {}
    input_tokens = _usage_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    output_tokens = _usage_int(usage.get("output_tokens") or usage.get("completion_tokens"))
    total_tokens = _usage_int(usage.get("total_tokens")) or input_tokens + output_tokens
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cache_details = usage.get("cache_creation_input_tokens_details") if isinstance(usage.get("cache_creation_input_tokens_details"), dict) else {}
    cached_tokens = _usage_int(usage.get("cached_tokens") or input_details.get("cached_tokens"))
    cache_creation_tokens = _usage_int(usage.get("cache_creation_tokens") or cache_details.get("cache_creation_tokens"))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_creation_tokens": cache_creation_tokens,
    }


def _usage_from_payload(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    return _extract_usage_counts(response.get("usage") if isinstance(response, dict) else None)


def record_bridge_usage(
    *,
    account_id: str,
    model: str | None,
    request_type: str,
    request_id: str,
    usage: Any,
    requested_model: str | None = None,
    duration_ms: int | None = None,
    status_code: int = 200,
    source: str = "proxy",
    route_path: str = "",
    bridge_port: int | None = None,
    client_port: int | None = None,
    client_label: str = "",
    desktop_route: bool = False,
    session_id: str = "",
    prompt_cache_key_present: bool = False,
    cache_key_source: str = "",
) -> None:
    with _bridge_state_lock:
        counts = _extract_usage_counts(usage)
        if not counts or not any(counts.values()):
            return
        cache_miss_tokens = max(0, counts["input_tokens"] - counts["cached_tokens"])
        cache_eligible_tokens = counts["input_tokens"]
        cache_hit_rate = (counts["cached_tokens"] / cache_eligible_tokens) if cache_eligible_tokens else 0.0
        cache_miss_rate = (cache_miss_tokens / cache_eligible_tokens) if cache_eligible_tokens else 0.0
        state = _read_bridge_state()
        metrics = state.get("usage_metrics") if isinstance(state.get("usage_metrics"), dict) else {}
        for key in ("input_tokens", "output_tokens", "total_tokens", "cached_tokens", "cache_creation_tokens"):
            metrics[key] = _usage_int(metrics.get(key)) + counts[key]
        aggregate_cache_eligible = _usage_int(metrics.get("input_tokens"))
        aggregate_cached = _usage_int(metrics.get("cached_tokens"))
        aggregate_missed = max(0, aggregate_cache_eligible - aggregate_cached)
        metrics["cache_miss_tokens"] = aggregate_missed
        metrics["cache_hit_rate"] = (aggregate_cached / aggregate_cache_eligible) if aggregate_cache_eligible else 0.0
        metrics["cache_miss_rate"] = (aggregate_missed / aggregate_cache_eligible) if aggregate_cache_eligible else 0.0
        metrics["request_count"] = _usage_int(metrics.get("request_count")) + 1
        metrics["last_account_id"] = account_id
        metrics["last_model"] = model or ""
        metrics["last_requested_model"] = requested_model or model or ""
        metrics["last_request_type"] = request_type
        metrics["last_request_id"] = request_id
        metrics["last_duration_ms"] = _usage_int(duration_ms)
        metrics["last_status_code"] = _usage_int(status_code)
        metrics["last_bridge_port"] = _usage_int(bridge_port)
        metrics["last_client_label"] = client_label or ""
        metrics["last_session_id"] = session_id or ""
        metrics["last_prompt_cache_key_present"] = bool(prompt_cache_key_present)
        metrics["last_cache_key_source"] = cache_key_source or ""
        metrics["last_updated_at"] = int(time.time())
        state["usage_metrics"] = metrics
        event = {
            "at": int(time.time()),
            "account_id": account_id,
            "model": model or "",
            "actual_model": model or "",
            "requested_model": requested_model or model or "",
            "request_type": request_type,
            "request_id": request_id,
            "status_code": _usage_int(status_code),
            "source": source,
            "route_path": route_path,
            "bridge_port": _usage_int(bridge_port),
            "client_port": _usage_int(client_port),
            "client_label": client_label or "",
            "desktop_route": bool(desktop_route),
            "session_id": session_id or "",
            "prompt_cache_key_present": bool(prompt_cache_key_present),
            "cache_key_source": cache_key_source or "",
            "duration_ms": _usage_int(duration_ms),
            "input_tokens": counts["input_tokens"],
            "output_tokens": counts["output_tokens"],
            "total_tokens": counts["total_tokens"],
            "cached_tokens": counts["cached_tokens"],
            "cache_creation_tokens": counts["cache_creation_tokens"],
            "cache_miss_tokens": cache_miss_tokens,
            "cache_hit_rate": cache_hit_rate,
            "cache_miss_rate": cache_miss_rate,
            "cost_usd": 0.0,
        }
        events = state.get("usage_events") if isinstance(state.get("usage_events"), list) else []
        events.append(event)
        state["usage_events"] = events[-MAX_USAGE_EVENTS:]
        state.pop("last_stream_error", None)
        _write_bridge_state(state)


def log_bridge_stream_error(
    *,
    account_id: str,
    requested_model: str | None,
    request_id: str,
    started_at: float,
    exc: BaseException,
    upstream_request_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "account_id": account_id,
        "model": requested_model or "",
        "request_id": request_id,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "error_type": type(exc).__name__,
        "error": truncate_log_text(str(exc), limit=500) or type(exc).__name__,
    }
    if upstream_request_id:
        payload["upstream_request_id"] = upstream_request_id
    record_bridge_stream_error(payload)
    print(
        f"{log_timestamp()} [bridge-stream-error] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
        file=sys.stderr,
    )


def log_bridge_client_disconnect(
    *,
    account_id: str,
    requested_model: str | None,
    request_id: str,
    started_at: float,
    detail: str,
    upstream_request_id: str | None = None,
) -> None:
    exc = BridgeClientDisconnect(f"downstream client disconnected before terminal event: {detail}")
    log_bridge_stream_error(
        account_id=account_id,
        requested_model=requested_model,
        request_id=request_id,
        started_at=started_at,
        exc=exc,
        upstream_request_id=upstream_request_id,
    )
    print(
        f"{log_timestamp()} [bridge-client-disconnect] request_id={request_id} model={requested_model or 'unknown'} detail={detail}",
        file=sys.stderr,
    )


class AuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._token_cache: dict[str, CachedToken] = {}
        self._session_affinity: dict[str, str] = {}

    def load(self) -> tuple[dict[str, AccountRecord], str | None]:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}, None
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"{log_timestamp()} [auth-store-corrupt] detail={exc}",
                file=sys.stderr,
            )
            return {}, None
        accounts = {
            account_id: AccountRecord(
                account_id=account_id,
                refresh_token=data["refresh_token"],
                email=data.get("email"),
                authenticated_at=data.get("authenticated_at"),
            )
            for account_id, data in raw.get("accounts", {}).items()
        }
        return accounts, raw.get("default_account_id")

    def save(self, accounts: dict[str, AccountRecord], default_account_id: str | None) -> None:
        payload = {
            "version": 1,
            "accounts": {
                account_id: {
                    "account_id": record.account_id,
                    "email": record.email,
                    "refresh_token": record.refresh_token,
                    "authenticated_at": record.authenticated_at,
                }
                for account_id, record in accounts.items()
            },
            "default_account_id": default_account_id,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}-{time.time_ns()}")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def get_access_token(self, requested_account_id: str | None) -> tuple[str, str]:
        lock_path = self.path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = lock_path.open("w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            with self._lock:
                accounts, default_account_id = self.load()
                account_id = requested_account_id or default_account_id
                if not account_id or account_id not in accounts:
                    raise RuntimeError(f"account not found: {requested_account_id or 'default'}")

                cached = self._token_cache.get(account_id)
                if cached and not cached.is_expiring_soon():
                    return account_id, cached.token

                record = accounts[account_id]
                token_data = self._refresh_token(record.refresh_token)

                new_refresh = token_data.get("refresh_token")
                if new_refresh and new_refresh != record.refresh_token:
                    record.refresh_token = new_refresh
                    accounts[account_id] = record
                    self.save(accounts, default_account_id)

                access_token = token_data["access_token"]
                expires_in = int(token_data.get("expires_in", 3600))
                self._token_cache[account_id] = CachedToken(
                    token=access_token,
                    expires_at=time.time() + expires_in,
                )
                return account_id, access_token
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def account_candidates(self, requested_account_id: str | None, session_key: str | None = None) -> list[str]:
        with self._lock:
            accounts, default_account_id = self.load()
            if requested_account_id:
                if requested_account_id not in accounts:
                    raise RuntimeError(f"account not found: {requested_account_id}")
                return [requested_account_id]

            ordered: list[str] = []
            bound = self._session_affinity.get(session_key or "") if session_key else None
            if session_affinity_enabled() and bound in accounts:
                ordered.append(bound)
            if default_account_id in accounts and default_account_id not in ordered:
                ordered.append(default_account_id)
            for account_id in accounts:
                if account_id not in ordered:
                    ordered.append(account_id)
            if not ordered:
                raise RuntimeError("account not found: default")
            return ordered

    def bind_session(self, session_key: str | None, account_id: str) -> None:
        if not session_key or not session_affinity_enabled():
            return
        with self._lock:
            self._session_affinity[session_key] = account_id

    def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        try:
            with build_upstream_http_client(timeout=30.0) as client:
                response = client.post(
                    OAUTH_TOKEN_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": CODEX_USER_AGENT,
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": CODEX_CLIENT_ID,
                        "scope": "openid profile email",
                    },
                )
            response.raise_for_status()
            log_upstream_result("oauth_token", None, True, status_code=response.status_code)
            return response.json()
        except httpx.HTTPStatusError as exc:
            log_upstream_result(
                "oauth_token",
                None,
                False,
                status_code=exc.response.status_code,
                detail=exc.response.text,
            )
            raise
        except Exception as exc:
            log_upstream_result("oauth_token", None, False, detail=upstream_exception_detail(exc))
            raise


def normalize_request_body(body: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(body)
    normalized["store"] = False
    # ChatGPT's Codex backend rejects non-streaming responses on this endpoint.
    # The bridge is dedicated to CC Switch/Claude flows, which already expect SSE.
    normalized["stream"] = True
    normalized["tool_choice"] = normalized.get("tool_choice", "auto")
    normalized["parallel_tool_calls"] = normalized.get("parallel_tool_calls", False)
    normalized["instructions"] = normalized.get("instructions", "")
    normalized["tools"] = normalized.get("tools", [])

    model = normalized.get("model")
    if isinstance(model, str):
        routed_model = map_claude_desktop_model(model)
        if routed_model != model:
            print(
                f"[bridge-normalize] desktop route {model} -> {routed_model}",
                file=sys.stderr,
            )
            normalized["model"] = routed_model
            model = routed_model
        normalized_model, default_effort = normalize_codex_model_and_effort(model)
        if normalized_model != model:
            print(
                f"[bridge-normalize] model {model} -> {normalized_model}",
                file=sys.stderr,
            )
            normalized["model"] = normalized_model
        if default_effort and not has_reasoning_effort(normalized):
            normalized["reasoning"] = {"effort": default_effort}
            print(
                f"[bridge-normalize] reasoning.effort -> {default_effort} (model={normalized['model']})",
                file=sys.stderr,
            )

    reasoning = normalized.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        model_name = str(normalized.get("model") or "").strip().lower()
        if isinstance(effort, str) and effort.strip().lower() == "minimal" and model_name == "gpt-5.4":
            reasoning["effort"] = "low"
            effort = "low"
            print(
                "[bridge-normalize] reasoning.effort minimal -> low (model=gpt-5.4)",
                file=sys.stderr,
            )
        if not supports_reasoning_summary_model(model_name):
            reasoning.pop("summary", None)
        summary_mode = reasoning_summary_mode()
        if (
            summary_mode != "off"
            and supports_reasoning_summary_model(model_name)
            and isinstance(effort, str)
            and effort.strip().lower() not in {"", "none"}
            and not isinstance(reasoning.get("summary"), str)
        ):
            reasoning["summary"] = summary_mode

    include = normalized.get("include")
    includes = [item for item in include if isinstance(item, str)] if isinstance(include, list) else []
    includes = [item for item in includes if item != "reasoning.summary"]
    if "reasoning.encrypted_content" not in includes:
        includes.append("reasoning.encrypted_content")
    normalized["include"] = includes

    for key in ("max_output_tokens", "temperature", "top_p"):
        normalized.pop(key, None)

    input_items = normalized.get("input")
    if isinstance(input_items, list):
        rewritten = []
        for item in input_items:
            if isinstance(item, dict) and "role" in item and "type" not in item:
                cloned = dict(item)
                cloned["type"] = "message"
                rewritten.append(cloned)
            else:
                rewritten.append(item)
        normalized["input"] = rewritten

    return normalized


def parse_sse_blocks(raw_bytes: bytes) -> list[tuple[str | None, dict[str, Any] | None]]:
    blocks: list[tuple[str | None, dict[str, Any] | None]] = []
    event_name: str | None = None
    data_lines: list[str] = []
    text = raw_bytes.decode("utf-8", "replace")

    for line in text.splitlines():
        if line == "":
            if data_lines:
                payload_text = "\n".join(data_lines).strip()
                payload: dict[str, Any] | None = None
                if payload_text and payload_text != "[DONE]":
                    try:
                        decoded = json.loads(payload_text)
                        if isinstance(decoded, dict):
                            payload = decoded
                    except Exception:  # noqa: BLE001
                        payload = None
                blocks.append((event_name, payload))
            event_name = None
            data_lines = []
            continue

        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())

    if data_lines:
        payload_text = "\n".join(data_lines).strip()
        payload: dict[str, Any] | None = None
        if payload_text and payload_text != "[DONE]":
            try:
                decoded = json.loads(payload_text)
                if isinstance(decoded, dict):
                    payload = decoded
            except Exception:  # noqa: BLE001
                payload = None
        blocks.append((event_name, payload))

    return blocks


def build_non_stream_json_from_sse(raw_bytes: bytes, fallback_model: str | None = None) -> bytes:
    blocks = parse_sse_blocks(raw_bytes)
    completed_response: dict[str, Any] | None = None
    failed_response: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    message_text_parts: list[str] = []
    final_text: str | None = None

    for event_name, payload in blocks:
        if not isinstance(payload, dict):
            continue
        if event_name == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str) and delta:
                message_text_parts.append(delta)
        elif event_name == "response.output_text.done":
            text = payload.get("text")
            if isinstance(text, str):
                final_text = text
        elif event_name == "response.completed":
            response_obj = payload.get("response")
            if isinstance(response_obj, dict):
                completed_response = response_obj
        elif event_name == "response.failed":
            response_obj = payload.get("response")
            if isinstance(response_obj, dict):
                failed_response = dict(response_obj)
        elif event_name == "error":
            error_payload = dict(payload)

    text = final_text if isinstance(final_text, str) else "".join(message_text_parts)

    if failed_response is not None:
        failed_response.setdefault("id", "resp_bridge_non_stream_failed")
        failed_response.setdefault("object", "response")
        failed_response.setdefault("status", "failed")
        failed_response.setdefault("model", fallback_model or "gpt-5.3-codex")
        return json.dumps(failed_response, ensure_ascii=False).encode("utf-8")

    if error_payload is not None:
        failed = {
            "id": "resp_bridge_non_stream_failed",
            "object": "response",
            "status": "failed",
            "model": fallback_model or "gpt-5.3-codex",
            "error": error_payload.get("error") if isinstance(error_payload.get("error"), dict) else error_payload,
        }
        return json.dumps(failed, ensure_ascii=False).encode("utf-8")

    if completed_response is None:
        completed_response = {
            "id": "resp_bridge_non_stream",
            "object": "response",
            "status": "completed",
            "model": fallback_model or "gpt-5.3-codex",
            "usage": None,
        }
    else:
        completed_response = dict(completed_response)

    output = completed_response.get("output")
    if not isinstance(output, list) or len(output) == 0:
        completed_response["output"] = [
            {
                "id": "msg_bridge_non_stream",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]

    return json.dumps(completed_response, ensure_ascii=False).encode("utf-8")


def has_reasoning_effort(body: dict[str, Any]) -> bool:
    reasoning = body.get("reasoning")
    return isinstance(reasoning, dict) and isinstance(reasoning.get("effort"), str)


def supports_reasoning_effort_model(model: str) -> bool:
    model_lower = model.lower()
    if re.match(r"^o\d", model_lower):
        return True
    if not model_lower.startswith("gpt-"):
        return False
    rest = model_lower[4:]
    return bool(rest) and rest[0].isdigit() and rest[0] >= "5"


def supports_reasoning_summary_model(model: str) -> bool:
    model_lower = model.strip().lower()
    return model_lower not in {"gpt-5.3-codex-spark"}


def normalize_codex_model_and_effort(model: str) -> tuple[str, str | None]:
    model_lower = model.strip().lower()
    if model_lower == "gpt-5.1-codex-max":
        return "gpt-5.4", "xhigh"
    if model_lower.endswith("-thinking"):
        base = model_lower[: -len("-thinking")]
        if supports_reasoning_effort_model(base):
            return base, "xhigh"
    return model, None


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _system_to_instructions(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts: list[str] = []
        for item in system:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n\n".join(part for part in parts if part)
    return ""


def _anthropic_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _coerce_text(content)
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            item_type = item.get("type")
            if item_type == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif item_type == "tool_result":
                tool_content = item.get("content")
                if isinstance(tool_content, str):
                    parts.append(tool_content)
                elif isinstance(tool_content, list):
                    parts.append(_anthropic_text_from_content(tool_content))
                elif tool_content is not None:
                    parts.append(_coerce_text(tool_content))
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(part for part in parts if part)


def _anthropic_tool_result_output(part: dict[str, Any]) -> str:
    content = part.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _anthropic_text_from_content(content)
    return _coerce_text(content)


def _json_arguments(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False)


def _response_message_content_part(role: str, text: str) -> dict[str, Any]:
    return {"type": "output_text" if role == "assistant" else "input_text", "text": text}


def _anthropic_content_to_response_items(role: str, content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"role": role, "content": [_response_message_content_part(role, content)]}]

    if not isinstance(content, list):
        text = _coerce_text(content)
        return [{"role": role, "content": [_response_message_content_part(role, text)]}] if text else []

    message_parts: list[dict[str, Any]] = []
    extra_items: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            text = _coerce_text(part)
            if text:
                message_parts.append(_response_message_content_part(role, text))
            continue

        part_type = part.get("type")
        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                message_parts.append(_response_message_content_part(role, text))
        elif part_type == "tool_result":
            tool_use_id = part.get("tool_use_id")
            if isinstance(tool_use_id, str) and tool_use_id:
                extra_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_use_id,
                        "output": _anthropic_tool_result_output(part),
                    }
                )
        elif part_type == "tool_use":
            tool_id = part.get("id")
            name = part.get("name")
            if isinstance(name, str) and name:
                extra_items.append(
                    {
                        "type": "function_call",
                        "call_id": tool_id if isinstance(tool_id, str) and tool_id else f"call_{uuid.uuid4().hex[:12]}",
                        "name": name,
                        "arguments": _json_arguments(part.get("input")),
                    }
                )
        elif part_type == "image":
            source = part.get("source")
            if isinstance(source, dict) and source.get("type") == "base64":
                media_type = source.get("media_type")
                data = source.get("data")
                if isinstance(media_type, str) and isinstance(data, str):
                    message_parts.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:{media_type};base64,{data}",
                        }
                    )

    items: list[dict[str, Any]] = []
    if message_parts:
        items.append({"role": role, "content": message_parts})
    items.extend(extra_items)
    return items


def anthropic_messages_to_responses(body: dict[str, Any]) -> dict[str, Any]:
    model = body.get("model")
    responses: dict[str, Any] = {
        "model": model if isinstance(model, str) and model else "gpt-5.5",
        "input": [],
        "stream": bool(body.get("stream", False)),
        "store": False,
    }

    instructions = _system_to_instructions(body.get("system"))
    if instructions:
        responses["instructions"] = instructions

    for key in ("temperature", "top_p"):
        if key in body:
            responses[key] = body[key]
    if "max_tokens" in body:
        responses["max_output_tokens"] = body["max_tokens"]

    thinking = body.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        budget = thinking.get("budget_tokens")
        if isinstance(budget, int):
            if budget >= 100000:
                effort = "xhigh"
            elif budget >= 32000:
                effort = "high"
            elif budget >= 8000:
                effort = "medium"
            else:
                effort = "low"
            responses["reasoning"] = {"effort": effort}

    tools = body.get("tools")
    if isinstance(tools, list):
        response_tools: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                continue
            schema = tool.get("input_schema")
            response_tools.append(
                {
                    "type": "function",
                    "name": name,
                    "description": tool.get("description") if isinstance(tool.get("description"), str) else "",
                    "parameters": schema if isinstance(schema, dict) else {"type": "object", "properties": {}},
                }
            )
        if response_tools:
            responses["tools"] = response_tools

    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, dict):
        choice_type = tool_choice.get("type")
        if choice_type == "tool" and isinstance(tool_choice.get("name"), str):
            responses["tool_choice"] = {"type": "function", "name": tool_choice["name"]}
        elif choice_type in {"auto", "any", "none"}:
            responses["tool_choice"] = "auto" if choice_type == "any" else choice_type

    input_items: list[dict[str, Any]] = []
    messages = body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            role_name = role if role in {"user", "assistant", "system"} else "user"
            if role_name == "system":
                text = _anthropic_text_from_content(message.get("content"))
                if text:
                    responses["instructions"] = "\n\n".join(
                        part for part in (responses.get("instructions", ""), text) if isinstance(part, str) and part
                    )
                continue
            input_items.extend(_anthropic_content_to_response_items(role_name, message.get("content")))
    responses["input"] = input_items
    return responses


def _decode_json_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            decoded = json.loads(arguments)
            return decoded if isinstance(decoded, dict) else {"value": decoded}
        except json.JSONDecodeError:
            return {"value": arguments}
    return {}


def _usage_to_anthropic(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else 0,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else 0,
    }


def responses_json_to_anthropic_message(response: dict[str, Any], fallback_model: str | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                for part in item.get("content", []):
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get("type")
                    if part_type in {"output_text", "text"} and isinstance(part.get("text"), str):
                        content.append({"type": "text", "text": part["text"]})
            elif item_type == "function_call":
                name = item.get("name")
                if isinstance(name, str) and name:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": item.get("call_id") if isinstance(item.get("call_id"), str) else item.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                            "name": name,
                            "input": _decode_json_arguments(item.get("arguments")),
                        }
                    )
    if not content:
        content.append({"type": "text", "text": ""})

    status = response.get("status")
    stop_reason = "end_turn"
    if status == "incomplete":
        stop_reason = "max_tokens"
    elif status == "failed":
        stop_reason = "error"

    return {
        "id": response.get("id") if isinstance(response.get("id"), str) else f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": response.get("model") if isinstance(response.get("model"), str) else fallback_model or "gpt-5.5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": _usage_to_anthropic(response.get("usage")),
    }


def _sse_event(event_name: str, payload: dict[str, Any]) -> bytes:
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    ).encode("utf-8")


def _extract_text_from_openai_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _coerce_text(content)
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict):
            part_type = part.get("type")
            if part_type == "text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif part_type == "input_text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
        elif isinstance(part, str):
            parts.append(part)
    return "\n".join(part for part in parts if part)


def _openai_content_to_response_parts(role: str, content: Any) -> list[dict[str, Any]]:
    text_type = "output_text" if role == "assistant" else "input_text"
    if isinstance(content, str):
        return [{"type": text_type, "text": content}]
    if not isinstance(content, list):
        text = _coerce_text(content)
        return [{"type": text_type, "text": text}] if text else []

    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            text = _coerce_text(part)
            if text:
                parts.append({"type": text_type, "text": text})
            continue
        part_type = part.get("type")
        if part_type in {"text", "input_text", "output_text"} and isinstance(part.get("text"), str):
            parts.append({"type": text_type, "text": part["text"]})
        elif part_type == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if isinstance(url, str) and url:
                parts.append({"type": "input_image", "image_url": url})
    return parts


def chat_completions_to_responses(body: dict[str, Any]) -> dict[str, Any]:
    model = body.get("model")
    responses: dict[str, Any] = {
        "model": model if isinstance(model, str) and model else "gpt-5.5",
        "input": [],
        "stream": bool(body.get("stream", False)),
        "store": False,
    }

    for key in ("temperature", "top_p"):
        if key in body:
            responses[key] = body[key]
    if "max_completion_tokens" in body:
        responses["max_output_tokens"] = body["max_completion_tokens"]
    elif "max_tokens" in body:
        responses["max_output_tokens"] = body["max_tokens"]

    reasoning_effort = body.get("reasoning_effort")
    if isinstance(reasoning_effort, str) and reasoning_effort:
        responses["reasoning"] = {"effort": reasoning_effort}

    tools = body.get("tools")
    if isinstance(tools, list):
        response_tools: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            if tool.get("type") != "function":
                continue
            function = tool.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str) or not name:
                continue
            response_tools.append(
                {
                    "type": "function",
                    "name": name,
                    "description": function.get("description") if isinstance(function.get("description"), str) else "",
                    "parameters": function.get("parameters") if isinstance(function.get("parameters"), dict) else {"type": "object", "properties": {}},
                }
            )
        if response_tools:
            responses["tools"] = response_tools

    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, str):
        responses["tool_choice"] = tool_choice
    elif isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        if tool_choice.get("type") == "function" and isinstance(function, dict) and isinstance(function.get("name"), str):
            responses["tool_choice"] = {"type": "function", "name": function["name"]}

    instructions: list[str] = []
    input_items: list[dict[str, Any]] = []
    messages = body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role in {"system", "developer"}:
                text = _extract_text_from_openai_content(content)
                if text:
                    instructions.append(text)
                continue
            if role == "tool":
                tool_call_id = message.get("tool_call_id")
                if isinstance(tool_call_id, str) and tool_call_id:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call_id,
                            "output": _extract_text_from_openai_content(content),
                        }
                    )
                continue
            role_name = role if role in {"user", "assistant"} else "user"
            content_parts = _openai_content_to_response_parts(role_name, content)
            if content_parts:
                input_items.append({"role": role_name, "content": content_parts})

            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function")
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    if isinstance(name, str) and name:
                        input_items.append(
                            {
                                "type": "function_call",
                                "call_id": tool_call.get("id") if isinstance(tool_call.get("id"), str) else f"call_{uuid.uuid4().hex[:12]}",
                                "name": name,
                                "arguments": _json_arguments(function.get("arguments")),
                            }
                        )
    if instructions:
        responses["instructions"] = "\n\n".join(instructions)
    responses["input"] = input_items
    return responses


def responses_json_to_chat_completion(response: dict[str, Any], fallback_model: str | None = None) -> dict[str, Any]:
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                        content_parts.append(part["text"])
            elif item.get("type") == "function_call":
                name = item.get("name")
                if isinstance(name, str) and name:
                    tool_calls.append(
                        {
                            "id": item.get("call_id") if isinstance(item.get("call_id"), str) else item.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": item.get("arguments") if isinstance(item.get("arguments"), str) else _json_arguments(item.get("arguments")),
                            },
                        }
                    )

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
    finish_reason = "stop"
    if tool_calls:
        message["tool_calls"] = tool_calls
        finish_reason = "tool_calls"
    if response.get("status") == "incomplete":
        finish_reason = "length"

    return {
        "id": response.get("id") if isinstance(response.get("id"), str) else f"chatcmpl_{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.get("model") if isinstance(response.get("model"), str) else fallback_model or "gpt-5.5",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": _usage_to_chat_completion(response.get("usage")),
    }


def _int_usage_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    return 0


def _usage_to_chat_completion(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    prompt_tokens = _int_usage_value(usage.get("prompt_tokens"))
    completion_tokens = _int_usage_value(usage.get("completion_tokens"))
    input_tokens = _int_usage_value(usage.get("input_tokens"))
    output_tokens = _int_usage_value(usage.get("output_tokens"))
    if prompt_tokens == 0 and input_tokens:
        prompt_tokens = input_tokens
    if completion_tokens == 0 and output_tokens:
        completion_tokens = output_tokens
    total_tokens = _int_usage_value(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "input_tokens": input_tokens or prompt_tokens,
        "output_tokens": output_tokens or completion_tokens,
    }


def iter_chat_completions_sse(chunks: Any, *, completion_id: str, model: str) -> Any:
    for chunk in chunks:
        if not chunk:
            continue
        text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else str(chunk)
        if text.startswith(":"):
            yield text.encode("utf-8")
            continue
        for event_name, payload in parse_sse_blocks(text.encode("utf-8")):
            if not isinstance(payload, dict):
                continue
            if event_name == "response.output_text.delta":
                delta = payload.get("delta")
                if isinstance(delta, str) and delta:
                    yield _sse_event(
                        "chat.completion.chunk",
                        {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                        },
                    )
            elif event_name == "response.completed":
                yield _sse_event(
                    "chat.completion.chunk",
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    },
                )
                yield b"data: [DONE]\n\n"
            elif event_name in {"response.failed", "error"}:
                error = payload.get("error")
                response_obj = payload.get("response")
                if not isinstance(error, dict) and isinstance(response_obj, dict):
                    error = response_obj.get("error")
                yield _sse_event(
                    "error",
                    {
                        "error": error if isinstance(error, dict) else {"type": "api_error", "message": _coerce_text(error)},
                    },
                )


def extract_session_key(headers: Any, body: dict[str, Any]) -> str | None:
    for header_name in ("x-session-id", "x-client-request-id", "x-amp-thread-id", "anthropic-conversation-id"):
        value = headers.get(header_name)
        if isinstance(value, str) and value.strip():
            return f"{header_name}:{value.strip()}"
    user = body.get("user")
    if isinstance(user, str) and user.strip():
        return f"user:{user.strip()}"
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        for key in ("user_id", "session_id", "conversation_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return f"{key}:{value.strip()}"
    return None


def _prepend_chunk(first_chunk: bytes, chunks: Any) -> Any:
    yield first_chunk
    for chunk in chunks:
        yield chunk


def iter_anthropic_messages_sse(
    chunks: Any,
    *,
    message_id: str,
    model: str,
    metrics: BridgeStreamMetrics | None = None,
) -> Any:
    yield _sse_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )

    text_block_open = False
    text_block_index: int | None = None
    next_content_index = 0
    active_tool_blocks: dict[str, dict[str, Any]] = {}
    pending_tool_calls: dict[str, dict[str, Any]] = {}
    output_index_to_item_id: dict[int, str] = {}
    saw_tool_use = False
    stopped = False
    tool_args_mode = anthropic_tool_args_mode()
    last_tool_arg_ping_at = 0.0
    if metrics is not None:
        metrics.tool_args_mode = tool_args_mode

    def close_text_block() -> bytes | None:
        nonlocal text_block_open, text_block_index
        if not text_block_open:
            return None
        text_block_open = False
        index = text_block_index if isinstance(text_block_index, int) else 0
        text_block_index = None
        return _sse_event("content_block_stop", {"type": "content_block_stop", "index": index})

    def start_tool_block(item: dict[str, Any], payload: dict[str, Any]) -> bytes | None:
        nonlocal next_content_index, saw_tool_use
        item_id = item.get("id") or payload.get("item_id")
        call_id = item.get("call_id") or payload.get("call_id") or item_id
        name = item.get("name") or payload.get("name")
        if not isinstance(item_id, str) or not item_id:
            item_id = f"fc_{uuid.uuid4().hex[:12]}"
        if item_id in active_tool_blocks:
            return None
        if not isinstance(call_id, str) or not call_id:
            call_id = item_id
        if not isinstance(name, str) or not name:
            name = "unknown_tool"
        output_index = payload.get("output_index")
        if isinstance(output_index, int):
            output_index_to_item_id[output_index] = item_id
        index = next_content_index
        next_content_index += 1
        active_tool_blocks[item_id] = {
            "index": index,
            "id": call_id,
            "name": name,
            "delta_seen": False,
            "closed": False,
        }
        saw_tool_use = True
        return _sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": {},
                },
            },
        )

    def remember_tool_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        item = payload.get("item")
        if not isinstance(item, dict):
            item = {"id": payload.get("item_id"), "call_id": payload.get("call_id"), "name": payload.get("name")}
        item_id = tool_item_id(payload)
        if not item_id:
            item_id = item.get("id") if isinstance(item.get("id"), str) and item.get("id") else f"fc_{uuid.uuid4().hex[:12]}"
            item["id"] = item_id
        output_index = payload.get("output_index")
        if isinstance(output_index, int):
            output_index_to_item_id[output_index] = item_id
        pending = pending_tool_calls.setdefault(item_id, {"item": item, "parts": [], "emitted": False})
        if isinstance(item, dict):
            existing = pending.get("item", {})
            pending["item"] = {
                **(existing if isinstance(existing, dict) else {}),
                **{key: value for key, value in item.items() if value is not None},
            }
        return item_id, pending

    def ensure_pending_tool_block(payload: dict[str, Any]) -> tuple[str, dict[str, Any], list[bytes]]:
        item_id, pending = remember_tool_call(payload)
        item = pending.get("item")
        if not isinstance(item, dict):
            item = {"id": item_id}
        item = dict(item)
        item.setdefault("id", item_id)
        chunks_out: list[bytes] = []
        started = start_tool_block(item, payload)
        if started:
            chunks_out.append(started)
        return item_id, pending, chunks_out

    def emit_tool_call(item_id: str, pending: dict[str, Any], payload: dict[str, Any] | None = None) -> list[bytes]:
        if pending.get("emitted"):
            return []
        pending["emitted"] = True
        payload = payload or {}
        item = pending.get("item")
        if not isinstance(item, dict):
            item = {"id": item_id}
        item = dict(item)
        item.setdefault("id", item_id)
        chunks_out: list[bytes] = []
        started = start_tool_block(item, payload)
        if started:
            chunks_out.append(started)
        block = active_tool_blocks.get(item_id)
        if not block:
            return chunks_out
        arguments = payload.get("arguments")
        payload_item = payload.get("item")
        if not isinstance(arguments, str) and isinstance(payload_item, dict):
            arguments = payload_item.get("arguments")
        if not isinstance(arguments, str):
            parts = pending.get("parts")
            arguments = "".join(part for part in parts if isinstance(part, str)) if isinstance(parts, list) else ""
        if not arguments:
            arguments = "{}"
        block["delta_seen"] = True
        if metrics is not None:
            metrics.tool_arg_coalesced_calls += 1
        chunks_out.append(
            _sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block["index"],
                    "delta": {"type": "input_json_delta", "partial_json": arguments},
                },
            )
        )
        stopped_tool = close_tool_block(item_id)
        if stopped_tool:
            chunks_out.append(stopped_tool)
        return chunks_out

    def maybe_tool_arg_ping() -> bytes | None:
        nonlocal last_tool_arg_ping_at
        interval = anthropic_tool_arg_ping_seconds()
        if interval <= 0:
            if metrics is not None:
                metrics.tool_arg_ping_events += 1
            return _sse_event("ping", {"type": "ping"})
        now = time.monotonic()
        if last_tool_arg_ping_at <= 0 or now - last_tool_arg_ping_at >= interval:
            last_tool_arg_ping_at = now
            if metrics is not None:
                metrics.tool_arg_ping_events += 1
            return _sse_event("ping", {"type": "ping"})
        return None

    def tool_item_id(payload: dict[str, Any]) -> str | None:
        item_id = payload.get("item_id")
        if isinstance(item_id, str) and item_id:
            return item_id
        output_index = payload.get("output_index")
        if isinstance(output_index, int):
            mapped = output_index_to_item_id.get(output_index)
            if mapped:
                return mapped
        item = payload.get("item")
        if isinstance(item, dict):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                return item_id
        return None

    def ensure_tool_block(payload: dict[str, Any]) -> tuple[str, list[bytes]]:
        item = payload.get("item")
        if not isinstance(item, dict):
            item = {"id": payload.get("item_id"), "call_id": payload.get("call_id"), "name": payload.get("name")}
        item_id = tool_item_id(payload)
        if not item_id:
            item_id = f"fc_{uuid.uuid4().hex[:12]}"
            item["id"] = item_id
        chunks_out: list[bytes] = []
        started = start_tool_block(item, payload)
        if started:
            chunks_out.append(started)
        return item_id, chunks_out

    def close_tool_block(item_id: str | None) -> bytes | None:
        if not item_id:
            return None
        block = active_tool_blocks.get(item_id)
        if not block or block.get("closed"):
            return None
        block["closed"] = True
        return _sse_event("content_block_stop", {"type": "content_block_stop", "index": block["index"]})
    for chunk in chunks:
        if not chunk:
            continue
        text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else str(chunk)
        if text.startswith(":"):
            yield text.encode("utf-8")
            continue
        for event_name, payload in parse_sse_blocks(text.encode("utf-8")):
            if not isinstance(payload, dict):
                continue
            if event_name == "response.output_text.delta":
                nonlocal_text_index = text_block_index
                delta = payload.get("delta")
                if not isinstance(delta, str) or not delta:
                    continue
                if not text_block_open:
                    text_block_open = True
                    index = next_content_index
                    next_content_index += 1
                    text_block_index = index
                    yield _sse_event(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": {"type": "text", "text": ""},
                        },
                    )
                    nonlocal_text_index = index
                text_index = text_block_index if isinstance(text_block_index, int) else nonlocal_text_index
                if not isinstance(text_index, int):
                    text_index = 0
                yield _sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": text_index,
                        "delta": {"type": "text_delta", "text": delta},
                    },
                )
            elif event_name == "response.output_item.added":
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") == "function_call":
                    closing = close_text_block()
                    if closing:
                        yield closing
                    if tool_args_mode == "stream":
                        started = start_tool_block(item, payload)
                        if started:
                            yield started
                    else:
                        _item_id, _pending, started_chunks = ensure_pending_tool_block(payload)
                        for started in started_chunks:
                            yield started
            elif event_name == "response.function_call_arguments.delta":
                delta = payload.get("delta")
                if not isinstance(delta, str) or not delta:
                    continue
                if tool_args_mode == "coalesce":
                    _item_id, pending, started_chunks = ensure_pending_tool_block(payload)
                    for started in started_chunks:
                        yield started
                    parts = pending.setdefault("parts", [])
                    if isinstance(parts, list):
                        parts.append(delta)
                    ping = maybe_tool_arg_ping()
                    if ping:
                        yield ping
                    continue
                item_id, started_chunks = ensure_tool_block(payload)
                for started in started_chunks:
                    yield started
                block = active_tool_blocks.get(item_id)
                if not block:
                    continue
                block["delta_seen"] = True
                yield _sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block["index"],
                        "delta": {"type": "input_json_delta", "partial_json": delta},
                    },
                )
            elif event_name in {"response.function_call_arguments.done", "response.output_item.done"}:
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") != "function_call":
                    continue
                if tool_args_mode == "coalesce":
                    item_id, pending = remember_tool_call(payload)
                    for emitted in emit_tool_call(item_id, pending, payload):
                        yield emitted
                    continue
                item_id, started_chunks = ensure_tool_block(payload)
                for started in started_chunks:
                    yield started
                block = active_tool_blocks.get(item_id)
                if not block:
                    continue
                arguments = payload.get("arguments")
                if not isinstance(arguments, str) and isinstance(item, dict):
                    arguments = item.get("arguments")
                if isinstance(arguments, str) and arguments and not block.get("delta_seen"):
                    block["delta_seen"] = True
                    yield _sse_event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block["index"],
                            "delta": {"type": "input_json_delta", "partial_json": arguments},
                        },
                    )
                stopped_tool = close_tool_block(item_id)
                if stopped_tool:
                    yield stopped_tool
            elif event_name == "response.completed":
                closing = close_text_block()
                if closing:
                    yield closing
                if tool_args_mode == "coalesce":
                    for item_id, pending in list(pending_tool_calls.items()):
                        for emitted in emit_tool_call(item_id, pending, {"item_id": item_id}):
                            yield emitted
                for item_id in list(active_tool_blocks):
                    stopped_tool = close_tool_block(item_id)
                    if stopped_tool:
                        yield stopped_tool
                response_obj = payload.get("response")
                usage = _usage_to_anthropic(response_obj.get("usage") if isinstance(response_obj, dict) else None)
                yield _sse_event(
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "tool_use" if saw_tool_use else "end_turn", "stop_sequence": None},
                        "usage": {"output_tokens": usage["output_tokens"]},
                    },
                )
                yield _sse_event("message_stop", {"type": "message_stop"})
                stopped = True
            elif event_name in {"response.failed", "error"}:
                closing = close_text_block()
                if closing:
                    yield closing
                for item_id in list(active_tool_blocks):
                    stopped_tool = close_tool_block(item_id)
                    if stopped_tool:
                        yield stopped_tool
                error = payload.get("error")
                response_obj = payload.get("response")
                if not isinstance(error, dict) and isinstance(response_obj, dict):
                    error = response_obj.get("error")
                yield _sse_event(
                    "error",
                    {
                        "type": "error",
                        "error": error if isinstance(error, dict) else {"type": "api_error", "message": _coerce_text(error)},
                    },
                )
                stopped = True
    if not stopped:
        closing = close_text_block()
        if closing:
            yield closing
        if tool_args_mode == "coalesce":
            for item_id, pending in list(pending_tool_calls.items()):
                for emitted in emit_tool_call(item_id, pending, {"item_id": item_id}):
                    yield emitted
        for item_id in list(active_tool_blocks):
            stopped_tool = close_tool_block(item_id)
            if stopped_tool:
                yield stopped_tool
        yield _sse_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use" if saw_tool_use else "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 0},
            },
        )
        yield _sse_event("message_stop", {"type": "message_stop"})


class CodexBridgeHandler(BaseHTTPRequestHandler):
    server_version = "CodexBridge/0.1"
    protocol_version = "HTTP/1.1"

    def _resolve_account_route(self) -> tuple[str | None, str]:
        target_path = urllib.parse.urlsplit(self.path).path
        match = ACCOUNT_ROUTE_RE.match(target_path)
        if not match:
            return None, target_path
        account_id = match.group(1)
        suffix = match.group(2) or "/"
        return account_id, suffix

    def _usage_context(
        self,
        *,
        request_type: str,
        route_path: str,
        original_body: dict[str, Any],
        actual_model: str | None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        requested_model = original_body.get("model") if isinstance(original_body.get("model"), str) else actual_model
        requested_model_id = normalize_bridge_model_id(requested_model)
        desktop_route = requested_model_id in claude_desktop_model_route_map()
        user_agent = str(self.headers.get("User-Agent") or "").lower()
        if desktop_route:
            client_label = "Claude Desktop 3P"
        elif request_type == "messages":
            client_label = "Claude Code / Anthropic"
        elif request_type == "chat.completions":
            client_label = "Hermes / OpenAI Chat" if "hermes" in user_agent else "OpenAI Chat"
        elif request_type == "responses":
            client_label = "Codex / OpenAI Responses" if "codex" in user_agent else "OpenAI Responses"
        else:
            client_label = request_type
        client_address = getattr(self, "client_address", None)
        client_port = client_address[1] if isinstance(client_address, tuple) and len(client_address) > 1 else 0
        return {
            "requested_model": requested_model or "",
            "actual_model": actual_model or "",
            "route_path": route_path,
            "bridge_port": int(getattr(self.server, "server_port", 0) or 0),
            "client_port": int(client_port or 0),
            "client_label": client_label,
            "desktop_route": desktop_route,
            "session_id": session_key or "",
            "prompt_cache_key_present": False,
            "cache_key_source": "none",
        }

    def do_GET(self) -> None:
        route_account_id, route_path = self._resolve_account_route()
        if route_path == "/health":
            payload = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self._write_bytes(payload)
            return
        if route_path in MODELS_PATHS:
            self._write_json_payload(200, build_models_payload())
            return
        if route_path == "/quota":
            try:
                requested_account_id = route_account_id or self.headers.get("x-account-id")
                account_id, access_token = self.server.auth_store.get_access_token(requested_account_id)
                upstream_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "ChatGPT-Account-Id": account_id,
                    "Accept": "application/json",
                    "User-Agent": CODEX_USER_AGENT,
                }
                with build_upstream_http_client(timeout=30.0) as client:
                    response = client.get(
                        f"{UPSTREAM_BASE_URL}/usage",
                        headers=upstream_headers,
                    )
                payload = response.content
                log_upstream_result("quota", account_id, response.is_success, status_code=response.status_code)
                if not response.is_success:
                    log_upstream_diagnostic(
                        "quota",
                        account_id,
                        status_code=response.status_code,
                        route_path=route_path,
                        response_headers=response.headers,
                        error_detail=payload.decode("utf-8", "replace"),
                    )
                self.send_response(response.status_code)
                self.send_header(
                    "Content-Type",
                    response.headers.get("content-type", "application/json"),
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self._write_bytes(payload)
            except httpx.HTTPStatusError as exc:
                log_upstream_result(
                    "quota",
                    route_account_id,
                    False,
                    status_code=exc.response.status_code,
                    detail=exc.response.text,
                )
                self._write_json_error(exc.response.status_code, exc.response.text)
            except Exception as exc:  # noqa: BLE001
                detail = upstream_exception_detail(exc)
                log_upstream_result("quota", route_account_id, False, detail=detail)
                self._write_json_error(500, detail)
            return
        self.send_error(404, "Not Found")

    def _send_upstream_headers(
        self,
        response: httpx.Response,
        *,
        is_stream: bool,
        content_length: int | None = None,
    ) -> None:
        self.send_response(response.status_code)
        passthrough_headers = [
            "content-type",
            "cache-control",
            "x-request-id",
            "openai-processing-ms",
        ]
        for key in passthrough_headers:
            value = response.headers.get(key)
            if value:
                if key == "content-type" and not is_stream:
                    continue
                self.send_header(key, value)
        if not is_stream:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.send_header("Connection", "close")
        self.end_headers()

    def do_POST(self) -> None:
        route_account_id, route_path = self._resolve_account_route()
        if route_path in RESPONSES_PATHS:
            self._handle_responses(route_account_id, route_path)
            return
        if route_path in MESSAGES_PATHS:
            self._handle_messages(route_account_id, route_path)
            return
        if route_path in CHAT_COMPLETIONS_PATHS:
            self._handle_chat_completions(route_account_id, route_path)
            return
        self.send_error(404, "Not Found")

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_REQUEST_BODY_BYTES:
            raise ValueError(
                f"request body too large: {content_length} bytes exceeds {MAX_REQUEST_BODY_BYTES}"
            )
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        decoded_body = decode_request_body(raw_body, self.headers.get("Content-Encoding"))
        decoded = json.loads(decoded_body.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("request body must be a JSON object")
        return decoded

    def _write_json_payload(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._write_bytes(body, flush=True)

    def _build_upstream_headers(self, account_id: str, access_token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
            "Content-Type": "application/json",
            "Accept": self.headers.get("Accept", "application/json"),
            "User-Agent": CODEX_USER_AGENT,
            "Originator": "cc-switch-local-bridge",
        }
        if self.headers.get("anthropic-beta"):
            headers["anthropic-beta"] = self.headers["anthropic-beta"]
        return headers

    def _account_candidates(self, requested_account_id: str | None, body: dict[str, Any]) -> tuple[list[str], str | None]:
        session_key = extract_session_key(self.headers, body)
        return self.server.auth_store.account_candidates(requested_account_id, session_key), session_key

    def _is_passthrough_request(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return bool(
            auth
            and auth != "Bearer local-bridge"
            and not auth.startswith("Bearer sk-bridgedeck-")
        )

    def _is_api_key_request(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return bool(auth and auth.startswith("Bearer sk-bridgedeck-"))

    def _validate_api_key(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth or not auth.startswith("Bearer sk-bridgedeck-"):
            return False
        key = auth[7:]
        try:
            raw = DEFAULT_API_KEYS_PATH.read_text(encoding="utf-8")
            keys = json.loads(raw)
            if not isinstance(keys, dict):
                return False
            entry = keys.get(key)
            return bool(entry and not entry.get("revoked"))
        except Exception:
            return False

    def _build_passthrough_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": self.headers["Authorization"],
            "Content-Type": "application/json",
            "Accept": self.headers.get("Accept", "application/json"),
        }
        if self.headers.get("User-Agent"):
            headers["User-Agent"] = self.headers["User-Agent"]
        if self.headers.get("anthropic-beta"):
            headers["anthropic-beta"] = self.headers["anthropic-beta"]
        return headers

    def _handle_responses(self, route_account_id: str | None, route_path: str) -> None:
        request_id = bridge_request_id()
        try:
            request_body = self._read_json_body()
            request_body, strip_result = strip_claude_attribution_from_request(
                request_body,
                request_type="responses",
                provider_kind="proxy",
            )
            log_claude_attribution_strip(
                account_id=route_account_id or self.headers.get("chatgpt-account-id"),
                route_path=route_path,
                result=strip_result,
            )
            requested_stream = bool(request_body.get("stream", False))
            requested_account_id = route_account_id or self.headers.get("chatgpt-account-id")
            candidate_account_ids, session_key = self._account_candidates(requested_account_id, request_body)
            requested_effort = extract_reasoning_effort(request_body)
            normalized_body = normalize_request_body(request_body)
            requested_model = (
                normalized_body.get("model")
                if isinstance(normalized_body.get("model"), str)
                else None
            )
            actual_effort = extract_reasoning_effort(normalized_body)
            self._forward_responses_body(
                candidate_account_ids=candidate_account_ids,
                session_key=session_key,
                route_path=route_path,
                request_id=request_id,
                request_type="responses",
                original_body=request_body,
                normalized_body=normalized_body,
                is_stream=requested_stream,
                requested_model=requested_model,
                requested_effort=requested_effort,
                actual_effort=actual_effort,
                output_format="responses",
            )
        except httpx.HTTPStatusError as exc:
            self._write_json_error(exc.response.status_code, exc.response.text)
        except Exception as exc:  # noqa: BLE001
            log_upstream_result(
                "responses",
                route_account_id or "default",
                False,
                detail=f"request_id={request_id} {upstream_exception_detail(exc)}",
            )
            self._write_json_error(500, upstream_exception_detail(exc))

    def _handle_messages(self, route_account_id: str | None, route_path: str) -> None:
        request_id = bridge_request_id()
        try:
            request_body = self._read_json_body()
            request_body, strip_result = strip_claude_attribution_from_request(
                request_body,
                request_type="messages",
                provider_kind="proxy",
            )
            log_claude_attribution_strip(
                account_id=route_account_id or self.headers.get("chatgpt-account-id"),
                route_path=route_path,
                result=strip_result,
            )
            requested_account_id = route_account_id or self.headers.get("chatgpt-account-id")
            candidate_account_ids, session_key = self._account_candidates(requested_account_id, request_body)
            responses_body = anthropic_messages_to_responses(request_body)
            requested_effort = extract_reasoning_effort(responses_body)
            normalized_body = normalize_request_body(responses_body)
            is_stream = bool(request_body.get("stream", False))
            requested_model = (
                normalized_body.get("model")
                if isinstance(normalized_body.get("model"), str)
                else None
            )
            actual_effort = extract_reasoning_effort(normalized_body)
            self._forward_responses_body(
                candidate_account_ids=candidate_account_ids,
                session_key=session_key,
                route_path=route_path,
                request_id=request_id,
                request_type="messages",
                original_body=request_body,
                normalized_body=normalized_body,
                is_stream=is_stream,
                requested_model=requested_model,
                requested_effort=requested_effort,
                actual_effort=actual_effort,
                output_format="messages",
            )
        except httpx.HTTPStatusError as exc:
            self._write_json_error(exc.response.status_code, exc.response.text)
        except Exception as exc:  # noqa: BLE001
            log_upstream_result(
                "messages",
                route_account_id or "default",
                False,
                detail=f"request_id={request_id} {upstream_exception_detail(exc)}",
            )
            self._write_json_error(500, upstream_exception_detail(exc))

    def _handle_chat_completions(self, route_account_id: str | None, route_path: str) -> None:
        request_id = bridge_request_id()
        try:
            request_body = self._read_json_body()
            request_body, strip_result = strip_claude_attribution_from_request(
                request_body,
                request_type="chat.completions",
                provider_kind="proxy",
            )
            log_claude_attribution_strip(
                account_id=route_account_id or self.headers.get("chatgpt-account-id"),
                route_path=route_path,
                result=strip_result,
            )
            requested_account_id = route_account_id or self.headers.get("chatgpt-account-id")
            candidate_account_ids, session_key = self._account_candidates(requested_account_id, request_body)
            responses_body = chat_completions_to_responses(request_body)
            requested_effort = extract_reasoning_effort(responses_body)
            normalized_body = normalize_request_body(responses_body)
            is_stream = bool(request_body.get("stream", False))
            requested_model = (
                normalized_body.get("model")
                if isinstance(normalized_body.get("model"), str)
                else None
            )
            actual_effort = extract_reasoning_effort(normalized_body)
            self._forward_responses_body(
                candidate_account_ids=candidate_account_ids,
                session_key=session_key,
                route_path=route_path,
                request_id=request_id,
                request_type="chat.completions",
                original_body=request_body,
                normalized_body=normalized_body,
                is_stream=is_stream,
                requested_model=requested_model,
                requested_effort=requested_effort,
                actual_effort=actual_effort,
                output_format="chat",
            )
        except httpx.HTTPStatusError as exc:
            self._write_json_error(exc.response.status_code, exc.response.text)
        except Exception as exc:  # noqa: BLE001
            log_upstream_result(
                "chat.completions",
                route_account_id or "default",
                False,
                detail=f"request_id={request_id} {upstream_exception_detail(exc)}",
            )
            self._write_json_error(500, upstream_exception_detail(exc))

    def _forward_responses_body(
        self,
        *,
        candidate_account_ids: list[str],
        session_key: str | None,
        route_path: str,
        request_id: str,
        request_type: str,
        original_body: dict[str, Any],
        normalized_body: dict[str, Any],
        is_stream: bool,
        requested_model: str | None,
        requested_effort: str | None,
        output_format: str,
        actual_effort: str | None = None,
    ) -> None:
        upstream_url = f"{UPSTREAM_BASE_URL}/responses"
        max_attempts = stream_max_retries() + 1 if is_stream else 1
        started_at = time.monotonic()
        usage_context = self._usage_context(
            request_type=request_type,
            route_path=route_path,
            original_body=original_body,
            actual_model=requested_model,
            session_key=session_key,
        )
        upstream_body, cache_context = prepare_upstream_responses_body(
            normalized_body,
            session_key=session_key,
        )
        usage_context.update(cache_context)

        if self._is_passthrough_request():
            upstream_headers = self._build_passthrough_headers()
            try:
                with build_upstream_http_client(timeout=600.0) as client, client.stream(
                    "POST",
                    upstream_url,
                    headers=upstream_headers,
                    json=upstream_body,
                ) as response:
                    log_upstream_result(
                        request_type,
                        "passthrough",
                        response.is_success,
                        status_code=response.status_code,
                        detail=None if response.is_success else response.read().decode("utf-8", "replace"),
                    )
                    if not response.is_success:
                        error_body = response.read()
                        self._send_upstream_headers(response, is_stream=False, content_length=len(error_body))
                        self._write_bytes(error_body, flush=True)
                        return
                    if is_stream:
                        self._send_upstream_headers(response, is_stream=True)
                        for chunk in response.iter_bytes():
                            self._write_bytes(chunk)
                    else:
                        body = response.read()
                        self._send_upstream_headers(response, is_stream=False, content_length=len(body))
                        self._write_bytes(body, flush=True)
            except Exception as exc:
                log_upstream_result(request_type, "passthrough", False, detail=str(exc))
                self._write_json_error(500, upstream_exception_detail(exc))
            return

        for account_index, candidate_account_id in enumerate(candidate_account_ids):
            account_id, access_token = self.server.auth_store.get_access_token(candidate_account_id)
            upstream_headers = self._build_upstream_headers(account_id, access_token)
            has_next_account = account_index < len(candidate_account_ids) - 1
            for attempt in range(1, max_attempts + 1):
                try:
                    with build_upstream_http_client(timeout=600.0) as client, client.stream(
                        "POST",
                        upstream_url,
                        headers=upstream_headers,
                        json=upstream_body,
                    ) as response:
                        error_body = response.read() if not response.is_success else None
                        log_upstream_result(
                            request_type,
                            account_id,
                            response.is_success,
                            status_code=response.status_code,
                            detail=None
                            if response.is_success
                            else error_body.decode("utf-8", "replace") if error_body is not None else None,
                        )
                        if not response.is_success:
                            log_upstream_diagnostic(
                                request_type,
                                account_id,
                                status_code=response.status_code,
                                route_path=route_path,
                                response_headers=response.headers,
                                request_shape=summarize_request_shape(original_body),
                                normalized_shape=summarize_request_shape(normalized_body),
                                error_detail=error_body.decode("utf-8", "replace") if error_body is not None else None,
                            )
                            if is_retryable_http_status(response.status_code):
                                if is_stream and attempt < max_attempts:
                                    log_bridge_stream_retry(
                                        request_id=request_id,
                                        account_id=account_id,
                                        requested_model=requested_model,
                                        attempt=attempt,
                                        max_attempts=max_attempts,
                                        reason=f"HTTP {response.status_code}",
                                    )
                                    continue
                                if has_next_account:
                                    print(
                                        f"{log_timestamp()} [bridge-account-failover] request_id={request_id} from_account={account_id} reason=HTTP {response.status_code}",
                                        file=sys.stderr,
                                    )
                                    break
                            body = error_body if error_body is not None else b""
                            self._send_upstream_headers(response, is_stream=is_stream, content_length=len(body))
                            self._write_bytes(body, flush=True)
                            return

                        upstream_request_id = response.headers.get("x-request-id")

                        if not is_stream:
                            body = response.read()
                            response_body = json.loads(
                                build_non_stream_json_from_sse(body, requested_model).decode("utf-8")
                            )
                            record_bridge_usage(
                                account_id=account_id,
                                model=requested_model,
                                requested_model=usage_context.get("requested_model"),
                                request_type=request_type,
                                request_id=request_id,
                                usage=response_body.get("usage") if isinstance(response_body, dict) else None,
                                duration_ms=int((time.monotonic() - started_at) * 1000),
                                status_code=response.status_code,
                                source="proxy",
                                route_path=route_path,
                                bridge_port=usage_context.get("bridge_port"),
                                client_port=usage_context.get("client_port"),
                                client_label=str(usage_context.get("client_label") or ""),
                                desktop_route=bool(usage_context.get("desktop_route")),
                                session_id=str(usage_context.get("session_id") or ""),
                                prompt_cache_key_present=bool(usage_context.get("prompt_cache_key_present")),
                                cache_key_source=str(usage_context.get("cache_key_source") or ""),
                            )
                            if output_format == "messages":
                                response_body = responses_json_to_anthropic_message(response_body, requested_model)
                            elif output_format == "chat":
                                response_body = responses_json_to_chat_completion(response_body, requested_model)
                            payload = json.dumps(response_body, ensure_ascii=False).encode("utf-8")
                            self.server.auth_store.bind_session(session_key, account_id)
                            self._send_upstream_headers(response, is_stream=False, content_length=len(payload))
                            self._write_bytes(payload, flush=True)
                            return

                        metrics = BridgeStreamMetrics()
                        response_chunks = self._iter_stream_with_reasoning_placeholder(
                            response,
                            account_id,
                            request_id=request_id,
                            started_at=started_at,
                            requested_effort=requested_effort,
                            actual_effort=actual_effort,
                            requested_model=requested_model,
                            upstream_request_id=upstream_request_id,
                            metrics=metrics,
                            usage_context=usage_context,
                        )
                        chunks: Any = iter(())
                        try:
                            if output_format == "messages":
                                first_response_chunk = next(response_chunks)
                                chunks = iter_anthropic_messages_sse(
                                    _prepend_chunk(first_response_chunk, response_chunks),
                                    message_id=f"msg_{request_id}",
                                    model=requested_model or "gpt-5.5",
                                    metrics=metrics,
                                )
                            elif output_format == "chat":
                                first_response_chunk = next(response_chunks)
                                chunks = iter_chat_completions_sse(
                                    _prepend_chunk(first_response_chunk, response_chunks),
                                    completion_id=f"chatcmpl_{request_id}",
                                    model=requested_model or "gpt-5.5",
                                )
                            else:
                                chunks = response_chunks
                            first_chunk = next(chunks)
                        except StopIteration:
                            first_chunk = b""
                        except RetryableStreamBootstrapError as exc:
                            if attempt < max_attempts:
                                log_bridge_stream_retry(
                                    request_id=request_id,
                                    account_id=account_id,
                                    requested_model=requested_model,
                                    attempt=attempt,
                                    max_attempts=max_attempts,
                                    reason=str(exc),
                                )
                                continue
                            if has_next_account:
                                print(
                                    f"{log_timestamp()} [bridge-account-failover] request_id={request_id} from_account={account_id} reason={type(exc).__name__}",
                                    file=sys.stderr,
                                )
                                break
                            raise

                        if output_format == "messages":
                            self.send_response(response.status_code)
                            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                            self.send_header("Cache-Control", "no-cache")
                            self.send_header("Connection", "close")
                            self.end_headers()
                        elif output_format == "chat":
                            self.send_response(response.status_code)
                            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                            self.send_header("Cache-Control", "no-cache")
                            self.send_header("Connection", "close")
                            self.end_headers()
                        else:
                            self._send_upstream_headers(response, is_stream=True)

                        self.server.auth_store.bind_session(session_key, account_id)
                        try:
                            if first_chunk:
                                if not self._write_bytes(first_chunk, flush=True):
                                    metrics.client_disconnected = True
                                    log_bridge_client_disconnect(
                                        account_id=account_id,
                                        requested_model=requested_model,
                                        request_id=request_id,
                                        started_at=started_at,
                                        detail="write_failed",
                                        upstream_request_id=upstream_request_id,
                                    )
                                    return
                                metrics.downstream_writes += 1
                            for chunk in chunks:
                                if chunk and not self._write_bytes(chunk, flush=True):
                                    metrics.client_disconnected = True
                                    log_bridge_client_disconnect(
                                        account_id=account_id,
                                        requested_model=requested_model,
                                        request_id=request_id,
                                        started_at=started_at,
                                        detail="write_failed",
                                        upstream_request_id=upstream_request_id,
                                    )
                                    break
                                if chunk:
                                    metrics.downstream_writes += 1
                        except OSError as exc:
                            metrics.client_disconnected = True
                            log_bridge_client_disconnect(
                                account_id=account_id,
                                requested_model=requested_model,
                                request_id=request_id,
                                started_at=started_at,
                                detail=f"{type(exc).__name__}: {truncate_log_text(str(exc))}",
                                upstream_request_id=upstream_request_id,
                            )
                        return
                except Exception as exc:
                    if is_stream and (isinstance(exc, BridgeStreamRetryableError) or is_retryable_stream_exception(exc)):
                        if attempt < max_attempts:
                            log_bridge_stream_retry(
                                request_id=request_id,
                                account_id=account_id,
                                requested_model=requested_model,
                                attempt=attempt,
                                max_attempts=max_attempts,
                                reason=f"{type(exc).__name__}: {exc}",
                            )
                            continue
                        if has_next_account:
                            print(
                                f"{log_timestamp()} [bridge-account-failover] request_id={request_id} from_account={account_id} reason={type(exc).__name__}",
                                file=sys.stderr,
                            )
                            break
                    raise

    def _iter_stream_with_reasoning_placeholder(
        self,
        response: httpx.Response,
        account_id: str,
        *,
        request_id: str | None = None,
        started_at: float | None = None,
        requested_effort: str | None = None,
        actual_effort: str | None = None,
        requested_model: str | None = None,
        upstream_request_id: str | None = None,
        metrics: BridgeStreamMetrics | None = None,
        usage_context: dict[str, Any] | None = None,
    ):
        def idle_limit_seconds() -> tuple[float, str]:
            if state.active or state.saw_text_delta or committed or metrics.upstream_events > 0:
                return STREAM_IDLE_PARTIAL_FAIL_SECS, "partial"
            return STREAM_IDLE_FAIL_SECS, "bootstrap"

        block_queue: queue.Queue[list[str] | BaseException | object] = queue.Queue(maxsize=16)
        done_marker = object()
        stream_request_id = request_id or bridge_request_id()
        stream_started_at = started_at if started_at is not None else time.monotonic()
        stop_reader = threading.Event()

        def put_queued(item: list[str] | BaseException | object) -> None:
            while not stop_reader.is_set():
                try:
                    block_queue.put(item, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def read_blocks() -> None:
            block_lines: list[str] = []
            try:
                for raw_line in response.iter_lines():
                    if stop_reader.is_set():
                        break
                    if isinstance(raw_line, bytes):
                        line = raw_line.decode("utf-8", "replace")
                    else:
                        line = raw_line
                    if line == "":
                        if block_lines:
                            put_queued(block_lines)
                            block_lines = []
                        continue
                    block_lines.append(line)
                if block_lines:
                    put_queued(block_lines)
            except BaseException as exc:  # noqa: BLE001
                put_queued(exc)
            finally:
                put_queued(done_marker)

        reader = threading.Thread(target=read_blocks, daemon=True)
        reader.start()
        state = ReasoningPlaceholderState()
        metrics = metrics or BridgeStreamMetrics()
        committed = False
        pending_chunks: list[bytes] = []
        usage_recorded = False
        last_state_recorded_at = 0.0

        def active_stream_payload(status: str) -> dict[str, Any]:
            guard_secs = stream_tool_call_guard_seconds()
            elapsed = time.monotonic() - stream_started_at
            return {
                "account_id": account_id,
                "client_disconnected": bool(metrics.client_disconnected),
                "downstream_writes": metrics.downstream_writes,
                "duration_s": round(elapsed, 3),
                "actual_effort": actual_effort or requested_effort or "unknown",
                "effort": actual_effort or requested_effort or "unknown",
                "first_visible_after_ms": metrics.first_visible_after_ms,
                "guard_mode": stream_tool_call_guard_mode(),
                "guard_seconds": int(guard_secs) if guard_secs else 0,
                "last_event_name": metrics.last_event_name,
                "model": requested_model or "unknown",
                "reasoning_events": metrics.reasoning_events,
                "requested_effort": requested_effort or "unknown",
                "request_id": stream_request_id,
                "started_at": int(time.time() - elapsed),
                "status": status,
                "terminal_event_seen": bool(metrics.terminal_event_seen),
                "tool_arg_buffer_chars": metrics.tool_arg_buffer_chars,
                "tool_arg_coalesced_calls": metrics.tool_arg_coalesced_calls,
                "tool_arg_delta_events": metrics.tool_arg_delta_events,
                "tool_arg_ping_events": metrics.tool_arg_ping_events,
                "tool_args_mode": metrics.tool_args_mode or anthropic_tool_args_mode(),
                "tool_events": metrics.tool_events,
                "upstream_events": metrics.upstream_events,
                "visible_text_chars": metrics.visible_text_chars,
                "visible_text_events": metrics.visible_text_events,
            }

        def maybe_record_active_stream(status: str, *, force: bool = False) -> None:
            nonlocal last_state_recorded_at
            now = time.monotonic()
            if force or STREAM_STATE_UPDATE_SECS <= 0 or now - last_state_recorded_at >= STREAM_STATE_UPDATE_SECS:
                last_state_recorded_at = now
                record_bridge_active_stream(active_stream_payload(status))

        maybe_record_active_stream("open", force=True)

        try:
            while True:
                timeout = self._reasoning_placeholder_timeout(state)
                poll_timeout = timeout if timeout is not None else STREAM_IDLE_LOG_SECS
                idle_fail_secs, idle_phase = idle_limit_seconds()
                if idle_fail_secs > 0:
                    now = time.monotonic()
                    idle_for = now - (state.last_upstream_at or stream_started_at)
                    idle_fail_remaining = max(idle_fail_secs - idle_for, 0.001)
                    poll_timeout = min(poll_timeout, idle_fail_remaining)
                try:
                    queued = block_queue.get(timeout=poll_timeout)
                except queue.Empty:
                    now = time.monotonic()
                    idle_for = now - (state.last_upstream_at or stream_started_at)
                    idle_fail_secs, idle_phase = idle_limit_seconds()
                    if idle_fail_secs > 0 and idle_for >= idle_fail_secs:
                        metrics.idle_timeout_seen = True
                        state.completed = True
                        state.active = False
                        exc = BridgeStreamIdleTimeout(
                            f"bridge stream idle timeout request_id={stream_request_id} phase={idle_phase} idle_s={idle_for:.1f} limit_s={idle_fail_secs:.1f} model={requested_model or 'unknown'}"
                        )
                        log_bridge_stream_error(
                            account_id=account_id,
                            requested_model=requested_model,
                            request_id=stream_request_id,
                            started_at=stream_started_at,
                            exc=exc,
                            upstream_request_id=upstream_request_id,
                        )
                        yield response_failed_sse(
                            request_id=stream_request_id,
                            requested_model=requested_model,
                            exc=exc,
                            error_code="bridge_stream_idle_timeout",
                            error_type="bridge_stream_idle_timeout",
                        )
                        break
                    if idle_for >= STREAM_IDLE_LOG_SECS and now - state.last_idle_logged_at >= STREAM_IDLE_LOG_SECS:
                        state.last_idle_logged_at = now
                        print(
                            f"{log_timestamp()} [bridge-stream-idle] request_id={stream_request_id} account_id={account_id} model={requested_model or 'unknown'} requested_effort={requested_effort or 'unknown'} actual_effort={actual_effort or requested_effort or 'unknown'} phase={idle_phase} idle_s={idle_for:.1f} limit_s={idle_fail_secs:.1f} active_reasoning={str(state.active).lower()} upstream_events={metrics.upstream_events} heartbeats={state.emitted_count}",
                            file=sys.stderr,
                        )
                    heartbeat = self._build_reasoning_placeholder_sse(
                        account_id,
                        state,
                        requested_effort=requested_effort,
                        requested_model=requested_model,
                        source="heartbeat",
                    )
                    if heartbeat:
                        if reasoning_placeholder_mode() == "visible":
                            committed = True
                            while pending_chunks:
                                yield pending_chunks.pop(0)
                        yield heartbeat
                    elif state.saw_text_delta or committed or metrics.upstream_events > 0:
                        yield (
                            f": bridge upstream idle phase={idle_phase} idle_s={idle_for:.1f}\n\n"
                        ).encode("utf-8")
                    continue

                if queued is done_marker:
                    while pending_chunks:
                        yield pending_chunks.pop(0)
                    break
                if isinstance(queued, BaseException):
                    if metrics.upstream_events == 0 and is_retryable_stream_exception(queued):
                        raise RetryableStreamBootstrapError(f"{type(queued).__name__}: {queued}") from queued
                    if state.completed:
                        break
                    if not committed and is_retryable_stream_exception(queued):
                        retryable = BridgeStreamRetryableError(str(queued))
                        raise retryable from queued
                    log_bridge_stream_error(
                        account_id=account_id,
                        requested_model=requested_model,
                        request_id=stream_request_id,
                        started_at=stream_started_at,
                        exc=queued,
                        upstream_request_id=upstream_request_id,
                    )
                    yield response_failed_sse(
                        request_id=stream_request_id,
                        requested_model=requested_model,
                        exc=queued,
                    )
                    break

                state.last_upstream_at = time.monotonic()
                event_name, payload, _data_lines = self._parse_sse_block(queued)
                if not usage_recorded and event_name == "response.completed":
                    usage_counts = _usage_from_payload(payload)
                    if usage_counts:
                        record_bridge_usage(
                            account_id=account_id,
                            model=requested_model,
                            requested_model=(usage_context or {}).get("requested_model"),
                            request_type="responses",
                            request_id=stream_request_id,
                            usage=usage_counts,
                            duration_ms=int((time.monotonic() - stream_started_at) * 1000),
                            status_code=response.status_code,
                            source="proxy",
                            route_path=str((usage_context or {}).get("route_path") or ""),
                            bridge_port=(usage_context or {}).get("bridge_port"),
                            client_port=(usage_context or {}).get("client_port"),
                            client_label=str((usage_context or {}).get("client_label") or ""),
                            desktop_route=bool((usage_context or {}).get("desktop_route")),
                            session_id=str((usage_context or {}).get("session_id") or ""),
                            prompt_cache_key_present=bool((usage_context or {}).get("prompt_cache_key_present")),
                            cache_key_source=str((usage_context or {}).get("cache_key_source") or ""),
                        )
                        usage_recorded = True
                terminal_error = terminal_stream_error_from_payload(event_name, payload)
                if terminal_error is not None and not committed and is_retryable_terminal_stream_error(terminal_error):
                    metrics.upstream_events += 1
                    retryable = BridgeStreamRetryableError(str(terminal_error))
                    raise retryable from terminal_error

                chunks = list(self._emit_sse_block_with_reasoning_placeholder(
                    queued,
                    account_id,
                    state=state,
                    request_id=stream_request_id,
                    started_at=stream_started_at,
                    requested_effort=requested_effort,
                    requested_model=requested_model,
                    upstream_request_id=upstream_request_id,
                    metrics=metrics,
                ))
                if (
                    event_name == "response.completed"
                    and incomplete_answer_guard_mode() == "fail"
                    and _answer_incomplete_risk(metrics)
                ):
                    exc = _incomplete_answer_error(metrics)
                    log_bridge_stream_error(
                        account_id=account_id,
                        requested_model=requested_model,
                        request_id=stream_request_id,
                        started_at=stream_started_at,
                        exc=exc,
                        upstream_request_id=upstream_request_id,
                    )
                    chunks = [
                        response_failed_sse(
                            request_id=stream_request_id,
                            requested_model=requested_model,
                            exc=exc,
                            error_code="bridge_incomplete_answer",
                            error_type="bridge_incomplete_answer",
                        )
                    ]
                status = "tool_arguments_streaming" if "function_call_arguments.delta" in (metrics.last_event_name or "") else "streaming"
                maybe_record_active_stream(status)
                if (
                    STREAM_LONG_WARNING_SECS > 0
                    and not metrics.long_stream_warning_logged
                    and not metrics.terminal_event_seen
                    and time.monotonic() - stream_started_at >= STREAM_LONG_WARNING_SECS
                ):
                    metrics.long_stream_warning_logged = True
                    log_bridge_long_stream_warning(
                        account_id=account_id,
                        requested_model=requested_model,
                        requested_effort=requested_effort,
                        actual_effort=actual_effort,
                        request_id=stream_request_id,
                        started_at=stream_started_at,
                        upstream_request_id=upstream_request_id,
                        metrics=metrics,
                    )
                if (
                    stream_tool_call_guard_seconds() > 0
                    and not metrics.terminal_event_seen
                    and "function_call_arguments.delta" in (metrics.last_event_name or "")
                    and time.monotonic() - stream_started_at >= stream_tool_call_guard_seconds()
                ):
                    guard_secs = stream_tool_call_guard_seconds()
                    exc = BridgeToolCallRunaway(
                        "bridge tool call argument stream exceeded "
                        f"{guard_secs:.0f}s before a terminal event; "
                        "closing early so the client can retry instead of hitting its own stream idle timeout"
                    )
                    maybe_record_active_stream("guard_triggered", force=True)
                    log_bridge_stream_error(
                        account_id=account_id,
                        requested_model=requested_model,
                        request_id=stream_request_id,
                        started_at=stream_started_at,
                        exc=exc,
                        upstream_request_id=upstream_request_id,
                    )
                    state.completed = True
                    state.active = False
                    metrics.terminal_event_seen = True
                    metrics.terminal_events += 1
                    if not committed and sse_block_commits_stream(event_name, payload):
                        committed = True
                    if committed:
                        while pending_chunks:
                            yield pending_chunks.pop(0)
                        for chunk in chunks:
                            yield chunk
                    yield response_failed_sse(
                        request_id=stream_request_id,
                        requested_model=requested_model,
                        exc=exc,
                        error_code="bridge_tool_call_runaway",
                        error_type="bridge_tool_call_runaway",
                    )
                    break
                if not committed and sse_block_commits_stream(event_name, payload):
                    committed = True
                if committed:
                    while pending_chunks:
                        yield pending_chunks.pop(0)
                    for chunk in chunks:
                        yield chunk
                else:
                    pending_chunks.extend(chunks)
        finally:
            record_bridge_active_stream(None)
            log_bridge_stream_summary(
                account_id=account_id,
                requested_model=requested_model,
                requested_effort=requested_effort,
                actual_effort=actual_effort,
                request_id=stream_request_id,
                started_at=stream_started_at,
                upstream_request_id=upstream_request_id,
                state=state,
                metrics=metrics,
            )
            stop_reader.set()
            try:
                response.close()
            except Exception:
                pass
            reader.join(timeout=0.5)

    def _reasoning_placeholder_timeout(self, state: ReasoningPlaceholderState) -> float | None:
        if state.completed or state.saw_text_delta or not state.active or state.emitted_count == 0:
            return None
        elapsed = time.monotonic() - state.last_emitted_at
        return max(REASONING_PLACEHOLDER_HEARTBEAT_SECS - elapsed, 0.001)

    def _parse_sse_block(
        self,
        block_lines: list[str],
    ) -> tuple[str | None, dict[str, Any] | None, list[str]]:
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block_lines:
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())

        payload: dict[str, Any] | None = None
        payload_text = "\n".join(data_lines).strip() if data_lines else ""
        if payload_text and payload_text != "[DONE]":
            try:
                decoded = json.loads(payload_text)
                if isinstance(decoded, dict):
                    payload = decoded
            except Exception:
                payload = None

        return event_name, payload, data_lines

    def _normalize_responses_completed_sse_block(
        self,
        event_name: str | None,
        payload: dict[str, Any] | None,
        raw_block: str,
    ) -> str:
        if event_name != "response.completed" or not isinstance(payload, dict):
            return raw_block
        response_obj = payload.get("response")
        if not isinstance(response_obj, dict):
            return raw_block
        if isinstance(response_obj.get("output"), list):
            return raw_block

        normalized_payload = dict(payload)
        normalized_response = dict(response_obj)
        normalized_response["output"] = []
        normalized_payload["response"] = normalized_response
        return (
            "event: response.completed\n"
            f"data: {json.dumps(normalized_payload, ensure_ascii=False)}\n\n"
        )

    def _block_has_reasoning_signal(
        self,
        event_name: str | None,
        payload: dict[str, Any] | None,
    ) -> bool:
        if event_name and "reasoning" in event_name:
            return True
        if not isinstance(payload, dict):
            return False
        payload_type = payload.get("type")
        if isinstance(payload_type, str) and "reasoning" in payload_type:
            return True
        item = payload.get("item")
        return isinstance(item, dict) and item.get("type") == "reasoning"

    def _update_reasoning_placeholder_state(
        self,
        state: ReasoningPlaceholderState,
        event_name: str | None,
        payload: dict[str, Any] | None,
    ) -> None:
        if event_name in {
            "response.completed",
            "response.failed",
            "response.cancelled",
            "response.incomplete",
            "error",
        }:
            state.completed = True
            state.active = False
            return

        if event_name == "response.output_text.delta":
            state.saw_text_delta = True
            state.active = False
            return

        if not isinstance(payload, dict):
            return

        item = payload.get("item")
        if isinstance(item, dict) and item.get("type") == "reasoning":
            state.active = event_name != "response.output_item.done"
            item_id = item.get("id") or payload.get("item_id")
            if isinstance(item_id, str) and item_id:
                state.item_id = item_id
            output_index = payload.get("output_index")
            if isinstance(output_index, int):
                state.output_index = output_index
            return

        if self._block_has_reasoning_signal(event_name, payload):
            state.active = True
            item_id = payload.get("item_id")
            if isinstance(item_id, str) and item_id:
                state.item_id = item_id
            output_index = payload.get("output_index")
            if isinstance(output_index, int):
                state.output_index = output_index

    def _build_reasoning_placeholder_sse(
        self,
        account_id: str,
        state: ReasoningPlaceholderState,
        *,
        requested_effort: str | None = None,
        requested_model: str | None = None,
        source: str,
    ) -> bytes | None:
        if state.completed or state.saw_text_delta:
            return None

        mode = reasoning_placeholder_mode()
        if mode == "off":
            return None
        if mode == "comment":
            state.emitted_count += 1
            state.last_emitted_at = time.monotonic()
            return (
                f": bridge reasoning active source={source} effort={requested_effort or 'unknown'}\n\n"
            ).encode("utf-8")

        placeholder: dict[str, Any] = {
            "type": "response.output_text.delta",
            "delta": build_visible_model_hint(None, requested_model, None, requested_effort),
        }
        if state.item_id:
            placeholder["item_id"] = state.item_id
        if state.output_index is not None:
            placeholder["output_index"] = state.output_index
            placeholder["content_index"] = 0

        state.emitted_count += 1
        state.last_emitted_at = time.monotonic()
        print(
            f"{log_timestamp()} [bridge-thinking-visible] account_id={account_id} item_id={state.item_id or 'unknown'} source={source} effort={requested_effort or 'unknown'} count={state.emitted_count}",
            file=sys.stderr,
        )
        sse = (
            "event: response.output_text.delta\n"
            f"data: {json.dumps(placeholder, ensure_ascii=False)}\n\n"
        )
        return sse.encode("utf-8")

    def _emit_sse_block_with_reasoning_placeholder(
        self,
        block_lines: list[str],
        account_id: str,
        *,
        state: ReasoningPlaceholderState,
        request_id: str,
        started_at: float,
        requested_effort: str | None = None,
        requested_model: str | None = None,
        upstream_request_id: str | None = None,
        metrics: BridgeStreamMetrics | None = None,
    ):
        event_name, payload, data_lines = self._parse_sse_block(block_lines)
        raw_block = self._normalize_responses_completed_sse_block(
            event_name,
            payload,
            "\n".join(block_lines) + "\n\n",
        )
        yield raw_block.encode("utf-8")

        if metrics is not None:
            metrics.upstream_events += 1
            event_key = event_name or ""
            if isinstance(payload, dict) and not event_key:
                payload_type = payload.get("type")
                if isinstance(payload_type, str):
                    event_key = payload_type
            metrics.last_event_name = event_key or "unknown"
            if event_key in {"response.output_text.delta", "response.output_text.done"}:
                metrics.visible_text_events += 1
                _append_visible_text_metrics(metrics, _visible_text_from_payload(event_key, payload))
                if metrics.first_visible_after_ms is None:
                    metrics.first_visible_after_ms = int((time.monotonic() - started_at) * 1000)
            if self._block_has_reasoning_signal(event_name, payload):
                metrics.reasoning_events += 1
            if "tool" in event_key or "function_call" in event_key:
                metrics.tool_events += 1
            if event_key == "response.function_call_arguments.delta" and isinstance(payload, dict):
                metrics.tool_args_mode = metrics.tool_args_mode or anthropic_tool_args_mode()
                metrics.tool_arg_delta_events += 1
                delta = payload.get("delta")
                if isinstance(delta, str):
                    metrics.tool_arg_buffer_chars += len(delta)
            if event_key in {
                "response.completed",
                "response.failed",
                "response.cancelled",
                "response.incomplete",
                "error",
            }:
                _update_terminal_response_metrics(metrics, payload)
                metrics.terminal_event_seen = True
                metrics.terminal_events += 1
        self._update_reasoning_placeholder_state(state, event_name, payload)
        terminal_error = terminal_stream_error_from_payload(event_name, payload)
        if terminal_error is not None and not state.logged_terminal_error:
            state.logged_terminal_error = True
            log_bridge_stream_error(
                account_id=account_id,
                requested_model=requested_model,
                request_id=request_id,
                started_at=started_at,
                exc=terminal_error,
                upstream_request_id=upstream_request_id,
            )

        if not data_lines or payload is None:
            return

        if not self._block_has_reasoning_signal(event_name, payload):
            return

        item = payload.get("item")
        if isinstance(item, dict) and reasoning_has_visible_summary(item):
            return

        placeholder = self._build_reasoning_placeholder_sse(
            account_id,
            state,
            requested_effort=requested_effort,
            requested_model=requested_model,
            source=event_name or "reasoning",
        )
        if placeholder:
            yield placeholder

    def log_message(self, fmt: str, *args: Any) -> None:
        message = redact_log_text(fmt % args) or ""
        sys.stderr.write(f"{log_timestamp()} [codex-bridge] {self.address_string()} - {message}\n")

    def _write_json_error(self, status: int, message: str) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._write_bytes(payload)

    def _write_bytes(self, payload: bytes, *, flush: bool = False) -> bool:
        try:
            self.wfile.write(payload)
            if flush:
                self.wfile.flush()
            return True
        except OSError:
            return False


class CodexBridgeServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], auth_store: AuthStore) -> None:
        super().__init__(server_address, handler)
        self.auth_store = auth_store


def main() -> int:
    host = os.environ.get("CODEX_BRIDGE_HOST", DEFAULT_HOST)
    port = int(os.environ.get("CODEX_BRIDGE_PORT", str(DEFAULT_PORT)))
    auth_store_path = Path(os.environ.get("CODEX_AUTH_STORE_PATH", str(AUTH_STORE_PATH)))

    if not auth_store_path.exists():
        print(f"auth store not found: {auth_store_path}", file=sys.stderr)
        return 1

    try:
        proxy_url = get_upstream_proxy_url()
    except Exception as exc:  # noqa: BLE001
        print(f"{log_timestamp()} invalid upstream proxy config: {exc}", file=sys.stderr)
        return 1
    try:
        host = resolve_listen_host(host, allow_remote=parse_bool_env(os.environ.get(ALLOW_REMOTE_ENV)))
    except Exception as exc:  # noqa: BLE001
        print(f"{log_timestamp()} invalid listen host: {exc}", file=sys.stderr)
        return 1

    auth_store = AuthStore(auth_store_path)
    try:
        server = CodexBridgeServer((host, port), CodexBridgeHandler, auth_store)
    except OSError as exc:
        sleep_s = bind_failure_sleep_seconds(exc)
        print(
            f"{log_timestamp()} failed to bind local bridge on {host}:{port}: "
            f"{type(exc).__name__}: {truncate_log_text(str(exc))}; "
            f"launchd_backoff_s={sleep_s}",
            file=sys.stderr,
        )
        if sleep_s > 0:
            time.sleep(sleep_s)
        return 1
    print(
        f"{log_timestamp()} codex bridge listening on http://{host}:{port} (upstream_proxy={mask_proxy_url(proxy_url)})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
