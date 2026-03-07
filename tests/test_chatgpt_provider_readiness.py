from __future__ import annotations

import pytest

from clausy.providers.chatgpt import ChatGPTWebProvider


class DummyKeyboard:
    def __init__(self):
        self.presses: list[str] = []
        self.typed: list[str] = []

    def press(self, key: str):
        self.presses.append(key)

    def type(self, text: str, delay: int = 0):
        _ = delay
        self.typed.append(text)


class DummyPage:
    def __init__(self, url: str = "https://chatgpt.com"):
        self.url = url
        self.keyboard = DummyKeyboard()
        self.reload_calls = 0
        self.goto_calls: list[tuple[str, str | None]] = []
        self.wait_for_timeout_calls: list[int] = []

    def goto(self, url: str, wait_until: str | None = None):
        self.goto_calls.append((url, wait_until))
        self.url = url

    def reload(self, wait_until: str | None = None):
        _ = wait_until
        self.reload_calls += 1

    def wait_for_timeout(self, ms: int):
        self.wait_for_timeout_calls.append(ms)

    def locator(self, _selector: str):
        raise RuntimeError("not needed in this test")


class DummyComposer:
    def __init__(self):
        self.clicked = 0

    def click(self):
        self.clicked += 1


def test_ensure_ready_allows_composer_only_when_enter_send_is_valid(monkeypatch):
    provider = ChatGPTWebProvider(url="https://chatgpt.com", allow_anonymous_browser=True)
    page = DummyPage()

    monkeypatch.setattr(provider, "_is_login_screen", lambda _p: False)
    monkeypatch.setattr(provider, "_find_composer", lambda _p: object())
    monkeypatch.setattr(provider, "_find_send_button", lambda _p: None)
    monkeypatch.setattr(provider, "_can_submit_with_enter", lambda _p, _c: True)

    provider.ensure_ready(page)

    assert page.reload_calls == 0


def test_ensure_ready_retries_and_recovers_after_reload(monkeypatch):
    provider = ChatGPTWebProvider(url="https://chatgpt.com", allow_anonymous_browser=True)
    page = DummyPage()

    monkeypatch.setattr(provider, "_is_login_screen", lambda _p: False)

    state = {"calls": 0}

    def composer_after_retry(_p):
        state["calls"] += 1
        return None if state["calls"] == 1 else object()

    monkeypatch.setattr(provider, "_find_composer", composer_after_retry)
    monkeypatch.setattr(provider, "_find_send_button", lambda _p: None)
    monkeypatch.setattr(provider, "_can_submit_with_enter", lambda _p, c: c is not None)

    provider.ensure_ready(page)

    assert page.reload_calls == 1


def test_ensure_ready_still_fails_without_send_or_enter_submit(monkeypatch):
    provider = ChatGPTWebProvider(url="https://chatgpt.com", allow_anonymous_browser=True)
    page = DummyPage()

    monkeypatch.setattr(provider, "_is_login_screen", lambda _p: False)
    monkeypatch.setattr(provider, "_find_composer", lambda _p: object())
    monkeypatch.setattr(provider, "_find_send_button", lambda _p: None)
    monkeypatch.setattr(provider, "_can_submit_with_enter", lambda _p, _c: False)

    with pytest.raises(RuntimeError, match="UI_NOT_READY"):
        provider.ensure_ready(page)


def test_send_prompt_falls_back_to_enter_when_send_button_missing(monkeypatch):
    provider = ChatGPTWebProvider(url="https://chatgpt.com", allow_anonymous_browser=True)
    page = DummyPage()
    composer = DummyComposer()

    monkeypatch.setattr(provider, "_find_composer", lambda _p: composer)
    monkeypatch.setattr(provider, "_find_send_button", lambda _p: None)
    monkeypatch.setattr(provider, "_can_submit_with_enter", lambda _p, _c: True)

    provider.send_prompt(page, "hello")

    assert composer.clicked == 1
    assert page.keyboard.typed == ["hello"]
    assert "Enter" in page.keyboard.presses
