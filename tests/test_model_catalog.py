import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import local_codex_bridge
import model_catalog


class ModelCatalogCase(unittest.TestCase):
    def test_missing_and_corrupt_cache_keep_gpt56_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            corrupt = Path(tmp) / "corrupt.json"
            corrupt.write_text("{broken", encoding="utf-8")
            for path in (missing, corrupt):
                by_id = {item["id"]: item for item in model_catalog.model_options(path)}
                self.assertEqual(by_id["gpt-5.6-sol"]["context_tokens"], 372000)
                self.assertEqual(by_id["gpt-5.6-terra"]["context_tokens"], 372000)
                self.assertEqual(by_id["gpt-5.6-luna"]["context_tokens"], 372000)

    def test_stale_cache_is_reported_but_still_merged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(json.dumps({"models": [{"slug": "gpt-9.1", "context_window": 444000}]}), encoding="utf-8")
            stale = time.time() - model_catalog.CATALOG_STALE_SECS - 60
            os.utime(path, (stale, stale))
            result = model_catalog.load_model_catalog(path)
            self.assertTrue(result["stale"])
            self.assertIn("gpt-9.1", {item["id"] for item in result["models"]})

    def test_gpt56_reasoning_matrix_and_alias(self) -> None:
        self.assertEqual(model_catalog.normalize_model_id("gpt-5.6"), "gpt-5.6-sol")
        self.assertEqual(model_catalog.normalize_reasoning_effort("gpt-5.6-luna", "ultra")["effective"], "max")
        self.assertEqual(model_catalog.normalize_reasoning_effort("gpt-5.6-terra", "ultra")["effective"], "ultra")
        self.assertEqual(model_catalog.normalize_reasoning_effort("gpt-5.6-sol", "max")["effective"], "max")
        self.assertEqual(model_catalog.normalize_reasoning_effort("gpt-5.5", "ultra")["effective"], "xhigh")
        self.assertEqual(model_catalog.normalize_reasoning_effort("gpt-5.6-luna", "minimal")["effective"], "low")

    def test_unknown_gpt_model_preserves_known_effort(self) -> None:
        decision = model_catalog.normalize_reasoning_effort("gpt-9.9", "ultra")
        self.assertEqual(decision["effective"], "ultra")
        self.assertFalse(decision["model_known"])
        with self.assertRaises(ValueError):
            model_catalog.normalize_reasoning_effort("gpt-9.9", "pro")

    def test_local_bridge_ignores_generic_anthropic_route_pollution(self) -> None:
        polluted = {
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-8",
        }
        with mock.patch.dict(os.environ, polluted, clear=False):
            routes = local_codex_bridge.claude_desktop_model_route_map()
        self.assertEqual(routes["haiku"], "gpt-5.3-codex-spark")
        self.assertEqual(routes["sonnet"], "gpt-5.3-codex")
        self.assertEqual(routes["opus"], "gpt-5.5")

    def test_local_bridge_clamps_reasoning_without_mutating_input(self) -> None:
        original = {"model": "gpt-5.6-luna", "reasoning": {"effort": "ultra"}}
        normalized = local_codex_bridge.normalize_request_body(original)
        self.assertEqual(normalized["reasoning"]["effort"], "max")
        self.assertEqual(original["reasoning"]["effort"], "ultra")


if __name__ == "__main__":
    unittest.main()
