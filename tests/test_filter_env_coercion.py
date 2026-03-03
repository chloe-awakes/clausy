from __future__ import annotations

import logging
from unittest.mock import patch

from clausy.filter import load_filter_config_from_env, load_profanity_filter_config_from_env


def test_filter_scan_openclaw_accepts_off_token_case_insensitive():
    with patch.dict("os.environ", {"CLAUSY_FILTER_SCAN_OPENCLAW": " OFF "}, clear=False):
        cfg = load_filter_config_from_env()

    assert cfg.scan_openclaw is False


def test_filter_prefix_patterns_accepts_on_token_case_insensitive():
    with patch.dict("os.environ", {"CLAUSY_FILTER_PREFIX_PATTERNS": " ON "}, clear=False):
        cfg = load_filter_config_from_env()

    assert cfg.enable_prefix_patterns is True


def test_filter_bool_invalid_value_falls_back_to_default_with_warning(caplog):
    with patch.dict("os.environ", {"CLAUSY_FILTER_PREFIX_PATTERNS": "maybe"}, clear=False):
        with caplog.at_level(logging.WARNING):
            cfg = load_filter_config_from_env()

    assert cfg.enable_prefix_patterns is False
    assert "CLAUSY_FILTER_PREFIX_PATTERNS='maybe' is invalid" in caplog.text


def test_profanity_words_parses_csv_semicolon_and_newline_tokens():
    with patch.dict("os.environ", {"CLAUSY_BADWORD_WORDS": "foo;bar\n baz,QUX"}, clear=False):
        cfg = load_profanity_filter_config_from_env()

    assert cfg.words == ("foo", "bar", "baz", "qux")
