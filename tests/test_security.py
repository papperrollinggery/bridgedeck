from __future__ import annotations

import json
import http.client
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bridgedeck


class FakeManager:
    def __init__(self) -> None:
        self.set_current_called = False

    def snapshot(self, include_secrets: bool = False) -> dict[str, Any]:
        return {
            "version": bridgedeck.APP_VERSION,
            "paths": {"db": "", "settings": "", "auth_store": ""},
            "exists": {"db": False, "settings": False, "auth_store": False},
            "accounts": [],
            "providers": [
                {
                    "id": "provider-1",
                    "name": "Provider",
                    "auth_token": "full-token" if include_secrets else "",
                    "auth_token_masked": "full...oken",
                }
            ],
            "codex_providers": [],
            "cli_homes": [],
            "current_provider_from_settings": "",
        }

    def set_current_provider(self, provider_id: str) -> dict[str, Any]:
        self.set_current_called = True
        return {"ok": True, "provider_id": provider_id}

    def create_or_update_provider(self, account_id: str, provider_name: str, set_current: bool) -> dict[str, Any]:
        return {"ok": True}

    def patch_provider(self, provider_id: str) -> dict[str, Any]:
        return {"ok": True}

    def repair_plus_pro(self) -> dict[str, Any]:
        return {"ok": True}

    def create_or_sync_cli_home(self, account_id: str, target_dir: str, profile_name: str) -> dict[str, Any]:
        return {"ok": True}


class ServerCase(unittest.TestCase):
    def start_server(self, *, allow_sensitive: bool = True, allow_remote_access: bool = False):
        manager = FakeManager()
        handler = bridgedeck.build_handler(
            manager,
            "test-token",
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


if __name__ == "__main__":
    unittest.main()
