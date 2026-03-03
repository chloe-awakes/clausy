from __future__ import annotations

import json

from clausy import json_mode, output_mode


def _tool_call(arguments: str) -> list[dict]:
    return [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "exec", "arguments": arguments},
        }
    ]


def test_output_mode_rejects_non_object_arguments_json_string():
    payload = {"tool_calls": _tool_call('"rm -rf /"')}
    text = "```json\n" + json.dumps(payload) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert parsed is None
    assert reason == "tool_calls[].function.arguments must encode a JSON object"


def test_json_mode_schema_rejects_non_object_arguments_json_string():
    obj = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "clausy",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": _tool_call('42'),
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    ok, reason = json_mode.validate_chat_completion_schema(obj)

    assert ok is False
    assert reason == "tool_calls[].function.arguments must encode a JSON object"


def test_output_mode_accepts_object_arguments_json_string():
    payload = {"tool_calls": _tool_call('{"command": "ls -la"}')}
    text = "```json\n" + json.dumps(payload) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert reason == "ok"
    assert parsed is not None
