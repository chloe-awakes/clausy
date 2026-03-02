from __future__ import annotations

import json
import time
import uuid

import requests

from .base import APIProvider, APIProviderError


class GeminiAPIProvider(APIProvider):
    name = "gemini"

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _map_messages(payload: dict) -> tuple[str | None, list[dict]]:
        system_parts: list[str] = []
        contents: list[dict] = []

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

            gem_role = "user" if role == "user" else "model"
            contents.append({"role": gem_role, "parts": [{"text": content}]})

        system = "\n\n".join(p for p in system_parts if p.strip()) if system_parts else None
        return system, contents

    def _build_body(self, payload: dict) -> dict:
        system, contents = self._map_messages(payload)
        body: dict = {
            "contents": contents,
        }

        generation_config = {}
        if "temperature" in payload:
            generation_config["temperature"] = payload.get("temperature")
        if "top_p" in payload:
            generation_config["topP"] = payload.get("top_p")
        if "max_tokens" in payload:
            generation_config["maxOutputTokens"] = payload.get("max_tokens")
        if "stop" in payload:
            stop = payload.get("stop")
            if isinstance(stop, str):
                generation_config["stopSequences"] = [stop]
            elif isinstance(stop, list):
                generation_config["stopSequences"] = [str(x) for x in stop]
        if generation_config:
            body["generationConfig"] = generation_config

        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        return body

    def _request(self, payload: dict):
        model = payload.get("model") or "gemini-1.5-flash"
        url = f"{self.base_url}/models/{model}:generateContent"
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}
        body = self._build_body(payload)
        try:
            return requests.post(url, params=params, headers=headers, json=body, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise APIProviderError(f"Gemini request failed: {exc}") from exc

    @staticmethod
    def _extract_text(raw: dict) -> str:
        candidates = raw.get("candidates") if isinstance(raw, dict) else None
        if not isinstance(candidates, list) or not candidates:
            return ""
        content = (candidates[0] or {}).get("content")
        parts = (content or {}).get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            return ""
        chunks: list[str] = []
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                chunks.append(p["text"])
        return "".join(chunks)

    def _normalize_non_stream(self, raw: dict, *, model: str) -> dict:
        text = self._extract_text(raw)

        usage = raw.get("usageMetadata") if isinstance(raw, dict) else None
        in_tok = int((usage or {}).get("promptTokenCount") or 0)
        out_tok = int((usage or {}).get("candidatesTokenCount") or 0)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": in_tok,
                "completion_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
            },
        }

    def _normalize_stream(self, raw: dict, *, model: str):
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        text = self._extract_text(raw)
        yield "data: " + json.dumps(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
            }
        )
        if text:
            yield "data: " + json.dumps(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }
            )
        yield "data: " + json.dumps(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        yield "data: [DONE]"

    def chat_completion(self, payload: dict, *, stream: bool):
        model = payload.get("model") or "gemini-1.5-flash"
        resp = self._request(payload)
        if resp.status_code >= 400:
            raise APIProviderError(f"Gemini upstream error ({resp.status_code}): {resp.text}", status_code=resp.status_code)

        try:
            raw = resp.json()
        except ValueError as exc:
            raise APIProviderError("Gemini upstream returned invalid JSON") from exc

        if stream:
            return self._normalize_stream(raw, model=model)

        return self._normalize_non_stream(raw, model=model)
