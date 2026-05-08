from __future__ import annotations

import json
import http.client
import io
import sqlite3
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bridgedeck
try:
    import httpx as _httpx  # noqa: F401
except ModuleNotFoundError:
    httpx_stub = types.ModuleType("httpx")

    class _HttpxError(Exception):
        pass

    class _RemoteProtocolError(_HttpxError):
        pass

    class _ReadTimeout(_HttpxError):
        pass

    class _ReadError(_HttpxError):
        pass

    class _WriteError(_HttpxError):
        pass

    class _HTTPStatusError(_HttpxError):
        def __init__(self, response: Any) -> None:
            self.response = response
            super().__init__(str(response))

    class _URL:
        def __init__(self, value: str) -> None:
            self.scheme = value.split(":", 1)[0]

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    httpx_stub.RemoteProtocolError = _RemoteProtocolError
    httpx_stub.ReadTimeout = _ReadTimeout
    httpx_stub.ReadError = _ReadError
    httpx_stub.WriteError = _WriteError
    httpx_stub.HTTPStatusError = _HTTPStatusError
    httpx_stub.URL = _URL
    httpx_stub.Client = _Client
    sys.modules["httpx"] = httpx_stub

import local_codex_bridge


class FakeManager:
    def __init__(self) -> None:
        self.set_current_called = False

    def snapshot(self, include_secrets: bool = False) -> dict[str, Any]:
        home = str(Path.home())
        return {
            "version": bridgedeck.APP_VERSION,
            "paths": {
                "db": f"{home}/.cc-switch/cc-switch.db",
                "settings": f"{home}/.cc-switch/settings.json",
                "auth_store": f"{home}/.cc-switch/codex_oauth_auth.json",
            },
            "exists": {"db": False, "settings": False, "auth_store": False},
            "accounts": [
                {
                    "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "email": "person@example.com",
                    "label": "person@example.com",
                    "default_cli_home": f"{home}/.codex-cli-person",
                }
            ],
            "providers": [
                {
                    "id": "provider-1",
                    "name": "Provider",
                    "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "base_url": "http://127.0.0.1:8876/accounts/01234567-89ab-cdef-0123-456789abcdef",
                    "model": "gpt-5.5",
                    "max_context_tokens": "272000",
                    "auth_token": "full-token" if include_secrets else "",
                    "auth_token_masked": "full...oken",
                    "compact_enabled": True,
                    "compact_window_tokens": "220000",
                    "compact_threshold_percent": "80",
                }
            ],
            "codex_providers": [
                {
                    "id": "codex-1",
                    "name": "Codex",
                    "meta_account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "token_account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "token_mismatch": False,
                }
            ],
            "cli_homes": [
                {
                    "path": f"{home}/.codex",
                    "is_default": True,
                    "run_command": "codex",
                    "token_account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "access_account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "email": "person@example.com",
                    "risk_flags": [],
                }
            ],
            "cli_launchers": [],
            "codex_desktop": {
                "detected": True,
                "config_path": f"{home}/.codex/config.toml",
                "base_url": "http://127.0.0.1:15721/v1",
                "managed_by": "cc_switch",
                "risk_flags": [],
            },
            "current_codex_launcher": {
                "path": f"{home}/.cc-switch/codex-cli-launchers/codex-current.command",
                "exists": False,
                "account_id": "",
                "risk_flags": ["missing_current_launcher"],
            },
            "omc_codex_shim": {
                "active": False,
                "shims": [],
                "risk_flags": ["omc_codex_shim_missing"],
            },
            "account_matrix": [],
            "current_provider_from_settings": "",
        }

    def set_current_provider(self, provider_id: str) -> dict[str, Any]:
        self.set_current_called = True
        return {"ok": True, "provider_id": provider_id}

    def create_or_update_provider(
        self,
        account_id: str,
        provider_name: str,
        set_current: bool,
        compact_config: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"ok": True}

    def patch_provider(self, provider_id: str) -> dict[str, Any]:
        return {"ok": True}

    def update_provider_compact(
        self,
        provider_id: str,
        compact_config: dict[str, Any] | None,
        model_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "上下文配置已保存",
            "provider_id": provider_id,
            "compact_config": bridgedeck.normalize_compact_config(compact_config),
            "model_config": bridgedeck.normalize_bridge_model_config(model_config),
        }

    def sync_common_env_to_bridge_providers(self, provider_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "通用 env 已同步",
            "source_provider_id": provider_id,
            "env_keys": ["ANTHROPIC_MODEL", "HUB_CLAUDE_MEM"],
            "updated": [{"id": "provider-1", "name": "Provider"}],
            "skipped": [],
        }

    def extract_safe_claude_common_config(self) -> dict[str, Any]:
        return {
            "ok": True,
            "changed": True,
            "message": "安全通用配置已提取",
            "keys": ["hooks", "permissions", "enabledPlugins"],
            "env_keys": ["ENABLE_TOOL_SEARCH"],
            "removed_keys": [],
            "removed_env_keys": ["ANTHROPIC_BASE_URL"],
            "backups": [],
        }

    def proxy_diagnosis(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "healthy",
            "message": "代理链路可用，问题更像 Codex.app 事件会话层重连",
            "proxy": {
                "source": f"{Path.home()}/.codex/.env",
                "url": "http://127.0.0.1:1087",
                "host": "127.0.0.1",
                "port": 1087,
                "running": True,
            },
            "codex_auth": {
                "present": True,
                "authenticated": True,
                "plan": "pro",
                "email_masked": "pe***n@example.com",
            },
            "checks": [
                {"label": "Codex 代理配置", "status": "ok", "detail": "http://127.0.0.1:1087"},
                {"label": "api.openai.com 基础探测", "status": "ok", "detail": "HTTP 401"},
                {"label": "chatgpt.com Codex 流式探测", "status": "ok", "detail": "HTTP 200"},
            ],
            "recommendations": ["完全退出并重启 Codex.app 后重测"],
        }

    def sync_claude_enabled_plugins(self) -> dict[str, Any]:
        return {
            "ok": True,
            "changed": False,
            "installed_count": 7,
            "enabled_count": 7,
            "added": [],
            "backups": [],
        }

    def claude_plugin_sync_status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "installed_count": 7,
            "common_enabled_count": 7,
            "settings_enabled_count": 7,
            "missing_from_common": [],
            "missing_from_settings": [],
            "disabled": [],
            "needs_sync": False,
        }

    def dedupe_bridge_providers(self, *, apply: bool = False) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "重复 provider 预览" if not apply else "重复 Local Bridge provider 已清理",
            "apply": apply,
            "plan": [
                {
                    "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "keep": {"id": "provider-1", "name": "Provider"},
                    "delete": [{"id": "provider-old", "name": "Provider Old"}],
                    "switch_current_to": "",
                }
            ],
            "deleted": [{"id": "provider-old", "name": "Provider Old"}] if apply else [],
            "backups": [],
        }

    def repair_plus_pro(self) -> dict[str, Any]:
        return {"ok": True}

    def create_or_sync_cli_home(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}

    def create_cli_launcher(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}

    def migrate_cli_launcher(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}

    def set_default_codex_account(self, account_id: str) -> dict[str, Any]:
        return {"ok": True}

    def health(self) -> dict[str, Any]:
        return {"ok": True, "status": "ok", "risk_flags": []}

    def quotas(self) -> dict[str, Any]:
        return {
            "ok": True,
            "quotas": [
                {
                    "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "email": "person@example.com",
                    "quota_status": "ok",
                    "plan_type": "plus",
                    "windows": [{"name": "5小时", "used_percent": 0}],
                }
            ],
        }

    def update_auto_switch_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "auto_switch": payload}

    def run_auto_switch(self, *, force: bool = False) -> dict[str, Any]:
        return {"ok": True, "enabled": True, "actions": [], "force": force}

    def missing_bridge_accounts(self, quotas: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        return []

    def create_missing_bridge_providers(self) -> dict[str, Any]:
        return {"ok": True, "created": [], "skipped": [], "missing": []}

    def services(self, *, server_port: int = 8899) -> dict[str, Any]:
        return {
            "ok": True,
            "services": {
                "bridgedeck": {"name": "BridgeDeck", "running": True, "port": server_port},
                "local_bridge": {
                    "name": "Local Codex Bridge",
                    "running": True,
                    "port": 8876,
                    "processes": [{"pid": 123, "command": "/Users/person/local_codex_bridge.py"}],
                    "script": "/Users/person/local_codex_bridge.py",
                    "log_path": "/Users/person/.cc-switch/bridgedeck-local-bridge.log",
                    "upstream_proxy": "http://user:pass@127.0.0.1:1087",
                    "last_stream_error": {
                        "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                        "model": "gpt-5.5",
                        "request_id": "bridge-test",
                        "duration_ms": 100,
                        "error_type": "RemoteProtocolError",
                        "error": "incomplete chunked read",
                    },
                },
                "cc_switch_proxy": {"name": "CC Switch Proxy", "running": True, "port": 15721},
            },
        }

    def control_local_bridge(self, action: str) -> dict[str, Any]:
        return {"ok": True, "message": f"local bridge {action}", **self.services()}

    def repair_quota_query(self) -> dict[str, Any]:
        payload = self.quotas()
        payload["actions"] = []
        payload["services"] = self.services()["services"]
        return payload


class FakeSseResponse:
    def __init__(self, lines: list[str], exc: BaseException | None = None) -> None:
        self.lines = lines
        self.exc = exc
        self.headers = {"x-request-id": "upstream-test"}

    def iter_lines(self):
        for line in self.lines:
            yield line
        if self.exc is not None:
            raise self.exc

    def close(self) -> None:
        return None


class FakeForwardResponse:
    def __init__(self, status_code: int, *, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.content = body
        self.headers = headers or {"content-type": "text/event-stream"}

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def __enter__(self) -> "FakeForwardResponse":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def read(self) -> bytes:
        return self.content

    def iter_lines(self):
        for line in self.content.decode("utf-8").splitlines():
            yield line

    def close(self) -> None:
        return None


class FakeForwardClient:
    def __init__(self, responses: list[FakeForwardResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "FakeForwardClient":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def stream(self, *args: Any, **kwargs: Any) -> FakeForwardResponse:
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.responses.pop(0)


class PoolAuthStore:
    def __init__(self) -> None:
        self.token_requests: list[str | None] = []
        self.bound: tuple[str | None, str] | None = None

    def get_access_token(self, requested_account_id: str | None) -> tuple[str, str]:
        self.token_requests.append(requested_account_id)
        account_id = requested_account_id or "acct-1"
        return account_id, f"token-{account_id}"

    def bind_session(self, session_key: str | None, account_id: str) -> None:
        self.bound = (session_key, account_id)


class SlowReasoningResponse:
    headers = {"x-request-id": "upstream-test"}

    def iter_lines(self):
        yield "event: response.output_item.added"
        yield 'data: {"type":"response.output_item.added","item":{"id":"rs_1","type":"reasoning"},"output_index":0}'
        yield ""
        time.sleep(0.05)
        yield "event: response.output_text.delta"
        yield 'data: {"type":"response.output_text.delta","delta":"done"}'
        yield ""


class SilentReasoningResponse:
    headers = {"x-request-id": "upstream-test"}

    def iter_lines(self):
        yield "event: response.output_item.added"
        yield 'data: {"type":"response.output_item.added","item":{"id":"rs_1","type":"reasoning"},"output_index":0}'
        yield ""
        time.sleep(0.05)
        yield "event: response.completed"
        yield 'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}'
        yield ""


class BrokenWriter:
    def write(self, payload: bytes) -> int:
        raise BrokenPipeError("client closed")

    def flush(self) -> None:
        raise AssertionError("flush should not run after write failure")


class OSErrorWriter:
    def write(self, payload: bytes) -> int:
        raise OSError("socket write failed")

    def flush(self) -> None:
        raise AssertionError("flush should not run after write failure")


class NoopAuthStore:
    def get_access_token(self, requested_account_id: str | None) -> tuple[str, str]:
        return requested_account_id or "acct-1", "unused-access-token"

    def account_candidates(self, requested_account_id: str | None, session_key: str | None = None) -> list[str]:
        return [requested_account_id or "acct-1"]

    def bind_session(self, session_key: str | None, account_id: str) -> None:
        return None


class LocalCodexBridgeCase(unittest.TestCase):
    def make_handler(self) -> local_codex_bridge.CodexBridgeHandler:
        return object.__new__(local_codex_bridge.CodexBridgeHandler)

    def start_local_bridge_server(self):
        server = local_codex_bridge.CodexBridgeServer(
            ("127.0.0.1", 0),
            local_codex_bridge.CodexBridgeHandler,
            NoopAuthStore(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def post_local_bridge_json(
        self,
        server: local_codex_bridge.CodexBridgeServer,
        path: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str, dict[str, str]]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}{path}",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers.items())

    def test_stream_passthrough_preserves_delta_and_completed(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"hello"}',
                "",
                "event: response.completed",
                'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}',
                "",
            ]
        )

        chunks = list(
            self.make_handler()._iter_stream_with_reasoning_placeholder(
                response,
                "acct-1",
                request_id="bridge-test",
                started_at=local_codex_bridge.time.monotonic(),
                requested_model="gpt-5.5",
            )
        )
        body = b"".join(chunks).decode("utf-8")

        self.assertIn("event: response.output_text.delta", body)
        self.assertIn('"delta":"hello"', body)
        self.assertIn("event: response.completed", body)

    def test_normalize_preserves_reasoning_summary_and_adds_encrypted_content(self) -> None:
        body = {
            "model": "gpt-5.4",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "stream": True,
            "reasoning": {"effort": "low"},
            "include": ["reasoning.summary"],
        }

        normalized = local_codex_bridge.normalize_request_body(body)

        self.assertEqual(normalized["reasoning"]["summary"], "concise")
        self.assertNotIn("reasoning.summary", normalized["include"])
        self.assertIn("reasoning.encrypted_content", normalized["include"])

    def test_normalize_maps_gpt_54_minimal_reasoning_to_low(self) -> None:
        body = {
            "model": "gpt-5.4",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "stream": True,
            "reasoning": {"effort": "minimal"},
        }

        normalized = local_codex_bridge.normalize_request_body(body)

        self.assertEqual(normalized["reasoning"]["effort"], "low")
        self.assertEqual(normalized["reasoning"]["summary"], "concise")

    def test_reasoning_heartbeat_defaults_to_comment_not_output_text(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_item.added",
                'data: {"type":"response.output_item.added","item":{"id":"rs_1","type":"reasoning"},"output_index":0}',
                "",
            ]
        )

        chunks = list(
            self.make_handler()._iter_stream_with_reasoning_placeholder(
                response,
                "acct-1",
                request_id="bridge-test",
                started_at=local_codex_bridge.time.monotonic(),
                requested_model="gpt-5.4",
                requested_effort="high",
            )
        )
        body = b"".join(chunks).decode("utf-8")

        self.assertIn(": bridge reasoning active", body)
        self.assertNotIn("event: response.output_text.delta", body)
        self.assertNotIn("思考等级", body)

    def test_reasoning_summary_delta_passthrough_does_not_emit_fake_output_text(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.reasoning_summary_text.delta",
                'data: {"type":"response.reasoning_summary_text.delta","item_id":"rs_1","output_index":0,"summary_index":0,"delta":"thinking summary"}',
                "",
            ]
        )

        chunks = list(
            self.make_handler()._iter_stream_with_reasoning_placeholder(
                response,
                "acct-1",
                request_id="bridge-test",
                started_at=local_codex_bridge.time.monotonic(),
                requested_model="gpt-5.4",
                requested_effort="high",
            )
        )
        body = b"".join(chunks).decode("utf-8")

        self.assertIn("event: response.reasoning_summary_text.delta", body)
        self.assertIn("thinking summary", body)
        self.assertNotIn("event: response.output_text.delta", body)
        self.assertNotIn("思考等级", body)

    def test_legacy_visible_reasoning_placeholder_uses_requested_effort(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_item.added",
                'data: {"type":"response.output_item.added","item":{"id":"rs_1","type":"reasoning"},"output_index":0}',
                "",
            ]
        )

        with mock.patch.dict(local_codex_bridge.os.environ, {local_codex_bridge.REASONING_PLACEHOLDER_MODE_ENV: "visible"}):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.4",
                    requested_effort="high",
                )
            )
        body = b"".join(chunks).decode("utf-8")

        self.assertIn("event: response.output_text.delta", body)
        self.assertIn("思考等级：high", body)
        self.assertNotIn("思考等级：xhigh", body)

    def test_stream_idle_logs_when_upstream_is_silent(self) -> None:
        with (
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_LOG_SECS", 0.01),
            mock.patch.object(local_codex_bridge, "REASONING_PLACEHOLDER_HEARTBEAT_SECS", 0.01),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    SlowReasoningResponse(),
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.4",
                    requested_effort="high",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("done", body)
        self.assertIn("[bridge-stream-idle]", stderr.getvalue())

    def test_stream_idle_timeout_emits_failed_sse_without_fake_output_text(self) -> None:
        with (
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_LOG_SECS", 0.005),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_FAIL_SECS", 0.02),
            mock.patch.object(local_codex_bridge, "REASONING_PLACEHOLDER_HEARTBEAT_SECS", 0.005),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    SilentReasoningResponse(),
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.4",
                    requested_effort="high",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        logs = stderr.getvalue()
        self.assertIn("event: response.failed", body)
        self.assertIn("bridge_stream_idle_timeout", body)
        self.assertIn("bridge-test", body)
        self.assertNotIn("event: response.output_text.delta", body)
        self.assertIn("[bridge-stream-idle]", logs)
        self.assertIn("[bridge-stream-end]", logs)
        self.assertIn('"idle_timeout_seen": true', logs)

    def test_pre_output_overloaded_terminal_raises_retryable_without_failed_sse(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.failed",
                'data: {"type":"response.failed","response":{"status":"failed","error":{"message":"Our servers are currently overloaded. Please try again later."}}}',
                "",
            ]
        )

        with self.assertRaises(local_codex_bridge.BridgeStreamRetryableError):
            list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.5",
                )
            )

    def test_after_output_overloaded_terminal_is_not_retried(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"half"}',
                "",
                "event: response.failed",
                'data: {"type":"response.failed","response":{"status":"failed","error":{"message":"Our servers are currently overloaded. Please try again later."}}}',
                "",
            ]
        )

        chunks = list(
            self.make_handler()._iter_stream_with_reasoning_placeholder(
                response,
                "acct-1",
                request_id="bridge-test",
                started_at=local_codex_bridge.time.monotonic(),
                requested_model="gpt-5.5",
            )
        )
        body = b"".join(chunks).decode("utf-8")

        self.assertIn('"delta":"half"', body)
        self.assertIn("event: response.failed", body)

    def test_stream_final_summary_logs_terminal_event(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"hello"}',
                "",
                "event: response.completed",
                'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}',
                "",
            ]
        )

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        logs = stderr.getvalue()
        self.assertIn("event: response.completed", body)
        self.assertIn("[bridge-stream-end]", logs)
        self.assertIn('"terminal_event_seen": true', logs)
        self.assertIn('"upstream_events": 2', logs)

    def test_stream_final_summary_records_client_disconnect(self) -> None:
        metrics = local_codex_bridge.BridgeStreamMetrics()
        iterator = self.make_handler()._iter_stream_with_reasoning_placeholder(
            FakeSseResponse(
                [
                    "event: response.output_text.delta",
                    'data: {"type":"response.output_text.delta","delta":"hello"}',
                    "",
                ]
            ),
            "acct-1",
            request_id="bridge-test",
            started_at=local_codex_bridge.time.monotonic(),
            requested_model="gpt-5.4",
            metrics=metrics,
        )

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            next(iterator)
            metrics.client_disconnected = True
            iterator.close()

        self.assertIn("[bridge-stream-end]", stderr.getvalue())
        self.assertIn('"client_disconnected": true', stderr.getvalue())

    def test_stream_write_failure_records_client_disconnect(self) -> None:
        with (
            mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            local_codex_bridge.log_bridge_client_disconnect(
                account_id="acct-1",
                requested_model="gpt-5.4",
                request_id="bridge-test",
                started_at=local_codex_bridge.time.monotonic(),
                detail="write_failed",
                upstream_request_id="upstream-test",
            )

        record.assert_called_once()
        payload = record.call_args.args[0]
        self.assertEqual(payload["error_type"], "BridgeClientDisconnect")
        self.assertIn("write_failed", payload["error"])
        self.assertEqual(payload["upstream_request_id"], "upstream-test")
        self.assertIn("[bridge-client-disconnect]", stderr.getvalue())

    def test_stream_remote_protocol_error_emits_failed_sse(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"half"}',
                "",
            ],
            exc=local_codex_bridge.httpx.RemoteProtocolError("incomplete chunked read"),
        )

        with mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record:
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.5",
                    upstream_request_id="upstream-test",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("event: response.failed", body)
        self.assertIn("upstream_stream_error", body)
        self.assertIn("RemoteProtocolError", body)
        record.assert_called_once()
        self.assertEqual(record.call_args.args[0]["request_id"], "bridge-test")
        self.assertEqual(record.call_args.args[0]["model"], "gpt-5.5")

    def test_stream_bootstrap_protocol_error_is_retryable_before_first_event(self) -> None:
        response = FakeSseResponse(
            [],
            exc=local_codex_bridge.httpx.RemoteProtocolError("incomplete chunked read"),
        )

        with self.assertRaises(local_codex_bridge.RetryableStreamBootstrapError):
            list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.5",
                )
            )

    def test_stream_error_after_completed_does_not_emit_second_terminal(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.completed",
                'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}',
                "",
            ],
            exc=local_codex_bridge.httpx.RemoteProtocolError("late disconnect"),
        )

        with mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record:
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("event: response.completed", body)
        self.assertNotIn("event: response.failed", body)
        record.assert_not_called()

    def test_upstream_response_failed_is_logged_as_stream_error(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.failed",
                'data: {"type":"response.failed","response":{"status":"failed","error":{"message":"permission denied"}}}',
                "",
            ]
        )

        with mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record:
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("event: response.failed", body)
        record.assert_called_once()
        self.assertEqual(record.call_args.args[0]["error_type"], "TerminalStreamError")

    def test_write_bytes_swallow_client_broken_pipe(self) -> None:
        handler = self.make_handler()
        handler.wfile = BrokenWriter()

        self.assertFalse(handler._write_bytes(b"payload", flush=True))

    def test_write_bytes_swallow_generic_oserror(self) -> None:
        handler = self.make_handler()
        handler.wfile = OSErrorWriter()

        self.assertFalse(handler._write_bytes(b"payload", flush=True))

    def test_non_stream_json_builds_message_from_sse(self) -> None:
        raw = (
            b"event: response.output_text.delta\n"
            b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
            b"event: response.output_text.delta\n"
            b'data: {"type":"response.output_text.delta","delta":" world"}\n\n'
        )

        payload = json.loads(local_codex_bridge.build_non_stream_json_from_sse(raw, "gpt-5.5"))

        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["output"][0]["content"][0]["text"], "hello world")

    def test_non_stream_json_preserves_failed_sse_status(self) -> None:
        raw = (
            b"event: response.failed\n"
            b'data: {"type":"response.failed","response":{"id":"resp_failed","status":"failed","error":{"message":"overloaded"}}}\n\n'
        )

        payload = json.loads(local_codex_bridge.build_non_stream_json_from_sse(raw, "gpt-5.5"))

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["error"]["message"], "overloaded")

    def test_models_registry_includes_scoped_gpt55_limits(self) -> None:
        payload = local_codex_bridge.build_models_payload()
        by_id = {item["id"]: item for item in payload["data"]}

        self.assertEqual(payload["object"], "list")
        self.assertIn("gpt-5.5", by_id)
        self.assertEqual(by_id["gpt-5.5"]["context_length"], 272000)
        self.assertEqual(by_id["gpt-5.5"]["max_completion_tokens"], 128000)
        self.assertEqual(by_id["gpt-5.5"]["thinking"]["levels"], ["low", "medium", "high", "xhigh"])
        self.assertTrue(by_id["gpt-5.5"]["capabilities"]["messages"])
        self.assertTrue(by_id["gpt-5.5"]["capabilities"]["responses"])

    def test_models_registry_exposes_claude_desktop_safe_routes(self) -> None:
        payload = local_codex_bridge.build_models_payload()
        by_id = {item["id"]: item for item in payload["data"]}

        self.assertEqual(by_id["claude-haiku-4-5"]["bridge_target_model"], "gpt-5.3-codex-spark")
        self.assertEqual(by_id["claude-sonnet-4-6"]["bridge_target_model"], "gpt-5.3-codex")
        self.assertEqual(by_id["claude-opus-4-7"]["bridge_target_model"], "gpt-5.5")
        self.assertEqual(by_id["claude-opus-4-7"]["context_length"], 272000)
        self.assertTrue(by_id["claude-opus-4-7"]["capabilities"]["claude_desktop_gateway"])

    def test_claude_desktop_safe_route_maps_before_forwarding(self) -> None:
        body = local_codex_bridge.normalize_request_body(
            {"model": "claude-opus-4-7", "input": [{"role": "user", "content": []}]}
        )

        self.assertEqual(body["model"], "gpt-5.5")

    def test_models_endpoint_is_account_scoped_and_ignores_sensitive_query(self) -> None:
        server = self.start_local_bridge_server()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/accounts/acct-1/v1/models?api_key=secret"
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        by_id = {item["id"]: item for item in payload["data"]}
        self.assertEqual(response.status, 200)
        self.assertIn("gpt-5.5", by_id)
        self.assertIn("claude-opus-4-7", by_id)
        self.assertEqual(by_id["gpt-5.5"]["context_length"], 272000)

    def test_models_endpoint_accepts_openai_base_url_path_variants(self) -> None:
        server = self.start_local_bridge_server()
        for path in ("/accounts/acct-1/models", "/accounts/acct-1/v1/v1/models"):
            with self.subTest(path=path):
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}")
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))

                self.assertEqual(response.status, 200)
                self.assertIn("gpt-5.5", {item["id"] for item in payload["data"]})

    def test_messages_endpoint_posts_translated_responses_request_to_mock_upstream(self) -> None:
        server = self.start_local_bridge_server()
        client = FakeForwardClient(
            [
                FakeForwardResponse(
                    200,
                    body=(
                        b"event: response.output_text.delta\n"
                        b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
                    ),
                )
            ]
        )

        with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
            status, body, headers = self.post_local_bridge_json(
                server,
                "/accounts/acct-1/v1/messages",
                {
                    "model": "gpt-5.5",
                    "max_tokens": 200,
                    "system": "Be direct.",
                    "stream": False,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
                },
            )

        sent = client.calls[0]["kwargs"]
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(sent["headers"]["ChatGPT-Account-Id"], "acct-1")
        self.assertEqual(sent["headers"]["Authorization"], "Bearer unused-access-token")
        self.assertEqual(sent["json"]["model"], "gpt-5.5")
        self.assertEqual(sent["json"]["instructions"], "Be direct.")
        self.assertEqual(sent["json"]["stream"], True)
        self.assertEqual(sent["json"]["input"][0]["content"][0], {"type": "input_text", "text": "hi"})
        payload = json.loads(body)
        self.assertEqual(payload["type"], "message")
        self.assertEqual(payload["content"][0], {"type": "text", "text": "hello"})

    def test_messages_endpoint_maps_claude_desktop_safe_model_to_gpt(self) -> None:
        server = self.start_local_bridge_server()
        client = FakeForwardClient(
            [
                FakeForwardResponse(
                    200,
                    body=(
                        b"event: response.output_text.delta\n"
                        b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
                    ),
                )
            ]
        )

        with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
            status, _, _ = self.post_local_bridge_json(
                server,
                "/accounts/acct-1/v1/messages",
                {
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 200,
                    "stream": False,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )

        sent = client.calls[0]["kwargs"]
        self.assertEqual(status, 200)
        self.assertEqual(sent["json"]["model"], "gpt-5.3-codex")

    def test_chat_completions_endpoint_accepts_openai_base_url_path_variants(self) -> None:
        for path in ("/accounts/acct-1/chat/completions", "/accounts/acct-1/v1/v1/chat/completions"):
            with self.subTest(path=path):
                server = self.start_local_bridge_server()
                client = FakeForwardClient(
                    [
                        FakeForwardResponse(
                            200,
                            body=(
                                b"event: response.output_text.delta\n"
                                b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
                            ),
                        )
                    ]
                )

                with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
                    status, body, _ = self.post_local_bridge_json(
                        server,
                        path,
                        {
                            "model": "gpt-5.5",
                            "stream": False,
                            "messages": [{"role": "user", "content": "hi"}],
                        },
                    )

                payload = json.loads(body)
                self.assertEqual(status, 200)
                self.assertEqual(payload["choices"][0]["message"]["content"], "hello")
                self.assertEqual(client.calls[0]["kwargs"]["json"]["model"], "gpt-5.5")

    def test_chat_completions_endpoint_posts_translated_responses_request_to_mock_upstream(self) -> None:
        server = self.start_local_bridge_server()
        client = FakeForwardClient(
            [
                FakeForwardResponse(
                    200,
                    body=(
                        b"event: response.output_text.delta\n"
                        b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
                    ),
                )
            ]
        )

        with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
            status, body, headers = self.post_local_bridge_json(
                server,
                "/accounts/acct-1/v1/chat/completions",
                {
                    "model": "gpt-5.5",
                    "stream": False,
                    "reasoning_effort": "high",
                    "messages": [
                        {"role": "system", "content": "Be direct."},
                        {"role": "user", "content": "hi"},
                    ],
                },
            )

        sent = client.calls[0]["kwargs"]
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(sent["headers"]["ChatGPT-Account-Id"], "acct-1")
        self.assertEqual(sent["json"]["instructions"], "Be direct.")
        self.assertEqual(sent["json"]["reasoning"]["effort"], "high")
        self.assertEqual(sent["json"]["input"][0]["content"][0], {"type": "input_text", "text": "hi"})
        payload = json.loads(body)
        self.assertEqual(payload["object"], "chat.completion")
        self.assertEqual(payload["choices"][0]["message"]["content"], "hello")

    def test_chat_completions_endpoint_streams_openai_sse_from_mock_upstream(self) -> None:
        server = self.start_local_bridge_server()
        client = FakeForwardClient(
            [
                FakeForwardResponse(
                    200,
                    body=(
                        b"event: response.output_text.delta\n"
                        b'data: {"type":"response.output_text.delta","delta":"hi"}\n\n'
                        b"event: response.completed\n"
                        b'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}\n\n'
                    ),
                )
            ]
        )

        with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
            status, body, headers = self.post_local_bridge_json(
                server,
                "/accounts/acct-1/v1/chat/completions",
                {
                    "model": "gpt-5.5",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                headers={"Accept": "text/event-stream"},
            )

        sent = client.calls[0]["kwargs"]
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers["Content-Type"])
        self.assertEqual(sent["json"]["stream"], True)
        self.assertIn("event: chat.completion.chunk", body)
        self.assertIn('"content":"hi"', body)
        self.assertIn("data: [DONE]", body)
        self.assertNotIn("response.output_text.delta", body)

    def test_anthropic_messages_request_maps_text_tools_and_thinking_to_responses(self) -> None:
        payload = local_codex_bridge.anthropic_messages_to_responses(
            {
                "model": "gpt-5.5",
                "system": "You are terse.",
                "thinking": {"type": "enabled", "budget_tokens": 32000},
                "tools": [
                    {
                        "name": "lookup",
                        "description": "Find a record",
                        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
                    }
                ],
                "tool_choice": {"type": "tool", "name": "lookup"},
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "hi"}]},
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "lookup", "input": {"id": "42"}}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "found"}]},
                ],
            }
        )

        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["instructions"], "You are terse.")
        self.assertEqual(payload["reasoning"]["effort"], "high")
        self.assertEqual(payload["tools"][0]["name"], "lookup")
        self.assertEqual(payload["tool_choice"], {"type": "function", "name": "lookup"})
        self.assertEqual(payload["input"][0]["content"][0]["type"], "input_text")
        self.assertEqual(payload["input"][1]["type"], "function_call")
        self.assertEqual(payload["input"][1]["call_id"], "toolu_1")
        self.assertEqual(payload["input"][2]["type"], "function_call_output")
        self.assertEqual(payload["input"][2]["output"], "found")

    def test_responses_json_converts_to_anthropic_message(self) -> None:
        payload = local_codex_bridge.responses_json_to_anthropic_message(
            {
                "id": "resp_1",
                "status": "completed",
                "model": "gpt-5.5",
                "usage": {"input_tokens": 7, "output_tokens": 3},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "lookup",
                        "arguments": '{"id":"42"}',
                    },
                ],
            }
        )

        self.assertEqual(payload["type"], "message")
        self.assertEqual(payload["role"], "assistant")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["content"][0], {"type": "text", "text": "hello"})
        self.assertEqual(payload["content"][1]["type"], "tool_use")
        self.assertEqual(payload["content"][1]["input"], {"id": "42"})
        self.assertEqual(payload["usage"], {"input_tokens": 7, "output_tokens": 3})

    def test_chat_completions_request_maps_messages_tools_and_reasoning(self) -> None:
        payload = local_codex_bridge.chat_completions_to_responses(
            {
                "model": "gpt-5.5",
                "reasoning_effort": "xhigh",
                "max_completion_tokens": 123,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "description": "Find",
                            "parameters": {"type": "object", "properties": {"id": {"type": "string"}}},
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "lookup"}},
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "hi"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": '{"id":"42"}'},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "call_1", "content": "found"},
                ],
            }
        )

        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["instructions"], "You are terse.")
        self.assertEqual(payload["reasoning"], {"effort": "xhigh"})
        self.assertEqual(payload["max_output_tokens"], 123)
        self.assertEqual(payload["tools"][0]["name"], "lookup")
        self.assertEqual(payload["tool_choice"], {"type": "function", "name": "lookup"})
        self.assertEqual(payload["input"][0]["role"], "user")
        self.assertEqual(payload["input"][1]["type"], "function_call")
        self.assertEqual(payload["input"][2]["type"], "function_call_output")

    def test_responses_json_converts_to_chat_completion(self) -> None:
        payload = local_codex_bridge.responses_json_to_chat_completion(
            {
                "id": "resp_1",
                "status": "completed",
                "model": "gpt-5.5",
                "usage": {"input_tokens": 3, "output_tokens": 2},
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "hello"}]},
                    {"type": "function_call", "call_id": "call_1", "name": "lookup", "arguments": '{"id":"42"}'},
                ],
            }
        )

        self.assertEqual(payload["object"], "chat.completion")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["choices"][0]["message"]["content"], "hello")
        self.assertEqual(payload["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(payload["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "lookup")
        self.assertEqual(payload["usage"], {"input_tokens": 3, "output_tokens": 2})

    def test_chat_stream_converts_response_text_delta_and_done(self) -> None:
        chunks = [
            (
                b"event: response.output_text.delta\n"
                b'data: {"type":"response.output_text.delta","delta":"hi"}\n\n'
            ),
            (
                b"event: response.completed\n"
                b'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}\n\n'
            ),
        ]

        body = b"".join(
            local_codex_bridge.iter_chat_completions_sse(
                iter(chunks),
                completion_id="chatcmpl_1",
                model="gpt-5.5",
            )
        ).decode("utf-8")

        self.assertIn("event: chat.completion.chunk", body)
        self.assertIn('"content":"hi"', body)
        self.assertIn('"finish_reason":"stop"', body)
        self.assertIn("data: [DONE]", body)
        self.assertNotIn("response.output_text.delta", body)

    def test_anthropic_stream_uses_comments_for_reasoning_keepalive(self) -> None:
        chunks = [
            (
                b"event: response.output_item.added\n"
                b'data: {"type":"response.output_item.added","item":{"id":"rs_1","type":"reasoning"},"output_index":0}\n\n'
            ),
            b": bridge reasoning active source=heartbeat effort=high\n\n",
            (
                b"event: response.output_text.delta\n"
                b'data: {"type":"response.output_text.delta","delta":"done"}\n\n'
            ),
            (
                b"event: response.completed\n"
                b'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed","usage":{"output_tokens":1}}}\n\n'
            ),
        ]

        body = b"".join(
            local_codex_bridge.iter_anthropic_messages_sse(
                iter(chunks),
                message_id="msg_1",
                model="gpt-5.5",
            )
        ).decode("utf-8")

        self.assertIn("event: message_start", body)
        self.assertIn(": bridge reasoning active", body)
        self.assertIn("event: content_block_delta", body)
        self.assertIn('"text":"done"', body)
        self.assertIn("event: message_stop", body)
        self.assertNotIn("response.output_text.delta", body)
        self.assertNotIn("思考等级", body)

    def test_bridge_listen_host_rejects_non_loopback_by_default(self) -> None:
        self.assertEqual(local_codex_bridge.resolve_listen_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(local_codex_bridge.resolve_listen_host("localhost"), "localhost")
        with self.assertRaises(RuntimeError):
            local_codex_bridge.resolve_listen_host("0.0.0.0")
        self.assertEqual(
            local_codex_bridge.resolve_listen_host("0.0.0.0", allow_remote=True),
            "0.0.0.0",
        )

    def test_auth_store_session_affinity_orders_candidates_without_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auth.json"
            path.write_text(
                json.dumps(
                    {
                        "accounts": {
                            "acct-1": {"refresh_token": "refresh-1"},
                            "acct-2": {"refresh_token": "refresh-2"},
                        },
                        "default_account_id": "acct-1",
                    }
                ),
                encoding="utf-8",
            )
            store = local_codex_bridge.AuthStore(path)

            self.assertEqual(store.account_candidates(None, "session:a"), ["acct-1", "acct-2"])
            store.bind_session("session:a", "acct-2")
            self.assertEqual(store.account_candidates(None, "session:a"), ["acct-2", "acct-1"])
            self.assertEqual(store.account_candidates("acct-1", "session:a"), ["acct-1"])

    def test_forward_responses_fails_over_to_next_account_before_writing_error(self) -> None:
        handler = self.make_handler()
        auth_store = PoolAuthStore()
        handler.server = types.SimpleNamespace(auth_store=auth_store)
        handler.headers = {}
        handler._send_upstream_headers = mock.Mock()
        handler._write_bytes = mock.Mock(return_value=True)
        responses = [
            FakeForwardResponse(503, body=b'{"error":"busy"}'),
            FakeForwardResponse(
                200,
                body=(
                    b"event: response.output_text.delta\n"
                    b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
                ),
            ),
        ]

        with mock.patch.object(
            local_codex_bridge,
            "build_upstream_http_client",
            side_effect=lambda timeout: FakeForwardClient(responses),
        ):
            handler._forward_responses_body(
                candidate_account_ids=["acct-1", "acct-2"],
                session_key="session:a",
                route_path="/v1/responses",
                request_id="bridge-test",
                request_type="responses",
                original_body={"model": "gpt-5.5", "input": []},
                normalized_body={"model": "gpt-5.5", "input": [], "stream": False},
                is_stream=False,
                requested_model="gpt-5.5",
                requested_effort=None,
                output_format="responses",
            )

        self.assertEqual(auth_store.token_requests, ["acct-1", "acct-2"])
        self.assertEqual(auth_store.bound, ("session:a", "acct-2"))
        self.assertEqual(handler._send_upstream_headers.call_count, 1)
        written = b"".join(call.args[0] for call in handler._write_bytes.call_args_list)
        self.assertIn(b"ok", written)
        self.assertNotIn(b"busy", written)

    def test_request_log_redacts_account_id_and_sensitive_query(self) -> None:
        handler = self.make_handler()
        handler.address_string = lambda: "127.0.0.1"  # type: ignore[method-assign]

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            handler.log_message(
                '"GET /accounts/acct-secret/v1/models?api_key=sk-secret&safe=1 HTTP/1.1" 200 -'
            )

        log = stderr.getvalue()
        self.assertIn("/accounts/<redacted>/v1/models?api_key=<redacted>&safe=1", log)
        self.assertIn("HTTP/1.1", log)
        self.assertNotIn("acct-secret", log)
        self.assertNotIn("sk-secret", log)

    def test_quota_timeout_is_local_to_quota_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LauncherCase().make_manager(Path(tmp))
            with (
                mock.patch.object(bridgedeck, "tcp_open", return_value=True),
                mock.patch.object(bridgedeck, "read_local_url", side_effect=TimeoutError("proxy timeout")),
            ):
                result = manager._fetch_quota({"account_id": "acct-1", "email": "person@example.com"})

        self.assertEqual(result["quota_status"], "network_error")
        self.assertIn("TimeoutError", result["error"])

    def test_repair_quota_query_does_not_restart_running_bridge_on_quota_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LauncherCase().make_manager(Path(tmp))
            with (
                mock.patch.object(bridgedeck, "tcp_open", return_value=True),
                mock.patch.object(
                    manager,
                    "quotas",
                    return_value={
                        "ok": True,
                        "quotas": [{"account_id": "acct-1", "quota_status": "network_error"}],
                    },
                ),
                mock.patch.object(manager, "control_local_bridge") as control,
                mock.patch.object(manager, "services", return_value={"services": {}}),
            ):
                result = manager.repair_quota_query()

        control.assert_not_called()
        self.assertIn("未重启 Local Bridge", result["actions"][0])

    def test_bridge_state_reads_last_stream_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "updated_at": 123,
                        "last_stream_error": {
                            "account_id": "acct-1",
                            "model": "gpt-5.5",
                            "request_id": "bridge-test",
                            "duration_ms": 5,
                            "error_type": "RemoteProtocolError",
                            "error": "incomplete chunked read",
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = bridgedeck.read_local_bridge_state(state_path)

        self.assertEqual(payload["last_stream_error"]["error_type"], "RemoteProtocolError")
        self.assertEqual(payload["last_stream_error"]["request_id"], "bridge-test")


class ServerCase(unittest.TestCase):
    def start_server(self, *, allow_sensitive: bool = True, allow_remote_access: bool = False):
        manager = FakeManager()
        handler = bridgedeck.build_handler(
            manager,
            "test-token",
            "test-nonce",
            allow_sensitive=allow_sensitive,
            allow_remote_access=allow_remote_access,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, manager

    def request(
        self,
        server: ThreadingHTTPServer,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        url = f"http://127.0.0.1:{server.server_port}{path}"
        data = None
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
        elif isinstance(body, bytes):
            data = body
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Host", "127.0.0.1")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return response.status, payload
        except urllib.error.HTTPError as exc:
            with exc:
                payload = json.loads(exc.read().decode("utf-8"))
                return exc.code, payload

    def test_data_requires_valid_csrf_token(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(server, "/api/data")

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Invalid CSRF token")

    def test_data_can_include_secrets_only_when_allowed(self) -> None:
        server, _ = self.start_server(allow_sensitive=True)

        status, payload = self.request(
            server,
            "/api/data?include_secrets=1",
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["providers"][0]["auth_token"], "full-token")

    def test_html_uses_csp_and_no_frame_headers(self) -> None:
        server, _ = self.start_server()
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/")
        request.add_header("Host", "127.0.0.1")

        with urllib.request.urlopen(request, timeout=5) as response:
            html = response.read().decode("utf-8")
            csp = response.headers["Content-Security-Policy"]

        self.assertIn('nonce="test-nonce"', html)
        self.assertIn("script-src 'nonce-test-nonce'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_daily_ui_has_separate_account_selectors(self) -> None:
        server, _ = self.start_server()
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/")
        request.add_header("Host", "127.0.0.1")

        with urllib.request.urlopen(request, timeout=5) as response:
            html = response.read().decode("utf-8")

        self.assertIn('id="simpleClaudeAccount"', html)
        self.assertIn('id="simpleCliAccount"', html)
        self.assertIn('id="simpleDefaultAccount"', html)
        self.assertIn('id="simpleClaudeActual"', html)
        self.assertIn('id="simpleCliActual"', html)
        self.assertIn('id="simpleDesktopActual"', html)
        self.assertIn('id="simpleDefaultActual"', html)
        self.assertIn("button:disabled", html)
        self.assertIn("刷新中...", html)
        self.assertIn("refreshData(true)", html)
        self.assertIn("单独 Codex CLI", html)
        self.assertIn("全局 Codex CLI", html)
        self.assertIn("codex-current.command", html)
        self.assertIn("OMC/tmux 已接管 codex", html)
        self.assertIn("当前实际", html)
        self.assertIn('id="autoSwitchEnabled"', html)
        self.assertIn("OpenAI 自动切换", html)
        self.assertIn("为新账号创建 Local Codex Bridge", html)
        self.assertIn('id="apiAccessCard"', html)
        self.assertIn('id="simpleApiAccount"', html)
        self.assertIn("POST /v1/messages", html)
        self.assertIn("POST /v1/chat/completions", html)
        self.assertIn("GET /v1/models", html)
        self.assertIn("sk-bridgedeck-local-placeholder", html)
        self.assertIn("ANTHROPIC_BASE_URL", html)
        self.assertIn("ANTHROPIC_MODEL=gpt-5.5", html)
        self.assertIn("ANTHROPIC_DEFAULT_HAIKU_MODEL=gpt-5.3-codex-spark", html)
        self.assertIn("ANTHROPIC_DEFAULT_SONNET_MODEL=gpt-5.3-codex", html)
        self.assertIn("ANTHROPIC_DEFAULT_OPUS_MODEL=gpt-5.5", html)
        self.assertIn("claude-haiku-4-5", html)
        self.assertIn("claude-sonnet-4-6", html)
        self.assertIn("claude-opus-4-7", html)
        self.assertIn("Desktop Gateway", html)
        self.assertIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000", html)
        self.assertIn("272k context / 128k max output", html)
        self.assertIn("copy-api-base-url", html)
        self.assertIn("copy-claude-env", html)
        self.assertIn('id="bridgeModel"', html)
        self.assertIn('id="modelContextTokens"', html)
        self.assertIn('data-action="compact-preset-model"', html)
        self.assertIn("context unknown", html)
        self.assertIn('id="compactWindow"', html)
        self.assertIn('data-action="compact-preset-1m"', html)
        self.assertIn('data-action="save-compact-selected"', html)
        self.assertIn('data-action="sync-common-env-selected"', html)
        self.assertIn('data-action="stop-bridgedeck-ui"', html)
        self.assertIn("只停 8899，不影响 8876 Local Bridge", html)
        self.assertIn('id="pluginSyncStatus"', html)
        self.assertIn('data-action="extract-safe-common-config"', html)
        self.assertIn('data-action="sync-claude-plugins"', html)
        self.assertIn('data-action="preview-bridge-dedupe"', html)
        self.assertIn('data-action="apply-bridge-dedupe"', html)
        self.assertIn('data-action="proxy-diagnosis"', html)
        self.assertIn('id="proxyDiagnosis"', html)
        self.assertIn('id="anthropicAccessToken"', html)
        self.assertIn('id="anthropicAccessBaseUrl"', html)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", html)
        self.assertIn("ANTHROPIC_BASE_URL", html)
        self.assertIn('data-action="copy-anthropic-token"', html)
        self.assertIn('data-action="copy-anthropic-base-url"', html)
        self.assertIn('data-action="copy-anthropic-env"', html)
        self.assertIn('const LOCAL_BRIDGE_BASE_URL = "http://127.0.0.1:8876"', html)
        self.assertIn("`${LOCAL_BRIDGE_BASE_URL}/accounts/${encodeURIComponent(item.account_id)}/v1`", html)
        self.assertIn("return apiAccessBaseUrl(item);", html)
        self.assertNotIn("__LOCAL_BRIDGE_BASE_URL__", html)
        self.assertIn('id="actualCurrentAccounts"', html)
        self.assertIn("const actualGlobalAccount = data.codex_desktop", html)
        self.assertIn("row.account_id === desktopAccount ? '默认' : '备用'", html)
        self.assertIn("固定入口/OMC/tmux", html)
        self.assertIn("~/.codex/auth.json token", html)
        self.assertIn("CC Switch Codex OAuth Provider", html)
        self.assertIn("CC Switch 当前", html)
        self.assertIn("renderAccounts(data);", html)
        self.assertIn("Spark", html)
        self.assertNotIn('id="simpleAccount"', html)
        self.assertNotIn("今天用哪个账号", html)
        self.assertNotIn("默认 Codex Desktop/CLI：只检测", html)
        self.assertNotIn("只检测，不由 BridgeDeck 接管", html)

    def test_quota_summary_marks_limit_states(self) -> None:
        payload = {
            "plan_type": "plus",
            "rate_limit": {
                "limit_reached": False,
                "primary_window": {"used_percent": 0, "limit_window_seconds": 18000},
                "secondary_window": {"used_percent": 84, "limit_window_seconds": 604800},
            },
        }

        result = bridgedeck.summarize_quota_payload(payload)

        self.assertEqual(result["quota_status"], "near_limit")
        self.assertEqual(result["windows"][0]["name"], "5小时")
        self.assertEqual(result["windows"][1]["name"], "7天")
        self.assertEqual(result["capacity_factor"], 1)
        self.assertEqual(result["effective_remaining_units"], 16.0)

    def test_quota_summary_extracts_spark_additional_limit(self) -> None:
        payload = {
            "plan_type": "pro",
            "rate_limit": {
                "limit_reached": False,
                "primary_window": {"used_percent": 10, "limit_window_seconds": 18000},
            },
            "additional_rate_limits": [
                {
                    "limit_name": "GPT-5.3-Codex-Spark",
                    "metered_feature": "codex_bengalfox",
                    "rate_limit": {
                        "allowed": True,
                        "limit_reached": False,
                        "primary_window": {"used_percent": 2, "limit_window_seconds": 18000},
                        "secondary_window": {"used_percent": 28, "limit_window_seconds": 604800},
                    },
                }
            ],
        }

        result = bridgedeck.summarize_quota_payload(payload)

        self.assertEqual(result["additional_limits"][0]["limit_name"], "GPT-5.3-Codex-Spark")
        self.assertEqual(result["additional_limits"][0]["quota_status"], "ok")
        self.assertEqual(result["additional_limits"][0]["windows"][1]["used_percent"], 28)

    def test_read_local_url_disables_proxy_lookup(self) -> None:
        class FakeResponse:
            def __enter__(self) -> io.BytesIO:
                return io.BytesIO(b'{"ok": true}')

            def __exit__(self, *_: Any) -> None:
                return None

        class FakeOpener:
            def open(self, request: urllib.request.Request, *, timeout: float) -> FakeResponse:
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        fake_opener = FakeOpener()
        seen: dict[str, Any] = {}

        def fake_build_opener(handler: Any) -> FakeOpener:
            seen["handler"] = handler
            return fake_opener

        with mock.patch.object(urllib.request, "build_opener", side_effect=fake_build_opener):
            body = bridgedeck.read_local_url("http://127.0.0.1:8876/quota", timeout=3, max_bytes=100)

        self.assertEqual(body, b'{"ok": true}')
        self.assertIsInstance(seen["handler"], urllib.request.ProxyHandler)
        self.assertEqual(getattr(seen["handler"], "proxies", None), {})
        self.assertEqual(fake_opener.timeout, 3)
        self.assertEqual(fake_opener.request.headers["Connection"], "close")

    def test_mask_url_credentials_redacts_proxy_password(self) -> None:
        self.assertEqual(
            bridgedeck.mask_url_credentials("http://user:pass@127.0.0.1:1087"),
            "http://<redacted>@127.0.0.1:1087",
        )
        self.assertEqual(
            bridgedeck.mask_url_credentials("http://127.0.0.1:1087"),
            "http://127.0.0.1:1087",
        )

    def test_remote_mode_blocks_secret_reveal(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(
            server,
            "/api/data?include_secrets=1",
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Secret display is disabled for remote mode")

    def test_remote_mode_blocks_write_apis(self) -> None:
        server, manager = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(
            server,
            "/api/set-current",
            method="POST",
            body={"provider_id": "provider-1"},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Write APIs are disabled for remote mode")
        self.assertFalse(manager.set_current_called)

    def test_provider_compact_endpoint_accepts_1m_window(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/provider-compact",
            method="POST",
            body={
                "provider_id": "provider-1",
                "model_config": {"model": "gpt-5.5"},
                "compact_config": {"enabled": True, "window_tokens": "1000000", "threshold_percent": "80"},
            },
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["compact_config"]["window_tokens"], "1000000")
        self.assertEqual(payload["model_config"]["model"], "gpt-5.5")
        self.assertEqual(payload["model_config"]["context_tokens"], "272000")

    def test_sync_common_env_endpoint_uses_selected_provider(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/sync-common-env",
            method="POST",
            body={"provider_id": "provider-1"},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["source_provider_id"], "provider-1")
        self.assertIn("HUB_CLAUDE_MEM", payload["env_keys"])

    def test_sync_claude_plugins_endpoint_returns_status(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/sync-claude-plugins",
            method="POST",
            body={},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["installed_count"], 7)

    def test_extract_safe_common_config_endpoint_returns_status(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/extract-safe-common-config",
            method="POST",
            body={},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("ENABLE_TOOL_SEARCH", payload["env_keys"])

    def test_proxy_diagnosis_endpoint_returns_status(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/proxy-diagnosis",
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["proxy"]["port"], 1087)

    def test_dedupe_bridge_providers_endpoint_defaults_to_preview(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/dedupe-bridge-providers",
            method="POST",
            body={},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertFalse(payload["apply"])
        self.assertEqual(payload["deleted"], [])
        self.assertEqual(payload["plan"][0]["delete"][0]["id"], "provider-old")

    def test_remote_mode_redacts_snapshot_fields(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(
            server,
            "/api/data",
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["accounts"][0]["account_id"], "01234567...cdef")
        self.assertEqual(payload["accounts"][0]["email"], "pe***n@example.com")
        self.assertEqual(payload["accounts"][0]["default_cli_home"], "~/.codex-cli-person")
        self.assertEqual(payload["providers"][0]["account_id"], "01234567...cdef")
        self.assertIn("/accounts/<redacted>", payload["providers"][0]["base_url"])
        self.assertEqual(payload["cli_homes"][0]["path"], "~/.codex")

    def test_cross_site_fetch_metadata_is_rejected(self) -> None:
        server, manager = self.start_server()

        status, payload = self.request(
            server,
            "/api/set-current",
            method="POST",
            body={"provider_id": "provider-1"},
            headers={"Sec-Fetch-Site": "cross-site", "X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Invalid fetch metadata")
        self.assertFalse(manager.set_current_called)

    def test_post_rejects_non_loopback_origin(self) -> None:
        server, manager = self.start_server()

        status, payload = self.request(
            server,
            "/api/set-current",
            method="POST",
            body={"provider_id": "provider-1"},
            headers={"Origin": "https://example.com", "X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Invalid Origin header")
        self.assertFalse(manager.set_current_called)

    def test_post_rejects_large_request_body(self) -> None:
        server, manager = self.start_server()

        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest("POST", "/api/set-current")
        conn.putheader("Host", "127.0.0.1")
        conn.putheader("X-CCSBT-Token", "test-token")
        conn.putheader("Content-Length", str(bridgedeck.MAX_REQUEST_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        status = response.status
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(status, 413)
        self.assertEqual(payload["error"], "Request body too large")
        self.assertFalse(manager.set_current_called)

    def test_invalid_host_header_is_rejected(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/data",
            headers={"Host": "example.com", "X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Invalid Host header")

    def test_health_requires_csrf_token(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(server, "/api/health")

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Invalid CSRF token")

    def test_services_reports_local_bridge_state(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(server, "/api/services", headers={"X-CCSBT-Token": "test-token"})

        self.assertEqual(status, 200)
        self.assertTrue(payload["services"]["local_bridge"]["running"])
        self.assertIn("processes", payload["services"]["local_bridge"])

    def test_local_bridge_control_requires_local_write_mode(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(
            server,
            "/api/local-bridge-control",
            method="POST",
            body={"action": "restart"},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Write APIs are disabled for remote mode")

    def test_ui_control_shutdown_is_local_only_and_async(self) -> None:
        server, _ = self.start_server()

        with mock.patch.object(server, "shutdown") as shutdown:
            status, payload = self.request(
                server,
                "/api/ui-control",
                method="POST",
                body={"action": "shutdown"},
                headers={"X-CCSBT-Token": "test-token"},
            )
            time.sleep(0.35)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("Local Bridge 保持运行", payload["message"])
        shutdown.assert_called_once()

    def test_ui_control_requires_local_write_mode(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(
            server,
            "/api/ui-control",
            method="POST",
            body={"action": "shutdown"},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Write APIs are disabled for remote mode")

    def test_remote_services_redacts_process_paths_and_proxy(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(server, "/api/services", headers={"X-CCSBT-Token": "test-token"})

        local_bridge = payload["services"]["local_bridge"]
        self.assertEqual(status, 200)
        self.assertNotIn("processes", local_bridge)
        self.assertNotIn("script", local_bridge)
        self.assertNotIn("log_path", local_bridge)
        self.assertEqual(local_bridge["upstream_proxy"], "<redacted>")
        self.assertEqual(local_bridge["last_stream_error"]["account_id"], "01234567...cdef")
        self.assertNotIn("/Users/person", json.dumps(payload))
        self.assertNotIn("user:pass", json.dumps(payload))

    def test_remote_proxy_diagnosis_redacts_proxy_url(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(server, "/api/proxy-diagnosis", headers={"X-CCSBT-Token": "test-token"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["proxy"]["url"], "<redacted>")

    def test_detect_codex_proxy_url_prefers_codex_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / ".codex"
            codex_home.mkdir(parents=True)
            (codex_home / ".env").write_text('HTTPS_PROXY="http://127.0.0.1:1087"\n', encoding="utf-8")

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home),
                mock.patch.dict(bridgedeck.os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9999"}, clear=False),
            ):
                value, source = bridgedeck.detect_codex_proxy_url()

        self.assertEqual(value, "http://127.0.0.1:1087")
        self.assertEqual(source, str(codex_home / ".env"))

    def test_probe_remote_url_uses_explicit_proxy_handler(self) -> None:
        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: Any) -> None:
                return None

            def read(self, _max_bytes: int) -> bytes:
                return b'{"ok":true}'

            def getcode(self) -> int:
                return 401

        class FakeOpener:
            def open(self, request: urllib.request.Request, *, timeout: float) -> FakeResponse:
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        fake_opener = FakeOpener()
        seen: dict[str, Any] = {}

        def fake_build_opener(handler: Any) -> FakeOpener:
            seen["handler"] = handler
            return fake_opener

        with mock.patch.object(urllib.request, "build_opener", side_effect=fake_build_opener):
            result = bridgedeck.probe_remote_url(
                "https://api.openai.com/v1/models",
                proxy_url="http://127.0.0.1:1087",
                headers={"Accept": "application/json"},
            )

        self.assertTrue(result["reached"])
        self.assertEqual(result["status_code"], 401)
        self.assertIsInstance(seen["handler"], urllib.request.ProxyHandler)
        self.assertEqual(getattr(seen["handler"], "proxies", None), {"http": "http://127.0.0.1:1087", "https": "http://127.0.0.1:1087"})
        self.assertEqual(fake_opener.request.headers["Connection"], "close")


class LauncherCase(unittest.TestCase):
    def make_manager(self, root: Path) -> bridgedeck.BridgeManager:
        auth_store = root / ".cc-switch" / "codex_oauth_auth.json"
        auth_store.parent.mkdir(parents=True, exist_ok=True)
        auth_store.write_text(
            json.dumps(
                {
                    "accounts": {
                        "acct-1": {
                            "email": "person@example.com",
                            "refresh_token": "secret-refresh-token",
                            "access_token": "secret-access-token",
                            "id_token": "secret-id-token",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return bridgedeck.BridgeManager(
            bridgedeck.ManagerPaths(
                db=root / ".cc-switch" / "cc-switch.db",
                settings=root / ".cc-switch" / "settings.json",
                auth_store=auth_store,
            )
        )

    def test_create_cli_launcher_does_not_refresh_or_write_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            target = root / ".codex-cli-person"
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            with (
                mock.patch.object(bridgedeck.Path, "home", return_value=root),
                mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir),
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", root / ".codex"),
            ):
                result = manager.create_cli_launcher("acct-1", str(target), "person")

            self.assertTrue(result["launcher_only"])
            self.assertFalse(hasattr(manager, "_refresh_codex_token"))
            self.assertFalse((target / "auth.json").exists())
            launcher = Path(result["launcher"])
            body = launcher.read_text(encoding="utf-8")
            self.assertIn('export OPENAI_API_KEY="local-bridge"', body)
            self.assertIn('base_url="http://127.0.0.1:8876/accounts/acct-1/v1"', body)
            self.assertNotIn("secret-refresh-token", body)
            self.assertNotIn("secret-access-token", body)
            self.assertNotIn("secret-id-token", body)

    def test_current_codex_launcher_is_not_dedicated_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            launcher_dir.mkdir(parents=True)
            current = launcher_dir / "codex-current.command"
            dedicated = launcher_dir / "codex-person.command"
            current.write_text(
                '#!/bin/zsh\nexport OPENAI_API_KEY="local-bridge"\n'
                'exec "/opt/homebrew/bin/codex" -c \'base_url="http://127.0.0.1:8876/accounts/acct-1/v1"\' "$@"\n',
                encoding="utf-8",
            )
            dedicated.write_text(
                '#!/bin/zsh\nexport CODEX_HOME="/tmp/person"\nexport OPENAI_API_KEY="local-bridge"\n'
                'exec "/opt/homebrew/bin/codex" -c \'base_url="http://127.0.0.1:8876/accounts/acct-1/v1"\' "$@"\n',
                encoding="utf-8",
            )

            with mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir):
                launchers = manager._known_cli_launchers()
                matrix = manager._account_matrix(
                    [{"account_id": "acct-1", "email": "person@example.com"}],
                    [],
                    [],
                    [],
                    [item for item in launchers if item["is_current_launcher"]],
                    {},
                )

            by_name = {item["name"]: item for item in launchers}
            self.assertTrue(by_name["current"]["is_current_launcher"])
            self.assertEqual(by_name["current"]["launcher_role"], "current")
            self.assertFalse(by_name["person"]["is_current_launcher"])
            self.assertEqual(by_name["person"]["launcher_role"], "dedicated")
            self.assertEqual(matrix[0]["cli_launchers"], [])
            self.assertIn("missing_cli_launcher", matrix[0]["risk_flags"])

    def test_account_matrix_uses_bridge_url_account_when_provider_binding_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))
            with mock.patch.object(bridgedeck, "tcp_open", return_value=True):
                matrix = manager._account_matrix(
                    [{"account_id": "acct-1", "email": "person@example.com"}],
                    [
                        {
                            "name": "Local Codex Bridge - Pro",
                            "is_current": True,
                            "account_id": "",
                            "base_url": "http://127.0.0.1:8876/accounts/acct-1",
                        }
                    ],
                    [],
                    [],
                    [{"account_id": "acct-1", "is_current_launcher": False}],
                    {},
                )

        self.assertTrue(matrix[0]["claude_current"])
        self.assertEqual(matrix[0]["claude_providers"], ["Local Codex Bridge - Pro"])

    def test_write_omc_codex_shims_uses_current_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            shim_paths = (root / ".codebuddy" / "bin" / "codex", root / ".workbuddy" / "bin" / "codex")
            zprofile = root / ".zprofile"
            zprofile.write_text('eval "$(/opt/homebrew/bin/brew shellenv)"\n', encoding="utf-8")
            with mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir):
                launcher_dir.mkdir(parents=True)
                current = launcher_dir / "codex-current.command"
                current.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
                with (
                    mock.patch.object(bridgedeck, "DEFAULT_OMC_CODEX_SHIM_PATHS", shim_paths),
                    mock.patch.object(bridgedeck, "DEFAULT_ZPROFILE_PATH", zprofile),
                ):
                    result = manager.write_omc_codex_shims()
                    path_result = manager.ensure_omc_codex_path()

            self.assertEqual(result["paths"], [str(path) for path in shim_paths])
            self.assertTrue(path_result["changed"])
            self.assertIn(str(launcher_dir / "bin"), zprofile.read_text(encoding="utf-8"))
            for path in shim_paths:
                body = path.read_text(encoding="utf-8")
                self.assertIn(bridgedeck.MANAGED_CODEX_SHIM_MARKER, body)
                self.assertIn(str(current), body)
                self.assertNotIn("secret-refresh-token", body)

    def test_write_omc_codex_shims_refuses_unmanaged_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            shim_path = root / ".codebuddy" / "bin" / "codex"
            shim_path.parent.mkdir(parents=True)
            shim_path.write_text("#!/bin/zsh\nexec /opt/homebrew/bin/codex \"$@\"\n", encoding="utf-8")
            with mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir):
                launcher_dir.mkdir(parents=True)
                (launcher_dir / "codex-current.command").write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
                with mock.patch.object(bridgedeck, "DEFAULT_OMC_CODEX_SHIM_PATHS", (shim_path,)):
                    with self.assertRaises(ValueError):
                        manager.write_omc_codex_shims()

            self.assertIn("/opt/homebrew/bin/codex", shim_path.read_text(encoding="utf-8"))

    def test_find_local_bridge_python_prefers_managed_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python_bin = root / ".cc-switch" / "bridgedeck-bridge-venv" / "bin" / "python"
            python_bin.parent.mkdir(parents=True)
            python_bin.write_text("#!/bin/sh\n", encoding="utf-8")

            with (
                mock.patch.object(bridgedeck.Path, "home", return_value=root),
                mock.patch.object(bridgedeck, "which", return_value="/missing/python3"),
                mock.patch.object(bridgedeck.sys, "executable", str(root / "missing-executable")),
                mock.patch.object(
                    bridgedeck,
                    "python_supports_local_bridge",
                    side_effect=lambda value: value == str(python_bin),
                ),
                mock.patch.dict(bridgedeck.os.environ, {"BRIDGEDECK_BRIDGE_PYTHON": ""}),
            ):
                selected = bridgedeck.find_local_bridge_python()

            self.assertEqual(selected, str(python_bin))

    def test_local_bridge_provider_payload_does_not_use_codex_oauth_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, meta = manager._build_provider_payload(
                "acct-1",
                settings_config={"env": {}},
                meta={"providerType": "codex_oauth", "authBinding": {"authProvider": "codex_oauth"}},
            )

            env = settings["env"]
            self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:8876/accounts/acct-1")
            self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "local-bridge")
            self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "gpt-5.3-codex-spark")
            self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "gpt-5.3-codex")
            self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "gpt-5.5")
            self.assertEqual(meta["apiFormat"], "openai_responses")
            self.assertEqual(meta["codexOauthTransport"], "local_bridge")
            self.assertEqual(meta["authBinding"]["authProvider"], "codex_oauth")
            self.assertTrue(meta["usage_script"]["enabled"])
            self.assertEqual(meta["usage_script"]["templateType"], "custom")
            self.assertIn("http://127.0.0.1:8876/accounts/acct-1/quota", meta["usage_script"]["code"])
            self.assertIn('planName: "five_hour"', meta["usage_script"]["code"])
            self.assertIn('planName: "weekly_limit"', meta["usage_script"]["code"])
            self.assertNotIn("providerType", meta)

    def test_provider_payload_applies_adjustable_compact_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={"env": {}},
                compact_config={"enabled": True, "window_tokens": "1000000", "threshold_percent": "85"},
            )

            env = settings["env"]
            self.assertEqual(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "1000000")
            self.assertEqual(env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"], "85")

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={
                    "env": {
                        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "220000",
                        "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80",
                    }
                },
                compact_config={"enabled": False},
            )

            self.assertNotIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", settings["env"])
            self.assertNotIn("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", settings["env"])

    def test_provider_payload_applies_selected_bridge_model_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={"env": {}},
                model_config={"model": "GPT-5.5"},
            )

            env = settings["env"]
            self.assertEqual(env["ANTHROPIC_MODEL"], "gpt-5.5")
            self.assertEqual(env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "272000")

    def test_unknown_bridge_model_does_not_invent_context(self) -> None:
        normalized = bridgedeck.normalize_bridge_model_config({"model": "gpt-5.4"})

        self.assertEqual(normalized["model"], "gpt-5.4")
        self.assertEqual(normalized["context_tokens"], "")
        self.assertEqual(normalized["max_output_tokens"], "")

    def test_provider_payload_normalizes_gpt_model_env_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={"env": {"ANTHROPIC_DEFAULT_HAIKU_MODEL": "GPT-5.3-Codex-Spark"}},
            )

            self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "gpt-5.3-codex-spark")

    def test_sync_common_env_preserves_provider_scoped_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        name TEXT,
                        app_type TEXT,
                        settings_config TEXT,
                        sort_index INTEGER
                    )
                    """
                )
                rows = [
                    (
                        "source",
                        "Local Codex Bridge - Source",
                        {
                            "env": {
                                "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-source",
                                "ANTHROPIC_AUTH_TOKEN": "source-token",
                                "ANTHROPIC_MODEL": "GPT-5.5",
                                "HUB_CLAUDE_MEM": "1",
                                "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000",
                                "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "220000",
                            }
                        },
                        1,
                    ),
                    (
                        "target",
                        "Local Codex Bridge - Target",
                        {
                            "env": {
                                "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-target",
                                "ANTHROPIC_AUTH_TOKEN": "target-token",
                                "TARGET_ONLY": "keep",
                            }
                        },
                        2,
                    ),
                    (
                        "external",
                        "External",
                        {
                            "env": {
                                "ANTHROPIC_BASE_URL": "https://example.com",
                                "ANTHROPIC_AUTH_TOKEN": "external-token",
                            }
                        },
                        3,
                    ),
                ]
                for provider_id, name, settings, sort_index in rows:
                    conn.execute(
                        "INSERT INTO providers VALUES (?, ?, ?, ?, ?)",
                        (provider_id, name, "claude", json.dumps(settings), sort_index),
                    )
                conn.commit()
            finally:
                conn.close()

            result = manager.sync_common_env_to_bridge_providers("source")

            self.assertTrue(result["ok"])
            self.assertIn("HUB_CLAUDE_MEM", result["env_keys"])
            conn = sqlite3.connect(manager.paths.db)
            try:
                loaded = {
                    row[0]: json.loads(row[1])
                    for row in conn.execute("SELECT id, settings_config FROM providers")
                }
            finally:
                conn.close()
            source_env = loaded["source"]["env"]
            target_env = loaded["target"]["env"]
            external_env = loaded["external"]["env"]
            self.assertEqual(source_env["ANTHROPIC_MODEL"], "gpt-5.5")
            self.assertEqual(source_env["ANTHROPIC_AUTH_TOKEN"], "source-token")
            self.assertEqual(target_env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:8876/accounts/acct-target")
            self.assertEqual(target_env["ANTHROPIC_AUTH_TOKEN"], "target-token")
            self.assertEqual(target_env["HUB_CLAUDE_MEM"], "1")
            self.assertNotIn("ANTHROPIC_MODEL", target_env)
            self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", target_env)
            self.assertNotIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", target_env)
            self.assertEqual(target_env["TARGET_ONLY"], "keep")
            self.assertEqual(external_env["ANTHROPIC_AUTH_TOKEN"], "external-token")

    def test_extract_safe_claude_common_config_filters_provider_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            common = root / ".ccswitch-common-config.json"
            settings = root / ".claude" / "settings.json"
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
                conn.execute(
                    "INSERT INTO settings VALUES (?, ?)",
                    (
                        "common_config_claude",
                        json.dumps(
                            {
                                "env": {
                                    "ANTHROPIC_AUTH_TOKEN": "old-secret",
                                    "ANTHROPIC_MODEL": "old-model",
                                    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000",
                                    "ENABLE_TOOL_SEARCH": "false",
                                }
                            }
                        ),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            settings.parent.mkdir(parents=True, exist_ok=True)
            common.write_text(
                json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "https://old.example.com",
                            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "220000",
                            "ENABLE_TOOL_SEARCH": "false",
                        },
                        "enabledPlugins": {"old@old": True},
                    }
                ),
                encoding="utf-8",
            )
            settings.write_text(
                json.dumps(
                    {
                        "hooks": {"Stop": []},
                        "permissions": {"allow": ["Bash(ls:*)"]},
                        "enabledPlugins": {"caveman@caveman": True},
                        "env": {
                            "ANTHROPIC_BASE_URL": "https://provider.example.com",
                            "ANTHROPIC_AUTH_TOKEN": "secret",
                            "ANTHROPIC_MODEL": "provider-model",
                            "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000",
                            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000",
                            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80",
                            "ENABLE_TOOL_SEARCH": "true",
                            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CCSWITCH_COMMON_CONFIG_PATH", common),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_SETTINGS_PATH", settings),
            ):
                result = manager.extract_safe_claude_common_config()

            self.assertTrue(result["changed"])
            loaded = json.loads(common.read_text(encoding="utf-8"))
            self.assertEqual(loaded["hooks"], {"Stop": []})
            self.assertEqual(loaded["permissions"], {"allow": ["Bash(ls:*)"]})
            self.assertEqual(loaded["enabledPlugins"], {"caveman@caveman": True})
            self.assertEqual(
                loaded["env"],
                {
                    "ENABLE_TOOL_SEARCH": "true",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                },
            )
            self.assertNotIn("ANTHROPIC_BASE_URL", loaded["env"])
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", loaded["env"])
            self.assertNotIn("ANTHROPIC_MODEL", loaded["env"])
            self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", loaded["env"])
            self.assertNotIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", loaded["env"])
            self.assertNotIn("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", loaded["env"])
            conn = sqlite3.connect(manager.paths.db)
            try:
                db_common = json.loads(
                    conn.execute("SELECT value FROM settings WHERE key = 'common_config_claude'").fetchone()[0]
                )
            finally:
                conn.close()
            self.assertEqual(db_common["env"]["ENABLE_TOOL_SEARCH"], "true")
            self.assertEqual(db_common["env"]["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", db_common["env"])
            self.assertNotIn("ANTHROPIC_MODEL", db_common["env"])
            self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", db_common["env"])

    def test_sync_claude_enabled_plugins_merges_installed_into_common_and_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            common = root / ".ccswitch-common-config.json"
            settings = root / ".claude" / "settings.json"
            installed = root / ".claude" / "plugins" / "installed_plugins.json"
            common.write_text(json.dumps({"enabledPlugins": {"claude-hud@claude-hud": True}}), encoding="utf-8")
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({"enabledPlugins": {"claude-mem@thedotmack": True}}), encoding="utf-8")
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "claude-hud@claude-hud": [{"scope": "user"}],
                            "claude-mem@thedotmack": [{"scope": "user"}],
                            "caveman@caveman": [{"scope": "user"}],
                        }
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CCSWITCH_COMMON_CONFIG_PATH", common),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_SETTINGS_PATH", settings),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_INSTALLED_PLUGINS_PATH", installed),
            ):
                result = manager.sync_claude_enabled_plugins()

            self.assertTrue(result["changed"])
            self.assertEqual(result["added"], ["caveman@caveman"])
            common_enabled = json.loads(common.read_text(encoding="utf-8"))["enabledPlugins"]
            settings_enabled = json.loads(settings.read_text(encoding="utf-8"))["enabledPlugins"]
            self.assertEqual(common_enabled, settings_enabled)
            self.assertTrue(common_enabled["caveman@caveman"])
            self.assertTrue(result["backups"])

    def test_sync_claude_enabled_plugins_preserves_explicit_disabled_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            common = root / ".ccswitch-common-config.json"
            settings = root / ".claude" / "settings.json"
            installed = root / ".claude" / "plugins" / "installed_plugins.json"
            common.write_text(json.dumps({"enabledPlugins": {"caveman@caveman": False}}), encoding="utf-8")
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({"enabledPlugins": {}}), encoding="utf-8")
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_text(
                json.dumps({"plugins": {"caveman@caveman": [{"scope": "user"}]}}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CCSWITCH_COMMON_CONFIG_PATH", common),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_SETTINGS_PATH", settings),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_INSTALLED_PLUGINS_PATH", installed),
            ):
                result = manager.sync_claude_enabled_plugins()

            self.assertTrue(result["changed"])
            self.assertEqual(result["added"], [])
            self.assertFalse(json.loads(common.read_text(encoding="utf-8"))["enabledPlugins"]["caveman@caveman"])
            self.assertFalse(json.loads(settings.read_text(encoding="utf-8"))["enabledPlugins"]["caveman@caveman"])

    def test_create_provider_reuses_existing_bridge_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        name TEXT,
                        app_type TEXT,
                        settings_config TEXT,
                        meta TEXT,
                        provider_type TEXT,
                        sort_index INTEGER
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "existing",
                        "Local Codex Bridge - Pro 20x",
                        "claude",
                        json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1"}}),
                        json.dumps({}),
                        None,
                        1,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            result = manager.create_or_update_provider("acct-1", "Local Codex Bridge - person", False)

            self.assertEqual(result["provider_id"], "existing")
            self.assertEqual(result["provider_name"], "Local Codex Bridge - Pro 20x")
            conn = sqlite3.connect(manager.paths.db)
            try:
                count = conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 1)

    def test_create_provider_does_not_default_compact_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        name TEXT,
                        app_type TEXT,
                        settings_config TEXT,
                        meta TEXT,
                        provider_type TEXT,
                        sort_index INTEGER
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            result = manager.create_or_update_provider("acct-1", "Local Codex Bridge - person", False)

            conn = sqlite3.connect(manager.paths.db)
            try:
                settings = json.loads(
                    conn.execute("SELECT settings_config FROM providers WHERE id = ?", (result["provider_id"],)).fetchone()[0]
                )
            finally:
                conn.close()
            self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", settings["env"])
            self.assertNotIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", settings["env"])
            self.assertNotIn("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", settings["env"])

    def test_dedupe_bridge_providers_switches_current_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            manager.paths.settings.parent.mkdir(parents=True, exist_ok=True)
            manager.paths.settings.write_text(json.dumps({"currentProviderClaude": "old"}), encoding="utf-8")
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        name TEXT,
                        app_type TEXT,
                        is_current INTEGER,
                        settings_config TEXT,
                        meta TEXT,
                        sort_index INTEGER
                    )
                    """
                )
                rows = [
                    (
                        "keep",
                        "Local Codex Bridge - Pro 20x",
                        0,
                        {
                            "env": {
                                "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                                "ANTHROPIC_AUTH_TOKEN": "keep-token",
                                "ANTHROPIC_MODEL": "gpt-5.4",
                            }
                        },
                    ),
                    (
                        "old",
                        "Local Codex Bridge - person",
                        1,
                        {
                            "env": {
                                "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                                "ANTHROPIC_AUTH_TOKEN": "old-token",
                                "ANTHROPIC_MODEL": "GPT-5.5",
                                "HUB_CLAUDE_MEM": "1",
                            }
                        },
                    ),
                    (
                        "external",
                        "MiniMax",
                        0,
                        {"env": {"ANTHROPIC_BASE_URL": "https://example.com", "ANTHROPIC_AUTH_TOKEN": "external-token"}},
                    ),
                ]
                for index, (provider_id, name, is_current, settings) in enumerate(rows, start=1):
                    conn.execute(
                        "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (provider_id, name, "claude", is_current, json.dumps(settings), json.dumps({}), index),
                    )
                conn.commit()
            finally:
                conn.close()

            preview = manager.dedupe_bridge_providers(apply=False)
            result = manager.dedupe_bridge_providers(apply=True)

            self.assertEqual(preview["plan"][0]["keep"]["id"], "keep")
            self.assertEqual(preview["plan"][0]["delete"][0]["id"], "old")
            self.assertEqual(preview["plan"][0]["switch_current_to"], "keep")
            self.assertEqual(result["deleted"][0]["id"], "old")
            self.assertEqual(json.loads(manager.paths.settings.read_text(encoding="utf-8"))["currentProviderClaude"], "keep")
            conn = sqlite3.connect(manager.paths.db)
            try:
                ids = [row[0] for row in conn.execute("SELECT id FROM providers ORDER BY id")]
                keep_settings = json.loads(conn.execute("SELECT settings_config FROM providers WHERE id = 'keep'").fetchone()[0])
                keep_current = conn.execute("SELECT is_current FROM providers WHERE id = 'keep'").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(ids, ["external", "keep"])
            self.assertEqual(keep_current, 1)
            self.assertEqual(keep_settings["env"]["ANTHROPIC_AUTH_TOKEN"], "keep-token")
            self.assertEqual(keep_settings["env"]["ANTHROPIC_MODEL"], "gpt-5.5")
            self.assertEqual(keep_settings["env"]["HUB_CLAUDE_MEM"], "1")

    def test_auto_switch_does_not_touch_third_party_current_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))
            snapshot = {
                "providers": [
                    {
                        "id": "minimax",
                        "name": "MiniMax",
                        "is_current": True,
                        "account_id": "",
                        "base_url": "https://platform.minimaxi.com",
                    },
                    {
                        "id": "plus",
                        "name": "Local Codex Bridge - Plus",
                        "is_current": False,
                        "account_id": "acct-plus",
                        "base_url": "http://127.0.0.1:8876/accounts/acct-plus",
                    },
                ],
                "current_provider_from_settings": "minimax",
                "codex_desktop": {"managed_by": "custom"},
            }
            with mock.patch.object(manager, "_load_auto_switch_config", return_value={"enabled": True, "claude": True, "default_codex": True, "priority": [], "last_result": {}}), \
                mock.patch.object(manager, "snapshot", return_value=snapshot), \
                mock.patch.object(manager, "quotas", return_value={"ok": True, "quotas": [{"account_id": "acct-plus", "quota_status": "ok", "limit_reached": False}]}), \
                mock.patch.object(manager, "set_current_provider") as set_current, \
                mock.patch.object(manager, "set_default_codex_account") as set_codex, \
                mock.patch.object(manager, "_save_auto_switch_config"):
                result = manager.run_auto_switch()

            self.assertTrue(result["ok"])
            self.assertFalse(set_current.called)
            self.assertFalse(set_codex.called)
            self.assertEqual(result["actions"][0]["reason"], "current_provider_is_not_local_bridge")

    def test_auto_switch_creates_missing_bridge_provider_only_in_bridge_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))
            snapshot = {
                "providers": [
                    {
                        "id": "current-plus",
                        "name": "Local Codex Bridge - Plus",
                        "is_current": True,
                        "account_id": "acct-plus",
                        "base_url": "http://127.0.0.1:8876/accounts/acct-plus",
                    }
                ],
                "current_provider_from_settings": "current-plus",
                "codex_desktop": {"managed_by": "custom"},
            }
            quotas = {
                "ok": True,
                "quotas": [
                    {"account_id": "acct-new-plus", "quota_status": "ok", "limit_reached": False, "plan_type": "plus"},
                    {"account_id": "acct-plus", "quota_status": "limit_reached", "limit_reached": True, "plan_type": "plus"},
                ],
            }
            snapshots = [snapshot, {**snapshot, "providers": [*snapshot["providers"], {
                "id": "created-plus",
                "name": "Local Codex Bridge - person",
                "is_current": False,
                "account_id": "acct-new-plus",
                "base_url": "http://127.0.0.1:8876/accounts/acct-new-plus",
            }]}]
            with mock.patch.object(manager, "_load_auto_switch_config", return_value={"enabled": True, "claude": True, "default_codex": False, "priority": [], "last_result": {}}), \
                mock.patch.object(manager, "snapshot", side_effect=snapshots), \
                mock.patch.object(manager, "quotas", return_value=quotas), \
                mock.patch.object(manager, "create_or_update_provider", return_value={"ok": True, "provider_id": "created-plus"}) as create_provider, \
                mock.patch.object(manager, "set_current_provider", return_value={"ok": True}) as set_current, \
                mock.patch.object(manager, "_save_auto_switch_config"):
                result = manager.run_auto_switch()

            self.assertTrue(result["ok"])
            create_provider.assert_called_once()
            self.assertEqual(create_provider.call_args.args[0], "acct-new-plus")
            set_current.assert_called_once_with("created-plus")

    def test_auto_switch_keeps_current_bridge_account_until_limit_reached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))
            snapshot = {
                "providers": [
                    {
                        "id": "current-plus",
                        "name": "Local Codex Bridge - Plus",
                        "is_current": True,
                        "account_id": "acct-plus",
                        "base_url": "http://127.0.0.1:8876/accounts/acct-plus",
                    },
                    {
                        "id": "pro-max",
                        "name": "Local Codex Bridge - Pro Max 20x",
                        "is_current": False,
                        "account_id": "acct-pro-max",
                        "base_url": "http://127.0.0.1:8876/accounts/acct-pro-max",
                    },
                ],
                "current_provider_from_settings": "current-plus",
                "codex_desktop": {"managed_by": "bridgedeck_or_local_bridge", "account_id": "acct-plus"},
            }
            quotas = {
                "ok": True,
                "quotas": [
                    {"account_id": "acct-plus", "quota_status": "near_limit", "limit_reached": False, "plan_type": "plus", "windows": [{"used_percent": 99}]},
                    {"account_id": "acct-pro-max", "quota_status": "ok", "limit_reached": False, "plan_type": "pro", "windows": [{"used_percent": 0}]},
                ],
            }
            with mock.patch.object(manager, "_load_auto_switch_config", return_value={"enabled": True, "claude": True, "default_codex": True, "priority": [], "last_result": {}}), \
                mock.patch.object(manager, "snapshot", return_value=snapshot), \
                mock.patch.object(manager, "quotas", return_value=quotas), \
                mock.patch.object(manager, "set_current_provider") as set_current, \
                mock.patch.object(manager, "set_default_codex_account") as set_codex, \
                mock.patch.object(manager, "_save_auto_switch_config"):
                result = manager.run_auto_switch()

            self.assertTrue(result["ok"])
            self.assertFalse(set_current.called)
            self.assertFalse(set_codex.called)
            self.assertEqual(result["actions"][0]["reason"], "current_account_still_usable")
            self.assertEqual(result["actions"][1]["reason"], "current_account_still_usable")

    def test_auto_switch_priority_uses_quota_plan_before_provider_name(self) -> None:
        manager = self.make_manager(Path(tempfile.mkdtemp()))
        snapshot = {"providers": [{"name": "Local Codex Bridge - Old Pro", "account_id": "acct-pro"}]}
        quotas = [
            {"account_id": "acct-pro", "quota_status": "ok", "limit_reached": False, "plan_type": "pro", "windows": [{"used_percent": 99}]},
            {"account_id": "acct-plus-new", "quota_status": "ok", "limit_reached": False, "plan_type": "plus", "windows": [{"used_percent": 50}]},
        ]

        best = manager._best_quota_account(snapshot, quotas)

        self.assertEqual(best["account_id"], "acct-plus-new")

    def test_auto_switch_prefers_larger_effective_remaining_capacity(self) -> None:
        manager = self.make_manager(Path(tempfile.mkdtemp()))
        snapshot = {
            "providers": [
                {"name": "Local Codex Bridge - Plus", "account_id": "acct-plus"},
                {"name": "Local Codex Bridge - Pro Max 20x", "account_id": "acct-pro-max"},
            ]
        }
        quotas = [
            {"account_id": "acct-plus", "quota_status": "ok", "limit_reached": False, "plan_type": "plus", "windows": [{"used_percent": 95}]},
            {"account_id": "acct-pro-max", "quota_status": "near_limit", "limit_reached": False, "plan_type": "pro", "windows": [{"used_percent": 99}]},
        ]

        best = manager._best_quota_account(snapshot, quotas)

        self.assertEqual(best["account_id"], "acct-pro-max")

    def test_create_missing_bridge_providers_creates_without_switching_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))
            with mock.patch.object(manager, "quotas", return_value={"ok": True, "quotas": [{"account_id": "acct-1", "quota_status": "ok", "plan_type": "plus"}]}), \
                mock.patch.object(manager, "snapshot", return_value={"providers": [], "codex_desktop": {}}), \
                mock.patch.object(manager, "create_or_update_provider", return_value={"ok": True, "provider_id": "new"}) as create_provider:
                result = manager.create_missing_bridge_providers()

            self.assertTrue(result["ok"])
            create_provider.assert_called_once()
            self.assertEqual(create_provider.call_args.args[0], "acct-1")
            self.assertFalse(create_provider.call_args.args[2])
            self.assertEqual(len(result["created"]), 1)

    def test_create_cli_home_compatibility_wrapper_is_launcher_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            target = root / ".codex-cli-person"
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            with (
                mock.patch.object(bridgedeck.Path, "home", return_value=root),
                mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir),
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", root / ".codex"),
            ):
                result = manager.create_or_sync_cli_home("acct-1", str(target), "person")

            self.assertTrue(result["compatibility"])
            self.assertFalse((target / "auth.json").exists())

    def test_migrate_cli_launcher_disables_old_tokenful_auth_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            target = root / ".codex-cli-person"
            target.mkdir()
            (target / "auth.json").write_text(
                json.dumps({"tokens": {"access_token": "a", "refresh_token": "r", "id_token": "i"}}),
                encoding="utf-8",
            )
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            with (
                mock.patch.object(bridgedeck.Path, "home", return_value=root),
                mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir),
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", root / ".codex"),
            ):
                result = manager.migrate_cli_launcher("acct-1", str(target), "person")

            self.assertEqual(result["message"], "CLI 启动器已迁移")
            self.assertFalse((target / "auth.json").exists())
            self.assertTrue(list(target.glob("auth.json.disabled-by-bridgedeck-*")))

    def test_stale_tokenful_cli_home_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            target = root / ".codex-cli-person"
            target.mkdir()
            (target / "auth.json").write_text(
                json.dumps({"tokens": {"access_token": "a", "refresh_token": "r", "id_token": "i"}}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(bridgedeck.Path, "home", return_value=root),
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", root / ".codex"),
            ):
                summary = manager._codex_auth_summary(target)

            self.assertEqual(summary["status"], "stale_launcher")
            self.assertIn("stale_cli_token_profile", summary["risk_flags"])

    def test_codex_desktop_detection_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            original = 'base_url = "http://127.0.0.1:15721/v1"\n'
            config.write_text(original, encoding="utf-8")
            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                status = manager._codex_desktop_status()

            self.assertEqual(status["managed_by"], "cc_switch")
            self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_set_default_codex_account_writes_only_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            launcher_dir = root / ".cc-switch" / "codex-cli-launchers"
            shim_paths = (root / ".codebuddy" / "bin" / "codex", root / ".workbuddy" / "bin" / "codex")
            zprofile = root / ".zprofile"
            zprofile.write_text('eval "$(/opt/homebrew/bin/brew shellenv)"\n', encoding="utf-8")
            config = codex_home / "config.toml"
            config.write_text(
                'model = "gpt-5.5"\nbase_url = "http://127.0.0.1:15721/v1"\n',
                encoding="utf-8",
            )

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home),
                mock.patch.object(bridgedeck, "DEFAULT_CLI_LAUNCHER_DIR", launcher_dir),
                mock.patch.object(bridgedeck, "DEFAULT_OMC_CODEX_SHIM_PATHS", shim_paths),
                mock.patch.object(bridgedeck, "DEFAULT_ZPROFILE_PATH", zprofile),
                mock.patch.object(bridgedeck, "codex_binary_path", return_value="/opt/homebrew/bin/codex"),
            ):
                result = manager.set_default_codex_account("acct-1")

            body = config.read_text(encoding="utf-8")
            launcher = launcher_dir / "codex-current.command"
            launcher_body = launcher.read_text(encoding="utf-8")
            self.assertTrue(result["ok"])
            self.assertIn('base_url = "http://127.0.0.1:8876/accounts/acct-1/v1"', body)
            self.assertIn('model = "gpt-5.5"', body)
            self.assertNotIn("secret-refresh-token", body)
            self.assertNotIn("access_token", body)
            self.assertTrue(result["backups"])
            self.assertEqual(result["current_launcher"], str(launcher))
            self.assertIn('export OPENAI_API_KEY="local-bridge"', launcher_body)
            self.assertIn('base_url="http://127.0.0.1:8876/accounts/acct-1/v1"', launcher_body)
            self.assertIn('exec "/opt/homebrew/bin/codex"', launcher_body)
            self.assertNotIn("CODEX_HOME", launcher_body)
            self.assertNotIn("secret-refresh-token", launcher_body)
            self.assertNotIn("secret-access-token", launcher_body)
            self.assertNotIn("secret-id-token", launcher_body)
            self.assertEqual(result["omc_codex_shims"], [str(path) for path in shim_paths])
            self.assertIn(str(launcher_dir / "bin"), zprofile.read_text(encoding="utf-8"))
            for path in shim_paths:
                shim_body = path.read_text(encoding="utf-8")
                self.assertIn(bridgedeck.MANAGED_CODEX_SHIM_MARKER, shim_body)
                self.assertIn(str(launcher), shim_body)

    def test_set_default_codex_account_does_not_change_config_if_launcher_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            original = 'model = "gpt-5.5"\nbase_url = "http://127.0.0.1:15721/v1"\n'
            config.write_text(original, encoding="utf-8")

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home),
                mock.patch.object(manager, "write_current_codex_launcher", side_effect=ValueError("blocked")),
            ):
                with self.assertRaises(ValueError):
                    manager.set_default_codex_account("acct-1")

            self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_error_classifier(self) -> None:
        self.assertEqual(
            bridgedeck.classify_error_text('{"error":"refresh_token_reused"}'),
            "refresh_token_reused",
        )
        self.assertEqual(
            bridgedeck.classify_error_text("unsupported_country_region_territory"),
            "unsupported_region",
        )


if __name__ == "__main__":
    unittest.main()
