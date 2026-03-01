from __future__ import annotations

from dataclasses import dataclass


@dataclass
class APIProviderError(RuntimeError):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


class APIProvider:
    name: str

    def chat_completion(self, payload: dict, *, stream: bool):
        raise NotImplementedError
