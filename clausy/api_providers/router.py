from __future__ import annotations

import os

from .base import APIProviderError
from .openai import OpenAIAPIProvider
from .stubs import AnthropicAPIProvider, OllamaAPIProvider


class APIProviderRouter:
    def __init__(self):
        self._providers = {
            "openai": OpenAIAPIProvider(
                base_url=(os.environ.get("CLAUSY_OPENAI_BASE_URL", "https://api.openai.com/v1").strip()),
                api_key=(os.environ.get("CLAUSY_OPENAI_API_KEY", "").strip()),
            ),
            "anthropic": AnthropicAPIProvider(
                base_url=(os.environ.get("CLAUSY_ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").strip()),
                api_key=(os.environ.get("CLAUSY_ANTHROPIC_API_KEY", "").strip()),
            ),
            "ollama": OllamaAPIProvider(
                base_url=(os.environ.get("CLAUSY_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").strip()),
                api_key=(os.environ.get("CLAUSY_OLLAMA_API_KEY", "").strip()),
            ),
        }

    def get(self, name: str):
        key = (name or "").strip().lower()
        if key not in self._providers:
            raise APIProviderError(f"Unknown API provider: {name}")
        return self._providers[key]


def is_api_provider(name: str) -> bool:
    return (name or "").strip().lower() in {"openai", "anthropic", "ollama"}
