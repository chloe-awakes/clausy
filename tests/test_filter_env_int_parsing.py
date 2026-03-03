from __future__ import annotations

import logging
from unittest.mock import patch

from clausy.filter import load_filter_config_from_env


def test_filter_max_bytes_invalid_value_falls_back_with_warning(caplog):
    with patch.dict("os.environ", {"CLAUSY_FILTER_MAX_BYTES": "oops"}, clear=False):
        with caplog.at_level(logging.WARNING):
            cfg = load_filter_config_from_env()

    assert cfg.max_bytes == 2_000_000
    assert "CLAUSY_FILTER_MAX_BYTES='oops' is invalid" in caplog.text
    assert "using 2000000" in caplog.text


def test_filter_max_tail_out_of_range_falls_back_with_warning(caplog):
    with patch.dict("os.environ", {"CLAUSY_FILTER_MAX_TAIL": "0"}, clear=False):
        with caplog.at_level(logging.WARNING):
            cfg = load_filter_config_from_env()

    assert cfg.max_tail == 32_768
    assert "CLAUSY_FILTER_MAX_TAIL=0 is out of range" in caplog.text
    assert "valid range is 1-2000000" in caplog.text
    assert "using 32768" in caplog.text


def test_filter_env_int_values_valid_without_warning(caplog):
    with patch.dict(
        "os.environ",
        {
            "CLAUSY_FILTER_MAX_BYTES": "1500000",
            "CLAUSY_FILTER_MAX_TAIL": "4096",
        },
        clear=False,
    ):
        with caplog.at_level(logging.WARNING):
            cfg = load_filter_config_from_env()

    assert cfg.max_bytes == 1_500_000
    assert cfg.max_tail == 4096
    assert caplog.text == ""
