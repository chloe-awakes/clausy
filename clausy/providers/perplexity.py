from __future__ import annotations

from .chatgpt import ChatGPTWebProvider


class PerplexityWebProvider(ChatGPTWebProvider):
    """Perplexity web UI adapter.

    Uses ChatGPT-style fallback heuristics with Perplexity-specific defaults and selectors.
    """

    name = "perplexity"

    def __init__(self, url: str = "https://www.perplexity.ai"):
        super().__init__(url=url)

    def _find_composer(self, page):
        return self._first_locator(page, [
            "textarea[placeholder*='Ask']",
            "textarea[aria-label*='Ask']",
            "textarea",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
        ])

    def _find_send_button(self, page):
        return self._first_locator(page, [
            "button[aria-label*='Submit']",
            "button[aria-label*='Send']",
            "button[aria-label*='Senden']",
            "button[type='submit']",
        ])

    def _stop_selector(self) -> str:
        return "button[aria-label*='Stop'], button:has-text('Stop')"
