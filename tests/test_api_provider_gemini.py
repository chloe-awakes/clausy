from __future__ import annotations

import json

from clausy.api_providers.gemini import GeminiAPIProvider


class _Resp:
    def __init__(self, *, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


def test_gemini_non_stream_maps_to_openai_shape(monkeypatch):
    calls = []

    def _post(url, params=None, headers=None, json=None, timeout=None):
        calls.append((url, params, headers, json, timeout))
        return _Resp(
            json_data={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "hello from gemini"}],
                            "role": "model",
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 6,
                    "candidatesTokenCount": 4,
                },
            }
        )

    monkeypatch.setattr("clausy.api_providers.gemini.requests.post", _post)

    p = GeminiAPIProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="key",
        timeout_seconds=13,
    )
    out = p.chat_completion(
        {
            "model": "gemini-1.5-flash",
            "messages": [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "hi"},
            ],
            "stream": False,
            "temperature": 0,
        },
        stream=False,
    )

    assert out["object"] == "chat.completion"
    assert out["model"] == "gemini-1.5-flash"
    assert out["choices"][0]["message"]["role"] == "assistant"
    assert out["choices"][0]["message"]["content"] == "hello from gemini"
    assert out["usage"] == {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10}

    url, params, headers, body, timeout = calls[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    assert params == {"key": "key"}
    assert headers["Content-Type"] == "application/json"
    assert timeout == 13
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert body["systemInstruction"] == {"parts": [{"text": "be brief"}]}


def test_gemini_stream_maps_to_openai_sse(monkeypatch):
    def _post(url, params=None, headers=None, json=None, timeout=None):
        return _Resp(
            json_data={
                "candidates": [{"content": {"parts": [{"text": "hello stream"}]}}],
            }
        )

    monkeypatch.setattr("clausy.api_providers.gemini.requests.post", _post)

    p = GeminiAPIProvider(base_url="https://generativelanguage.googleapis.com/v1beta", api_key="key")
    out = list(
        p.chat_completion(
            {"model": "gemini-1.5-flash", "messages": [{"role": "user", "content": "hi"}]},
            stream=True,
        )
    )

    first = json.loads(out[0][len("data: ") :])
    second = json.loads(out[1][len("data: ") :])
    finish = json.loads(out[2][len("data: ") :])

    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"
    assert second["choices"][0]["delta"]["content"] == "hello stream"
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert out[-1] == "data: [DONE]"
