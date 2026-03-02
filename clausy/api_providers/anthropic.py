from __future__ import annotations

import json
import time
import uuid

import requests

from .base import APIProvider, APIProviderError


class AnthropicAPIProvider(APIProvider):
    name = "anthropic"

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _map_messages(self, payload: dict) -> tuple[str | None, list[dict]]:
        system_parts: list[str] = []
        messages: list[dict] = []

        for msg in payload.get("messages", []) or []:
            if not isinstance(msg, dict):
                continue
            role = (msg.get("role") or "").strip().lower()
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                content = "\n".join(text_parts)
            if not isinstance(content, str):
                content = str(content)

            if role == "system":
                if content.strip():
                    system_parts.append(content)
                continue

            if role not in {"user", "assistant"}:
                continue

            messages.append({"role": role, "content": content})

        system = "\n\n".join(p for p in system_parts if p.strip()) if system_parts else None
        return system, messages

    @staticmethod
    def _map_finish_reason(stop_reason: str | None) -> str:
        if stop_reason == "end_turn":
            return "stop"
        if stop_reason == "max_tokens":
            return "length"
        if stop_reason == "tool_use":
            return "tool_calls"
        return "stop"

    def _build_anthropic_body(self, payload: dict, *, stream: bool) -> dict:
        system, messages = self._map_messages(payload)
        body: dict = {
            "model": payload.get("model") or "claude-3-5-sonnet-latest",
            "messages": messages,
            "stream": stream,
            "max_tokens": int(payload.get("max_tokens") or 1024),
        }
        if system:
            body["system"] = system
        if "temperature" in payload:
            body["temperature"] = payload.get("temperature")
        if "top_p" in payload:
            body["top_p"] = payload.get("top_p")
        if "stop" in payload:
            stop = payload.get("stop")
            if isinstance(stop, str):
                body["stop_sequences"] = [stop]
            elif isinstance(stop, list):
                body["stop_sequences"] = [str(x) for x in stop]
        return body

    def _request(self, payload: dict, *, stream: bool):
        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = self._build_anthropic_body(payload, stream=stream)
        try:
            return requests.post(url, headers=headers, json=body, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise APIProviderError(f"Anthropic request failed: {exc}") from exc

    def _normalize_non_stream(self, raw: dict) -> dict:
        content = raw.get("content") if isinstance(raw, dict) else None
        text_parts: list[str] = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
        text = "".join(text_parts)

        usage = raw.get("usage") if isinstance(raw, dict) else None
        in_tok = int((usage or {}).get("input_tokens") or 0)
        out_tok = int((usage or {}).get("output_tokens") or 0)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": raw.get("model") or "anthropic",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": self._map_finish_reason(raw.get("stop_reason")),
                }
            ],
            "usage": {
                "prompt_tokens": in_tok,
                "completion_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
            },
        }

    def _normalize_stream(self, lines):
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        model = "anthropic"
        emitted_start = False
        collected = ""
        finish_reason = "stop"

        for line in lines:
            if not line:
                continue
            s = line.strip()
            if s.startswith("event:"):
                continue
            if not s.startswith("data:"):
                continue
            data = s[len("data:") :].strip()
            if not data:
                continue
            if data == "[DONE]":
                break

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")
            if etype == "message_start" and not emitted_start:
                model = event.get("message", {}).get("model") or model
                emitted_start = True
                yield "data: " + json.dumps(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
                    }
                )
                continue

            if etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") != "text_delta":
                    continue
                piece = delta.get("text") or ""
                if not isinstance(piece, str) or not piece:
                    continue
                if not emitted_start:
                    emitted_start = True
                    yield "data: " + json.dumps(
                        {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
                        }
                    )
                collected += piece
                yield "data: " + json.dumps(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": collected}, "finish_reason": None}],
                    }
                )
                continue

            if etype == "message_delta":
                finish_reason = self._map_finish_reason((event.get("delta") or {}).get("stop_reason"))
                continue

            if etype == "message_stop":
                break

        if not emitted_start:
            yield "data: " + json.dumps(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
                }
            )

        yield "data: " + json.dumps(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            }
        )
        yield "data: [DONE]"

    def chat_completion(self, payload: dict, *, stream: bool):
        resp = self._request(payload, stream=stream)
        if resp.status_code >= 400:
            raise APIProviderError(f"Anthropic upstream error ({resp.status_code}): {resp.text}", status_code=resp.status_code)

        if stream:
            return self._normalize_stream(resp.iter_lines(decode_unicode=True))

        try:
            raw = resp.json()
        except ValueError as exc:
            raise APIProviderError("Anthropic upstream returned invalid JSON") from exc

        return self._normalize_non_stream(raw)
