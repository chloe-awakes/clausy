from __future__ import annotations

from .base import APIProvider, APIProviderError


class OllamaAPIProvider(APIProvider):
    name = "ollama"

    def __init__(self, *, base_url: str, api_key: str = ""):
        self.base_url = base_url
        self.api_key = api_key

    def chat_completion(self, payload: dict, *, stream: bool):
        raise APIProviderError("Ollama API provider scaffolded but not implemented yet")
