from __future__ import annotations

import json
from typing import Any, Tuple


def _is_json_object_string(s: str) -> bool:
    try:
        return isinstance(json.loads(s), dict)
    except Exception:
        return False


def _contains_control_characters(s: str) -> bool:
    return any((ord(ch) < 32) or (127 <= ord(ch) <= 159) for ch in s)


def validate_tool_calls(tool_calls: Any) -> Tuple[bool, str]:
    if not isinstance(tool_calls, list) or not tool_calls:
        return (False, "tool_calls must be a non-empty list")

    for tc in tool_calls:
        if not isinstance(tc, dict):
            return (False, "tool_calls entries must be objects")
        tool_call_id = tc.get("id")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            return (False, "tool_calls[].id must be a non-empty string")
        if _contains_control_characters(tool_call_id):
            return (False, "tool_calls[].id must not contain control characters")
        if len(tool_call_id) > 128:
            return (False, "tool_calls[].id must be <= 128 chars")
        if tc.get("type") != "function":
            return (False, "tool_calls[].type must be 'function'")
        fn = tc.get("function")
        if not isinstance(fn, dict):
            return (False, "tool_calls[].function missing or not an object")
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            return (False, "tool_calls[].function.name missing/invalid")
        if _contains_control_characters(name):
            return (False, "tool_calls[].function.name must not contain control characters")
        if len(name) > 128:
            return (False, "tool_calls[].function.name must be <= 128 chars")
        args = fn.get("arguments")
        if not isinstance(args, str):
            return (False, "tool_calls[].function.arguments must be a JSON-encoded string")
        if not _is_json_object_string(args):
            return (False, "tool_calls[].function.arguments must encode a JSON object")

    return (True, "ok")
