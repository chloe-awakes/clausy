from __future__ import annotations

import time
from typing import Iterable

from .base import WebChatProvider


def _delta(prev: str, cur: str) -> str:
    if cur.startswith(prev):
        return cur[len(prev):]
    i = 0
    m = min(len(prev), len(cur))
    while i < m and prev[i] == cur[i]:
        i += 1
    return cur[i:]


class GrokWebProvider(WebChatProvider):
    name = "grok"

    def __init__(self, url: str = "https://grok.com"):
        self.url = url

    def _first_locator(self, page, selectors):
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    return loc
            except Exception:
                pass
        return None

    def _is_login_screen(self, page) -> bool:
        url = (page.url or "").lower()
        if any(k in url for k in ("login", "signin", "auth", "x.com/i/flow")):
            return True
        try:
            txt = (page.locator("body").inner_text(timeout=1000) or "").lower()
        except Exception:
            return False
        return any(
            k in txt
            for k in (
                "log in",
                "sign in",
                "sign up",
                "continue with",
                "anmelden",
                "einloggen",
            )
        )

    def _find_composer(self, page):
        return self._first_locator(
            page,
            [
                "textarea[placeholder*='Ask']",
                "textarea[aria-label*='Ask']",
                "textarea",
                "div[contenteditable='true'][role='textbox']",
                "div[contenteditable='true']",
            ],
        )

    def _find_send_button(self, page):
        return self._first_locator(
            page,
            [
                "button[aria-label*='Send']",
                "button[aria-label*='send']",
                "button[data-testid*='send']",
                "button[type='submit']",
                "button:has-text('Send')",
            ],
        )

    def _find_new_chat(self, page):
        return self._first_locator(
            page,
            [
                "a[aria-label*='New chat']",
                "button[aria-label*='New chat']",
                "button:has-text('New chat')",
                "button:has-text('New Chat')",
                "button:has-text('New conversation')",
            ],
        )

    def _find_assistant_turns(self, page):
        return self._first_locator(
            page,
            [
                "article[data-author='assistant']",
                "[data-message-author-role='assistant']",
                "article:has([aria-label*='Grok'])",
                "main article",
                "article",
            ],
        )

    def ensure_ready(self, page) -> None:
        if not (page.url or "").startswith(self.url):
            page.goto(self.url, wait_until="domcontentloaded")

        for _ in range(3):
            if self._is_login_screen(page):
                raise RuntimeError("NEEDS_LOGIN: Grok shows login screen")

            composer = self._find_composer(page)
            send = self._find_send_button(page)
            if composer is not None and send is not None:
                return

            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            time.sleep(0.8)

        raise RuntimeError("UI_NOT_READY: Grok composer or send button not found")

    def send_prompt(self, page, text: str) -> None:
        composer = self._find_composer(page)
        if composer is None:
            raise RuntimeError("UI_NOT_READY: Grok composer missing")

        composer.first.click()
        try:
            page.keyboard.press("Meta+A")
        except Exception:
            page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(text, delay=1)

        send = self._find_send_button(page)
        if send is None:
            raise RuntimeError("UI_NOT_READY: Grok send button missing")
        try:
            send.first.click()
        except Exception:
            page.keyboard.press("Enter")

    def _stop_selector(self) -> str:
        return (
            "button[aria-label*='Stop'],"
            " button[data-testid*='stop'],"
            " button:has-text('Stop')"
        )

    def wait_done(self, page, timeout_ms: int = 120_000) -> None:
        stop_sel = self._stop_selector()
        try:
            page.wait_for_selector(stop_sel, timeout=15000)
        except Exception:
            pass
        try:
            page.wait_for_selector(stop_sel, state="hidden", timeout=timeout_ms)
        except Exception:
            # fallback stability check
            t0 = time.time()
            stable = 0
            prev = ""
            while (time.time() - t0) * 1000 < timeout_ms:
                cur = self.get_last_assistant_text(page) or ""
                if cur and cur == prev:
                    stable += 1
                else:
                    stable = 0
                    prev = cur
                if stable >= 6:
                    break
                time.sleep(0.25)
        time.sleep(0.4)

    def stream_last_assistant_deltas(self, page, poll_ms: int = 250, timeout_ms: int = 120_000) -> Iterable[str]:
        t0 = time.time()
        prev = ""
        stable = 0
        while (time.time() - t0) * 1000 < timeout_ms:
            cur = self.get_last_assistant_text(page) or ""
            d = _delta(prev, cur)
            if d:
                prev = cur
                stable = 0
                yield d
            else:
                stable += 1
            if stable >= 8 and cur:
                break
            time.sleep(poll_ms / 1000.0)

        cur = self.get_last_assistant_text(page) or ""
        d = _delta(prev, cur)
        if d:
            yield d

    def get_last_assistant_text(self, page) -> str:
        turns = self._find_assistant_turns(page)
        if turns is None:
            return "[No response found]"

        try:
            n = turns.count()
        except Exception:
            return "[No response found]"
        if n == 0:
            return "[No response found]"

        last = turns.nth(n - 1)
        for sel in [
            ".markdown",
            ".prose",
            "[data-testid*='message-text']",
            "div[class*='markdown']",
            "div[class*='prose']",
        ]:
            try:
                loc = last.locator(sel)
                if loc.count() > 0:
                    return (loc.first.inner_text() or "").strip()
            except Exception:
                pass

        try:
            return (last.inner_text() or "").strip()
        except Exception:
            return "[No response found]"

    def start_new_chat(self, page) -> None:
        try:
            btn = self._find_new_chat(page)
            if btn is not None:
                btn.first.click()
                time.sleep(0.8)
                return
        except Exception:
            pass

        try:
            page.goto(self.url, wait_until="domcontentloaded")
            time.sleep(0.8)
        except Exception:
            pass
