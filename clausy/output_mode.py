import json
import re
import time
import uuid
from typing import Callable, Optional, Dict, Any, Tuple

MARK_CONTENT = "<<<CONTENT>>>"
MARK_TOOLS = "<<<TOOLS>>>"

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

def output_mode_header() -> str:
    # Internal protocol between Clausy and the web backend (NOT the external OpenAI API).
    return (
        "<<<OUTPUT_RULES>>>\n"
        "You are an assistant connected to tools.\n\n"
        "You MUST start your output with exactly ONE of these lines:\n"
        f"- {MARK_CONTENT}\n"
        f"- {MARK_TOOLS}\n\n"
        f"If you output {MARK_CONTENT}:\n"
        "- Output ONLY the user-facing answer as plain text after the marker.\n"
        "- Do NOT output JSON, code blocks, or any additional markers.\n\n"
        f"If you output {MARK_TOOLS}:\n"
        "- Output ONLY a single valid JSON object inside ONE ```json``` code block.\n"
        "- The JSON MUST contain tool_calls in OpenAI format.\n"
        "- tool_calls[].function.arguments MUST be a JSON-encoded OBJECT string.\n"
        "- Do NOT output any other text.\n\n"
        "<<<INPUT>>>\n"
    )

def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    return m.group(1).strip()

def _is_json_object_string(s: str) -> bool:
    try:
        return isinstance(json.loads(s), dict)
    except Exception:
        return False

def _validate_tool_calls(tool_calls: Any) -> Tuple[bool, str]:
    if not isinstance(tool_calls, list) or not tool_calls:
        return (False, "tool_calls must be a non-empty list")

    for tc in tool_calls:
        if not isinstance(tc, dict):
            return (False, "tool_calls entries must be objects")
        if tc.get("type") != "function":
            return (False, "tool_calls[].type must be 'function'")
        fn = tc.get("function")
        if not isinstance(fn, dict):
            return (False, "tool_calls[].function missing or not an object")
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            return (False, "tool_calls[].function.name missing/invalid")
        args = fn.get("arguments")
        if not isinstance(args, str):
            return (False, "tool_calls[].function.arguments must be a JSON-encoded string")
        if not _is_json_object_string(args):
            return (False, "tool_calls[].function.arguments must encode a JSON object")

    return (True, "ok")

def _normalize_text(text: str) -> str:
    return (text or "").lstrip()

def detect_mode(text: str) -> Optional[str]:
    t = _normalize_text(text)
    if t.startswith(MARK_CONTENT):
        return "content"
    if t.startswith(MARK_TOOLS):
        return "tools"
    return None

def strip_marker(text: str) -> str:
    t = _normalize_text(text)
    if t.startswith(MARK_CONTENT):
        return t[len(MARK_CONTENT):].lstrip("\r\n").lstrip()
    if t.startswith(MARK_TOOLS):
        return t[len(MARK_TOOLS):].lstrip("\r\n").lstrip()
    return t

def parse_tools_json(text_after_marker: str) -> Tuple[Optional[list], str]:
    candidate = _extract_json_candidate(text_after_marker)
    if candidate is None:
        return None, "no_json_codeblock"

    try:
        obj = json.loads(candidate)
    except Exception as e:
        return None, f"json_parse_error: {e}"

    tool_calls = None
    if isinstance(obj, dict) and "tool_calls" in obj:
        tool_calls = obj.get("tool_calls")
    elif isinstance(obj, dict) and obj.get("object") == "chat.completion":
        try:
            tool_calls = obj["choices"][0]["message"]["tool_calls"]
        except Exception:
            tool_calls = None

    ok, reason = _validate_tool_calls(tool_calls)
    if not ok:
        return None, reason
    return tool_calls, "ok"

def build_chat_completion_content(content: str, model: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

def build_chat_completion_tool_calls(tool_calls: list, model: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": None, "tool_calls": tool_calls},
            "finish_reason": "tool_calls"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

def build_repair_prompt(invalid_output: str, expected_mode: Optional[str]) -> str:
    mode_rule = ""
    if expected_mode == "content":
        mode_rule = (
            f"- Your output MUST start with {MARK_CONTENT}.\n"
            "- After the marker, output ONLY plain text (no JSON, no code blocks).\n"
        )
    elif expected_mode == "tools":
        mode_rule = (
            f"- Your output MUST start with {MARK_TOOLS}.\n"
            "- After the marker, output ONLY one ```json``` code block with a JSON object containing tool_calls.\n"
            "- Each tool_calls[].function.arguments must be a JSON-encoded OBJECT string.\n"
            "- No other text.\n"
        )
    else:
        mode_rule = (
            f"- Your output MUST start with {MARK_CONTENT} or {MARK_TOOLS}.\n"
        )

    return (
        "You returned INVALID output. Fix it.\n"
        "Return output that follows the OUTPUT_RULES.\n"
        f"{mode_rule}"
        "Do NOT change the meaning—only repair formatting / missing marker / schema.\n"
        "Here is the invalid output to fix:\n"
        "-----\n"
        f"{invalid_output}\n"
        "-----\n"
    )

def parse_or_repair_output(
    raw_text: str,
    ask_fn: Callable[[str], str],
    model_name_for_fallback: str,
    max_repairs: int = 2,
) -> Dict[str, Any]:
    def try_parse(text: str) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
        mode = detect_mode(text)
        if mode is None:
            return None, "missing_marker", None

        body = strip_marker(text)
        if mode == "content":
            return build_chat_completion_content(body.strip(), model_name_for_fallback), "ok", "content"

        tool_calls, reason = parse_tools_json(body)
        if tool_calls is None:
            return None, reason, "tools"
        return build_chat_completion_tool_calls(tool_calls, model_name_for_fallback), "ok", "tools"

    parsed, _, exp_mode = try_parse(raw_text)
    if parsed is not None:
        return parsed

    last = raw_text
    for _ in range(max_repairs):
        repair_prompt = build_repair_prompt(last, expected_mode=exp_mode)
        fixed = ask_fn(repair_prompt)
        parsed, _, exp_mode = try_parse(fixed)
        if parsed is not None:
            return parsed
        last = fixed

    return build_chat_completion_content((raw_text or "").strip(), model_name_for_fallback)
