from __future__ import annotations

import importlib

import clausy.server as server


def test_provider_home_url_uses_selected_provider_and_env_override(monkeypatch):
    monkeypatch.setenv("CLAUSY_PROVIDER", "claude")
    monkeypatch.setenv("CLAUSY_CLAUDE_URL", "https://claude.example.local")

    reloaded = importlib.reload(server)

    assert reloaded.browser.home_url == "https://claude.example.local"


def test_main_opens_provider_page_when_requested(monkeypatch):
    calls: list[str] = []

    class _FakePage:
        def goto(self, url: str, wait_until: str | None = None):
            calls.append(f"goto:{url}:{wait_until}")

    class _FakeBrowser:
        home_url = "https://claude.ai"

        def start(self):
            calls.append("start")

        def get_first_page(self):
            calls.append("get_first_page")
            return _FakePage()

    monkeypatch.setenv("CLAUSY_OPEN_PROVIDER_ON_START", "1")
    monkeypatch.setattr(server, "browser", _FakeBrowser())
    monkeypatch.setattr(server.app, "run", lambda **_kwargs: calls.append("run"))

    server.main()

    assert calls == [
        "start",
        "get_first_page",
        "goto:https://claude.ai:domcontentloaded",
        "run",
    ]
