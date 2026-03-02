from __future__ import annotations
import time
from typing import Iterable
from .base import WebChatProvider

def _delta(prev: str, cur: str) -> str:
    """Return the appended delta assuming cur extends prev; else return cur."""
    if cur.startswith(prev):
        return cur[len(prev):]
    # fallback: find longest common prefix
    i = 0
    m = min(len(prev), len(cur))
    while i < m and prev[i] == cur[i]:
        i += 1
    return cur[i:]

class ChatGPTWebProvider(WebChatProvider):
    name = "chatgpt"

    def __init__(self, url: str = "https://chatgpt.com", allow_anonymous_browser: bool = False):
        self.url = url
        self.allow_anonymous_browser = allow_anonymous_browser

    def _first_locator(self, page, selectors):
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if loc.count() > 0:
                    return loc
            except Exception:
                pass
        return None

    def _find_composer(self, page):
        return self._first_locator(page, [
            "#prompt-textarea",
            "[data-testid='prompt-textarea']",
            "div#prompt-textarea",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
        ])

    def _find_send_button(self, page):
        return self._first_locator(page, [
            "button#composer-submit-button",
            "button[data-testid='send-button']",
            "button[aria-label*='Send']",
            "button[aria-label*='Senden']",
            "button[type='submit']",
        ])

    def _find_new_chat(self, page):
        return self._first_locator(page, [
            "a[aria-label*='New chat']",
            "button[aria-label*='New chat']",
            "a[aria-label*='Neuer Chat']",
            "button[aria-label*='Neuer Chat']",
            "[data-testid='new-chat-button']",
        ])

    def _is_login_screen(self, page) -> bool:
        url = page.url or ""
        if "auth" in url or "login" in url:
            return True
        try:
            txt = page.locator("body").inner_text(timeout=1000)
        except Exception:
            return False
        return ("Log in" in txt) or ("Sign up" in txt) or ("Anmelden" in txt) or ("Registrieren" in txt)

    def ensure_ready(self, page) -> None:
        if not (page.url or "").startswith(self.url):
            page.goto(self.url, wait_until="domcontentloaded")

        saw_login_screen = False
        for _ in range(3):
            login_screen = self._is_login_screen(page)
            composer = self._find_composer(page)
            send_btn = self._find_send_button(page)
            if composer is not None and send_btn is not None:
                if login_screen and not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: ChatGPT shows login screen")
                return

            if login_screen:
                saw_login_screen = True
                if not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: ChatGPT shows login screen")

            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            time.sleep(0.5)

        if saw_login_screen:
            raise RuntimeError("NEEDS_LOGIN: ChatGPT shows login screen")
        raise RuntimeError("UI_NOT_READY: composer or send button not found after recovery")

    def send_prompt(self, page, text: str) -> None:
        composer = self._find_composer(page)
        if composer is None:
            raise RuntimeError("UI_NOT_READY: composer missing")

        composer.click()
        try:
            page.keyboard.press("Meta+A")
        except Exception:
            page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")

        page.keyboard.type(text, delay=1)

        send_btn = self._find_send_button(page)
        if send_btn is None:
            raise RuntimeError("UI_NOT_READY: send button missing")
        try:
            send_btn.click()
        except Exception:
            page.keyboard.press("Enter")

    def _stop_selector(self) -> str:
        return "button[data-testid='stop-button'], button[aria-label='Stop streaming'], button[aria-label*='Stop']"

    def wait_done(self, page, timeout_ms: int = 120_000) -> None:
        start_sel = self._stop_selector()
        try:
            page.wait_for_selector(start_sel, timeout=15000)
        except Exception:
            pass
        try:
            page.wait_for_selector(start_sel, state="hidden", timeout=timeout_ms)
        except Exception:
            pass
        time.sleep(0.4)

    def stream_last_assistant_deltas(self, page, poll_ms: int = 250, timeout_ms: int = 120_000) -> Iterable[str]:
        """Yield live text deltas from the last assistant message while generating."""
        start_sel = self._stop_selector()
        t0 = time.time()

        # wait for generation to start (best-effort)
        try:
            page.wait_for_selector(start_sel, timeout=15000)
        except Exception:
            # maybe it already finished quickly; just yield nothing
            return

        prev = ""
        while True:
            if (time.time() - t0) * 1000 > timeout_ms:
                break

            # if stop button is hidden, we are done
            try:
                if page.locator(start_sel).count() > 0 and page.locator(start_sel).first.is_hidden():
                    break
            except Exception:
                # if we can't query, continue polling
                pass

            cur = self.get_last_assistant_text(page) or ""
            d = _delta(prev, cur)
            if d:
                prev = cur
                yield d

            time.sleep(poll_ms / 1000.0)

        # final flush
        cur = self.get_last_assistant_text(page) or ""
        d = _delta(prev, cur)
        if d:
            yield d

    def get_last_assistant_text(self, page) -> str:
        turns = self._first_locator(page, [
            "article[data-turn='assistant']",
            "[data-message-author-role='assistant']",
            "article:has([data-message-author-role='assistant'])",
        ])
        if turns is None or turns.count() == 0:
            return "[No response found]"

        last_turn = turns.nth(turns.count() - 1)

        prose = last_turn.locator(".cm-content")
        if prose.count() == 0:
            prose = last_turn.locator(".markdown")
        if prose.count() > 0:
            text = prose.first.inner_text()
        else:
            text = last_turn.inner_text()

        return (text or "").strip()

    def start_new_chat(self, page) -> None:
        # Try clicking "New chat"
        try:
            btn = self._find_new_chat(page)
            if btn is not None:
                btn.first.click()
                time.sleep(0.8)
                return
        except Exception:
            pass

        # Fallback: go home (sometimes opens a fresh conversation)
        try:
            page.goto(self.url, wait_until="domcontentloaded")
            time.sleep(0.8)
        except Exception:
            pass
