from __future__ import annotations

import json
from pathlib import Path

from clausy import cli


def test_direct_get_set_roundtrip(monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(cli, "_config_file_path", lambda: cfg)
    monkeypatch.delenv("CLAUSY_HEADLESS", raising=False)

    rc_get = cli.main(["headless"])
    out_get = capsys.readouterr().out

    assert rc_get == 0
    assert "headless=auto" in out_get

    rc_set = cli.main(["headless", "off"])
    out_set = capsys.readouterr().out

    assert rc_set == 0
    assert "Set headless=0" in out_set
    assert json.loads(cfg.read_text(encoding="utf-8"))["headless"] == "0"

    rc_get2 = cli.main(["headless"])
    out_get2 = capsys.readouterr().out
    assert rc_get2 == 0
    assert "headless=0" in out_get2


def test_direct_get_prefers_environment_over_persisted(monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"provider": "claude"}), encoding="utf-8")
    monkeypatch.setattr(cli, "_config_file_path", lambda: cfg)
    monkeypatch.setenv("CLAUSY_PROVIDER", "chatgpt")

    rc = cli.main(["provider"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "provider=chatgpt" in out
    assert "source=env" in out


def test_config_command_prints_all_settings(monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"bootstrap": "always", "port": "3131"}), encoding="utf-8")
    monkeypatch.setattr(cli, "_config_file_path", lambda: cfg)

    rc = cli.main(["config"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "bootstrap=always" in out
    assert "port=3131" in out


def test_start_creates_pid_and_stop_handles_not_running(monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "config.json"
    pid_file = tmp_path / "clausy.pid"
    monkeypatch.setattr(cli, "_config_file_path", lambda: cfg)
    monkeypatch.setattr(cli, "_pid_file_path", lambda: pid_file)

    popen_calls = []

    class _Proc:
        pid = 4242

    def _fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return _Proc()

    monkeypatch.setattr(cli.subprocess, "Popen", _fake_popen)

    rc_start = cli.main(["start"])
    out_start = capsys.readouterr().out

    assert rc_start == 0
    assert pid_file.read_text(encoding="utf-8").strip() == "4242"
    assert "Started Clausy" in out_start
    assert popen_calls

    # Simulate stale pid on stop
    monkeypatch.setattr(cli, "_try_stop_service_manager", lambda: False)
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    rc_stop = cli.main(["stop"])
    out_stop = capsys.readouterr().out

    assert rc_stop == 0
    assert "not running" in out_stop.lower()


def test_status_prints_health_snapshot(monkeypatch, tmp_path, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"port": "3108", "provider": "chatgpt"}), encoding="utf-8")
    monkeypatch.setattr(cli, "_config_file_path", lambda: cfg)

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "provider": "chatgpt"}

    monkeypatch.setattr(cli.requests, "get", lambda *args, **kwargs: _Resp())

    rc = cli.main(["status"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "health=ok" in out
    assert "provider=chatgpt" in out
