import copy
import http.client
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import test_security as fixtures
import bridgedeck
import local_codex_bridge
import model_catalog


class GPT6CompatibilityCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bridgedeck-gpt6-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "models.json"
        patcher = mock.patch.object(model_catalog, "MODELS_CACHE_PATH", self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_cache(self, models, **metadata):
        self.cache.write_text(json.dumps({"models": models, **metadata}), encoding="utf-8")

    def test_astra_available_offline_with_codex_limits_and_efforts(self):
        for cache_contents in (None, "{broken", "[]"):
            with self.subTest(cache=cache_contents):
                if cache_contents is not None:
                    self.cache.write_text(cache_contents)
                model = model_catalog.model_by_id("gpt-6-astra")
                self.assertEqual(model["context_tokens"], 272000)
                self.assertEqual(model["max_context_tokens"], 872000)
                self.assertEqual(model["max_output_tokens"], 128000)
                self.assertEqual(model["thinking_levels"], ("low", "medium", "high", "xhigh", "max", "ultra"))
                for effort in ("none", "minimal"):
                    self.assertEqual(model_catalog.normalize_reasoning_effort(model["id"], effort)["effective"], "low")
                self.assertEqual(model_catalog.normalize_reasoning_effort(model["id"], "ultra")["effective"], "ultra")
                self.assertTrue(model_catalog.public_catalog()["stale"])

    def test_malformed_cache_entry_does_not_hide_later_models(self):
        self.write_cache([
            {"slug": "gpt-9.1", "supported_reasoning_levels": 42, "context_window": True},
            {"slug": "gpt-9.2", "context_window": 333000, "supported_reasoning_levels": [{"effort": "high"}], "default_reasoning_level": "invalid"},
            {"slug": "gpt-9.3</script>"},
        ])
        self.assertIsNone(model_catalog.model_by_id("gpt-9.1")["context_tokens"])
        self.assertEqual(model_catalog.model_by_id("gpt-9.2")["default_reasoning_level"], "high")
        self.assertIsNone(model_catalog.model_by_id("gpt-9.3</script>"))
        self.assertEqual(model_catalog.public_catalog()["source"], "codex_models_cache")

    def test_fetched_timestamp_drives_staleness_even_when_file_is_new(self):
        self.write_cache([{"slug": "gpt-6-astra"}], fetched_at="2000-01-01T00:00:00Z")
        self.assertTrue(model_catalog.public_catalog()["stale"])
        self.write_cache([{"slug": "gpt-6-astra"}], fetched_at="not-a-date")
        self.assertTrue(model_catalog.public_catalog()["stale"])

    def test_current_cache_metadata_reaches_models_endpoint(self):
        self.write_cache([{
            "slug": "gpt-5.6-sol", "context_window": 272000, "max_context_window": 872000,
            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
            "default_reasoning_level": "low",
        }])
        listed = {item["id"]: item for item in local_codex_bridge.build_models_payload()["data"]}
        self.assertEqual(listed["gpt-5.6-sol"]["context_window"], 272000)
        self.assertEqual(listed["gpt-5.6-sol"]["max_context_window"], 872000)
        self.assertEqual(listed["gpt-5.6-sol"]["default_reasoning_level"], "low")
        self.assertEqual(listed["gpt-5.6-sol"]["max_completion_tokens"], 128000)

    def test_astra_normalization_preserves_supported_fields_and_input(self):
        body = {
            "model": "gpt-6-astra", "reasoning": {"effort": "none"},
            "temperature": 0.3, "top_p": 0.8, "top_logprobs": 3, "logprobs": True,
            "include": ["message.output_text.logprobs", "file_search_call.results"],
            "prompt_cache_retention": "24h",
            "tools": [{"type": "function", "name": "lookup", "async": True, "parameters": {"type": "object"}}],
            "input": [{"type": "configuration_update", "reasoning": {"effort": "high"}}],
        }
        original = copy.deepcopy(body)
        result = local_codex_bridge.normalize_request_body(body)
        self.assertEqual(result["reasoning"]["effort"], "low")
        self.assertEqual(result["prompt_cache_options"], {"ttl": "30m"})
        for key in ("temperature", "top_p", "top_logprobs", "logprobs", "prompt_cache_retention", "parallel_tool_calls"):
            self.assertNotIn(key, result)
        self.assertNotIn("message.output_text.logprobs", result["include"])
        self.assertIn("file_search_call.results", result["include"])
        self.assertIn("reasoning.encrypted_content", result["include"])
        self.assertEqual(result["tools"], body["tools"])
        self.assertEqual(result["input"], body["input"])
        self.assertEqual(body, original)

    def test_explicit_cache_options_and_parallel_choice_win(self):
        body = {"model": "gpt-6-astra", "prompt_cache_retention": "24h", "prompt_cache_options": {"ttl": "30m", "key": "caller"}, "parallel_tool_calls": False}
        result = local_codex_bridge.normalize_request_body(body)
        self.assertEqual(result["prompt_cache_options"], body["prompt_cache_options"])
        self.assertFalse(result["parallel_tool_calls"])
        legacy = local_codex_bridge.normalize_request_body({"model": "gpt-5.5", "prompt_cache_retention": "24h", "top_logprobs": 3})
        self.assertEqual(legacy["prompt_cache_retention"], "24h")
        self.assertEqual(legacy["top_logprobs"], 3)

    def test_both_compatibility_inputs_keep_astra_and_clamp_minimal(self):
        chat = local_codex_bridge.chat_completions_to_responses({
            "model": "gpt-6-astra", "messages": [{"role": "user", "content": "hi"}], "reasoning_effort": "minimal",
            "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
        })
        converted = local_codex_bridge.normalize_request_body(chat)
        self.assertEqual(converted["model"], "gpt-6-astra")
        self.assertEqual(converted["reasoning"]["effort"], "low")
        self.assertEqual(converted["tools"][0]["name"], "lookup")
        anthropic = local_codex_bridge.anthropic_messages_to_responses({
            "model": "gpt-6-astra", "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": 1000},
            "tools": [{"name": "lookup", "input_schema": {"type": "object"}}],
        })
        converted = local_codex_bridge.normalize_request_body(anthropic)
        self.assertEqual(converted["model"], "gpt-6-astra")
        self.assertEqual(converted["reasoning"]["effort"], "low")
        self.assertEqual(converted["tools"][0]["name"], "lookup")

    def make_manager(self, surface):
        manager = bridgedeck.BridgeManager(bridgedeck.ManagerPaths(
            db=self.root / "providers.db", settings=self.root / "settings.json", auth_store=self.root / "auth.json",
        ))
        original = {"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8876/accounts/fixture/v1", "ANTHROPIC_MODEL": "gpt-5.5", "X_USER_SETTING": "keep"}}
        with closing(sqlite3.connect(manager.paths.db)) as conn, conn:
            conn.execute("CREATE TABLE providers (id TEXT, app_type TEXT, name TEXT, settings_config TEXT, meta TEXT)")
            conn.execute("INSERT INTO providers VALUES (?, ?, ?, ?, ?)", ("fixture", surface, "Fixture", json.dumps(original), "{}"))
        return manager, original

    def test_astra_preset_preview_apply_idempotence_and_desktop_routes(self):
        for surface in ("claude", "claude-desktop"):
            with self.subTest(surface=surface):
                manager, original = self.make_manager(surface)
                preview = manager.apply_model_routing_preset("fixture", surface=surface, apply=False)
                with closing(sqlite3.connect(manager.paths.db)) as conn, conn:
                    self.assertEqual(json.loads(conn.execute("SELECT settings_config FROM providers").fetchone()[0]), original)
                self.assertEqual(preview["routes"], {"haiku": "gpt-5.6-luna", "sonnet": "gpt-5.6-terra", "opus": "gpt-6-astra", "fable": "gpt-6-astra"})
                applied = manager.apply_model_routing_preset("fixture", surface=surface, apply=True)
                self.assertEqual(len(applied["backups"]), 1)
                with closing(sqlite3.connect(manager.paths.db)) as conn, conn:
                    settings_json, meta_json = conn.execute("SELECT settings_config, meta FROM providers").fetchone()
                env = json.loads(settings_json)["env"]
                self.assertNotIn("ANTHROPIC_MODEL", env)
                self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "gpt-6-astra")
                self.assertEqual(env["X_USER_SETTING"], "keep")
                self.assertEqual(env[bridgedeck.MAX_CONTEXT_TOKENS_ENV], "272000")
                if surface == "claude-desktop":
                    routes = json.loads(meta_json)["claudeDesktopModelRoutes"]
                    self.assertEqual(routes["claude-opus-4-8"]["model"], "gpt-6-astra")
                    self.assertFalse(routes["claude-opus-4-8"]["supports1m"])
                again = manager.apply_model_routing_preset("fixture", surface=surface, apply=True)
                self.assertFalse(again["changed"])
                self.assertEqual(again["backups"], [])
                self.root.joinpath("providers.db").unlink()

    def test_unknown_model_is_preserved_without_claiming_context(self):
        self.assertEqual(bridgedeck.normalize_bridge_model_config(None)["model"], "gpt-6-astra")
        unknown = bridgedeck.normalize_bridge_model_config({"model": "gpt-9.9-custom"})
        self.assertEqual(unknown, {"model": "gpt-9.9-custom", "context_tokens": "", "max_output_tokens": ""})

    def start_ui(self, manager):
        handler = bridgedeck.build_handler(manager, "test-token", "test-nonce", allow_sensitive=True, allow_remote_access=False)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def test_ui_serves_new_default_and_escapes_catalog_markup(self):
        self.write_cache([{"slug": "gpt-9.1", "display_name": "</script><div>catalog data</div>"}])
        server = self.start_ui(fixtures.FakeManager())
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/")
        response = conn.getresponse()
        html = response.read().decode()
        self.assertEqual(response.status, 200)
        self.assertIn('const DEFAULT_BRIDGE_MODEL = "gpt-6-astra";', html)
        self.assertIn('data-action="apply-gpt6-routing-selected"', html)
        self.assertNotIn("</script><div>catalog data</div>", html)
        self.assertIn(r"\u003c/script>", html)

    def test_routing_http_endpoint_supports_preview_then_apply(self):
        manager, original = self.make_manager("claude")
        server = self.start_ui(manager)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(conn.close)
        for apply in (False, True):
            conn.request("POST", "/api/provider-routing", body=json.dumps({"provider_id": "fixture", "mode": "gpt6_auto", "surface": "claude_code", "apply": apply}), headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}", "X-CCSBT-Token": "test-token"})
            response = conn.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200, payload)
            self.assertEqual(payload["mode"], "gpt6_auto")
            self.assertEqual(payload["routes"]["opus"], "gpt-6-astra")
            with closing(sqlite3.connect(manager.paths.db)) as db, db:
                settings = json.loads(db.execute("SELECT settings_config FROM providers").fetchone()[0])
            if not apply:
                self.assertEqual(settings, original)
            else:
                self.assertNotIn("ANTHROPIC_MODEL", settings["env"])

    @unittest.skipUnless(shutil.which("node"), "Node is required for UI behavior checks")
    def test_model_picker_keeps_custom_models_and_export_uses_selection(self):
        script = re.search(r'<script nonce="__CSP_NONCE__">(.*?)</script>', bridgedeck.INDEX_HTML, re.S).group(1)
        functions = []
        for name in ("bridgeModelOption", "bridgeModelContext", "bridgeModelMaxOutput", "setBridgeModel", "apiOpenAiEnv", "renderReasoningEfforts"):
            functions.append(re.search(r"    function " + name + r"\([^\n]*\n.*?\n    }", script, re.S).group(0))
        prelude = "const BRIDGE_MODELS = " + json.dumps(list(model_catalog.model_options())) + ";\n"
        prelude += "const DEFAULT_BRIDGE_MODEL = 'gpt-6-astra'; const LOCAL_API_KEY_PLACEHOLDER = 'fake';\n"
        prelude += "const sel = {value: '', options: [], appendChild(n) {this.options.push(n);}, set innerHTML(v) {this.options = [];}}; const document = {getElementById() {return sel;}, createElement() {return {};}}; function updateBridgeModelMeta() {} function selectedBridgeModel() {return sel.value;} function apiAccessBaseUrl() {return 'http://127.0.0.1/v1';}\n"
        assertions = """
const assert = require('node:assert/strict');
assert.equal(bridgeModelOption('gpt-9.9-custom'), null);
assert.equal(bridgeModelOption('gpt-5.6').id, 'gpt-5.6-sol');
setBridgeModel('gpt-9.9-custom');
assert.equal(sel.value, 'gpt-9.9-custom');
assert.equal(bridgeModelContext(sel.value), '');
assert.match(apiOpenAiEnv({}), /MODEL=gpt-9.9-custom/);
setBridgeModel('gpt-6-astra');
assert.equal(bridgeModelContext(sel.value), '272000');
BRIDGE_MODELS.find(x => x.id === sel.value).default_reasoning_level = 'low';
renderReasoningEfforts();
assert.match(sel.options[0].textContent, /low/);
"""
        result = subprocess.run([shutil.which("node"), "-e", prelude + "\n".join(functions) + assertions], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
