from __future__ import annotations

import json

from clausy import json_mode, output_mode
from clausy.tool_call_validator import validate_tool_calls


BASE_TOOL_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "exec", "arguments": '{"command": "ls -la"}'},
}


def _payload_with_tool_call(overrides: dict) -> list[dict]:
    tc = json.loads(json.dumps(BASE_TOOL_CALL))
    for key, value in overrides.items():
        if key.startswith("function."):
            tc["function"][key.split(".", 1)[1]] = value
        else:
            tc[key] = value
    return [tc]


def test_shared_validator_rejects_invalid_type_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"type": "tool"}))

    assert ok is False
    assert reason == "tool_calls[].type must be 'function'"


def test_shared_validator_rejects_invalid_name_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"function.name": ""}))

    assert ok is False
    assert reason == "tool_calls[].function.name missing/invalid"


def test_shared_validator_rejects_non_json_arguments_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"function.arguments": "not-json"}))

    assert ok is False
    assert reason == "tool_calls[].function.arguments must encode a JSON object"


def test_output_and_json_mode_use_same_reason_for_type_name_arguments_constraints():
    cases = [
        ({"type": "tool"}, "tool_calls[].type must be 'function'"),
        ({"function.name": ""}, "tool_calls[].function.name missing/invalid"),
        ({"function.arguments": "not-json"}, "tool_calls[].function.arguments must encode a JSON object"),
    ]

    for overrides, expected_reason in cases:
        tool_calls = _payload_with_tool_call(overrides)

        # output_mode path
        output_text = "```json\n" + json.dumps({"tool_calls": tool_calls}) + "\n```"
        _, output_reason = output_mode.parse_tools_json(output_text)

        # json_mode path
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
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
        ok, json_reason = json_mode.validate_chat_completion_schema(obj)

        assert ok is False
        assert output_reason == expected_reason
        assert json_reason == expected_reason
