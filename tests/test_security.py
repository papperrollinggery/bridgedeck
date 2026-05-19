from __future__ import annotations

import json
import http.client
import io
import base64
import os
import sqlite3
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.parse
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


def fake_jwt(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"header.{encoded}.sig"


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
            "usage_metrics": {
                "request_count": 3,
                "input_tokens": 1200,
                "output_tokens": 340,
                "total_tokens": 1540,
                "cached_tokens": 900,
                "cache_creation_tokens": 100,
                "cache_miss_tokens": 300,
                "cache_hit_rate": 0.75,
                "cache_miss_rate": 0.25,
                "last_account_id": "01234567-89ab-cdef-0123-456789abcdef",
                "last_model": "gpt-5.5",
                "last_requested_model": "claude-opus-4-7",
                "last_bridge_port": 8876,
                "last_client_label": "Claude Desktop 3P",
            },
            "usage_events": [
                {
                    "at": 1778736000,
                    "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "model": "gpt-5.5",
                    "actual_model": "gpt-5.5",
                    "requested_model": "claude-opus-4-7",
                    "request_type": "messages",
                    "request_id": "bridge-test",
                    "status_code": 200,
                    "source": "proxy",
                    "route_path": "/v1/messages",
                    "bridge_port": 8876,
                    "client_port": 61234,
                    "client_label": "Claude Desktop 3P",
                    "desktop_route": True,
                    "duration_ms": 7650,
                    "input_tokens": 1200,
                    "output_tokens": 340,
                    "total_tokens": 1540,
                    "cached_tokens": 900,
                    "cache_creation_tokens": 100,
                    "cache_miss_tokens": 300,
                    "cache_hit_rate": 0.75,
                    "cache_miss_rate": 0.25,
                    "cost_usd": 0.0,
                }
            ],
            "stream_diagnostics": {
                "status": "ok",
                "message": "最近流式请求正常结束。",
                "latest": {},
                "counts": {},
                "events": [],
                "log_paths": [],
            },
            "claude_hook_risks": {
                "status": "ok",
                "message": "Claude hooks 未发现明显长等待风险。",
                "events": {},
                "risks": [],
            },
            "account_matrix": [],
            "current_provider_from_settings": "",
            "claude_attribution_header": {
                "status": "disabled",
                "message": "已关闭 Claude Code billing attribution header。",
                "sources": [],
            },
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
        context_config: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"ok": True}

    def patch_provider(self, provider_id: str) -> dict[str, Any]:
        return {"ok": True}

    def update_provider_compact(
        self,
        provider_id: str,
        compact_config: dict[str, Any] | None,
        context_config: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "上下文配置已保存",
            "provider_id": provider_id,
            "compact_config": bridgedeck.normalize_compact_config(compact_config),
            "context_config": (
                bridgedeck.normalize_bridge_model_config(context_config)
                if context_config is not None
                else None
            ),
            "model_config": (
                bridgedeck.normalize_bridge_model_config(model_config)
                if model_config is not None
                else None
            ),
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
            "codex_native_proxy": self.codex_native_proxy_status(),
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

    def codex_native_proxy_status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "message": "Codex 原生代理变量已齐全",
            "env_path": f"{Path.home()}/.codex/.env",
            "proxy_url": "http://127.0.0.1:1087",
            "proxy_url_masked": "http://127.0.0.1:1087",
            "proxy_port": 1087,
            "proxy_running": True,
            "missing_keys": [],
            "mismatched_keys": [],
            "restart_required": True,
        }

    def repair_codex_native_proxy(self) -> dict[str, Any]:
        return {
            "ok": True,
            "changed": True,
            "message": "Codex 原生代理已修复",
            "env_keys": list(bridgedeck.CODEX_NATIVE_PROXY_REQUIRED_KEYS),
            "status": self.codex_native_proxy_status(),
            "restart_required": True,
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

    def repair_claude_attribution_header(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Claude Code Attribution Header 修复完成",
            "changed": True,
            "files": [{"path": f"{Path.home()}/.claude/settings.json", "changed": True}],
            "updated_providers": [{"id": "provider-1", "name": "Provider"}],
            "status": {"status": "disabled"},
        }

    def create_or_sync_cli_home(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}

    def create_cli_launcher(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}

    def migrate_cli_launcher(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}

    def set_default_codex_account(self, account_id: str) -> dict[str, Any]:
        return {"ok": True, "account_id": account_id, "desktop_affected": False}

    def enable_codex_desktop_bridge_mode(self, account_id: str) -> dict[str, Any]:
        return {"ok": True, "account_id": account_id, "message": "已开启 Codex Desktop 临时 Bridge 模式"}

    def restore_codex_desktop_native_mode(self) -> dict[str, Any]:
        return {"ok": True, "changed": True, "message": "已恢复 Codex Desktop 原生配置"}

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
                    "stream_diagnostics": {
                        "status": "warning",
                        "message": "最近一次是客户端断开：Bridge 仍在接收上游流，不是 Bridge idle timeout。",
                        "latest": {
                            "kind": "client_disconnect",
                            "account_id": "01234567-89ab-cdef-0123-456789abcdef",
                            "log_path": "/Users/person/.cc-switch/bridgedeck-local-bridge.log",
                        },
                        "events": [],
                        "log_paths": ["/Users/person/.cc-switch/bridgedeck-local-bridge.log"],
                    },
                },
                "cc_switch_proxy": {"name": "CC Switch Proxy", "running": True, "port": 15721},
            },
        }

    def control_local_bridge(self, action: str, *, force: bool = False) -> dict[str, Any]:
        return {"ok": True, "message": f"local bridge {action}", "force": force, **self.services()}

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


class SlowBootstrapResponse:
    headers = {"x-request-id": "upstream-test"}

    def iter_lines(self):
        time.sleep(0.05)
        yield "event: response.completed"
        yield 'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}'
        yield ""


class SlowAfterTextResponse:
    headers = {"x-request-id": "upstream-test"}

    def iter_lines(self):
        yield "event: response.output_text.delta"
        yield 'data: {"type":"response.output_text.delta","delta":"partial"}'
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
    def setUp(self) -> None:
        self._bridge_state_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._bridge_state_tmp.cleanup)
        state_path = Path(self._bridge_state_tmp.name) / "bridge-state.json"
        patcher = mock.patch.object(local_codex_bridge, "BRIDGE_STATE_PATH", state_path)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_normalize_strips_reasoning_summary_for_codex_spark(self) -> None:
        body = {
            "model": "gpt-5.3-codex-spark",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "stream": True,
            "reasoning": {"effort": "low", "summary": "concise"},
            "include": ["reasoning.summary"],
        }

        normalized = local_codex_bridge.normalize_request_body(body)

        self.assertEqual(normalized["reasoning"]["effort"], "low")
        self.assertNotIn("summary", normalized["reasoning"])
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

    def test_strip_claude_attribution_header_from_system_prompt_prefix(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "system": "x-anthropic-billing-header: cc_version=2.1.116.d8c; cc_entrypoint=cli; cch=c1d6c;\n\nYou are Claude Code.",
            "messages": [{"role": "user", "content": "hi"}],
        }

        stripped, result = local_codex_bridge.strip_claude_attribution_from_request(
            body,
            request_type="messages",
            provider_kind="proxy",
        )

        self.assertTrue(result["stripped"])
        self.assertEqual(result["field"], "system")
        self.assertEqual(stripped["system"], "You are Claude Code.")
        self.assertEqual(body["system"].splitlines()[0].startswith("x-anthropic-billing-header"), True)

    def test_strip_claude_attribution_header_does_not_remove_user_mentions(self) -> None:
        body = {
            "messages": [
                {"role": "user", "content": "Please explain x-anthropic-billing-header in plain English."},
            ]
        }

        stripped, result = local_codex_bridge.strip_claude_attribution_from_request(
            body,
            request_type="chat.completions",
            provider_kind="proxy",
        )

        self.assertFalse(result["stripped"])
        self.assertEqual(stripped, body)

    def test_strip_claude_attribution_header_from_responses_input_system_item(self) -> None:
        body = {
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "x-anthropic-billing-header: cc_version=2.1.116.d8c; cc_entrypoint=cli; cch=c1d6c;\n\nStable system prompt.",
                        }
                    ],
                },
                {"role": "user", "content": [{"type": "input_text", "text": "hi"}]},
            ]
        }

        stripped, result = local_codex_bridge.strip_claude_attribution_from_request(
            body,
            request_type="responses",
            provider_kind="proxy",
        )

        self.assertTrue(result["stripped"])
        self.assertEqual(result["field"], "input[0].content")
        self.assertEqual(stripped["input"][0]["content"][0]["text"], "Stable system prompt.")
        self.assertIn("x-anthropic-billing-header", body["input"][0]["content"][0]["text"])

    def test_strip_claude_attribution_header_respects_provider_and_mode(self) -> None:
        body = {
            "system": "x-anthropic-billing-header: cc_version=2.1.116.d8c; cc_entrypoint=cli; cch=c1d6c;\n\nOfficial."
        }

        official, official_result = local_codex_bridge.strip_claude_attribution_from_request(
            body,
            request_type="messages",
            provider_kind="official_anthropic",
            mode="auto",
        )
        forced, forced_result = local_codex_bridge.strip_claude_attribution_from_request(
            body,
            request_type="messages",
            provider_kind="official_anthropic",
            mode="always",
        )
        never, never_result = local_codex_bridge.strip_claude_attribution_from_request(
            body,
            request_type="messages",
            provider_kind="proxy",
            mode="never",
        )

        self.assertFalse(official_result["stripped"])
        self.assertEqual(official, body)
        self.assertTrue(forced_result["stripped"])
        self.assertEqual(forced["system"], "Official.")
        self.assertFalse(never_result["stripped"])
        self.assertEqual(never, body)

    def test_claude_attribution_strip_log_omits_prompt_text(self) -> None:
        result = {
            "stripped": True,
            "provider_kind": "proxy",
            "request_type": "messages",
            "field": "system",
            "reason": "third_party_or_proxy",
            "before_len": 100,
            "after_len": 20,
            "before_hash": "abc",
            "after_hash": "def",
        }

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            local_codex_bridge.log_claude_attribution_strip(
                account_id="acct-1",
                route_path="/v1/messages",
                result=result,
            )

        log_text = stderr.getvalue()
        self.assertIn("[claude-attribution-strip]", log_text)
        self.assertIn('"stripped": true', log_text)
        self.assertIn('"provider_kind": "proxy"', log_text)
        self.assertNotIn("x-anthropic-billing-header", log_text)
        self.assertNotIn("You are Claude Code", log_text)

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

    def test_stream_idle_timeout_emits_failed_sse_before_first_upstream_event(self) -> None:
        with (
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_LOG_SECS", 0.005),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_FAIL_SECS", 0.02),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_PARTIAL_FAIL_SECS", 0.2),
            mock.patch.object(local_codex_bridge, "REASONING_PLACEHOLDER_HEARTBEAT_SECS", 0.005),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    SlowBootstrapResponse(),
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
        self.assertIn("phase=bootstrap", body)
        self.assertIn("bridge-test", body)
        self.assertNotIn("event: response.output_text.delta", body)
        self.assertIn("[bridge-stream-idle]", logs)
        self.assertIn("[bridge-stream-end]", logs)
        self.assertIn('"idle_timeout_seen": true', logs)

    def test_stream_idle_timeout_uses_longer_limit_after_reasoning_started(self) -> None:
        with (
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_LOG_SECS", 0.005),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_FAIL_SECS", 0.02),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_PARTIAL_FAIL_SECS", 0.2),
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
        self.assertIn("event: response.completed", body)
        self.assertNotIn("bridge_stream_idle_timeout", body)
        self.assertIn("[bridge-stream-idle]", logs)
        self.assertIn("phase=partial", logs)
        self.assertIn('"idle_timeout_seen": false', logs)

    def test_stream_idle_timeout_keeps_partial_text_stream_alive(self) -> None:
        with (
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_LOG_SECS", 0.005),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_FAIL_SECS", 0.02),
            mock.patch.object(local_codex_bridge, "STREAM_IDLE_PARTIAL_FAIL_SECS", 0.2),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    SlowAfterTextResponse(),
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic(),
                    requested_model="gpt-5.4",
                    requested_effort="high",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        logs = stderr.getvalue()
        self.assertIn("partial", body)
        self.assertIn("event: response.completed", body)
        self.assertIn(": bridge upstream idle phase=partial", body)
        self.assertNotIn("bridge_stream_idle_timeout", body)
        self.assertIn('"idle_timeout_seen": false', logs)

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
        self.assertIn('"visible_text_events": 1', logs)
        self.assertIn('"terminal_events": 1', logs)
        self.assertIn('"last_event_name": "response.completed"', logs)

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

    def test_long_stream_warning_logs_without_changing_stream(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"hello"}',
                "",
            ]
        )

        with (
            mock.patch.object(local_codex_bridge, "STREAM_LONG_WARNING_SECS", 0.001),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic() - 1,
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("hello", body)
        self.assertIn("[bridge-long-stream-warning]", stderr.getvalue())
        self.assertIn('"visible_text_events": 1', stderr.getvalue())

    def test_function_call_argument_runaway_fails_before_client_idle_timeout(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.function_call_arguments.delta",
                'data: {"type":"response.function_call_arguments.delta","delta":"{\\"path\\":"}',
                "",
            ]
        )

        with (
            mock.patch.dict(os.environ, {"CODEX_BRIDGE_STREAM_TOOL_CALL_GUARD": "auto"}),
            mock.patch.object(local_codex_bridge, "STREAM_TOOL_CALL_WALL_FAIL_SECS", 0.001),
            mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(local_codex_bridge.stream_tool_call_guard_mode(), "auto")
            self.assertLess(local_codex_bridge.stream_tool_call_guard_seconds(), 300)
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic() - 1,
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("event: response.function_call_arguments.delta", body)
        self.assertIn("event: response.failed", body)
        self.assertIn("bridge_tool_call_runaway", body)
        self.assertIn("[bridge-stream-error]", stderr.getvalue())
        self.assertIn('"terminal_event_seen": true', stderr.getvalue())
        record.assert_called_once()
        self.assertEqual(record.call_args.args[0]["error_type"], "BridgeToolCallRunaway")
        self.assertNotIn("active_stream", local_codex_bridge._read_bridge_state())

    def test_function_call_argument_guard_can_be_disabled_for_passthrough(self) -> None:
        response = FakeSseResponse(
            [
                "event: response.function_call_arguments.delta",
                'data: {"type":"response.function_call_arguments.delta","delta":"{\\"path\\":"}',
                "",
                "event: response.completed",
                'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed"}}',
                "",
            ]
        )

        with (
            mock.patch.dict(os.environ, {"CODEX_BRIDGE_STREAM_TOOL_CALL_GUARD": "passthrough"}),
            mock.patch.object(local_codex_bridge, "STREAM_TOOL_CALL_WALL_FAIL_SECS", 0.001),
            mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic() - 1,
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("event: response.function_call_arguments.delta", body)
        self.assertIn("event: response.completed", body)
        self.assertNotIn("bridge_tool_call_runaway", body)
        record.assert_not_called()

    def test_text_long_stream_does_not_trigger_tool_call_runaway(self) -> None:
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

        with (
            mock.patch.object(local_codex_bridge, "STREAM_TOOL_CALL_WALL_FAIL_SECS", 0.001),
            mock.patch.object(local_codex_bridge, "record_bridge_stream_error") as record,
        ):
            chunks = list(
                self.make_handler()._iter_stream_with_reasoning_placeholder(
                    response,
                    "acct-1",
                    request_id="bridge-test",
                    started_at=local_codex_bridge.time.monotonic() - 1,
                    requested_model="gpt-5.5",
                )
            )

        body = b"".join(chunks).decode("utf-8")
        self.assertIn("hello", body)
        self.assertIn("event: response.completed", body)
        self.assertNotIn("bridge_tool_call_runaway", body)
        record.assert_not_called()

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
        self.assertEqual(by_id["gpt-5.5"]["slug"], "gpt-5.5")
        self.assertEqual(by_id["gpt-5.5"]["context_length"], 272000)
        self.assertEqual(by_id["gpt-5.5"]["context_window"], 272000)
        self.assertEqual(by_id["gpt-5.5"]["max_completion_tokens"], 128000)
        self.assertEqual(by_id["gpt-5.5"]["thinking"]["levels"], ["low", "medium", "high", "xhigh"])
        self.assertEqual(by_id["gpt-5.5"]["default_reasoning_level"], "medium")
        self.assertEqual(
            [item["effort"] for item in by_id["gpt-5.5"]["supported_reasoning_levels"]],
            ["low", "medium", "high", "xhigh"],
        )
        self.assertEqual(by_id["gpt-5.5"]["shell_type"], "shell_command")
        self.assertEqual(by_id["gpt-5.5"]["visibility"], "list")
        self.assertEqual(by_id["gpt-5.5"]["priority"], 100)
        self.assertIn("fast", by_id["gpt-5.5"]["additional_speed_tiers"])
        self.assertTrue(by_id["gpt-5.5"]["capabilities"]["messages"])
        self.assertTrue(by_id["gpt-5.5"]["capabilities"]["responses"])
        self.assertEqual(by_id["gpt-5.4"]["context_length"], 220000)
        self.assertEqual(by_id["gpt-5.4-mini"]["context_length"], 220000)
        self.assertEqual(by_id["gpt-5.3-codex"]["context_length"], 220000)
        self.assertEqual(by_id["gpt-5.3-codex-spark"]["context_length"], 220000)

    def test_models_registry_exposes_claude_desktop_safe_routes(self) -> None:
        payload = local_codex_bridge.build_models_payload()
        by_id = {item["id"]: item for item in payload["data"]}

        self.assertEqual(payload["models"], payload["data"])
        self.assertIn("models", payload)
        self.assertEqual(by_id["claude-opus-4-7"]["slug"], "claude-opus-4-7")
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

    def test_claude_alias_routes_map_before_forwarding(self) -> None:
        cases = {
            "haiku": "gpt-5.3-codex-spark",
            "sonnet": "gpt-5.3-codex",
            "opus": "gpt-5.5",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                body = local_codex_bridge.normalize_request_body(
                    {"model": source, "input": [{"role": "user", "content": []}]}
                )

                self.assertEqual(body["model"], expected)

    def test_prepare_upstream_responses_body_only_emits_prompt_cache_key_with_session_identity(self) -> None:
        body = {
            "model": "gpt-5.5",
            "input": [
                {
                    "type": "function_call",
                    "name": "lookup",
                    "arguments": '{"b":2,"a":1}',
                }
            ],
        }

        without_session, without_meta = local_codex_bridge.prepare_upstream_responses_body(body, session_key=None)
        with_session, with_meta = local_codex_bridge.prepare_upstream_responses_body(body, session_key="x-session-id:thread-1")

        self.assertNotIn("prompt_cache_key", without_session)
        self.assertFalse(without_meta["prompt_cache_key_present"])
        self.assertIn("prompt_cache_key", with_session)
        self.assertTrue(with_meta["prompt_cache_key_present"])
        self.assertEqual(with_meta["cache_key_source"], "session_identity")
        self.assertEqual(with_session["input"][0]["arguments"], '{"a":1,"b":2}')

    def test_prompt_cache_key_can_be_disabled_by_env(self) -> None:
        with mock.patch.dict(os.environ, {"CODEX_BRIDGE_PROMPT_CACHE_KEY": "never"}):
            body, meta = local_codex_bridge.prepare_upstream_responses_body(
                {"model": "gpt-5.5"},
                session_key="x-session-id:thread-1",
            )

        self.assertNotIn("prompt_cache_key", body)
        self.assertEqual(meta["cache_key_source"], "disabled")

    def test_models_endpoint_is_account_scoped_and_ignores_sensitive_query(self) -> None:
        server = self.start_local_bridge_server()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/accounts/acct-1/v1/models?api_key=secret"
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        by_id = {item["id"]: item for item in payload["data"]}
        by_codex_id = {item["id"]: item for item in payload["models"]}
        self.assertEqual(response.status, 200)
        self.assertIn("gpt-5.5", by_id)
        self.assertIn("claude-opus-4-7", by_id)
        self.assertEqual(by_id["gpt-5.5"]["context_length"], 272000)
        self.assertIn("gpt-5.5", by_codex_id)
        self.assertEqual(by_codex_id["gpt-5.5"]["context_length"], 272000)
        self.assertEqual(by_codex_id["gpt-5.5"]["thinking"]["levels"], ["low", "medium", "high", "xhigh"])

    def test_models_endpoint_accepts_openai_base_url_path_variants(self) -> None:
        server = self.start_local_bridge_server()
        for path in ("/accounts/acct-1/models", "/accounts/acct-1/v1/v1/models"):
            with self.subTest(path=path):
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}")
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))

                self.assertEqual(response.status, 200)
                self.assertIn("gpt-5.5", {item["id"] for item in payload["data"]})
                self.assertIn("gpt-5.5", {item["id"] for item in payload["models"]})

    def test_decode_request_body_accepts_compressed_json(self) -> None:
        raw = json.dumps({"model": "gpt-5.5", "input": "hi"}).encode("utf-8")

        self.assertEqual(local_codex_bridge.decode_request_body(raw, None), raw)
        self.assertEqual(
            local_codex_bridge.decode_request_body(local_codex_bridge.gzip.compress(raw), "gzip"),
            raw,
        )
        self.assertEqual(
            local_codex_bridge.decode_request_body(local_codex_bridge.zlib.compress(raw), "deflate"),
            raw,
        )
        if local_codex_bridge.zstd is None:
            self.skipTest("zstd compression module is unavailable")
        zstd_body = local_codex_bridge.zstd.compress(raw)
        self.assertEqual(local_codex_bridge.decode_request_body(zstd_body, "zstd"), raw)
        self.assertEqual(local_codex_bridge.decode_request_body(zstd_body, None), raw)

    def test_launchd_bind_failure_is_throttled(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "XPC_SERVICE_NAME": "local.bridgedeck.test",
                "CODEX_BRIDGE_BIND_FAILURE_SLEEP_SECS": "7",
            },
            clear=False,
        ):
            exc = OSError(local_codex_bridge.errno.EADDRNOTAVAIL, "cannot assign requested address")
            self.assertEqual(local_codex_bridge.bind_failure_sleep_seconds(exc), 7)

        with mock.patch.dict(os.environ, {}, clear=True):
            exc = OSError(local_codex_bridge.errno.EADDRNOTAVAIL, "cannot assign requested address")
            self.assertEqual(local_codex_bridge.bind_failure_sleep_seconds(exc), 0)

    def test_responses_endpoint_accepts_zstd_request_body_from_codex_cli(self) -> None:
        if local_codex_bridge.zstd is None:
            self.skipTest("zstd compression module is unavailable")
        server = self.start_local_bridge_server()
        client = FakeForwardClient(
            [
                FakeForwardResponse(
                    200,
                    body=(
                        b"event: response.output_text.delta\n"
                        b'data: {"type":"response.output_text.delta","delta":"OK"}\n\n'
                    ),
                )
            ]
        )
        request_body = {
            "model": "gpt-5.5",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "stream": False,
        }
        raw_body = json.dumps(request_body).encode("utf-8")
        compressed_body = local_codex_bridge.zstd.compress(raw_body)
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/accounts/acct-1/v1/responses",
            data=compressed_body,
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Content-Encoding", "zstd")

        with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
            with urllib.request.urlopen(request, timeout=5) as response:
                response_body = json.loads(response.read().decode("utf-8"))

        sent = client.calls[0]["kwargs"]
        self.assertEqual(response.status, 200)
        self.assertEqual(sent["json"]["model"], "gpt-5.5")
        self.assertEqual(sent["json"]["input"][0]["content"][0], {"type": "input_text", "text": "hi"})
        self.assertEqual(response_body["output"][0]["content"][0]["text"], "OK")

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

    def test_responses_forward_adds_prompt_cache_key_from_session_header(self) -> None:
        server = self.start_local_bridge_server()
        client = FakeForwardClient(
            [
                FakeForwardResponse(
                    200,
                    body=(
                        b"event: response.completed\n"
                        b'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed","usage":{"input_tokens":1,"output_tokens":1}}}\n\n'
                    ),
                )
            ]
        )

        with mock.patch.object(local_codex_bridge, "build_upstream_http_client", return_value=client):
            status, _body, _headers = self.post_local_bridge_json(
                server,
                "/accounts/acct-1/v1/responses",
                {
                    "model": "gpt-5.5",
                    "stream": True,
                    "input": [{"type": "function_call", "name": "lookup", "arguments": '{"z":1,"a":2}'}],
                },
                headers={"Accept": "text/event-stream", "x-session-id": "thread-1"},
            )

        sent_body = client.calls[0]["kwargs"]["json"]
        self.assertEqual(status, 200)
        self.assertIn("prompt_cache_key", sent_body)
        self.assertEqual(sent_body["input"][0]["arguments"], '{"a":2,"z":1}')

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
        self.assertEqual(
            payload["usage"],
            {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "input_tokens": 3,
                "output_tokens": 2,
            },
        )

    def test_responses_json_chat_completion_usage_never_returns_null_standard_fields(self) -> None:
        payload = local_codex_bridge.responses_json_to_chat_completion(
            {
                "id": "resp_1",
                "status": "completed",
                "model": "gpt-5.5",
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 17,
                    "total_tokens": 28,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                },
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}],
            }
        )

        self.assertEqual(payload["usage"]["prompt_tokens"], 11)
        self.assertEqual(payload["usage"]["completion_tokens"], 17)
        self.assertEqual(payload["usage"]["total_tokens"], 28)
        self.assertIsInstance(payload["usage"]["prompt_tokens"], int)
        self.assertIsInstance(payload["usage"]["completion_tokens"], int)

    def test_record_bridge_usage_accumulates_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "bridge-state.json"
            state_path.write_text(
                json.dumps({"last_stream_error": {"error": "old timeout"}}),
                encoding="utf-8",
            )
            with mock.patch.object(local_codex_bridge, "BRIDGE_STATE_PATH", state_path):
                local_codex_bridge.record_bridge_usage(
                    account_id="acct-1",
                    model="gpt-5.5",
                    requested_model="claude-opus-4-7",
                    request_type="responses",
                    request_id="req-1",
                    usage={
                        "input_tokens": 11,
                        "output_tokens": 7,
                        "input_tokens_details": {"cached_tokens": 5},
                        "cache_creation_tokens": 2,
                    },
                    route_path="/v1/messages",
                    bridge_port=8876,
                    client_port=61234,
                    client_label="Claude Desktop 3P",
                    desktop_route=True,
                )
                local_codex_bridge.record_bridge_usage(
                    account_id="acct-1",
                    model="gpt-5.5",
                    request_type="chat.completions",
                    request_id="req-2",
                    usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                )

            payload = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["usage_metrics"]["request_count"], 2)
        self.assertEqual(payload["usage_metrics"]["input_tokens"], 14)
        self.assertEqual(payload["usage_metrics"]["output_tokens"], 9)
        self.assertEqual(payload["usage_metrics"]["total_tokens"], 23)
        self.assertEqual(payload["usage_metrics"]["cached_tokens"], 5)
        self.assertEqual(payload["usage_metrics"]["cache_creation_tokens"], 2)
        self.assertEqual(payload["usage_metrics"]["cache_miss_tokens"], 9)
        self.assertAlmostEqual(payload["usage_metrics"]["cache_hit_rate"], 5 / 14)
        self.assertAlmostEqual(payload["usage_metrics"]["cache_miss_rate"], 9 / 14)
        self.assertEqual(payload["usage_metrics"]["last_request_type"], "chat.completions")
        self.assertEqual(len(payload["usage_events"]), 2)
        self.assertEqual(payload["usage_events"][0]["cache_miss_tokens"], 6)
        self.assertEqual(payload["usage_events"][0]["requested_model"], "claude-opus-4-7")
        self.assertEqual(payload["usage_events"][0]["actual_model"], "gpt-5.5")
        self.assertEqual(payload["usage_events"][0]["bridge_port"], 8876)
        self.assertEqual(payload["usage_events"][0]["client_label"], "Claude Desktop 3P")
        self.assertTrue(payload["usage_events"][0]["desktop_route"])
        self.assertEqual(payload["usage_events"][1]["status_code"], 200)
        self.assertNotIn("last_stream_error", payload)

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

    def test_anthropic_stream_converts_function_call_arguments_to_tool_use(self) -> None:
        chunks = [
            (
                b"event: response.output_item.added\n"
                b'data: {"type":"response.output_item.added","item":{"id":"fc_1","type":"function_call","call_id":"call_1","name":"Read","arguments":""},"output_index":0}\n\n'
            ),
            (
                b"event: response.function_call_arguments.delta\n"
                b'data: {"type":"response.function_call_arguments.delta","item_id":"fc_1","output_index":0,"delta":"{\\\"file_path\\\":"}\n\n'
            ),
            (
                b"event: response.function_call_arguments.delta\n"
                b'data: {"type":"response.function_call_arguments.delta","item_id":"fc_1","output_index":0,"delta":"\\\"/tmp/a\\\"}"}\n\n'
            ),
            (
                b"event: response.function_call_arguments.done\n"
                b'data: {"type":"response.function_call_arguments.done","item_id":"fc_1","output_index":0,"arguments":"{\\\"file_path\\\":\\\"/tmp/a\\\"}"}\n\n'
            ),
            (
                b"event: response.completed\n"
                b'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed","usage":{"output_tokens":3}}}\n\n'
            ),
        ]

        body = b"".join(
            local_codex_bridge.iter_anthropic_messages_sse(
                iter(chunks),
                message_id="msg_1",
                model="gpt-5.5",
            )
        ).decode("utf-8")

        self.assertIn('"type":"tool_use"', body)
        self.assertIn('"id":"call_1"', body)
        self.assertIn('"name":"Read"', body)
        self.assertIn('"type":"input_json_delta"', body)
        self.assertIn('"partial_json":"{\\"file_path\\":"', body)
        self.assertIn('"partial_json":"\\"/tmp/a\\"}"', body)
        self.assertIn('"stop_reason":"tool_use"', body)
        self.assertNotIn("response.function_call_arguments.delta", body)

    def test_anthropic_stream_converts_completed_function_call_without_deltas(self) -> None:
        chunks = [
            (
                b"event: response.output_item.done\n"
                b'data: {"type":"response.output_item.done","item":{"id":"fc_1","type":"function_call","call_id":"call_1","name":"Write","arguments":"{\\\"path\\\":\\\"/tmp/a\\\"}"},"output_index":0}\n\n'
            ),
            (
                b"event: response.completed\n"
                b'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed","usage":{"output_tokens":3}}}\n\n'
            ),
        ]

        body = b"".join(
            local_codex_bridge.iter_anthropic_messages_sse(
                iter(chunks),
                message_id="msg_1",
                model="gpt-5.5",
            )
        ).decode("utf-8")

        self.assertIn('"type":"tool_use"', body)
        self.assertIn('"name":"Write"', body)
        self.assertIn('"partial_json":"{\\"path\\":\\"/tmp/a\\"}"', body)
        self.assertIn('"stop_reason":"tool_use"', body)

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

    def test_bridge_state_reads_active_stream_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "updated_at": 123,
                        "active_stream": {
                            "account_id": "acct-1",
                            "request_id": "bridge-active",
                            "status": "tool_arguments_streaming",
                            "model": "gpt-5.5",
                            "duration_s": 42.5,
                            "last_event_name": "response.function_call_arguments.delta",
                            "guard_mode": "auto",
                            "guard_seconds": 240,
                            "tool_events": 123,
                            "visible_text_events": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = bridgedeck.read_local_bridge_state(state_path)

        self.assertEqual(payload["active_stream"]["request_id"], "bridge-active")
        self.assertEqual(payload["active_stream"]["status"], "tool_arguments_streaming")
        self.assertEqual(payload["active_stream"]["guard_seconds"], 240)

    def test_bridge_state_reads_usage_metrics_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "updated_at": 123,
                        "usage_metrics": {
                            "request_count": 2,
                            "input_tokens": 11,
                            "output_tokens": 7,
                            "total_tokens": 18,
                            "cached_tokens": 5,
                            "cache_creation_tokens": 3,
                            "cache_miss_tokens": 6,
                            "cache_hit_rate": 0.45,
                            "cache_miss_rate": 0.55,
                            "last_model": "gpt-5.5",
                        },
                        "usage_events": [
                            {
                                "at": 1778736000,
                                "account_id": "acct-1",
                                "model": "gpt-5.5",
                                "actual_model": "gpt-5.5",
                                "requested_model": "claude-opus-4-7",
                                "request_type": "responses",
                                "request_id": "bridge-test",
                                "status_code": 200,
                                "source": "proxy",
                                "route_path": "/v1/messages",
                                "bridge_port": 8876,
                                "client_port": 61234,
                                "client_label": "Claude Desktop 3P",
                                "desktop_route": True,
                                "duration_ms": 1200,
                                "input_tokens": 11,
                                "output_tokens": 7,
                                "total_tokens": 18,
                                "cached_tokens": 5,
                                "cache_creation_tokens": 3,
                                "cache_miss_tokens": 6,
                                "cache_hit_rate": 0.45,
                                "cache_miss_rate": 0.55,
                                "cost_usd": 0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = bridgedeck.read_local_bridge_state(state_path)

        self.assertEqual(payload["usage_metrics"]["request_count"], 2)
        self.assertEqual(payload["usage_metrics"]["total_tokens"], 18)
        self.assertEqual(payload["usage_metrics"]["cached_tokens"], 5)
        self.assertEqual(payload["usage_metrics"]["cache_miss_tokens"], 6)
        self.assertAlmostEqual(payload["usage_metrics"]["cache_hit_rate"], 0.45)
        self.assertEqual(payload["usage_events"][0]["request_id"], "bridge-test")
        self.assertEqual(payload["usage_events"][0]["cache_miss_tokens"], 6)
        self.assertEqual(payload["usage_events"][0]["requested_model"], "claude-opus-4-7")
        self.assertEqual(payload["usage_events"][0]["actual_model"], "gpt-5.5")
        self.assertEqual(payload["usage_events"][0]["bridge_port"], 8876)
        self.assertTrue(payload["usage_events"][0]["desktop_route"])

    def test_bridge_stream_log_diagnostics_classifies_client_disconnect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "local-codex-bridge.log"
            log_path.write_text(
                "\n".join(
                    [
                        '2026-05-19T15:43:59 [bridge-stream-error] {"account_id":"acct-1","duration_ms":304682,"error":"downstream client disconnected before terminal event: write_failed","error_type":"BridgeClientDisconnect","model":"gpt-5.5","request_id":"bridge-test"}',
                        '2026-05-19T15:43:59 [bridge-stream-end] {"account_id":"acct-1","client_disconnected":true,"downstream_writes":9189,"duration_s":304.731,"first_visible_after_ms":null,"idle_timeout_seen":false,"last_event_name":"response.reasoning.delta","model":"gpt-5.5","reasoning_events":9189,"request_id":"bridge-test","terminal_event_seen":false,"terminal_events":0,"tool_events":0,"upstream_events":9190,"visible_text_events":0}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(bridgedeck, "DEFAULT_LOCAL_BRIDGE_LOG_PATHS", ()):
                payload = bridgedeck.bridge_stream_diagnostics([log_path])

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["latest"]["kind"], "client_disconnect")
        self.assertEqual(payload["counts"]["client_disconnect"], 1)
        self.assertIn("不是 Bridge idle timeout", payload["message"])

    def test_claude_hook_risk_status_flags_long_hooks_without_command_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "/Users/person/private/secret-hook.sh --token abc",
                                            "timeout": 300,
                                        }
                                    ]
                                }
                            ],
                            "PermissionRequest": [
                                {"hooks": [{"type": "command", "command": "curl http://127.0.0.1:23333/permission", "timeout": 600}]}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            payload = bridgedeck.claude_hook_risk_status(settings)

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["risk_count"], 2)
        encoded = json.dumps(payload)
        self.assertNotIn("secret-hook.sh --token abc", encoded)
        self.assertNotIn("/Users/person/private", encoded)
        self.assertIn("timeout=300s", encoded)


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
        self.assertIn("Codex Desktop 临时 Bridge 模式", html)
        self.assertIn('data-action="enable-desktop-bridge-mode"', html)
        self.assertIn('data-action="restore-desktop-native-mode"', html)
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
        self.assertNotIn("ANTHROPIC_MODEL=gpt-5.5", html)
        self.assertIn("ANTHROPIC_DEFAULT_HAIKU_MODEL=gpt-5.3-codex-spark", html)
        self.assertIn("ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME=Haiku 4.5", html)
        self.assertIn("ANTHROPIC_DEFAULT_SONNET_MODEL=gpt-5.3-codex", html)
        self.assertIn("ANTHROPIC_DEFAULT_SONNET_MODEL_NAME=Sonnet 4.6", html)
        self.assertIn("ANTHROPIC_DEFAULT_OPUS_MODEL=gpt-5.5", html)
        self.assertIn("ANTHROPIC_DEFAULT_OPUS_MODEL_NAME=Opus 4.7", html)
        self.assertIn("CLAUDE_CODE_ATTRIBUTION_HEADER=0", html)
        self.assertIn("repair-claude-attribution-header", html)
        self.assertIn("Claude 自动路由", html)
        self.assertIn("强制主模型", html)
        self.assertIn("copy-anthropic-forced-env", html)
        self.assertIn("claude-haiku-4-5", html)
        self.assertIn("claude-sonnet-4-6", html)
        self.assertIn("claude-opus-4-7", html)
        self.assertIn("Desktop Gateway", html)
        self.assertIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000", html)
        self.assertIn("272k context / 128k max output", html)
        self.assertIn('"id": "gpt-5.4"', html)
        self.assertIn('"context_tokens": 220000', html)
        self.assertIn("copy-api-base-url", html)
        self.assertIn("copy-claude-env", html)
        self.assertIn('id="bridgeModel"', html)
        self.assertIn('id="modelRoutingMode"', html)
        self.assertIn('id="modelContextTokens"', html)
        self.assertIn('id="selectedProviderMeta"', html)
        self.assertIn("syncClaudeProviderFormForSelectedAccount", html)
        self.assertIn("当前账号 provider", html)
        self.assertIn("replace(/\\n/g, '；')", html)
        self.assertNotIn("replace(/\n/g", html)
        self.assertIn('data-action="compact-preset-model"', html)
        self.assertIn("context unknown", html)
        self.assertIn('id="compactWindow"', html)
        self.assertIn('data-action="compact-preset-1m"', html)
        self.assertIn('data-action="save-compact-selected"', html)
        self.assertIn('data-action="save-forced-model-selected"', html)
        self.assertIn('data-action="clear-forced-model-selected"', html)
        self.assertIn('data-action="sync-common-env-selected"', html)
        self.assertIn("providerForSelectedClaudeAccount", html)
        self.assertIn("selectedProviderActionTarget", html)
        self.assertIn("已使用${target.source}", html)
        self.assertIn("请先选账号或选中一个 provider", html)
        self.assertIn('data-action="stop-bridgedeck-ui"', html)
        self.assertIn("只停 8899，不影响 8876 Local Bridge", html)
        self.assertIn('id="pluginSyncStatus"', html)
        self.assertIn('data-action="extract-safe-common-config"', html)
        self.assertIn('data-action="sync-claude-plugins"', html)
        self.assertIn('data-action="preview-bridge-dedupe"', html)
        self.assertIn('data-action="apply-bridge-dedupe"', html)
        self.assertIn('data-action="proxy-diagnosis"', html)
        self.assertIn('data-action="codex-native-proxy-status"', html)
        self.assertIn('data-action="repair-codex-native-proxy"', html)
        self.assertIn('id="proxyDiagnosis"', html)
        self.assertIn("不改模型、provider 或 config.toml", html)
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
        self.assertIn("const actualGlobalAccount = data.current_codex_launcher", html)
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

    def test_codex_desktop_mode_endpoints_require_explicit_post(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/codex-desktop-bridge-mode",
            method="POST",
            body={"account_id": "acct-1"},
            headers={"X-CCSBT-Token": "test-token"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["message"], "已开启 Codex Desktop 临时 Bridge 模式")

        status, payload = self.request(
            server,
            "/api/codex-desktop-native-mode",
            method="POST",
            body={},
            headers={"X-CCSBT-Token": "test-token"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["message"], "已恢复 Codex Desktop 原生配置")

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

    def test_port_active_connections_parses_lsof_field_output(self) -> None:
        proc = types.SimpleNamespace(
            returncode=0,
            stdout=(
                "p111\n"
                "clocal_codex\n"
                "n127.0.0.1:8876->127.0.0.1:52100\n"
                "p222\n"
                "cClaude\n"
                "n127.0.0.1:52100->127.0.0.1:8876\n"
            ),
        )

        with mock.patch.object(bridgedeck, "run_quiet", return_value=proc):
            connections = bridgedeck.port_active_connections(8876)

        self.assertEqual(len(connections), 2)
        self.assertEqual(connections[0]["pid"], 111)
        self.assertEqual(connections[1]["command"], "Claude")

    def test_local_bridge_restart_is_blocked_with_active_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = bridgedeck.BridgeManager(
                bridgedeck.ManagerPaths(
                    db=Path(tmp) / "cc-switch.db",
                    settings=Path(tmp) / "settings.json",
                    auth_store=Path(tmp) / "auth.json",
                )
            )
            with (
                mock.patch.object(
                    bridgedeck,
                    "port_processes",
                    return_value=[{"pid": 123, "command": "/Applications/BridgeDeck.app/Contents/Resources/local_codex_bridge.py"}],
                ),
                mock.patch.object(
                    bridgedeck,
                    "port_active_connections",
                    return_value=[{"pid": 456, "command": "Claude", "endpoint": "127.0.0.1:52100->127.0.0.1:8876"}],
                ),
                mock.patch.object(bridgedeck, "detect_upstream_proxy", return_value=""),
                mock.patch.object(bridgedeck, "tcp_open", return_value=True),
                mock.patch.object(bridgedeck, "read_local_bridge_state", return_value={}),
                mock.patch.object(bridgedeck.os, "kill") as kill,
            ):
                result = manager.control_local_bridge("restart")

        self.assertFalse(result["ok"])
        self.assertTrue(result["requires_force"])
        self.assertIn("正在被客户端使用", result["message"])
        kill.assert_not_called()

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
        self.assertIsNone(payload["context_config"])
        self.assertIsNone(payload["model_config"])

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

    def test_repair_claude_attribution_header_endpoint_returns_report(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/repair-claude-attribution-header",
            method="POST",
            body={},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["status"], "disabled")
        self.assertEqual(payload["updated_providers"][0]["id"], "provider-1")

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
        self.assertEqual(payload["codex_native_proxy"]["status"], "ok")

    def test_codex_native_proxy_endpoints_return_status_and_repair(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/codex-native-proxy-status",
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["proxy_port"], 1087)

        status, payload = self.request(
            server,
            "/api/repair-codex-native-proxy",
            method="POST",
            body={},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("WS_PROXY", payload["env_keys"])

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
        self.assertEqual(payload["usage_metrics"]["last_account_id"], "01234567...cdef")
        self.assertEqual(payload["usage_metrics"]["total_tokens"], 1540)
        self.assertEqual(payload["usage_events"][0]["account_id"], "01234567...cdef")
        self.assertEqual(payload["usage_events"][0]["input_tokens"], 1200)
        self.assertEqual(payload["usage_events"][0]["requested_model"], "claude-opus-4-7")
        self.assertEqual(payload["usage_events"][0]["actual_model"], "gpt-5.5")

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

    def test_local_bridge_control_accepts_force_flag(self) -> None:
        server, _ = self.start_server()

        status, payload = self.request(
            server,
            "/api/local-bridge-control",
            method="POST",
            body={"action": "restart", "force": True},
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["force"])

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

    def test_codex_native_proxy_status_marks_missing_websocket_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = bridgedeck.BridgeManager(
                bridgedeck.ManagerPaths(
                    db=root / ".cc-switch" / "cc-switch.db",
                    settings=root / ".cc-switch" / "settings.json",
                    auth_store=root / ".cc-switch" / "codex_oauth_auth.json",
                )
            )
            codex_home = root / ".codex"
            codex_home.mkdir(parents=True)
            (codex_home / ".env").write_text(
                "\n".join(
                    [
                        "HTTP_PROXY=http://127.0.0.1:1087",
                        "HTTPS_PROXY=http://127.0.0.1:1087",
                        "ALL_PROXY=http://127.0.0.1:1087",
                        "http_proxy=http://127.0.0.1:1087",
                        "https_proxy=http://127.0.0.1:1087",
                        "all_proxy=http://127.0.0.1:1087",
                        "NO_PROXY=127.0.0.1,localhost,::1",
                        "no_proxy=127.0.0.1,localhost,::1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home),
                mock.patch.object(bridgedeck, "tcp_open", return_value=True),
            ):
                status = manager.codex_native_proxy_status()

        self.assertEqual(status["status"], "incomplete")
        self.assertIn("WS_PROXY", status["missing_keys"])
        self.assertIn("WSS_PROXY", status["missing_keys"])

    def test_repair_codex_native_proxy_env_adds_ws_keys_and_preserves_unrelated_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = bridgedeck.BridgeManager(
                bridgedeck.ManagerPaths(
                    db=root / ".cc-switch" / "cc-switch.db",
                    settings=root / ".cc-switch" / "settings.json",
                    auth_store=root / ".cc-switch" / "codex_oauth_auth.json",
                )
            )
            codex_home = root / ".codex"
            codex_home.mkdir(parents=True)
            env_path = codex_home / ".env"
            config_path = codex_home / "config.toml"
            env_path.write_text(
                "CUSTOM_FLAG=keep\nHTTP_PROXY=http://127.0.0.1:1087\nNO_PROXY=old\n",
                encoding="utf-8",
            )
            os.chmod(env_path, 0o644)
            config_path.write_text('model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n', encoding="utf-8")

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home),
                mock.patch.object(bridgedeck, "tcp_open", side_effect=lambda host, port, timeout=0.25: port == 1087),
            ):
                result = manager.repair_codex_native_proxy()

            body = env_path.read_text(encoding="utf-8")
            self.assertTrue(result["changed"])
            self.assertIn("CUSTOM_FLAG=keep", body)
            self.assertIn("WS_PROXY=http://127.0.0.1:1087", body)
            self.assertIn("WSS_PROXY=http://127.0.0.1:1087", body)
            self.assertIn("ws_proxy=http://127.0.0.1:1087", body)
            self.assertIn("wss_proxy=http://127.0.0.1:1087", body)
            self.assertIn("NO_PROXY=localhost,127.0.0.1,::1", body)
            self.assertNotIn("127.0.0.1:6789", body)
            self.assertEqual(env_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config_path.read_text(encoding="utf-8"), 'model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n')

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

    def test_codex_oauth_authorize_url_uses_pkce_and_fixed_callback(self) -> None:
        url = bridgedeck.codex_oauth_authorize_url("state-1", "challenge-1")
        parsed = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", bridgedeck.CODEX_OAUTH_AUTHORIZE_URL)
        self.assertEqual(params["client_id"], [bridgedeck.CODEX_OAUTH_CLIENT_ID])
        self.assertEqual(params["redirect_uri"], [bridgedeck.CODEX_OAUTH_REDIRECT_URI])
        self.assertEqual(params["code_challenge"], ["challenge-1"])
        self.assertEqual(params["state"], ["state-1"])
        self.assertEqual(params["codex_cli_simplified_flow"], ["true"])
        self.assertNotIn("code_verifier", params)

    def test_parse_oauth_code_input_accepts_redirect_url_and_code_hash(self) -> None:
        parsed = bridgedeck.parse_oauth_code_input("http://localhost:1455/auth/callback?code=abc&state=xyz")
        self.assertEqual(parsed, {"code": "abc", "state": "xyz"})

        parsed = bridgedeck.parse_oauth_code_input("abc#xyz")
        self.assertEqual(parsed, {"code": "abc", "state": "xyz"})

    def test_request_codex_device_code_posts_ccswitch_shape(self) -> None:
        with mock.patch.object(
            bridgedeck,
            "_post_json_url",
            return_value={
                "device_auth_id": "deviceauth-test",
                "user_code": "ABCD-EFGH",
                "interval": "5",
                "expires_at": "2026-05-14T13:48:09Z",
            },
        ) as post:
            result = bridgedeck.request_codex_device_code()

        self.assertEqual(result["user_code"], "ABCD-EFGH")
        post.assert_called_once_with(
            bridgedeck.CODEX_DEVICE_USERCODE_URL,
            {"client_id": bridgedeck.CODEX_OAUTH_CLIENT_ID, "scope": bridgedeck.CODEX_DEVICE_SCOPE},
            user_agent=bridgedeck.CODEX_DEVICE_USER_AGENT,
        )

    def test_codex_oauth_device_flow_persists_across_ui_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = bridgedeck.ManagerPaths(
                db=root / "cc-switch.db",
                settings=root / "settings.json",
                auth_store=root / "codex_oauth_auth.json",
            )
            with mock.patch.object(
                bridgedeck,
                "request_codex_device_code",
                return_value={
                    "device_auth_id": "deviceauth-test",
                    "user_code": "ABCD-EFGH",
                    "interval": "5",
                    "expires_at": "2026-05-14T13:48:09Z",
                },
            ):
                started = bridgedeck.BridgeManager(paths).start_codex_oauth()

            restored = bridgedeck.BridgeManager(paths).codex_oauth_status(started["flow_id"])

        self.assertEqual(restored["status"], "pending")
        self.assertEqual(restored["user_code"], "ABCD-EFGH")

    def test_codex_oauth_exchanging_flow_reloads_as_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow_path = root / "bridgedeck-oauth-flows.json"
            flow_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "flows": [
                            {
                                "flow_id": "flow-1",
                                "set_default": False,
                                "created_at": time.time(),
                                "status": "exchanging",
                                "device_auth_id": "deviceauth-test",
                                "user_code": "ABCD-EFGH",
                                "verification_url": bridgedeck.CODEX_DEVICE_VERIFY_URL,
                                "interval": 5,
                                "next_poll_at": time.time() + 1000,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            paths = bridgedeck.ManagerPaths(
                db=root / "cc-switch.db",
                settings=root / "settings.json",
                auth_store=root / "codex_oauth_auth.json",
            )

            result = bridgedeck.BridgeManager(paths).codex_oauth_status("flow-1")

        self.assertEqual(result["status"], "pending")

    def test_exchange_codex_device_auth_exchanges_authorization_code(self) -> None:
        token = {"access_token": fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct"}}), "refresh_token": "refresh"}
        with mock.patch.object(
            bridgedeck,
            "_post_json_url",
            return_value={"authorization_code": "auth-code"},
        ), mock.patch.object(bridgedeck, "exchange_codex_oauth_code", return_value=token) as exchange:
            result = bridgedeck.exchange_codex_device_auth("deviceauth-test", "ABCD-EFGH")

        self.assertEqual(result, token)
        exchange.assert_called_once_with(
            "auth-code",
            bridgedeck.CODEX_DEVICE_CODE_VERIFIER,
            redirect_uri=bridgedeck.CODEX_DEVICE_REDIRECT_URI,
        )

    def test_exchange_codex_device_auth_uses_returned_code_verifier(self) -> None:
        token = {"access_token": fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct"}}), "refresh_token": "refresh"}
        with mock.patch.object(
            bridgedeck,
            "_post_json_url",
            return_value={"authorization_code": "auth-code", "code_verifier": "returned-verifier"},
        ), mock.patch.object(bridgedeck, "exchange_codex_oauth_code", return_value=token) as exchange:
            result = bridgedeck.exchange_codex_device_auth("deviceauth-test", "ABCD-EFGH")

        self.assertEqual(result, token)
        exchange.assert_called_once_with(
            "auth-code",
            "returned-verifier",
            redirect_uri=bridgedeck.CODEX_DEVICE_REDIRECT_URI,
        )

    def test_exchange_codex_device_auth_prefers_nested_token_payload(self) -> None:
        access = fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct"}})
        with mock.patch.object(
            bridgedeck,
            "_post_json_url",
            return_value={
                "authorization_code": "auth-code",
                "token": {"access_token": access, "refresh_token": "refresh"},
            },
        ), mock.patch.object(bridgedeck, "exchange_codex_oauth_code") as exchange:
            result = bridgedeck.exchange_codex_device_auth("deviceauth-test", "ABCD-EFGH")

        self.assertEqual(result["access_token"], access)
        self.assertEqual(result["refresh_token"], "refresh")
        exchange.assert_not_called()

    def test_exchange_codex_oauth_code_uses_ccswitch_headers(self) -> None:
        access = fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct"}})

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def read(self, max_bytes: int) -> bytes:
                return json.dumps({"access_token": access, "refresh_token": "refresh"}).encode()

        class FakeOpener:
            def open(self, request: urllib.request.Request, *, timeout: float) -> FakeResponse:
                self.request = request
                return FakeResponse()

        opener = FakeOpener()
        with mock.patch.object(bridgedeck, "_openai_oauth_opener", return_value=opener):
            bridgedeck.exchange_codex_oauth_code("code", "verifier", redirect_uri=bridgedeck.CODEX_DEVICE_REDIRECT_URI)

        self.assertEqual(opener.request.headers["User-agent"], bridgedeck.CODEX_DEVICE_USER_AGENT)
        self.assertEqual(opener.request.headers["Accept"], "application/json")

    def test_save_codex_oauth_account_stores_refresh_without_access_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_store = root / ".cc-switch" / "codex_oauth_auth.json"
            auth_store.parent.mkdir(parents=True, exist_ok=True)
            auth_store.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "accounts": {
                            "acct-existing": {
                                "account_id": "acct-existing",
                                "email": "old@example.com",
                                "refresh_token": "old-refresh",
                            }
                        },
                        "default_account_id": "acct-existing",
                    }
                ),
                encoding="utf-8",
            )
            manager = bridgedeck.BridgeManager(
                bridgedeck.ManagerPaths(
                    db=root / ".cc-switch" / "cc-switch.db",
                    settings=root / ".cc-switch" / "settings.json",
                    auth_store=auth_store,
                )
            )
            access = fake_jwt(
                {
                    "https://api.openai.com/auth": {"chatgpt_account_id": "acct-new"},
                    "https://api.openai.com/profile": {"email": "new@example.com"},
                }
            )

            account_id = manager._save_codex_oauth_account(
                {"access_token": access, "refresh_token": "new-refresh"},
                set_default=False,
            )

            saved = json.loads(auth_store.read_text(encoding="utf-8"))
            self.assertEqual(account_id, "acct-new")
            self.assertEqual(saved["default_account_id"], "acct-existing")
            self.assertEqual(saved["accounts"]["acct-new"]["email"], "new@example.com")
            self.assertEqual(saved["accounts"]["acct-new"]["refresh_token"], "new-refresh")
            self.assertNotIn("access_token", saved["accounts"]["acct-new"])

    def test_managed_codex_provider_uses_auth_store_binding_over_embedded_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(manager.paths.db) as conn:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT NOT NULL,
                        app_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        settings_config TEXT NOT NULL,
                        meta TEXT NOT NULL,
                        provider_type TEXT,
                        is_current BOOLEAN NOT NULL DEFAULT 0,
                        sort_index INTEGER
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO providers (
                        id, app_type, name, settings_config, meta, provider_type, is_current, sort_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "codex-1",
                        "codex",
                        "OpenAI PRO",
                        json.dumps(
                            {"auth": {"tokens": {"account_id": "acct-2", "refresh_token": "old-token"}}}
                        ),
                        json.dumps(
                            {
                                "authBinding": {
                                    "source": "managed_account",
                                    "authProvider": "codex_oauth",
                                    "accountId": "acct-1",
                                }
                            }
                        ),
                        "codex_oauth",
                        1,
                        1,
                    ),
                )

            with manager._connect() as conn:
                providers = manager._list_codex_providers(conn)

        self.assertEqual(providers[0]["meta_account_id"], "acct-1")
        self.assertEqual(providers[0]["token_account_id"], "acct-1")
        self.assertEqual(providers[0]["embedded_token_account_id"], "acct-2")
        self.assertTrue(providers[0]["uses_managed_auth_store"])
        self.assertTrue(providers[0]["embedded_token_stale"])
        self.assertFalse(providers[0]["token_mismatch"])

    def test_snapshot_lists_claude_desktop_surface_and_route_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(manager.paths.db) as conn:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        app_type TEXT,
                        name TEXT,
                        settings_config TEXT,
                        meta TEXT,
                        provider_type TEXT,
                        is_current BOOLEAN,
                        sort_index INTEGER
                    )
                    """
                )
                settings = json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                            "ANTHROPIC_AUTH_TOKEN": "local-bridge",
                            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.3-codex-spark",
                            "ANTHROPIC_DEFAULT_SONNET_MODEL": "gpt-5.3-codex",
                            "ANTHROPIC_DEFAULT_OPUS_MODEL": "gpt-5.5",
                        }
                    }
                )
                meta = json.dumps(
                    {
                        "apiFormat": "openai_responses",
                        "claudeDesktopMode": "proxy",
                        "authBinding": {"source": "managed_account", "authProvider": "codex_oauth", "accountId": "acct-1"},
                        "claudeDesktopModelRoutes": {
                            "claude-opus-4-7": {"model": "gpt-5.5", "labelOverride": "gpt-5.5"}
                        },
                    }
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("code-1", "claude", "Local Codex Bridge - Pro", settings, json.dumps({}), None, 1, 1),
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("desktop-1", "claude-desktop", "Local Codex Bridge - Pro", settings, meta, None, 1, 1),
                )
                external_settings = json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "https://api.example.test/anthropic",
                            "ANTHROPIC_AUTH_TOKEN": "test-token",
                        }
                    }
                )
                external_meta = json.dumps({"apiFormat": "anthropic", "claudeDesktopMode": "proxy"})
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("desktop-2", "claude-desktop", "External Model", external_settings, external_meta, None, 0, 2),
                )

            with (
                mock.patch.object(manager, "sync_claude_enabled_plugins", return_value={"ok": True, "changed": False}),
                mock.patch.object(manager, "claude_plugin_sync_status", return_value={"ok": True}),
                mock.patch.object(manager, "claude_attribution_header_status", return_value={"ok": True, "status": "disabled"}),
            ):
                snapshot = manager.snapshot(include_secrets=False)

        self.assertEqual(len(snapshot["providers"]), 1)
        self.assertEqual(len(snapshot["claude_desktop_providers"]), 2)
        desktop = next(item for item in snapshot["claude_desktop_providers"] if item["id"] == "desktop-1")
        self.assertEqual(desktop["surface"], "claude_desktop")
        self.assertEqual(desktop["desktop_route_scope"], "local_bridge")
        self.assertFalse(desktop["desktop_routes_ok"])
        self.assertGreater(snapshot["ccswitch_315"]["desktop_route_issue_count"], 0)
        external = next(item for item in snapshot["claude_desktop_providers"] if item["id"] == "desktop-2")
        self.assertEqual(external["desktop_route_scope"], "unmanaged")
        self.assertTrue(external["desktop_routes_ok"])
        self.assertEqual(external["desktop_route_issues"], [])

    def test_repair_ccswitch_315_desktop_routes_previews_then_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(manager.paths.db) as conn:
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        app_type TEXT,
                        name TEXT,
                        settings_config TEXT,
                        meta TEXT,
                        provider_type TEXT,
                        is_current BOOLEAN,
                        sort_index INTEGER
                    )
                    """
                )
                settings = json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                            "ANTHROPIC_AUTH_TOKEN": "local-bridge",
                            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.3-codex-spark",
                            "ANTHROPIC_DEFAULT_SONNET_MODEL": "gpt-5.3-codex",
                            "ANTHROPIC_DEFAULT_OPUS_MODEL": "gpt-5.5",
                        }
                    }
                )
                meta = json.dumps(
                    {
                        "apiFormat": "openai_responses",
                        "claudeDesktopMode": "proxy",
                        "authBinding": {"source": "managed_account", "authProvider": "codex_oauth", "accountId": "acct-1"},
                        "claudeDesktopModelRoutes": {
                            "claude-opus-4-7": {"model": "gpt-5.5", "labelOverride": "gpt-5.5"}
                        },
                    }
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("desktop-1", "claude-desktop", "Local Codex Bridge - Pro", settings, meta, None, 1, 1),
                )

            preview = manager.repair_ccswitch_315_desktop_routes(apply=False)
            with sqlite3.connect(manager.paths.db) as conn:
                before_meta = json.loads(conn.execute("SELECT meta FROM providers WHERE id='desktop-1'").fetchone()[0])
            applied = manager.repair_ccswitch_315_desktop_routes(apply=True)
            with sqlite3.connect(manager.paths.db) as conn:
                after_meta = json.loads(conn.execute("SELECT meta FROM providers WHERE id='desktop-1'").fetchone()[0])

        self.assertFalse(preview["apply"])
        self.assertTrue(preview["plan"][0]["changed"])
        self.assertNotIn("claude-haiku-4-5", before_meta["claudeDesktopModelRoutes"])
        self.assertTrue(applied["apply"])
        self.assertEqual(applied["updated"][0]["id"], "desktop-1")
        routes = after_meta["claudeDesktopModelRoutes"]
        self.assertEqual(routes["claude-haiku-4-5"]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(routes["claude-haiku-4-5"]["labelOverride"], "Haiku 4.5")
        self.assertEqual(routes["claude-sonnet-4-6"]["model"], "gpt-5.3-codex")
        self.assertEqual(routes["claude-sonnet-4-6"]["labelOverride"], "Sonnet 4.6")
        self.assertEqual(routes["claude-opus-4-7"]["model"], "gpt-5.5")
        self.assertEqual(routes["claude-opus-4-7"]["labelOverride"], "Opus 4.7")
        self.assertFalse(routes["claude-opus-4-7"]["supports1m"])

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
            self.assertNotIn("ANTHROPIC_MODEL", env)
            self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "gpt-5.3-codex-spark")
            self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME"], "Haiku 4.5")
            self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "gpt-5.3-codex")
            self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL_NAME"], "Sonnet 4.6")
            self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "gpt-5.5")
            self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL_NAME"], "Opus 4.7")
            self.assertEqual(env["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")
            self.assertEqual(meta["apiFormat"], "openai_responses")
            self.assertEqual(meta["codexOauthTransport"], "local_bridge")
            self.assertEqual(meta["authBinding"]["authProvider"], "codex_oauth")
            self.assertTrue(meta["usage_script"]["enabled"])
            self.assertEqual(meta["usage_script"]["templateType"], "custom")
            self.assertIn("http://127.0.0.1:8876/accounts/acct-1/quota", meta["usage_script"]["code"])
            self.assertIn('planName: "five_hour"', meta["usage_script"]["code"])
            self.assertIn('planName: "weekly_limit"', meta["usage_script"]["code"])
            self.assertNotIn("providerType", meta)

    def test_local_bridge_provider_payload_masks_gpt_model_menu_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={
                    "env": {
                        "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME": "gpt-5.3-codex-spark",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "Team Sonnet",
                        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "gpt-5.5",
                    }
                },
            )

            env = settings["env"]
            self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME"], "Haiku 4.5")
            self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL_NAME"], "Team Sonnet")
            self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL_NAME"], "Opus 4.7")

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

    def test_provider_payload_preserves_explicit_attribution_header_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={
                    "env": {
                        "CLAUDE_CODE_ATTRIBUTION_HEADER": "1",
                        "ANTHROPIC_BASE_URL": "http://old.example.com",
                        "ANTHROPIC_AUTH_TOKEN": "old-token",
                    }
                },
            )

            env = settings["env"]
            self.assertEqual(env["CLAUDE_CODE_ATTRIBUTION_HEADER"], "1")
            self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "local-bridge")

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

    def test_provider_payload_applies_context_without_forcing_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))

            settings, _ = manager._build_provider_payload(
                "acct-1",
                settings_config={"env": {}},
                context_config={"model": "GPT-5.5"},
            )

            env = settings["env"]
            self.assertNotIn("ANTHROPIC_MODEL", env)
            self.assertEqual(env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "272000")

    def test_unknown_bridge_model_does_not_invent_context(self) -> None:
        normalized = bridgedeck.normalize_bridge_model_config({"model": "gpt-unknown"})

        self.assertEqual(normalized["model"], "gpt-unknown")
        self.assertEqual(normalized["context_tokens"], "")
        self.assertEqual(normalized["max_output_tokens"], "")

    def test_gpt54_bridge_model_uses_known_context(self) -> None:
        normalized = bridgedeck.normalize_bridge_model_config({"model": "gpt-5.4"})

        self.assertEqual(normalized["model"], "gpt-5.4")
        self.assertEqual(normalized["context_tokens"], "220000")
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
                    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
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
            self.assertEqual(db_common["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", db_common["env"])
            self.assertNotIn("ANTHROPIC_MODEL", db_common["env"])
            self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", db_common["env"])

    def test_claude_attribution_header_status_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            common = root / ".ccswitch-common-config.json"
            settings = root / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CCSWITCH_COMMON_CONFIG_PATH", common),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_SETTINGS_PATH", settings),
            ):
                self.assertEqual(manager.claude_attribution_header_status()["status"], "unknown")

                settings.write_text(json.dumps({"env": {}}), encoding="utf-8")
                self.assertEqual(manager.claude_attribution_header_status()["status"], "enabled")

                common.write_text(json.dumps({"env": {"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"}}), encoding="utf-8")
                settings.write_text(json.dumps({"env": {"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"}}), encoding="utf-8")
                self.assertEqual(manager.claude_attribution_header_status()["status"], "disabled")

                common.write_text(json.dumps({"env": {"CLAUDE_CODE_ATTRIBUTION_HEADER": "1"}}), encoding="utf-8")
                self.assertEqual(manager.claude_attribution_header_status()["status"], "inconsistent")

    def test_repair_claude_attribution_header_updates_managed_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            common = root / ".ccswitch-common-config.json"
            settings = root / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(
                json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://provider.example.com", "KEEP": "1"}}),
                encoding="utf-8",
            )
            common.write_text(
                json.dumps({"env": {"CLAUDE_CODE_ATTRIBUTION_HEADER": "1", "ENABLE_TOOL_SEARCH": "true"}}),
                encoding="utf-8",
            )
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
                conn.execute(
                    "INSERT INTO settings VALUES (?, ?)",
                    ("common_config_claude", json.dumps({"env": {"ENABLE_TOOL_SEARCH": "true"}})),
                )
                conn.execute(
                    """
                    CREATE TABLE providers (
                        id TEXT,
                        name TEXT,
                        app_type TEXT,
                        settings_config TEXT,
                        meta TEXT,
                        sort_index INTEGER
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "local",
                        "Local Codex Bridge - Pro",
                        "claude",
                        json.dumps(
                            {
                                "env": {
                                    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                                    "ANTHROPIC_AUTH_TOKEN": "local-bridge",
                                    "OTHER": "keep",
                                }
                            }
                        ),
                        json.dumps({"codexOauthTransport": "local_bridge"}),
                        1,
                    ),
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "external",
                        "External",
                        "claude",
                        json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://example.com", "OTHER": "keep"}}),
                        "{}",
                        2,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            with (
                mock.patch.object(bridgedeck, "DEFAULT_CCSWITCH_COMMON_CONFIG_PATH", common),
                mock.patch.object(bridgedeck, "DEFAULT_CLAUDE_SETTINGS_PATH", settings),
            ):
                result = manager.repair_claude_attribution_header()

            self.assertTrue(result["ok"])
            self.assertTrue(result["changed"])
            loaded_settings = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(loaded_settings["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")
            self.assertEqual(loaded_settings["env"]["ANTHROPIC_BASE_URL"], "https://provider.example.com")
            loaded_common = json.loads(common.read_text(encoding="utf-8"))
            self.assertEqual(loaded_common["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")
            self.assertEqual(loaded_common["env"]["ENABLE_TOOL_SEARCH"], "true")

            conn = sqlite3.connect(manager.paths.db)
            try:
                db_common = json.loads(
                    conn.execute("SELECT value FROM settings WHERE key = 'common_config_claude'").fetchone()[0]
                )
                self.assertEqual(db_common["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")
                rows = {
                    row[0]: json.loads(row[1])
                    for row in conn.execute("SELECT id, settings_config FROM providers ORDER BY id").fetchall()
                }
            finally:
                conn.close()
            self.assertEqual(rows["local"]["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")
            self.assertEqual(rows["local"]["env"]["OTHER"], "keep")
            self.assertNotIn("CLAUDE_CODE_ATTRIBUTION_HEADER", rows["external"]["env"])

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
            self.assertNotIn("ANTHROPIC_MODEL", settings["env"])

    def test_create_provider_drops_template_forced_model_by_default(self) -> None:
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
                        "template",
                        "MiniMax",
                        "claude",
                        json.dumps(
                            {
                                "env": {
                                    "ANTHROPIC_MODEL": "gpt-5.4",
                                    "HUB_CLAUDE_MEM": "1",
                                }
                            }
                        ),
                        json.dumps({}),
                        None,
                        1,
                    ),
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
            self.assertNotIn("ANTHROPIC_MODEL", settings["env"])
            self.assertEqual(settings["env"]["HUB_CLAUDE_MEM"], "1")

    def test_update_provider_compact_does_not_change_forced_model(self) -> None:
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
                        settings_config TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?)",
                    (
                        "provider",
                        "Local Codex Bridge - Pro 20x",
                        "claude",
                        json.dumps(
                            {
                                "env": {
                                    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                                    "ANTHROPIC_AUTH_TOKEN": "local-bridge",
                                    "ANTHROPIC_MODEL": "gpt-5.4",
                                }
                            }
                        ),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            manager.update_provider_compact(
                "provider",
                {"enabled": True, "window_tokens": "272000", "threshold_percent": "80"},
                context_config={"model": "gpt-5.5"},
                model_config={"model": "gpt-5.5"},
            )

            conn = sqlite3.connect(manager.paths.db)
            try:
                settings = json.loads(conn.execute("SELECT settings_config FROM providers WHERE id = 'provider'").fetchone()[0])
            finally:
                conn.close()
            self.assertEqual(settings["env"]["ANTHROPIC_MODEL"], "gpt-5.4")
            self.assertEqual(settings["env"]["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "272000")
            self.assertEqual(settings["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "272000")

    def test_update_provider_forced_model_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute("CREATE TABLE providers (id TEXT, name TEXT, app_type TEXT, settings_config TEXT)")
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?)",
                    (
                        "provider",
                        "Local Codex Bridge - Pro",
                        "claude",
                        json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1"}}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            result = manager.update_provider_forced_model("provider", {"model": "GPT-5.5"})

            conn = sqlite3.connect(manager.paths.db)
            try:
                settings = json.loads(conn.execute("SELECT settings_config FROM providers WHERE id = 'provider'").fetchone()[0])
            finally:
                conn.close()
            self.assertEqual(result["model_config"]["model"], "gpt-5.5")
            self.assertEqual(settings["env"]["ANTHROPIC_MODEL"], "gpt-5.5")
            self.assertEqual(settings["env"]["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "272000")

    def test_clear_provider_forced_model_previews_then_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            manager.paths.db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(manager.paths.db)
            try:
                conn.execute("CREATE TABLE providers (id TEXT, name TEXT, app_type TEXT, settings_config TEXT)")
                conn.execute(
                    "INSERT INTO providers VALUES (?, ?, ?, ?)",
                    (
                        "provider",
                        "Local Codex Bridge - Pro",
                        "claude",
                        json.dumps(
                            {
                                "env": {
                                    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/acct-1",
                                    "ANTHROPIC_MODEL": "gpt-5.5",
                                    "ANTHROPIC_DEFAULT_OPUS_MODEL": "gpt-5.5",
                                }
                            }
                        ),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            preview = manager.clear_provider_forced_model("provider", apply=False)
            applied = manager.clear_provider_forced_model("provider", apply=True)

            conn = sqlite3.connect(manager.paths.db)
            try:
                settings = json.loads(conn.execute("SELECT settings_config FROM providers WHERE id = 'provider'").fetchone()[0])
            finally:
                conn.close()
            self.assertTrue(preview["changed"])
            self.assertEqual(preview["removed_model"], "gpt-5.5")
            self.assertTrue(applied["changed"])
            self.assertNotIn("ANTHROPIC_MODEL", settings["env"])
            self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "gpt-5.5")

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

    def test_set_default_codex_account_writes_launcher_only_and_leaves_desktop_config(self) -> None:
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
                '\n'.join(
                    [
                        'model = "gpt-5.5"',
                        'base_url = "http://127.0.0.1:15721/v1"',
                        '[shell_environment_policy]',
                        'inherit = "core"',
                        '[shell_environment_policy.set]',
                        'ANTHROPIC_AUTH_TOKEN = "PROXY_MANAGED"',
                        'ANTHROPIC_BASE_URL = "http://127.0.0.1:15721"',
                        'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"',
                        "",
                    ]
                ),
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
            self.assertIn('base_url = "http://127.0.0.1:15721/v1"', body)
            self.assertNotIn('base_url = "http://127.0.0.1:8876/accounts/acct-1/v1"', body)
            self.assertIn('model = "gpt-5.5"', body)
            self.assertIn("ANTHROPIC_AUTH_TOKEN", body)
            self.assertIn("ANTHROPIC_BASE_URL", body)
            self.assertIn("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", body)
            self.assertEqual(result["removed_env_keys"], [])
            self.assertNotIn("secret-refresh-token", body)
            self.assertNotIn("access_token", body)
            self.assertFalse(result["desktop_affected"])
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

    def test_codex_desktop_bridge_mode_is_explicit_and_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            config.write_text('model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\nnotify = ["done"]\n', encoding="utf-8")

            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                enabled = manager.enable_codex_desktop_bridge_mode("acct-1")
                status = manager._codex_desktop_status()

            body = config.read_text(encoding="utf-8")
            self.assertTrue(enabled["changed"])
            self.assertIn(bridgedeck.MANAGED_CODEX_DESKTOP_BRIDGE_START, body)
            self.assertIn('model_provider = "bridgedeck"', body)
            self.assertIn("[model_providers.bridgedeck]", body)
            self.assertIn('base_url = "http://127.0.0.1:8876/accounts/acct-1/v1"', body)
            self.assertIn('experimental_bearer_token = "local-bridge"', body)
            self.assertIn('supports_websockets = false', body)
            self.assertNotIn('model = "gpt-5.5"', body)
            self.assertNotIn("model_reasoning_effort", body)
            self.assertNotIn('service_tier = "fast"', body)
            self.assertEqual(status["managed_by"], "bridgedeck_provider")
            self.assertEqual(status["account_id"], "acct-1")
            self.assertIn("model", enabled["stripped_legacy_keys"])
            self.assertIn("model_reasoning_effort", enabled["stripped_legacy_keys"])

            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                restored = manager.restore_codex_desktop_native_mode()

            self.assertTrue(restored["changed"])
            self.assertEqual(config.read_text(encoding="utf-8"), 'notify = ["done"]\n')
            self.assertIn("managed_bridge_block", restored["removed"])

    def test_restore_codex_desktop_native_mode_removes_static_native_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            config.write_text(
                "\n".join(
                    [
                        'model = "gpt-5.5"',
                        'model_reasoning_effort = "xhigh"',
                        'service_tier = "fast"',
                        "",
                        "[features]",
                        "hooks = true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                result = manager.restore_codex_desktop_native_mode()

            body = config.read_text(encoding="utf-8")
            self.assertTrue(result["changed"])
            self.assertNotIn('model = "gpt-5.5"', body)
            self.assertNotIn("model_reasoning_effort", body)
            self.assertNotIn("service_tier", body)
            self.assertIn("[features]", body)
            self.assertIn("hooks = true", body)
            self.assertEqual(result["removed"], ["model", "model_reasoning_effort", "service_tier"])

    def test_restore_codex_desktop_native_mode_removes_legacy_bridgedeck_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            config.write_text(
                '\n'.join(
                    [
                        'model_provider = "bridgedeck"',
                        'model = "gpt-5.5"',
                        'model_reasoning_effort = "xhigh"',
                        'service_tier = "fast"',
                        "",
                        "[model_providers.bridgedeck]",
                        'name = "OpenAI"',
                        'base_url = "http://127.0.0.1:8876/accounts/acct-1/v1"',
                        'wire_api = "responses"',
                        "",
                        "[features]",
                        "hooks = true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                result = manager.restore_codex_desktop_native_mode()

            body = config.read_text(encoding="utf-8")
            self.assertTrue(result["changed"])
            self.assertNotIn("bridgedeck", body)
            self.assertNotIn('model = "gpt-5.5"', body)
            self.assertNotIn("model_reasoning_effort", body)
            self.assertNotIn("service_tier", body)
            self.assertIn("[features]", body)
            self.assertIn("hooks = true", body)

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

    def test_repair_codex_environment_conflicts_removes_only_global_anthropic_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            codex_home = root / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            config.write_text(
                '\n'.join(
                    [
                        'base_url = "http://127.0.0.1:8876/accounts/acct-1/v1"',
                        '[shell_environment_policy.set]',
                        'ANTHROPIC_AUTH_TOKEN = "PROXY_MANAGED"',
                        'ANTHROPIC_BASE_URL = "http://127.0.0.1:15721"',
                        'CLAUDE_CODE_AUTO_COMPACT_WINDOW = "220000"',
                        '[notice.model_migrations]',
                        '"gpt-5.3-codex" = "gpt-5.4"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                result = manager.repair_codex_environment_conflicts()

            body = config.read_text(encoding="utf-8")
            self.assertTrue(result["changed"])
            self.assertEqual(result["removed_env_keys"], ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"])
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", body)
            self.assertNotIn("ANTHROPIC_BASE_URL", body)
            self.assertIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", body)
            self.assertIn("[notice.model_migrations]", body)
            self.assertTrue(result["backup"])

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
