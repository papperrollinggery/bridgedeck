from __future__ import annotations

import json
import http.client
import io
import sqlite3
import tempfile
import threading
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
    ) -> dict[str, Any]:
        return {"ok": True}

    def patch_provider(self, provider_id: str) -> dict[str, Any]:
        return {"ok": True}

    def update_provider_compact(self, provider_id: str, compact_config: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "上下文配置已保存",
            "provider_id": provider_id,
            "compact_config": bridgedeck.normalize_compact_config(compact_config),
        }

    def sync_common_env_to_bridge_providers(self, provider_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "通用 env 已同步",
            "source_provider_id": provider_id,
            "env_keys": ["ANTHROPIC_MODEL", "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "HUB_CLAUDE_MEM"],
            "updated": [{"id": "provider-1", "name": "Provider"}],
            "skipped": [],
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
        self.assertIn("当前实际", html)
        self.assertIn('id="autoSwitchEnabled"', html)
        self.assertIn("OpenAI 自动切换", html)
        self.assertIn("为新账号创建 Local Codex Bridge", html)
        self.assertIn('id="compactWindow"', html)
        self.assertIn('data-action="compact-preset-1m"', html)
        self.assertIn('data-action="save-compact-selected"', html)
        self.assertIn('data-action="sync-common-env-selected"', html)
        self.assertIn('data-action="preview-bridge-dedupe"', html)
        self.assertIn('data-action="apply-bridge-dedupe"', html)
        self.assertIn('id="actualCurrentAccounts"', html)
        self.assertIn("const actualGlobalAccount = data.codex_desktop", html)
        self.assertIn("renderAccounts(data);", html)
        self.assertIn("Spark", html)
        self.assertNotIn('id="simpleAccount"', html)
        self.assertNotIn("今天用哪个账号", html)

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
                "compact_config": {"enabled": True, "window_tokens": "1000000", "threshold_percent": "80"},
            },
            headers={"X-CCSBT-Token": "test-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["compact_config"]["window_tokens"], "1000000")

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

    def test_remote_services_redacts_process_paths_and_proxy(self) -> None:
        server, _ = self.start_server(allow_sensitive=False, allow_remote_access=True)

        status, payload = self.request(server, "/api/services", headers={"X-CCSBT-Token": "test-token"})

        local_bridge = payload["services"]["local_bridge"]
        self.assertEqual(status, 200)
        self.assertNotIn("processes", local_bridge)
        self.assertNotIn("script", local_bridge)
        self.assertNotIn("log_path", local_bridge)
        self.assertEqual(local_bridge["upstream_proxy"], "<redacted>")
        self.assertNotIn("/Users/person", json.dumps(payload))
        self.assertNotIn("user:pass", json.dumps(payload))


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
            self.assertEqual(target_env["ANTHROPIC_MODEL"], "gpt-5.5")
            self.assertEqual(target_env["HUB_CLAUDE_MEM"], "1")
            self.assertEqual(target_env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "220000")
            self.assertEqual(target_env["TARGET_ONLY"], "keep")
            self.assertEqual(external_env["ANTHROPIC_AUTH_TOKEN"], "external-token")

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
            config = codex_home / "config.toml"
            config.write_text(
                'model = "gpt-5.5"\nbase_url = "http://127.0.0.1:15721/v1"\n',
                encoding="utf-8",
            )

            with mock.patch.object(bridgedeck, "DEFAULT_CODEX_HOME", codex_home):
                result = manager.set_default_codex_account("acct-1")

            body = config.read_text(encoding="utf-8")
            self.assertTrue(result["ok"])
            self.assertIn('base_url = "http://127.0.0.1:8876/accounts/acct-1/v1"', body)
            self.assertIn('model = "gpt-5.5"', body)
            self.assertNotIn("secret-refresh-token", body)
            self.assertNotIn("access_token", body)
            self.assertTrue(result["backups"])

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
