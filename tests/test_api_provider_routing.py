from __future__ import annotations

import json

import pytest

import clausy.server as server
from clausy.api_providers import APIProviderError


def _post_chat(client, payload, headers=None):
    merged_headers = {"X-Clausy-Session": "test-session"}
    if headers:
        merged_headers.update(headers)
    return client.post("/v1/chat/completions", json=payload, headers=merged_headers)


class _FakeAPIProvider:
    def __init__(self):
        self.calls = []

    def chat_completion(self, payload: dict, *, stream: bool):
        self.calls.append((payload, stream))
        return {
            "id": "chatcmpl-api",
            "object": "chat.completion",
            "created": 1,
            "model": payload.get("model") or "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "from api"},
                    "finish_reason": "stop",
                }
            ],
        }


@pytest.mark.routing
def test_openai_provider_routes_to_api_layer(monkeypatch, configure_server):
    api = _FakeAPIProvider()
    client = configure_server(provider_name="openai", providers={"openai": object()})

    monkeypatch.setattr(server, "api_router", type("R", (), {"get": lambda self, _n: api})())

    resp = _post_chat(
        client,
        {
            "model": "gpt-4o-mini",
            "stream": False,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["choices"][0]["message"]["content"] == "from api"
    assert len(api.calls) == 1
    assert api.calls[0][1] is False


@pytest.mark.contract
def test_openai_api_response_is_normalized(configure_server):
    raw = {
        "choices": [{"message": {"content": "hello"}}],
    }

    normalized = server._normalize_openai_response(raw, model="gpt-4o-mini")

    assert normalized["object"] == "chat.completion"
    assert normalized["model"] == "gpt-4o-mini"
    assert normalized["choices"][0]["message"]["role"] == "assistant"
    assert normalized["choices"][0]["finish_reason"] == "stop"


@pytest.mark.contract
def test_api_provider_error_maps_to_controlled_error(monkeypatch, configure_server):
    client = configure_server(provider_name="openai", providers={"openai": object()})

    class _BadProvider:
        def chat_completion(self, payload: dict, *, stream: bool):
            raise APIProviderError("upstream boom", status_code=503)

    monkeypatch.setattr(server, "api_router", type("R", (), {"get": lambda self, _n: _BadProvider()})())

    resp = _post_chat(
        client,
        {
            "model": "gpt-4o-mini",
            "stream": False,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    body = resp.get_json()
    assert resp.status_code == 502
    assert body["error"]["type"] == "provider_unavailable_error"
    assert "upstream boom" in body["error"]["message"]


@pytest.mark.routing
def test_anthropic_provider_routes_non_stream_to_api_layer(monkeypatch, configure_server):
    api = _FakeAPIProvider()
    client = configure_server(provider_name="anthropic", providers={"anthropic": object()})

    monkeypatch.setattr(server, "api_router", type("R", (), {"get": lambda self, _n: api})())

    resp = _post_chat(
        client,
        {
            "model": "claude-3-5-sonnet-latest",
            "stream": False,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["choices"][0]["message"]["content"] == "from api"
    assert len(api.calls) == 1
    assert api.calls[0][1] is False


@pytest.mark.routing
def test_anthropic_provider_routes_stream_to_api_layer(monkeypatch, configure_server):
    class _StreamProvider:
        def chat_completion(self, payload: dict, *, stream: bool):
            assert stream is True
            return iter([
                "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"\"},\"finish_reason\":null}]}",
                "data: {\"choices\":[{\"index\":0,\"delta\":{\"content\":\"hi\"},\"finish_reason\":null}]}",
                "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}",
                "data: [DONE]",
            ])

    client = configure_server(provider_name="anthropic", providers={"anthropic": object()})
    monkeypatch.setattr(server, "api_router", type("R", (), {"get": lambda self, _n: _StreamProvider()})())

    resp = _post_chat(
        client,
        {
            "model": "claude-3-5-sonnet-latest",
            "stream": True,
            "messages": [{"role": "user", "content": "stream"}],
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    data = b"".join(resp.response).decode("utf-8")
    assert "data: [DONE]" in data
    assert "\"content\":\"hi\"" in data


@pytest.mark.routing
def test_ollama_provider_routes_non_stream_to_api_layer(monkeypatch, configure_server):
    api = _FakeAPIProvider()
    client = configure_server(provider_name="ollama", providers={"ollama": object()})

    monkeypatch.setattr(server, "api_router", type("R", (), {"get": lambda self, _n: api})())

    resp = _post_chat(
        client,
        {
            "model": "llama3.2",
            "stream": False,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["choices"][0]["message"]["content"] == "from api"
    assert len(api.calls) == 1
    assert api.calls[0][1] is False


@pytest.mark.routing
def test_ollama_provider_routes_stream_to_api_layer(monkeypatch, configure_server):
    class _StreamProvider:
        def chat_completion(self, payload: dict, *, stream: bool):
            assert stream is True
            return iter([
                "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"\"},\"finish_reason\":null}]}",
                "data: {\"choices\":[{\"index\":0,\"delta\":{\"content\":\"hello\"},\"finish_reason\":null}]}",
                "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}",
                "data: [DONE]",
            ])

    client = configure_server(provider_name="ollama", providers={"ollama": object()})
    monkeypatch.setattr(server, "api_router", type("R", (), {"get": lambda self, _n: _StreamProvider()})())

    resp = _post_chat(
        client,
        {
            "model": "llama3.2",
            "stream": True,
            "messages": [{"role": "user", "content": "stream"}],
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    data = b"".join(resp.response).decode("utf-8")
    assert "data: [DONE]" in data
    assert "\"content\":\"hello\"" in data
