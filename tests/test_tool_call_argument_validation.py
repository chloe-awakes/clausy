from __future__ import annotations

import json

from clausy import json_mode, output_mode


def _tool_call(arguments: str, tool_call_id: object = "call_1") -> list[dict]:
    return [
        {
            "id": tool_call_id,
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


def test_output_mode_rejects_tool_call_id_when_not_non_empty_string():
    payload = {"tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id="")}
    text = "```json\n" + json.dumps(payload) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert parsed is None
    assert reason == "tool_calls[].id must be a non-empty string"


def test_json_mode_schema_rejects_tool_call_id_when_not_non_empty_string():
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
                    "tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id=123),
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    ok, reason = json_mode.validate_chat_completion_schema(obj)

    assert ok is False
    assert reason == "tool_calls[].id must be a non-empty string"


def test_output_mode_rejects_tool_call_id_with_control_character():
    payload = {"tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id="call_\n1")}
    text = "```json\n" + json.dumps(payload) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert parsed is None
    assert reason == "tool_calls[].id must not contain control characters"


def test_json_mode_schema_rejects_tool_call_id_with_control_character():
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
                    "tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id="call_\n1"),
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    ok, reason = json_mode.validate_chat_completion_schema(obj)

    assert ok is False
    assert reason == "tool_calls[].id must not contain control characters"


def test_output_mode_rejects_tool_call_id_longer_than_128_chars():
    payload = {"tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id=("c" * 129))}
    text = "```json\n" + json.dumps(payload) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert parsed is None
    assert reason == "tool_calls[].id must be <= 128 chars"


def test_json_mode_schema_rejects_tool_call_id_longer_than_128_chars():
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
                    "tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id=("c" * 129)),
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    ok, reason = json_mode.validate_chat_completion_schema(obj)

    assert ok is False
    assert reason == "tool_calls[].id must be <= 128 chars"


def test_output_mode_accepts_tool_call_id_exactly_128_chars():
    payload = {"tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id=("c" * 128))}
    text = "```json\n" + json.dumps(payload) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert reason == "ok"
    assert parsed is not None


def test_json_mode_schema_accepts_tool_call_id_exactly_128_chars():
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
                    "tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id=("c" * 128)),
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    ok, reason = json_mode.validate_chat_completion_schema(obj)

    assert ok is True
    assert reason == "ok"


def test_output_mode_accepts_non_ascii_printable_tool_call_id():
    payload = {"tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id="call_äöü_日本語_Δ")}
    text = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    parsed, reason = output_mode.parse_tools_json(text)

    assert reason == "ok"
    assert parsed is not None


def test_json_mode_schema_accepts_non_ascii_printable_tool_call_id():
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
                    "tool_calls": _tool_call('{"command": "ls -la"}', tool_call_id="call_äöü_日本語_Δ"),
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    ok, reason = json_mode.validate_chat_completion_schema(obj)

    assert ok is True
    assert reason == "ok"
