from __future__ import annotations

import json

from clausy.output_mode import (
    detect_mode,
    is_empty_provider_response,
    parse_or_repair_output,
    parse_tool_calls,
)


def test_parse_or_repair_output_skips_repair_for_no_response_sentinel():
    calls: list[str] = []

    def _ask(prompt: str) -> str:
        calls.append(prompt)
        return "should not be used"

    parsed = parse_or_repair_output(
        raw_text="[No response found]",
        ask_fn=_ask,
        model_name_for_fallback="chatgpt-web",
        max_repairs=2,
    )

    assert calls == []
    assert parsed["choices"][0]["message"]["content"] == ""


def test_is_empty_provider_response_covers_empty_whitespace_and_sentinel():
    assert is_empty_provider_response("")
    assert is_empty_provider_response("   \n\t")
    assert is_empty_provider_response("[No response found]")
    assert is_empty_provider_response("[no response found]")
    assert not is_empty_provider_response("Hello")


def test_parse_plain_text_output_as_content():
    parsed = parse_or_repair_output(
        raw_text="hello from provider",
        ask_fn=lambda _: "unused",
        model_name_for_fallback="chatgpt-web",
        max_repairs=0,
    )

    assert parsed["choices"][0]["message"]["content"] == "hello from provider"
    assert parsed["choices"][0]["finish_reason"] == "stop"


def test_parse_new_tool_call_block_into_openai_tool_calls():
    parsed = parse_or_repair_output(
        raw_text='```tool call\nexec {"command":"ls -la","meta":{"cwd":"/tmp"}}\n```',
        ask_fn=lambda _: "unused",
        model_name_for_fallback="chatgpt-web",
        max_repairs=0,
    )

    tc = parsed["choices"][0]["message"]["tool_calls"][0]
    assert parsed["choices"][0]["finish_reason"] == "tool_calls"
    assert tc["function"]["name"] == "exec"
    assert json.loads(tc["function"]["arguments"]) == {"command": "ls -la", "meta": {"cwd": "/tmp"}}


def test_parse_tool_call_block_supports_multiline_json_and_escaping():
    tool_calls, reason = parse_tool_calls(
        '```tool call\nwrite {\n  "path": "/tmp/demo.txt",\n  "content": "line1\\nline2 with ``` inside"\n}\n```'
    )

    assert reason == "ok"
    tc = tool_calls[0]
    assert tc["function"]["name"] == "write"
    assert json.loads(tc["function"]["arguments"]) == {
        "path": "/tmp/demo.txt",
        "content": "line1\nline2 with ``` inside",
    }


def test_malformed_tool_call_block_requires_repair_then_parses():
    calls: list[str] = []

    def _ask(prompt: str) -> str:
        calls.append(prompt)
        return '```tool call\nexec {"command":"pwd"}\n```'

    parsed = parse_or_repair_output(
        raw_text="```tool call\nexec not-json\n```",
        ask_fn=_ask,
        model_name_for_fallback="chatgpt-web",
        max_repairs=1,
    )

    assert len(calls) == 1
    tc = parsed["choices"][0]["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "exec"
    assert json.loads(tc["function"]["arguments"]) == {"command": "pwd"}


def test_mixed_content_with_tool_call_block_falls_back_to_text_when_unrepaired():
    parsed = parse_or_repair_output(
        raw_text='Before\n```tool call\nexec {"command":"ls"}\n```\nAfter',
        ask_fn=lambda _: "still invalid",
        model_name_for_fallback="chatgpt-web",
        max_repairs=0,
    )

    assert parsed["choices"][0]["message"]["content"].startswith("Before")
    assert parsed["choices"][0]["finish_reason"] == "stop"


def test_detect_mode_prefers_plain_text_and_identifies_tool_call_blocks():
    assert detect_mode("hello") == "content"
    assert detect_mode('```tool call\nexec {"command":"ls"}\n```') == "tools"
    assert detect_mode("```python\nprint(1)\n```") is None


def test_legacy_marker_tool_json_remains_accepted_for_compatibility():
    payload = {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "exec", "arguments": '{"command":"ls -la"}'},
            }
        ]
    }
    parsed = parse_or_repair_output(
        raw_text="<<<TOOLS>>>\n```json\n" + json.dumps(payload) + "\n```",
        ask_fn=lambda _: "unused",
        model_name_for_fallback="chatgpt-web",
        max_repairs=0,
    )

    assert parsed["choices"][0]["finish_reason"] == "tool_calls"
    assert parsed["choices"][0]["message"]["tool_calls"][0]["id"] == "call_1"
