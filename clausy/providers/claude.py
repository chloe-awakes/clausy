from __future__ import annotations
import re
import time
from typing import Iterable, Optional
from .base import WebChatProvider

def _delta(prev: str, cur: str) -> str:
    if cur.startswith(prev):
        return cur[len(prev):]
    i = 0
    m = min(len(prev), len(cur))
    while i < m and prev[i] == cur[i]:
        i += 1
    return cur[i:]

class ClaudeWebProvider(WebChatProvider):
    """Claude web UI adapter (claude.ai).

    This provider uses accessibility-first heuristics:
    - input: role=textbox (often a contenteditable element)
    - send: button near composer, or button with name/label matching send/submit
    - output: last assistant message container heuristics

    Note: claude.ai DOM can change frequently; keep overrides minimal and prefer role-based locators.
    """
    name = "claude"

    def __init__(self, url: str = "https://claude.ai", allow_anonymous_browser: bool = False):
        self.url = url
        self.allow_anonymous_browser = allow_anonymous_browser

    def _is_login_screen(self, page) -> bool:
        url = page.url or ""
        if "login" in url or "auth" in url:
            return True
        try:
            txt = page.locator("body").inner_text(timeout=1000)
        except Exception:
            return False
        txt_low = (txt or "").lower()
        return any(k in txt_low for k in ("log in", "sign in", "sign up", "anmelden", "einloggen", "continue with"))

    def _find_input(self, page):
        # Prefer accessible role textbox
        try:
            loc = page.get_by_role("textbox")
            if loc.count() > 0:
                return loc.last
        except Exception:
            pass

        # Fallbacks
        for sel in [
            "textarea",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass
        return None

    def _find_send_button(self, page):
        # Try explicit accessible names
        name_re = re.compile(r"(send|submit|enter|senden|abschicken)", re.I)
        try:
            btn = page.get_by_role("button", name=name_re)
            if btn.count() > 0:
                # prefer enabled
                for i in range(min(btn.count(), 6)):
                    b = btn.nth(i)
                    try:
                        if b.is_enabled():
                            return b
                    except Exception:
                        pass
                return btn.first
        except Exception:
            pass

        # Generic fallbacks
        for sel in [
            "button[type='submit']",
            "button[aria-label*='Send']",
            "button[aria-label*='Senden']",
            "button:has-text('Send')",
            "button:has-text('Senden')",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    # pick first enabled
                    for i in range(min(loc.count(), 6)):
                        b = loc.nth(i)
                        try:
                            if b.is_enabled():
                                return b
                        except Exception:
                            pass
                    return loc.first
            except Exception:
                pass
        return None

    def _find_turns(self, page):
        # Heuristic containers for messages
        for sel in [
            "main article",
            "article",
            "[role='article']",
            "main [data-testid]",
            "main div:has(p)",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    return loc
            except Exception:
                pass
        return None

    def ensure_ready(self, page) -> None:
        if not (page.url or "").startswith(self.url):
            page.goto(self.url, wait_until="domcontentloaded")

        saw_login_screen = False
        for _ in range(3):
            login_screen = self._is_login_screen(page)
            inp = self._find_input(page)
            send = self._find_send_button(page)
            if inp is not None and send is not None:
                if login_screen and not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: Claude shows login screen")
                return

            if login_screen:
                saw_login_screen = True
                if not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: Claude shows login screen")

            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            time.sleep(0.8)

        if saw_login_screen:
            raise RuntimeError("NEEDS_LOGIN: Claude shows login screen")
        raise RuntimeError("UI_NOT_READY: Claude input or send button not found")

    def send_prompt(self, page, text: str) -> None:
        inp = self._find_input(page)
        if inp is None:
            raise RuntimeError("UI_NOT_READY: Claude input missing")
        inp.click()
        # Clear via select-all
        try:
            page.keyboard.press("Meta+A")
        except Exception:
            page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(text, delay=1)

        btn = self._find_send_button(page)
        if btn is None:
            raise RuntimeError("UI_NOT_READY: Claude send button missing")
        try:
            btn.click()
        except Exception:
            page.keyboard.press("Enter")

    def wait_done(self, page, timeout_ms: int = 120_000) -> None:
        # Generic: wait until last assistant text stops changing for a bit.
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
            if stable >= 6:  # ~1.5s if poll=250ms
                break
            time.sleep(0.25)

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

        # final flush
        cur = self.get_last_assistant_text(page) or ""
        d = _delta(prev, cur)
        if d:
            yield d

    def get_last_assistant_text(self, page) -> str:
        turns = self._find_turns(page)
        if turns is None or turns.count() == 0:
            return "[No response found]"

        # Best-effort: pick last article-like element and extract text
        last = turns.nth(turns.count() - 1)
        # Prefer markdown-ish blocks if present
        for sel in [".markdown", ".prose", "div[class*='markdown']", "div[class*='prose']"]:
            try:
                prose = last.locator(sel)
                if prose.count() > 0:
                    return (prose.first.inner_text() or "").strip()
            except Exception:
                pass
        try:
            return (last.inner_text() or "").strip()
        except Exception:
            return "[No response found]"

    def start_new_chat(self, page) -> None:
        # Very best-effort: navigate home to start fresh
        try:
            page.goto(self.url, wait_until="domcontentloaded")
            time.sleep(0.8)
        except Exception:
            pass
