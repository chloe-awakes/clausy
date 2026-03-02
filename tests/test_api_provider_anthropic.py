from __future__ import annotations

import json

from clausy.api_providers.anthropic import AnthropicAPIProvider


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


def test_anthropic_non_stream_maps_to_openai_shape(monkeypatch):
    calls = []

    def _post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json, timeout))
        return _Resp(
            json_data={
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-5-sonnet-latest",
                "content": [{"type": "text", "text": "hello from anthropic"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 7, "output_tokens": 3},
            }
        )

    monkeypatch.setattr("clausy.api_providers.anthropic.requests.post", _post)

    p = AnthropicAPIProvider(base_url="https://api.anthropic.com/v1", api_key="key", timeout_seconds=11)
    out = p.chat_completion(
        {
            "model": "claude-3-5-sonnet-latest",
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
    assert out["choices"][0]["message"]["role"] == "assistant"
    assert out["choices"][0]["message"]["content"] == "hello from anthropic"
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["usage"] == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}

    url, headers, body, timeout = calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert timeout == 11
    assert body["model"] == "claude-3-5-sonnet-latest"
    assert body["stream"] is False
    assert body["system"] == "be brief"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_anthropic_stream_maps_to_openai_sse(monkeypatch):
    lines = [
        'data: {"type":"message_start"}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
        'data: {"type":"message_stop"}',
    ]

    def _post(url, headers=None, json=None, timeout=None):
        return _Resp(lines=lines)

    monkeypatch.setattr("clausy.api_providers.anthropic.requests.post", _post)

    p = AnthropicAPIProvider(base_url="https://api.anthropic.com/v1", api_key="key")
    out = list(
        p.chat_completion(
            {"model": "claude-3-5-sonnet-latest", "messages": [{"role": "user", "content": "hi"}]},
            stream=True,
        )
    )

    first = json.loads(out[0][len("data: ") :])
    second = json.loads(out[1][len("data: ") :])
    third = json.loads(out[2][len("data: ") :])
    finish = json.loads(out[3][len("data: ") :])

    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"
    assert second["choices"][0]["delta"]["content"] == "hello"
    assert third["choices"][0]["delta"]["content"] == "hello world"
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert out[-1] == "data: [DONE]"
