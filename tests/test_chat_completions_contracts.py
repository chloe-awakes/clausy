from __future__ import annotations

import json
from collections import deque

import pytest


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


def _post_chat(client, payload):
    return client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"X-Clausy-Session": "test-session"},
    )


@pytest.mark.contract
def test_non_stream_chat_completion_contract(configure_server):
    provider = FakeProvider(non_stream_reply="<<<CONTENT>>>\nhello from provider")
    client = configure_server(provider_name="chatgpt", providers={"chatgpt": provider})

    resp = _post_chat(
        client,
        {
            "model": "chatgpt-web",
            "stream": False,
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["object"] == "chat.completion"
    assert body["model"] == "chatgpt-web"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "hello from provider"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert provider.sent_prompts and "<<<OUTPUT_RULES>>>" in provider.sent_prompts[0]


@pytest.mark.contract
def test_stream_sse_contract_includes_done(configure_server):
    provider = FakeProvider(stream_steps=["<<<CONTENT>>>\nstreamed", "<<<CONTENT>>>\nstreamed hello"])
    client = configure_server(provider_name="chatgpt", providers={"chatgpt": provider})

    resp = _post_chat(
        client,
        {
            "model": "chatgpt-web",
            "stream": True,
            "messages": [{"role": "user", "content": "stream pls"}],
        },
    )

    payload = resp.data.decode("utf-8")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    assert "\"chat.completion.chunk\"" in payload
    assert "\"finish_reason\": \"stop\"" in payload
    assert "data: [DONE]" in payload


@pytest.mark.contract
def test_tool_call_passthrough_shape_preserved_non_stream(configure_server, tools_reply_json):
    provider = FakeProvider(non_stream_reply=tools_reply_json)
    client = configure_server(provider_name="chatgpt", providers={"chatgpt": provider})

    resp = _post_chat(
        client,
        {
            "model": "chatgpt-web",
            "stream": False,
            "messages": [{"role": "user", "content": "run tool"}],
        },
    )

    body = resp.get_json()
    tc = body["choices"][0]["message"]["tool_calls"][0]
    args_obj = json.loads(tc["function"]["arguments"])

    assert resp.status_code == 200
    assert body["choices"][0]["finish_reason"] == "tool_calls"
    assert tc["id"] == "call_1"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "exec"
    assert args_obj == {"command": "ls -la", "meta": {"cwd": "/tmp"}}


@pytest.mark.filtering
def test_filtering_non_stream_content_and_tools(configure_server):
    secret = "sk-abcdef1234567890"
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "exec",
                "arguments": json.dumps({"command": f"echo toxic and {secret}"}),
            },
        }
    ]
    provider = FakeProvider(
        non_stream_reply="<<<TOOLS>>>\n```json\n"
        + json.dumps({"tool_calls": tool_calls}, ensure_ascii=False)
        + "\n```"
    )
    client = configure_server(
        provider_name="chatgpt",
        providers={"chatgpt": provider},
        known_secrets={secret},
        bad_words=("toxic",),
    )

    resp = _post_chat(
        client,
        {
            "model": "chatgpt-web",
            "stream": False,
            "messages": [{"role": "user", "content": "go"}],
        },
    )

    body = resp.get_json()
    tool_args = body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    assert secret not in tool_args
    assert "toxic" not in tool_args.lower()
    assert "[CENSORED]" in tool_args


@pytest.mark.filtering
def test_filtering_stream_content(configure_server):
    secret = "sk-abcdef1234567890"
    provider = FakeProvider(
        stream_steps=[
            "<<<CONTENT>>>\nthis is toxic and ",
            f"<<<CONTENT>>>\nthis is toxic and {secret}",
        ]
    )
    client = configure_server(
        provider_name="chatgpt",
        providers={"chatgpt": provider},
        known_secrets={secret},
        bad_words=("toxic",),
    )

    resp = _post_chat(
        client,
        {
            "model": "chatgpt-web",
            "stream": True,
            "messages": [{"role": "user", "content": "go"}],
        },
    )

    payload = resp.data.decode("utf-8")
    assert secret not in payload
    assert "toxic" not in payload.lower()
    assert "[CENSORED]" in payload
    assert "data: [DONE]" in payload


@pytest.mark.routing
def test_provider_routing_uses_selected_provider(configure_server):
    chatgpt = FakeProvider(non_stream_reply="<<<CONTENT>>>\nchatgpt")
    claude = FakeProvider(non_stream_reply="<<<CONTENT>>>\nclaude")
    client = configure_server(
        provider_name="claude",
        providers={"chatgpt": chatgpt, "claude": claude},
    )

    resp = _post_chat(
        client,
        {
            "model": "chatgpt-web",
            "stream": False,
            "messages": [{"role": "user", "content": "route"}],
        },
    )

    assert resp.status_code == 200
    assert claude.ensure_ready_calls == 1
    assert chatgpt.ensure_ready_calls == 0
