import json
import re
import time
import uuid
from typing import Callable, Optional, Dict, Any, Tuple

from .tool_call_validator import validate_tool_calls

MARK_CONTENT = "<<<CONTENT>>>"
MARK_TOOLS = "<<<TOOLS>>>"

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_TOOL_CALL_BLOCK_RE = re.compile(r"^```\s*tool(?:[ _-]?call)?\s*\n([\s\S]*?)\n```\s*$", re.IGNORECASE)
_EMPTY_PROVIDER_SENTINELS = {
    "[no response found]",
}


def output_mode_header() -> str:
    # Internal protocol between Clausy and the web backend (NOT the external OpenAI API).
    return (
        "<<<OUTPUT_RULES>>>\n"
        "You are an assistant connected to tools.\n\n"
        "Output format rules:\n"
        "- If the answer is user-facing text, output ONLY plain text. No JSON. No wrapper markers.\n"
        "- If you want to call a tool, output ONLY ONE fenced code block marked exactly as tool call.\n"
        "- Inside that code block, write the tool name followed by a JSON object of arguments.\n"
        "- Example:\n"
        "```tool call\n"
        "exec {\"command\": \"ls -la\"}\n"
        "```\n"
        "- Do not mix normal text with a tool-call block.\n"
        "- tool arguments must be a JSON object, not an array/string/number.\n"
        "- Legacy <<<CONTENT>>> / <<<TOOLS>>> output is still accepted, but do not use it.\n\n"
        "<<<INPUT>>>\n"
    )


def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    return m.group(1).strip()


def _normalize_text(text: str) -> str:
    return (text or "").lstrip()


def is_empty_provider_response(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    return stripped.lower() in _EMPTY_PROVIDER_SENTINELS


def _strip_legacy_marker(text: str) -> str:
    t = _normalize_text(text)
    if t.startswith(MARK_CONTENT):
        return t[len(MARK_CONTENT):].lstrip("\r\n").lstrip()
    if t.startswith(MARK_TOOLS):
        return t[len(MARK_TOOLS):].lstrip("\r\n").lstrip()
    return t


def detect_mode(text: str) -> Optional[str]:
    t = _normalize_text(text)
    if not t:
        return None
    if t.startswith(MARK_CONTENT):
        return "content"
    if t.startswith(MARK_TOOLS):
        return "tools"
    if t.startswith("```"):
        if _TOOL_CALL_BLOCK_RE.match(t):
            return "tools"
        header_line = t.splitlines()[0].strip().lower()
        if header_line.startswith("```tool"):
            return "tools"
        return None
    return "content"


def strip_marker(text: str) -> str:
    t = _normalize_text(text)
    if t.startswith(MARK_CONTENT) or t.startswith(MARK_TOOLS):
        return _strip_legacy_marker(t)
    return t


def _parse_tool_call_block(text: str) -> Tuple[Optional[list], str]:
    stripped = (text or "").strip()
    m = _TOOL_CALL_BLOCK_RE.match(stripped)
    if not m:
        return None, "no_tool_call_codeblock"

    body = m.group(1).strip()
    if not body:
        return None, "empty_tool_call_block"

    parts = body.split(None, 1)
    if not parts:
        return None, "empty_tool_call_block"

    tool_name = parts[0].strip()
    if not tool_name:
        return None, "tool_call_name_missing"

    if len(parts) < 2:
        return None, "tool_call_arguments_missing"

    arguments_text = parts[1].strip()
    try:
        arguments_obj = json.loads(arguments_text)
    except Exception as e:
        return None, f"tool_call_arguments_json_parse_error: {e}"

    if not isinstance(arguments_obj, dict):
        return None, "tool_calls[].function.arguments must encode a JSON object"

    tool_calls = [{
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments_obj, ensure_ascii=False),
        },
    }]

    ok, reason = validate_tool_calls(tool_calls)
    if not ok:
        return None, reason
    return tool_calls, "ok"


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

    ok, reason = validate_tool_calls(tool_calls)
    if not ok:
        return None, reason
    return tool_calls, "ok"


def parse_tool_calls(text: str) -> Tuple[Optional[list], str]:
    stripped = _normalize_text(text)
    if stripped.startswith(MARK_TOOLS):
        return parse_tools_json(_strip_legacy_marker(stripped))
    return _parse_tool_call_block(stripped)


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
            "- Return ONLY plain user-facing text. No markers, no JSON, no code blocks.\n"
        )
    elif expected_mode == "tools":
        mode_rule = (
            "- Return ONLY one ```tool call``` fenced block.\n"
            "- Inside it, write the tool name followed by a JSON object of arguments.\n"
            "- The arguments must be a JSON object.\n"
            "- No other text.\n"
        )
    else:
        mode_rule = (
            "- Return either plain text OR exactly one ```tool call``` fenced block.\n"
        )

    return (
        "You returned INVALID output. Fix it.\n"
        "Return output that follows the OUTPUT_RULES.\n"
        f"{mode_rule}"
        "Do NOT change the meaning—only repair formatting / missing fences / schema.\n"
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
    if is_empty_provider_response(raw_text):
        return build_chat_completion_content("", model_name_for_fallback)

    def try_parse(text: str) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
        normalized = _normalize_text(text)
        legacy_mode = detect_mode(normalized)

        if legacy_mode == "tools":
            tool_calls, reason = parse_tool_calls(normalized)
            if tool_calls is None:
                return None, reason, "tools"
            return build_chat_completion_tool_calls(tool_calls, model_name_for_fallback), "ok", "tools"

        if normalized.startswith("```"):
            return None, "unexpected_fenced_block", None

        body = strip_marker(normalized)
        return build_chat_completion_content(body.strip(), model_name_for_fallback), "ok", "content"

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
