from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Iterable

class WebChatProvider(ABC):
    """Thin adapter for a specific web chat UI."""

    name: str

    @abstractmethod
    def ensure_ready(self, page) -> None:
        """Ensure UI is ready for typing+sending. Raise RuntimeError on fatal states (e.g. needs login)."""

    @abstractmethod
    def send_prompt(self, page, text: str) -> None:
        """Type/insert text and submit."""

    @abstractmethod
    def wait_done(self, page, timeout_ms: int = 120_000) -> None:
        """Wait until generation is complete."""

    @abstractmethod
    def get_last_assistant_text(self, page) -> str:
        """Extract last assistant message as text."""

    def stream_last_assistant_deltas(self, page, poll_ms: int = 250, timeout_ms: int = 120_000) -> Iterable[str]:
        """Optional: yield incremental text deltas while model is generating."""
        raise NotImplementedError

    def start_new_chat(self, page) -> None:
        """Optional: start a new chat in the current tab."""
        raise NotImplementedError
