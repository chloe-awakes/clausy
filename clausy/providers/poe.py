from __future__ import annotations

from .chatgpt import ChatGPTWebProvider


class PoeWebProvider(ChatGPTWebProvider):
    """Poe web UI adapter.

    Poe's composer/send controls are close to ChatGPT-style UIs, so we reuse
    robust fallback heuristics and override selectors for Poe-specific labels.
    """

    name = "poe"

    def __init__(self, url: str = "https://poe.com"):
        super().__init__(url=url)

    def _find_composer(self, page):
        return self._first_locator(page, [
            "textarea[placeholder*='Ask']",
            "textarea[placeholder*='Message']",
            "textarea[aria-label*='Message']",
            "textarea",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
        ])

    def _find_send_button(self, page):
        return self._first_locator(page, [
            "button[aria-label*='Send']",
            "button[aria-label*='Senden']",
            "button[type='submit']",
        ])

    def _stop_selector(self) -> str:
        return "button[aria-label*='Stop'], button:has-text('Stop')"
