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


class GeminiWebProvider(WebChatProvider):
    name = "gemini_web"

    def __init__(self, url: str = "https://gemini.google.com", allow_anonymous_browser: bool = False):
        self.url = url
        self.allow_anonymous_browser = allow_anonymous_browser

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
        if any(k in url for k in ("login", "signin", "accounts.google.com", "auth")):
            return True
        try:
            txt = (page.locator("body").inner_text(timeout=1000) or "").lower()
        except Exception:
            return False
        return any(k in txt for k in ("sign in", "anmelden", "continue with google"))

    def _find_composer(self, page):
        return self._first_locator(
            page,
            [
                "textarea",
                "div[contenteditable='true'][role='textbox']",
                "div[contenteditable='true']",
                "[aria-label*='Enter a prompt']",
                "[aria-label*='Eingabe']",
            ],
        )

    def _find_send_button(self, page):
        return self._first_locator(
            page,
            [
                "button[aria-label*='Send']",
                "button[aria-label*='Senden']",
                "button[data-testid*='send']",
                "button[type='submit']",
            ],
        )

    def _find_assistant_turns(self, page):
        return self._first_locator(
            page,
            [
                "article",
                "main article",
                "[data-message-author-role='assistant']",
                "main div:has(p)",
            ],
        )

    def ensure_ready(self, page) -> None:
        if not (page.url or "").startswith(self.url):
            page.goto(self.url, wait_until="domcontentloaded")

        saw_login_screen = False
        for _ in range(3):
            login_screen = self._is_login_screen(page)
            composer = self._find_composer(page)
            send = self._find_send_button(page)
            if composer is not None and (send is not None or self.allow_anonymous_browser):
                if login_screen and not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: Gemini shows login screen")
                return

            if login_screen:
                saw_login_screen = True
                if not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: Gemini shows login screen")

            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            time.sleep(0.8)

        if saw_login_screen:
            raise RuntimeError("NEEDS_LOGIN: Gemini shows login screen")
        raise RuntimeError("UI_NOT_READY: Gemini composer or send button not found")

    def send_prompt(self, page, text: str) -> None:
        composer = self._find_composer(page)
        if composer is None:
            raise RuntimeError("UI_NOT_READY: Gemini composer missing")

        target = composer.first if hasattr(composer, "first") else composer
        target.click()
        try:
            page.keyboard.press("Meta+A")
        except Exception:
            page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(text, delay=1)

        send = self._find_send_button(page)
        if send is not None:
            try:
                (send.first if hasattr(send, "first") else send).click()
                return
            except Exception:
                pass
        page.keyboard.press("Enter")

    def _stop_selector(self) -> str:
        return "button[aria-label*='Stop'], button:has-text('Stop')"

    def wait_done(self, page, timeout_ms: int = 120_000) -> None:
        stop_sel = self._stop_selector()
        try:
            page.wait_for_selector(stop_sel, timeout=15000)
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
        for sel in [".markdown", ".prose", "div[class*='markdown']", "div[class*='prose']"]:
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
            page.goto(self.url, wait_until="domcontentloaded")
            time.sleep(0.8)
        except Exception:
            pass
