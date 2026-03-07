import importlib
import os
import runpy
import sys
from pathlib import Path

import pytest


def test_cli_main_no_args_shows_status_and_usage(monkeypatch, capsys):
    cli = importlib.import_module("clausy.cli")

    monkeypatch.setattr(cli, "_show_status", lambda: print("health=down provider=chatgpt port=3108 pid=-"))

    rc = cli.main([])
    out = capsys.readouterr().out

    assert rc == 0
    assert "health=down" in out
    assert "Usage: clausy" in out


def test_cli_main_chrome_starts_background_visible_mode(monkeypatch):
    cli = importlib.import_module("clausy.cli")

    called = {"extra_env": None}

    def _fake_launch(extra_env=None):
        called["extra_env"] = extra_env
        return 0

    monkeypatch.setattr(cli, "_launch_background", _fake_launch)

    rc = cli.main(["chrome"])

    assert rc == 0
    assert called["extra_env"] == {
        "CLAUSY_BROWSER_BOOTSTRAP": "always",
        "CLAUSY_HEADLESS": "0",
    }


def test_module_invocation_path_respects_chrome_subcommand(monkeypatch):
    cli = importlib.import_module("clausy.cli")

    called = {"extra_env": None}

    def _fake_launch(extra_env=None):
        called["extra_env"] = extra_env
        return 0

    monkeypatch.setattr(cli, "_launch_background", _fake_launch)
    monkeypatch.setattr(sys, "argv", ["python", "chrome"])
    monkeypatch.delenv("CLAUSY_BROWSER_BOOTSTRAP", raising=False)
    monkeypatch.delenv("CLAUSY_HEADLESS", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("clausy", run_name="__main__")

    assert excinfo.value.code == 0
    assert called["extra_env"] == {
        "CLAUSY_BROWSER_BOOTSTRAP": "always",
        "CLAUSY_HEADLESS": "0",
    }


def test_console_script_entrypoint_targets_cli_main():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")

    assert 'clausy = "clausy.cli:main"' in content
