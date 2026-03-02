from __future__ import annotations

import pytest

import clausy.server as server
from clausy.providers import ProviderRegistry
from clausy.providers.chatgpt import ChatGPTWebProvider
from clausy.providers.claude import ClaudeWebProvider
from clausy.providers.grok import GrokWebProvider


class DummyPage:
    def __init__(self, url: str = "https://example.com"):
        self.url = url

    def goto(self, url: str, wait_until: str | None = None):
        self.url = url

    def reload(self, wait_until: str | None = None):
        return None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", False),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_env_flag_parsing(raw, expected):
    assert server._env_flag(raw, default=False) is expected


def test_provider_registry_default_wires_allow_anonymous_flag():
    registry = ProviderRegistry.default(chatgpt_url="https://chatgpt.com", allow_anonymous_browser=True)

    assert isinstance(registry.get("chatgpt"), ChatGPTWebProvider)
    assert registry.get("chatgpt").allow_anonymous_browser is True
    assert isinstance(registry.get("claude"), ClaudeWebProvider)
    assert registry.get("claude").allow_anonymous_browser is True
    assert isinstance(registry.get("grok"), GrokWebProvider)
    assert registry.get("grok").allow_anonymous_browser is True


@pytest.mark.parametrize(
    "provider_cls,input_method,send_method,home_url",
    [
        (ChatGPTWebProvider, "_find_composer", "_find_send_button", "https://chatgpt.com"),
        (ClaudeWebProvider, "_find_input", "_find_send_button", "https://claude.ai"),
        (GrokWebProvider, "_find_composer", "_find_send_button", "https://grok.com"),
    ],
)
def test_provider_remains_strict_when_anonymous_disabled(monkeypatch, provider_cls, input_method, send_method, home_url):
    monkeypatch.setattr("clausy.providers.chatgpt.time.sleep", lambda _x: None)
    monkeypatch.setattr("clausy.providers.claude.time.sleep", lambda _x: None)
    monkeypatch.setattr("clausy.providers.grok.time.sleep", lambda _x: None)

    provider = provider_cls(url=home_url, allow_anonymous_browser=False)
    page = DummyPage(url=home_url)

    monkeypatch.setattr(provider, "_is_login_screen", lambda _p: True)
    monkeypatch.setattr(provider, input_method, lambda _p: object())
    monkeypatch.setattr(provider, send_method, lambda _p: object())

    with pytest.raises(RuntimeError, match="NEEDS_LOGIN"):
        provider.ensure_ready(page)


@pytest.mark.parametrize(
    "provider_cls,input_method,send_method,home_url",
    [
        (ChatGPTWebProvider, "_find_composer", "_find_send_button", "https://chatgpt.com"),
        (ClaudeWebProvider, "_find_input", "_find_send_button", "https://claude.ai"),
        (GrokWebProvider, "_find_composer", "_find_send_button", "https://grok.com"),
    ],
)
def test_provider_allows_anon_when_enabled_if_ui_is_ready(monkeypatch, provider_cls, input_method, send_method, home_url):
    monkeypatch.setattr("clausy.providers.chatgpt.time.sleep", lambda _x: None)
    monkeypatch.setattr("clausy.providers.claude.time.sleep", lambda _x: None)
    monkeypatch.setattr("clausy.providers.grok.time.sleep", lambda _x: None)

    provider = provider_cls(url=home_url, allow_anonymous_browser=True)
    page = DummyPage(url=home_url)

    monkeypatch.setattr(provider, "_is_login_screen", lambda _p: True)
    monkeypatch.setattr(provider, input_method, lambda _p: object())
    monkeypatch.setattr(provider, send_method, lambda _p: object())

    provider.ensure_ready(page)


@pytest.mark.parametrize(
    "provider_cls,input_method,send_method,home_url",
    [
        (ChatGPTWebProvider, "_find_composer", "_find_send_button", "https://chatgpt.com"),
        (ClaudeWebProvider, "_find_input", "_find_send_button", "https://claude.ai"),
        (GrokWebProvider, "_find_composer", "_find_send_button", "https://grok.com"),
    ],
)
def test_provider_returns_auth_error_when_anon_enabled_but_page_hard_blocked(monkeypatch, provider_cls, input_method, send_method, home_url):
    monkeypatch.setattr("clausy.providers.chatgpt.time.sleep", lambda _x: None)
    monkeypatch.setattr("clausy.providers.claude.time.sleep", lambda _x: None)
    monkeypatch.setattr("clausy.providers.grok.time.sleep", lambda _x: None)

    provider = provider_cls(url=home_url, allow_anonymous_browser=True)
    page = DummyPage(url=home_url)

    monkeypatch.setattr(provider, "_is_login_screen", lambda _p: True)
    monkeypatch.setattr(provider, input_method, lambda _p: None)
    monkeypatch.setattr(provider, send_method, lambda _p: None)

    with pytest.raises(RuntimeError, match="NEEDS_LOGIN"):
        provider.ensure_ready(page)
