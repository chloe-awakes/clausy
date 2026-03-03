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


def test_shared_validator_rejects_whitespace_only_name_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"function.name": "   "}))

    assert ok is False
    assert reason == "tool_calls[].function.name missing/invalid"


def test_shared_validator_rejects_non_json_arguments_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"function.arguments": "not-json"}))

    assert ok is False
    assert reason == "tool_calls[].function.arguments must encode a JSON object"


def test_shared_validator_rejects_control_character_in_function_name_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"function.name": "ex\nec"}))

    assert ok is False
    assert reason == "tool_calls[].function.name must not contain control characters"


def test_shared_validator_rejects_function_name_longer_than_128_chars_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"function.name": "x" * 129}))

    assert ok is False
    assert reason == "tool_calls[].function.name must be <= 128 chars"


def test_shared_validator_rejects_control_character_in_id_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"id": "call_\n1"}))

    assert ok is False
    assert reason == "tool_calls[].id must not contain control characters"


def test_shared_validator_rejects_id_longer_than_128_chars_with_expected_reason():
    ok, reason = validate_tool_calls(_payload_with_tool_call({"id": "c" * 129}))

    assert ok is False
    assert reason == "tool_calls[].id must be <= 128 chars"


def test_output_and_json_mode_use_same_reason_for_type_name_arguments_constraints():
    cases = [
        ({"type": "tool"}, "tool_calls[].type must be 'function'"),
        ({"function.name": ""}, "tool_calls[].function.name missing/invalid"),
        ({"function.name": "   "}, "tool_calls[].function.name missing/invalid"),
        ({"function.arguments": "not-json"}, "tool_calls[].function.arguments must encode a JSON object"),
        ({"function.name": "ex\nec"}, "tool_calls[].function.name must not contain control characters"),
        ({"function.name": "x" * 129}, "tool_calls[].function.name must be <= 128 chars"),
        ({"id": "call_\n1"}, "tool_calls[].id must not contain control characters"),
        ({"id": "c" * 129}, "tool_calls[].id must be <= 128 chars"),
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


def test_output_and_json_mode_accept_128_char_and_non_ascii_tool_call_ids():
    cases = [
        "c" * 128,
        "call_ß工具_🚀",
    ]

    for tool_call_id in cases:
        tool_calls = _payload_with_tool_call({"id": tool_call_id})

        # output_mode path
        output_text = "```json\n" + json.dumps({"tool_calls": tool_calls}) + "\n```"
        parsed_tool_calls, output_reason = output_mode.parse_tools_json(output_text)

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

        assert parsed_tool_calls == tool_calls
        assert output_reason == "ok"
        assert ok is True
        assert json_reason == "ok"


def test_output_and_json_mode_accept_128_char_and_non_ascii_function_names():
    cases = [
        "x" * 128,
        "exec_ß工具_🚀",
    ]

    for function_name in cases:
        tool_calls = _payload_with_tool_call({"function.name": function_name})

        # output_mode path
        output_text = "```json\n" + json.dumps({"tool_calls": tool_calls}) + "\n```"
        parsed_tool_calls, output_reason = output_mode.parse_tools_json(output_text)

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

        assert parsed_tool_calls == tool_calls
        assert output_reason == "ok"
        assert ok is True
        assert json_reason == "ok"
