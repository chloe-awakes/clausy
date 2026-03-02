from __future__ import annotations

from clausy.api_providers.openrouter import OpenRouterAPIProvider


class _Resp:
    def __init__(self, *, status_code=200, text="", json_data=None, lines=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data
        self._lines = lines or []

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)


def test_openrouter_non_stream_uses_openai_compatible_endpoint(monkeypatch):
    calls = []

    def _post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json, timeout))
        return _Resp(json_data={"choices": [{"message": {"role": "assistant", "content": "hello from openrouter"}}]})

    monkeypatch.setattr("clausy.api_providers.openrouter.requests.post", _post)

    p = OpenRouterAPIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key="key",
        site_url="https://example.org",
        app_name="Clausy",
        timeout_seconds=9,
    )

    out = p.chat_completion(
        {
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
        stream=False,
    )

    assert out["choices"][0]["message"]["content"] == "hello from openrouter"

    url, headers, body, timeout = calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer key"
    assert headers["HTTP-Referer"] == "https://example.org"
    assert headers["X-Title"] == "Clausy"
    assert timeout == 9
    assert body["model"] == "openai/gpt-4o-mini"


def test_openrouter_stream_returns_iter_lines(monkeypatch):
    lines = [
        'data: {"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{"content":"hello"},"finish_reason":null}]}',
        "data: [DONE]",
    ]

    def _post(url, headers=None, json=None, timeout=None):
        return _Resp(lines=lines)

    monkeypatch.setattr("clausy.api_providers.openrouter.requests.post", _post)

    p = OpenRouterAPIProvider(base_url="https://openrouter.ai/api/v1", api_key="key")
    out = list(
        p.chat_completion(
            {"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            stream=True,
        )
    )

    assert out == lines
