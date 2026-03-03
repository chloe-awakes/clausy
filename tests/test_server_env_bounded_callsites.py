from __future__ import annotations

import importlib
import logging

import clausy.server as server


def _reload_server() -> None:
    importlib.reload(server)


def test_profile_rotation_count_invalid_env_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setenv("CLAUSY_PROFILE_ROTATION_COUNT", "oops")

    with caplog.at_level(logging.WARNING):
        _reload_server()

    assert server.PROFILE_ROTATION_COUNT == 0
    assert "CLAUSY_PROFILE_ROTATION_COUNT='oops' is invalid" in caplog.text


def test_event_log_max_items_out_of_range_env_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setenv("CLAUSY_EVENT_LOG_MAX_ITEMS", "10001")

    with caplog.at_level(logging.WARNING):
        _reload_server()

    assert server.EVENT_LOG_MAX_ITEMS == 500
    assert "CLAUSY_EVENT_LOG_MAX_ITEMS=10001 is out of range" in caplog.text


def test_event_log_max_items_accepts_upper_boundary(monkeypatch, caplog):
    monkeypatch.setenv("CLAUSY_EVENT_LOG_MAX_ITEMS", "10000")

    with caplog.at_level(logging.WARNING):
        _reload_server()

    assert server.EVENT_LOG_MAX_ITEMS == 10000
    assert caplog.text == ""
