from __future__ import annotations
import re
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
        # Prefer stable ChatGPT composer hooks first; role=textbox can match sidebar/search fields.
        explicit = self._first_locator(
            page,
            [
                "#prompt-textarea",
                "[data-testid='prompt-textarea']",
                "textarea#prompt-textarea",
                "textarea[data-testid='prompt-textarea']",
                "div#prompt-textarea",
                "form #prompt-textarea",
                "textarea[placeholder*='Message']",
                "textarea[placeholder*='Nachricht']",
                "div[contenteditable='true'][role='textbox']",
                "div[contenteditable='true'][aria-label*='Message']",
                "div[contenteditable='true'][aria-label*='Nachricht']",
                "div[contenteditable='true'][aria-label*='Ask']",
                "div[contenteditable='true'][data-lexical-editor='true']",
                "div.ProseMirror[contenteditable='true']",
                "textarea[aria-label*='Message']",
                "textarea[aria-label*='Ask']",
                "div[contenteditable='true']",
            ],
        )
        if explicit is not None:
            return explicit.first if hasattr(explicit, "first") else explicit

        # Accessibility fallback: pick an interactable textbox, prefer prompt-textarea/contenteditable.
        try:
            textbox = page.get_by_role("textbox")
            count = textbox.count()
            if count > 0:
                preferred = None
                for i in range(min(count, 12)):
                    cand = textbox.nth(i)
                    try:
                        cid = (cand.get_attribute("id") or "").lower()
                        ctest = (cand.get_attribute("data-testid") or "").lower()
                        role = (cand.get_attribute("role") or "").lower()
                        editable = cand.get_attribute("contenteditable")
                        if "prompt-textarea" in cid or "prompt-textarea" in ctest:
                            return cand
                        if editable == "true" and role == "textbox":
                            preferred = cand
                    except Exception:
                        pass
                    if self._is_composer_interactable(cand):
                        preferred = preferred or cand
                if preferred is not None:
                    return preferred
                return textbox.last
        except Exception:
            pass

        return None

    def _find_send_button(self, page):
        # Prefer explicit button role with translated send/submit names.
        try:
            by_name = page.get_by_role("button", name=re.compile(r"(send|submit|senden|abschicken)", re.I))
            if by_name.count() > 0:
                for i in range(min(by_name.count(), 8)):
                    btn = by_name.nth(i)
                    try:
                        if btn.is_enabled():
                            return btn
                    except Exception:
                        pass
                return by_name.first
        except Exception:
            pass

        return self._first_locator(
            page,
            [
                "button#composer-submit-button",
                "#composer-submit-button",
                "button[data-testid='send-button']",
                "button[data-testid='composer-submit-button']",
                "button[aria-label*='Send prompt']",
                "button[aria-label*='Send']",
                "button[aria-label*='Senden']",
                "button[type='submit']",
                "form button:last-child",
                "button:has-text('Send')",
                "button:has-text('Senden')",
            ],
        )

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

    def _wait_for_ui_settle(self, page, ms: int = 350) -> None:
        try:
            page.wait_for_timeout(ms)
            return
        except Exception:
            pass
        time.sleep(ms / 1000.0)

    def _is_composer_interactable(self, composer) -> bool:
        if composer is None:
            return False
        try:
            target = composer.first if hasattr(composer, "first") else composer
            if hasattr(target, "is_disabled") and target.is_disabled():
                return False
        except Exception:
            pass
        try:
            target = composer.first if hasattr(composer, "first") else composer
            if target.get_attribute("readonly") is not None:
                return False
        except Exception:
            pass
        return True

    def _can_submit_with_enter(self, page, composer) -> bool:
        if not self._is_composer_interactable(composer):
            return False

        # Most ChatGPT-style composers submit on Enter and use Shift+Enter for newline.
        # If we can detect that hint, treat composer-only as ready.
        try:
            body = page.locator("body").inner_text(timeout=500) or ""
            body_l = body.lower()
            if ("shift+enter" in body_l and "enter" in body_l) or "press enter" in body_l:
                return True
        except Exception:
            pass

        # Fallback: interactable composer implies Enter submission is usually available.
        return True

    def ensure_ready(self, page) -> None:
        if not (page.url or "").startswith(self.url):
            page.goto(self.url, wait_until="domcontentloaded")

        saw_login_screen = False
        # ChatGPT UI can take a few seconds to hydrate; use a longer bounded poll
        # before attempting hard recovery reloads.
        attempts = 8
        for attempt in range(attempts):
            self._wait_for_ui_settle(page, ms=900 if attempt < 3 else 500)
            login_screen = self._is_login_screen(page)
            composer = self._find_composer(page)
            send_btn = self._find_send_button(page)
            enter_submit_ready = self._can_submit_with_enter(page, composer)

            if composer is not None and (send_btn is not None or enter_submit_ready):
                if login_screen and not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: ChatGPT shows login screen")
                return

            if login_screen:
                saw_login_screen = True
                if not self.allow_anonymous_browser:
                    raise RuntimeError("NEEDS_LOGIN: ChatGPT shows login screen")

            # Avoid aggressive reload loops while the app is hydrating.
            # Do a hard recovery reload only after a few failed polls.
            if attempt in (3, 6):
                try:
                    page.reload(wait_until="domcontentloaded")
                except Exception:
                    pass
                self._wait_for_ui_settle(page, ms=900)

        if saw_login_screen:
            raise RuntimeError("NEEDS_LOGIN: ChatGPT shows login screen")
        raise RuntimeError("UI_NOT_READY: composer or send controls not found after recovery")

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
        if send_btn is not None:
            try:
                send_btn.click()
                return
            except Exception:
                pass

        if self._can_submit_with_enter(page, composer):
            page.keyboard.press("Enter")
            return

        raise RuntimeError("UI_NOT_READY: send controls missing")

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
