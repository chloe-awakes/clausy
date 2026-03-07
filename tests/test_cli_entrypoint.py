import importlib
import os
import runpy
import sys
from pathlib import Path

import pytest


def test_cli_main_default_invokes_server_without_forcing_chrome(monkeypatch):
    cli = importlib.import_module("clausy.cli")

    called = {"count": 0}

    def _fake_server_main():
        called["count"] += 1

    monkeypatch.setattr(cli, "server_main", _fake_server_main)
    monkeypatch.delenv("CLAUSY_BROWSER_BOOTSTRAP", raising=False)
    monkeypatch.delenv("CLAUSY_HEADLESS", raising=False)

    rc = cli.main([])

    assert rc == 0
    assert called["count"] == 1
    assert os.environ.get("CLAUSY_BROWSER_BOOTSTRAP") is None
    assert os.environ.get("CLAUSY_HEADLESS") is None


def test_cli_main_chrome_sets_visible_browser_defaults(monkeypatch):
    cli = importlib.import_module("clausy.cli")

    called = {"count": 0}

    def _fake_server_main():
        called["count"] += 1

    monkeypatch.setattr(cli, "server_main", _fake_server_main)
    monkeypatch.delenv("CLAUSY_BROWSER_BOOTSTRAP", raising=False)
    monkeypatch.delenv("CLAUSY_HEADLESS", raising=False)

    rc = cli.main(["chrome"])

    assert rc == 0
    assert called["count"] == 1
    assert os.environ["CLAUSY_BROWSER_BOOTSTRAP"] == "always"
    assert os.environ["CLAUSY_HEADLESS"] == "0"


def test_module_invocation_path_respects_chrome_subcommand(monkeypatch):
    cli = importlib.import_module("clausy.cli")

    called = {"count": 0}

    def _fake_server_main():
        called["count"] += 1

    monkeypatch.setattr(cli, "server_main", _fake_server_main)
    monkeypatch.setattr(sys, "argv", ["python", "chrome"])
    monkeypatch.delenv("CLAUSY_BROWSER_BOOTSTRAP", raising=False)
    monkeypatch.delenv("CLAUSY_HEADLESS", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("clausy", run_name="__main__")

    assert excinfo.value.code == 0
    assert called["count"] == 1
    assert os.environ["CLAUSY_BROWSER_BOOTSTRAP"] == "always"
    assert os.environ["CLAUSY_HEADLESS"] == "0"


def test_console_script_entrypoint_targets_cli_main():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")

    assert 'clausy = "clausy.cli:main"' in content
