from __future__ import annotations

from clausy.output_mode import parse_or_repair_output, is_empty_provider_response


def test_parse_or_repair_output_skips_repair_for_no_response_sentinel():
    calls: list[str] = []

    def _ask(prompt: str) -> str:
        calls.append(prompt)
        return "<<<CONTENT>>>\nshould not be used"

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
    assert not is_empty_provider_response("<<<CONTENT>>>\nHello")
