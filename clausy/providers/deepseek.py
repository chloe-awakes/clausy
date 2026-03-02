from __future__ import annotations

from .chatgpt import ChatGPTWebProvider


class DeepSeekWebProvider(ChatGPTWebProvider):
    """DeepSeek web UI adapter.

    DeepSeek uses a chat-composer/send interaction close to ChatGPT-like UIs,
    so we reuse resilient ChatGPT fallbacks with DeepSeek-specific selectors.
    """

    name = "deepseek"

    def __init__(self, url: str = "https://chat.deepseek.com"):
        super().__init__(url=url)

    def _find_composer(self, page):
        return self._first_locator(page, [
            "textarea[placeholder*='Message']",
            "textarea[placeholder*='Ask']",
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
