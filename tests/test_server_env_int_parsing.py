from __future__ import annotations

import logging

import clausy.server as server


def test_env_int_bounded_invalid_value_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        got = server._env_int_bounded(
            "oops",
            var_name="CLAUSY_MAX_REPAIRS",
            default=2,
            min_value=0,
            max_value=10,
        )

    assert got == 2
    assert "CLAUSY_MAX_REPAIRS='oops' is invalid" in caplog.text
    assert "using 2" in caplog.text


def test_env_int_bounded_out_of_range_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        got = server._env_int_bounded(
            "999",
            var_name="CLAUSY_BROWSER_RESTART_EVERY_RESETS",
            default=0,
            min_value=0,
            max_value=100,
        )

    assert got == 0
    assert "CLAUSY_BROWSER_RESTART_EVERY_RESETS=999 is out of range" in caplog.text
    assert "valid range is 0-100" in caplog.text
    assert "using 0" in caplog.text


def test_env_int_bounded_valid_value_is_used_without_warning(caplog):
    with caplog.at_level(logging.WARNING):
        got = server._env_int_bounded(
            "20",
            var_name="CLAUSY_RESET_TURNS",
            default=10,
            min_value=1,
            max_value=1000,
        )

    assert got == 20
    assert caplog.text == ""
