from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
from .chatgpt import ChatGPTWebProvider
from .claude import ClaudeWebProvider
from .grok import GrokWebProvider

@dataclass
class ProviderRegistry:
    providers: Dict[str, object]

    @staticmethod
    def default(
        chatgpt_url: str,
        claude_url: str = "https://claude.ai",
        grok_url: str = "https://grok.com",
    ):
        return ProviderRegistry(providers={
            "chatgpt": ChatGPTWebProvider(url=chatgpt_url),
            "claude": ClaudeWebProvider(url=claude_url),
            "grok": GrokWebProvider(url=grok_url),
        })

    def get(self, name: str):
        if not name:
            name = "chatgpt"
        if name not in self.providers:
            raise KeyError(f"Unknown provider: {name}")
        return self.providers[name]
