from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import test_security as _test_security


local_codex_bridge = _test_security.local_codex_bridge


def _event(name: str, payload: dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


def _chat_payloads(chunks: list[bytes]) -> list[dict[str, Any]]:
    body = _chat_body(chunks)
    return [
        payload
        for _event_name, payload in local_codex_bridge.parse_sse_blocks(body)
        if isinstance(payload, dict) and payload.get("object") == "chat.completion.chunk"
    ]


def _chat_body(chunks: list[bytes]) -> bytes:
    return b"".join(
        local_codex_bridge.iter_chat_completions_sse(
            iter(chunks), completion_id="chatcmpl_test", model="gpt-6-astra"
        )
    )


class ChatStreamingToolCallCase(unittest.TestCase):
    def test_streams_tool_call_deltas_without_repeating_arguments(self) -> None:
        payloads = _chat_payloads(
            [
                _event("response.output_text.delta", {"delta": "Checking."}),
                _event(
                    "response.output_item.added",
                    {
                        "item": {
                            "id": "fc_1",
                            "call_id": "call_1",
                            "type": "function_call",
                            "name": "read_file",
                        },
                        "output_index": 0,
                    },
                ),
                _event(
                    "response.function_call_arguments.delta",
                    {"item_id": "fc_1", "output_index": 0, "delta": "{\"path\":"},
                ),
                _event(
                    "response.function_call_arguments.delta",
                    {"item_id": "fc_1", "output_index": 0, "delta": "\"/tmp/a\"}"},
                ),
                _event(
                    "response.function_call_arguments.done",
                    {
                        "item_id": "fc_1",
                        "output_index": 0,
                        "arguments": "{\"path\":\"/tmp/a\"}",
                    },
                ),
                _event("response.completed", {"response": {"status": "completed"}}),
            ]
        )

        deltas = [payload["choices"][0]["delta"] for payload in payloads]
        tool_deltas = [delta["tool_calls"][0] for delta in deltas if "tool_calls" in delta]
        self.assertEqual(deltas[0], {"content": "Checking."})
        self.assertEqual(tool_deltas[0]["index"], 0)
        self.assertEqual(tool_deltas[0]["id"], "call_1")
        self.assertEqual(tool_deltas[0]["function"]["name"], "read_file")
        self.assertEqual(
            "".join(item.get("function", {}).get("arguments", "") for item in tool_deltas),
            "{\"path\":\"/tmp/a\"}",
        )
        self.assertEqual(payloads[-1]["choices"][0]["finish_reason"], "tool_calls")

    def test_buffers_real_done_until_output_item_done_supplies_call_id(self) -> None:
        payloads = _chat_payloads(
            [
                _event(
                    "response.function_call_arguments.done",
                    {
                        "item_id": "fc_2",
                        "output_index": 3,
                        "name": "get_weather",
                        "arguments": "{\"city\":\"Shanghai\"}",
                    },
                ),
                _event(
                    "response.output_item.done",
                    {
                        "item": {
                            "id": "fc_2",
                            "call_id": "call_2",
                            "type": "function_call",
                            "name": "get_weather",
                            "arguments": "{\"city\":\"Shanghai\"}",
                        },
                        "output_index": 3,
                    },
                ),
                _event("response.completed", {"response": {"status": "completed"}}),
            ]
        )

        tool_deltas = [
            payload["choices"][0]["delta"]["tool_calls"][0]
            for payload in payloads
            if "tool_calls" in payload["choices"][0]["delta"]
        ]
        self.assertEqual(tool_deltas[0]["index"], 0)
        self.assertEqual(tool_deltas[0]["id"], "call_2")
        self.assertEqual(tool_deltas[0]["function"]["name"], "get_weather")
        self.assertEqual(
            "".join(item.get("function", {}).get("arguments", "") for item in tool_deltas),
            "{\"city\":\"Shanghai\"}",
        )
        self.assertEqual(payloads[-1]["choices"][0]["finish_reason"], "tool_calls")

    def test_streams_interleaved_tools_with_stable_indices(self) -> None:
        payloads = _chat_payloads(
            [
                _event(
                    "response.output_item.added",
                    {"item": {"id": "fc_a", "call_id": "call_a", "type": "function_call", "name": "first"}, "output_index": 0},
                ),
                _event(
                    "response.output_item.added",
                    {"item": {"id": "fc_b", "call_id": "call_b", "type": "function_call", "name": "second"}, "output_index": 1},
                ),
                _event("response.function_call_arguments.delta", {"item_id": "fc_a", "output_index": 0, "delta": "{\"a\":"}),
                _event("response.function_call_arguments.delta", {"item_id": "fc_b", "output_index": 1, "delta": "{\"b\":"}),
                _event("response.function_call_arguments.delta", {"item_id": "fc_a", "output_index": 0, "delta": "1}"}),
                _event("response.function_call_arguments.delta", {"item_id": "fc_b", "output_index": 1, "delta": "2}"}),
                _event("response.completed", {"response": {"status": "completed"}}),
            ]
        )
        calls: dict[int, dict[str, Any]] = {}
        for payload in payloads:
            for call in payload["choices"][0]["delta"].get("tool_calls", []):
                current = calls.setdefault(call["index"], {"id": call.get("id"), "name": call.get("function", {}).get("name"), "arguments": ""})
                current["arguments"] += call.get("function", {}).get("arguments", "")

        self.assertEqual(calls, {0: {"id": "call_a", "name": "first", "arguments": "{\"a\":1}"}, 1: {"id": "call_b", "name": "second", "arguments": "{\"b\":2}"}})
        self.assertEqual(payloads[-1]["choices"][0]["finish_reason"], "tool_calls")

    def test_conflicting_complete_arguments_emits_error_without_corrupting_json(self) -> None:
        body = _chat_body(
            [
                _event("response.output_item.added", {"item": {"id": "fc_4", "call_id": "call_4", "type": "function_call", "name": "run"}}),
                _event("response.function_call_arguments.delta", {"item_id": "fc_4", "delta": "{\"left\":1}"}),
                _event("response.function_call_arguments.done", {"item_id": "fc_4", "arguments": "{\"right\":2}"}),
            ]
        )
        self.assertIn(b"event: error", body)
        self.assertIn(b"conflicting function call arguments", body)
        self.assertNotIn(b"{\\\"left\\\":1}{\\\"right\\\":2}", body)

    def test_terminal_events_finish_the_stream_once(self) -> None:
        for terminal in ("response.completed", "response.failed"):
            for combined in (False, True):
                with self.subTest(terminal=terminal, combined=combined):
                    first = _event(terminal, {"response": {"status": "completed" if terminal == "response.completed" else "failed", "error": {"message": "busy"}}})
                    chunks = [
                        first,
                        _event("response.completed", {"response": {"status": "completed"}}),
                        _event("response.output_text.delta", {"delta": "late output"}),
                        _event("error", {"error": {"message": "late error"}}),
                    ]
                    body = _chat_body([b"".join(chunks)] if combined else chunks)
                    completed = terminal == "response.completed"
                    self.assertEqual(body.count(b"data: [DONE]"), 1 if completed else 0)
                    self.assertEqual(body.count(b'"finish_reason":"stop"'), 1 if completed else 0)
                    self.assertEqual(body.count(b"event: error"), 0 if completed else 1)
                    self.assertNotIn(b"late output", body)
                    self.assertNotIn(b"late error", body)

    def test_text_completion_and_error_events_keep_existing_shapes(self) -> None:
        completed = _chat_body(
            [
                _event("response.output_text.delta", {"delta": "done"}),
                _event("response.completed", {"response": {"status": "completed"}}),
            ]
        )
        failed = _chat_body(
            [_event("response.failed", {"response": {"error": {"type": "server_error", "message": "busy"}}})]
        )
        self.assertIn(b'"content":"done"', completed)
        self.assertIn(b'"finish_reason":"stop"', completed)
        self.assertIn(b"data: [DONE]", completed)
        self.assertIn(b"event: error", failed)
        self.assertIn(b'"message":"busy"', failed)

    def test_emits_tool_call_when_only_completed_response_contains_it(self) -> None:
        payloads = _chat_payloads(
            [
                _event(
                    "response.completed",
                    {
                        "response": {
                            "status": "completed",
                            "output": [
                                {
                                    "id": "fc_3",
                                    "call_id": "call_3",
                                    "type": "function_call",
                                    "name": "list_files",
                                    "arguments": "{\"path\":\"/tmp\"}",
                                }
                            ],
                        }
                    },
                )
            ]
        )

        tool_deltas = [
            payload["choices"][0]["delta"]["tool_calls"][0]
            for payload in payloads
            if "tool_calls" in payload["choices"][0]["delta"]
        ]
        self.assertEqual(tool_deltas[0]["id"], "call_3")
        self.assertEqual(tool_deltas[0]["function"]["name"], "list_files")
        self.assertEqual(
            "".join(item.get("function", {}).get("arguments", "") for item in tool_deltas),
            "{\"path\":\"/tmp\"}",
        )
        self.assertEqual(payloads[-1]["choices"][0]["finish_reason"], "tool_calls")
