from __future__ import annotations

import json
import time
import uuid

import requests

from .base import APIProvider, APIProviderError


class OllamaAPIProvider(APIProvider):
    name = "ollama"

    def __init__(self, *, base_url: str, api_key: str = "", timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _map_finish_reason(reason: str | None) -> str:
        if reason in {"stop", "end_turn", "tool_calls"}:
            return reason
        if reason in {"length", "max_tokens"}:
            return "length"
        return "stop"

    def _build_body(self, payload: dict, *, stream: bool) -> dict:
        body = {
            "model": payload.get("model") or "llama3.2",
            "messages": payload.get("messages") or [],
            "stream": stream,
        }
        options = {}
        if "temperature" in payload:
            options["temperature"] = payload.get("temperature")
        if "top_p" in payload:
            options["top_p"] = payload.get("top_p")
        if "max_tokens" in payload:
            options["num_predict"] = payload.get("max_tokens")
        if options:
            body["options"] = options
        return body

    def _request(self, payload: dict, *, stream: bool):
        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = self._build_body(payload, stream=stream)
        try:
            return requests.post(url, headers=headers, json=body, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise APIProviderError(f"Ollama request failed: {exc}") from exc

    def _normalize_non_stream(self, raw: dict) -> dict:
        msg = raw.get("message") if isinstance(raw, dict) else None
        content = ""
        if isinstance(msg, dict):
            content = str(msg.get("content") or "")

        in_tok = int((raw or {}).get("prompt_eval_count") or 0)
        out_tok = int((raw or {}).get("eval_count") or 0)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": (raw or {}).get("model") or "ollama",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": self._map_finish_reason((raw or {}).get("done_reason")),
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
        model = "ollama"
        emitted_start = False
        collected = ""
        finish_reason = "stop"

        for line in lines:
            if not line:
                continue
            s = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
            s = s.strip()
            if not s:
                continue
            if s.startswith("data:"):
                s = s[len("data:") :].strip()
            if s == "[DONE]":
                break
            try:
                event = json.loads(s)
            except json.JSONDecodeError:
                continue

            model = event.get("model") or model
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

            message = event.get("message") if isinstance(event, dict) else None
            piece = ""
            if isinstance(message, dict):
                piece = message.get("content") or ""
            if isinstance(piece, str) and piece:
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

            if event.get("done"):
                finish_reason = self._map_finish_reason(event.get("done_reason"))
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
            raise APIProviderError(f"Ollama upstream error ({resp.status_code}): {resp.text}", status_code=resp.status_code)

        if stream:
            return self._normalize_stream(resp.iter_lines(decode_unicode=True))

        try:
            raw = resp.json()
        except ValueError as exc:
            raise APIProviderError("Ollama upstream returned invalid JSON") from exc

        return self._normalize_non_stream(raw)
