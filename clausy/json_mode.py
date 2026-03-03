import json
import re
import time
import uuid
from typing import Callable, Tuple, Optional, Dict, Any

from .tool_call_validator import validate_tool_calls

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

KNOWN_TOOL_NAMES_DEFAULT = {"exec", "read", "write", "web_search"}

def json_mode_header() -> str:
    # Short, stable header. Keep it small to reduce drift.
    return (
        "<<<LLM_SERVER_MODE>>>\n\n"
        "You are an OpenAI-compatible LLM server.\n"
        "Output rules:\n"
        "- Return ONLY a valid JSON object inside a single ```json``` code block.\n"
        "- Do not output any text before or after the code block.\n"
        "- Follow the OpenAI chat.completion response schema (object=\"chat.completion\").\n\n"
        "Example output:\n\n"
        "```json\n"
        "{\"id\":\"chatcmpl-1\",\"object\":\"chat.completion\",\"created\":1234567890,"
        "\"model\":\"clausy\",\"choices\":[{\"index\":0,\"message\":{\"role\":\"assistant\",\"content\":\"hello\"},\"finish_reason\":\"stop\"}]}\n"
        "```\n\n"
        "<<<INPUT>>>\n"
    )

def extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    return m.group(1).strip()

def validate_chat_completion_schema(obj: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return (False, "Top-level is not an object")
    if obj.get("object") != "chat.completion":
        return (False, 'object must be "chat.completion"')

    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return (False, "choices must be a non-empty list")

    c0 = choices[0]
    if not isinstance(c0, dict):
        return (False, "choices[0] must be an object")

    msg = c0.get("message")
    if not isinstance(msg, dict):
        return (False, "choices[0].message missing or not an object")

    role = msg.get("role")
    if role not in ("assistant", "tool"):
        return (False, "choices[0].message.role must be assistant/tool")

    content = msg.get("content", None)
    tool_calls = msg.get("tool_calls", None)

    if tool_calls is None:
        if content is None:
            return (False, "message.content missing (expected string or null)")
        if not (isinstance(content, str) or content is None):
            return (False, "message.content must be string or null")
    else:
        ok, reason = validate_tool_calls(tool_calls)
        if not ok:
            return (False, reason)

    if "finish_reason" not in c0:
        return (False, "choices[0].finish_reason missing")

    return (True, "ok")

def build_repair_prompt(invalid_output: str, require_toolcalls: Optional[bool]) -> str:
    tool_rule = ""
    if require_toolcalls is True:
        tool_rule = (
            "- The corrected JSON MUST use tool_calls (choices[0].message.content must be null).\n"
            "- Do NOT remove tool_calls.\n"
        )
    elif require_toolcalls is False:
        tool_rule = (
            "- The corrected JSON MUST NOT include tool_calls.\n"
            "- Use choices[0].message.content as a normal assistant text response.\n"
        )

    return (
        "You returned INVALID output. Fix it.\n"
        "Return ONLY a valid JSON object inside ONE ```json``` code block. No other text.\n"
        "Requirements:\n"
        "- Top-level must be a chat.completion object.\n"
        "- object field must be exactly \"chat.completion\".\n"
        "- choices[0].message must include role and (content or tool_calls).\n"
        "- If tool_calls are present: each tool_calls[].function.arguments MUST be a JSON-encoded OBJECT string.\n"
        f"{tool_rule}"
        "Do NOT change the meaning—only repair formatting/schema.\n"
        "Here is the invalid output to fix:\n"
        "-----\n"
        f"{invalid_output}\n"
        "-----\n"
    )

def parse_or_repair_chat_completion(
    reply_text: str,
    ask_fn: Callable[[str], str],
    model_name_for_fallback: str,
    max_repairs: int = 2,
    known_tool_names = None,
) -> Dict[str, Any]:
    if known_tool_names is None:
        known_tool_names = KNOWN_TOOL_NAMES_DEFAULT

    def try_parse(text: str):
        candidate = extract_json_candidate(text)
        if candidate is None:
            return None, "no_json_codeblock"
        try:
            obj = json.loads(candidate)
        except Exception as e:
            return None, f"json_parse_error: {e}"
        ok, reason = validate_chat_completion_schema(obj)
        return (obj if ok else None), reason

    parsed, reason = try_parse(reply_text)
    if parsed is not None:
        return parsed

    # Conservative security: don't let "repair" invent tool_calls unless there's strong hint.
    text_l = (reply_text or "").lower()
    allow_toolcalls = ("tool_calls" in text_l) or any(name.lower() in text_l for name in known_tool_names)
    require_toolcalls = None if allow_toolcalls else False

    last_text = reply_text
    for _ in range(max_repairs):
        repair_prompt = build_repair_prompt(last_text, require_toolcalls=require_toolcalls)
        fixed = ask_fn(repair_prompt)
        parsed, reason = try_parse(fixed)
        if parsed is not None:
            return parsed
        last_text = fixed

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    safe_text = (reply_text or "").strip()
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model_name_for_fallback,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": safe_text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
