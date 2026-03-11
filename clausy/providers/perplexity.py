from __future__ import annotations

import time

from .chatgpt import ChatGPTWebProvider


class PerplexityWebProvider(ChatGPTWebProvider):
    """Perplexity web UI adapter.

    Perplexity's DOM is closer to a search/results app than a chat thread:
    - composer is usually a contenteditable role=textbox
    - answers render inside role=tabpanel containers, not assistant articles
    - an auth/signup modal can appear after the answer without blocking reads
    """

    name = "perplexity"

    def __init__(self, url: str = "https://www.perplexity.ai"):
        super().__init__(url=url)

    def _find_composer(self, page):
        try:
            textbox = page.get_by_role("textbox")
            if textbox.count() > 0:
                for i in range(min(textbox.count(), 8)):
                    cand = textbox.nth(i)
                    try:
                        if cand.is_visible():
                            return cand
                    except Exception:
                        return cand
                return textbox.first
        except Exception:
            pass

        return self._first_locator(page, [
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
            "textarea[placeholder*='Ask']",
            "textarea[aria-label*='Ask']",
            "textarea",
        ])

    def _find_send_button(self, page):
        try:
            btn = page.get_by_role("button", name="Submit")
            if btn.count() > 0:
                return btn.first
        except Exception:
            pass
        return self._first_locator(page, [
            "button[aria-label*='Submit']",
            "button[aria-label*='Send']",
            "button[aria-label*='Senden']",
            "button[type='submit']",
        ])

    def _stop_selector(self) -> str:
        return "button[aria-label*='Stop'], button:has-text('Stop')"

    def wait_done(self, page, timeout_ms: int = 120_000) -> None:
        stop_sel = self._stop_selector()
        try:
            page.wait_for_selector(stop_sel, timeout=8000)
        except Exception:
            pass
        try:
            page.wait_for_selector(stop_sel, state="hidden", timeout=timeout_ms)
        except Exception:
            t0 = time.time()
            stable = 0
            prev = ""
            while (time.time() - t0) * 1000 < timeout_ms:
                cur = self.get_last_assistant_text(page) or ""
                if cur and cur == prev and cur != "[No response found]":
                    stable += 1
                else:
                    stable = 0
                    prev = cur
                if stable >= 6:
                    break
                time.sleep(0.25)
        time.sleep(0.4)

    def get_last_assistant_text(self, page) -> str:
        candidates = []
        for sel in [
            "[role='tabpanel']",
            "main [role='tabpanel']",
            "main article",
            "article",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    candidates.append(loc.nth(loc.count() - 1))
            except Exception:
                pass

        for cand in candidates:
            try:
                text = (cand.inner_text() or "").strip()
            except Exception:
                continue
            if not text:
                continue

            cleaned = text
            for prefix in [
                "Answer\nLinks\nImages\nShare\nDownload Comet\n",
                "Answer\nLinks\nImages\nShare\n",
                "Answer\nLinks\nImages\n",
            ]:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()

            for trailer in ["\nAsk a follow-up", "\nModel", "\nSign up below to unlock the full potential of Perplexity"]:
                if trailer in cleaned:
                    cleaned = cleaned.split(trailer, 1)[0].rstrip()

            if cleaned:
                return cleaned

        return "[No response found]"

    def start_new_chat(self, page) -> None:
        try:
            btn = page.get_by_role("button", name="New Thread")
            if btn.count() > 0:
                btn.first.click()
                time.sleep(0.8)
                return
        except Exception:
            pass
        super().start_new_chat(page)
