from __future__ import annotations

import json
from collections import deque

import pytest

from clausy.filter import FilterConfig, PrefixMatcher, ProfanityFilter, ProfanityFilterConfig, SecretFilter
import clausy.server as server


class FakeLocatorFirst:
    def __init__(self, hidden: bool):
        self._hidden = hidden

    def is_hidden(self) -> bool:
        return self._hidden


class FakeLocator:
    def __init__(self, hidden: bool = True, count: int = 1):
        self._hidden = hidden
        self._count = count
        self.first = FakeLocatorFirst(hidden)

    def count(self) -> int:
        return self._count


class FakePage:
    def __init__(self, provider):
        self.provider = provider

    def locator(self, _selector: str):
        return FakeLocator(hidden=True, count=1)


class FakeProvider:
    def __init__(self, *, non_stream_reply: str | None = None, stream_steps: list[str] | None = None):
        self.non_stream_reply = non_stream_reply
        self.stream_steps = deque(stream_steps or [])
        self._last = ""
        self.sent_prompts: list[str] = []
        self.ensure_ready_calls = 0
        self.wait_done_calls = 0

    def ensure_ready(self, _page):
        self.ensure_ready_calls += 1

    def send_prompt(self, _page, prompt: str):
        self.sent_prompts.append(prompt)

    def wait_done(self, _page):
        self.wait_done_calls += 1

    def get_last_assistant_text(self, _page):
        if self.stream_steps:
            self._last = self.stream_steps.popleft()
            return self._last
        if self.non_stream_reply is not None:
            return self.non_stream_reply
        return self._last

    def _stop_selector(self):
        return "[data-testid='stop']"


class FakeBrowser:
    def __init__(self, providers_by_session):
        self.providers_by_session = providers_by_session
        self.pages = {}

    def get_page(self, session_id: str):
        if session_id not in self.pages:
            provider = self.providers_by_session[session_id]
            self.pages[session_id] = FakePage(provider)
        return self.pages[session_id]

    def reset_page(self, session_id: str):
        self.pages.pop(session_id, None)


@pytest.fixture
def make_secret_filter():
    def _make(known_values: set[str]):
        sf = SecretFilter(FilterConfig(mode="smart", scan_openclaw=False))
        sf.known = set(known_values)
        sf._compiled = sf._compile_known_regex()
        sf._matcher = PrefixMatcher(sf.known) if sf.known else None
        return sf

    return _make


@pytest.fixture
def make_profanity_filter():
    def _make(*words: str):
        return ProfanityFilter(
            ProfanityFilterConfig(mode="mask", words=tuple(words), replacement="[CENSORED]")
        )

    return _make


@pytest.fixture
def configure_server(monkeypatch, make_secret_filter, make_profanity_filter):
    def _configure(
        *,
        provider_name: str,
        providers: dict[str, FakeProvider],
        known_secrets: set[str] | None = None,
        bad_words: tuple[str, ...] = (),
        tool_password: str = "",
        tool_password_header: str = "X-Clausy-Tool-Password",
        auto_model_switch: bool = True,
    ):
        providers_by_session = {"test-session": providers[provider_name]}

        class _Registry:
            def __init__(self, p):
                self._p = p

            def get(self, name: str):
                return self._p[name]

        monkeypatch.setattr(server, "PROVIDER_NAME", provider_name)
        monkeypatch.setattr(server, "AUTO_MODEL_SWITCH", auto_model_switch)
        monkeypatch.setattr(server, "registry", _Registry(providers))
        monkeypatch.setattr(server, "browser", FakeBrowser(providers_by_session))
        monkeypatch.setattr(server, "secret_filter", make_secret_filter(known_secrets or set()))
        monkeypatch.setattr(server, "profanity_filter", make_profanity_filter(*bad_words) if bad_words else ProfanityFilter(ProfanityFilterConfig(mode="off")))
        monkeypatch.setattr(server, "TOOL_PASSWORD", tool_password)
        monkeypatch.setattr(server, "TOOL_PASSWORD_HEADER", tool_password_header)
        monkeypatch.setattr(
            server,
            "TOOL_PASSWORD_MESSAGE",
            "Tool execution is password-protected. Provide a valid tool password to continue.",
        )
        monkeypatch.setattr(server.time, "sleep", lambda _x: None)
        server._session_meta.clear()
        return server.app.test_client()

    return _configure


@pytest.fixture
def tools_reply_json():
    return (
        "```tool call\n"
        "exec {\"command\": \"ls -la\", \"meta\": {\"cwd\": \"/tmp\"}}\n"
        "```"
    )
