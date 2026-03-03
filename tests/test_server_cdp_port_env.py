from __future__ import annotations

import logging

import clausy.server as server


def test_parse_cdp_port_invalid_value_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        got = server._env_port("not-a-number", var_name="CLAUSY_CDP_PORT", default=9200)

    assert got == 9200
    assert "CLAUSY_CDP_PORT='not-a-number' is invalid" in caplog.text
    assert "using 9200" in caplog.text


def test_parse_cdp_port_out_of_range_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        got = server._env_port("70000", var_name="CLAUSY_CDP_PORT", default=9200)

    assert got == 9200
    assert "CLAUSY_CDP_PORT=70000 is out of range" in caplog.text
    assert "valid range is 1-65535" in caplog.text
    assert "using 9200" in caplog.text


def test_parse_cdp_port_valid_value_is_used_without_warning(caplog):
    with caplog.at_level(logging.WARNING):
        got = server._env_port("65535", var_name="CLAUSY_CDP_PORT", default=9200)

    assert got == 65535
    assert caplog.text == ""
