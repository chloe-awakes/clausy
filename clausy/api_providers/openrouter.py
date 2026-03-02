from __future__ import annotations

import requests

from .base import APIProvider, APIProviderError


class OpenRouterAPIProvider(APIProvider):
    name = "openrouter"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        site_url: str = "",
        app_name: str = "",
        timeout_seconds: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.site_url = site_url
        self.app_name = app_name
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-Title"] = self.app_name
        return headers

    def chat_completion(self, payload: dict, *, stream: bool):
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise APIProviderError(f"OpenRouter request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise APIProviderError(f"OpenRouter upstream error ({resp.status_code}): {resp.text}", status_code=resp.status_code)

        if stream:
            return resp.iter_lines(decode_unicode=True)

        try:
            return resp.json()
        except ValueError as exc:
            raise APIProviderError("OpenRouter upstream returned invalid JSON") from exc
