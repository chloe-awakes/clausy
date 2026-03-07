from __future__ import annotations

import importlib

import clausy.server as server


def test_provider_home_url_uses_selected_provider_and_env_override(monkeypatch):
    monkeypatch.setenv("CLAUSY_PROVIDER", "claude")
    monkeypatch.setenv("CLAUSY_CLAUDE_URL", "https://claude.example.local")

    reloaded = importlib.reload(server)

    assert reloaded.browser.home_url == "https://claude.example.local"


def test_main_starts_server_without_explicit_open_provider_flag(monkeypatch):
    calls: list[str] = []

    class _FakeBrowser:
        home_url = "https://claude.ai"

        def start(self):
            calls.append("start")

    monkeypatch.delenv("CLAUSY_OPEN_PROVIDER_ON_START", raising=False)
    monkeypatch.setattr(server, "browser", _FakeBrowser())
    monkeypatch.setattr(server.app, "run", lambda **_kwargs: calls.append("run"))

    server.main()

    assert calls == [
        "start",
        "run",
    ]
