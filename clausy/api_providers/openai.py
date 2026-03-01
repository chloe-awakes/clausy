from __future__ import annotations

import requests

from .base import APIProvider, APIProviderError


class OpenAIAPIProvider(APIProvider):
    name = "openai"

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def chat_completion(self, payload: dict, *, stream: bool):
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise APIProviderError(f"OpenAI request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise APIProviderError(f"OpenAI upstream error ({resp.status_code}): {resp.text}", status_code=resp.status_code)

        if stream:
            return resp.iter_lines(decode_unicode=True)

        try:
            return resp.json()
        except ValueError as exc:
            raise APIProviderError("OpenAI upstream returned invalid JSON") from exc
