from __future__ import annotations

import json

from clausy.api_providers.ollama import OllamaAPIProvider


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


def test_ollama_non_stream_maps_to_openai_shape(monkeypatch):
    calls = []

    def _post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json, timeout))
        return _Resp(
            json_data={
                "model": "llama3.2",
                "message": {"role": "assistant", "content": "hello from ollama"},
                "done_reason": "stop",
                "prompt_eval_count": 5,
                "eval_count": 3,
            }
        )

    monkeypatch.setattr("clausy.api_providers.ollama.requests.post", _post)

    p = OllamaAPIProvider(base_url="http://127.0.0.1:11434", api_key="", timeout_seconds=9)
    out = p.chat_completion(
        {
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
        stream=False,
    )

    assert out["object"] == "chat.completion"
    assert out["model"] == "llama3.2"
    assert out["choices"][0]["message"]["role"] == "assistant"
    assert out["choices"][0]["message"]["content"] == "hello from ollama"
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["usage"] == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    url, headers, body, timeout = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert headers["Content-Type"] == "application/json"
    assert timeout == 9
    assert body["model"] == "llama3.2"
    assert body["stream"] is False


def test_ollama_stream_maps_to_openai_sse(monkeypatch):
    lines = [
        '{"model":"llama3.2","message":{"role":"assistant","content":"hello"},"done":false}',
        '{"model":"llama3.2","message":{"role":"assistant","content":" world"},"done":false}',
        '{"model":"llama3.2","done":true,"done_reason":"stop"}',
    ]

    def _post(url, headers=None, json=None, timeout=None):
        return _Resp(lines=lines)

    monkeypatch.setattr("clausy.api_providers.ollama.requests.post", _post)

    p = OllamaAPIProvider(base_url="http://127.0.0.1:11434", api_key="")
    out = list(
        p.chat_completion(
            {"model": "llama3.2", "messages": [{"role": "user", "content": "hi"}]},
            stream=True,
        )
    )

    first = json.loads(out[0][len("data: ") :])
    second = json.loads(out[1][len("data: ") :])
    third = json.loads(out[2][len("data: ") :])

    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"
    assert second["choices"][0]["delta"]["content"] == "hello"
    assert third["choices"][0]["delta"]["content"] == "hello world"

    finish = json.loads(out[-2][len("data: ") :])
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert out[-1] == "data: [DONE]"
