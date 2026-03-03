from __future__ import annotations
import os
import re
import time
import threading
import subprocess
from typing import Dict
from playwright.sync_api import sync_playwright

from .browser_runtime import (
    BrowserRuntimeConfig,
    build_browser_launch_command,
    detect_browser_binary,
    parse_bootstrap_mode,
)


_PROFILE_TRAVERSAL_SEGMENT_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)")


def _is_safe_profile_path(value: str | None) -> bool:
    if not value:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    if _PROFILE_TRAVERSAL_SEGMENT_RE.search(value):
        return False
    return True


class BrowserPool:
    """Manages a single Chrome/Chromium instance (CDP) and per-session pages/tabs."""

    def __init__(self, cdp_host: str, cdp_port: int, profile_dir: str, home_url: str):
        self.cdp_host = cdp_host
        self.cdp_port = cdp_port
        if not _is_safe_profile_path(profile_dir):
            raise ValueError("Unsafe browser profile path")
        self.profile_dir = os.path.abspath(profile_dir)
        self.home_url = home_url

        self._lock = threading.Lock()
        self._pw = None
        self._browser = None
        self._context = None
        self._pages: Dict[str, object] = {}
        self._bootstrap_proc = None

    def _connect_over_cdp(self):
        return self._pw.chromium.connect_over_cdp(f"http://{self.cdp_host}:{self.cdp_port}")

    def _wait_for_cdp(self, timeout_s: float = 15.0):
        deadline = time.time() + max(0.1, timeout_s)
        last_error = None
        while time.time() < deadline:
            try:
                return self._connect_over_cdp()
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
        raise RuntimeError(f"Could not connect to CDP endpoint http://{self.cdp_host}:{self.cdp_port}: {last_error}")

    def _bootstrap_browser(self) -> None:
        playwright_binary = self._pw.chromium.executable_path
        browser_binary = detect_browser_binary(playwright_binary=playwright_binary)
        if not browser_binary:
            install_hint = "python -m playwright install chromium"
            raise RuntimeError(
                "Browser bootstrap requested but no Chrome/Chromium binary was found. "
                f"Set CLAUSY_BROWSER_BINARY or install Chromium via: {install_hint}"
            )

        headless = (os.environ.get("CLAUSY_HEADLESS", "0").strip().lower() in {"1", "true", "yes", "on"})
        extra_args_raw = (os.environ.get("CLAUSY_BROWSER_ARGS") or "").strip()
        extra_args = [a for a in extra_args_raw.split(" ") if a] if extra_args_raw else []
        cmd = build_browser_launch_command(
            browser_binary,
            BrowserRuntimeConfig(
                cdp_host=self.cdp_host,
                cdp_port=self.cdp_port,
                profile_dir=self.profile_dir,
                headless=headless,
                extra_args=extra_args,
            ),
        )
        os.makedirs(self.profile_dir, exist_ok=True)
        self._bootstrap_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start(self) -> None:
        with self._lock:
            if self._browser:
                return
            self._pw = sync_playwright().start()

            last_error = None
            try:
                self._browser = self._connect_over_cdp()
            except Exception as e:
                last_error = e
                mode = parse_bootstrap_mode(os.environ.get("CLAUSY_BROWSER_BOOTSTRAP"))
                if mode == "never":
                    raise RuntimeError(
                        "Could not connect to Chrome/Chromium over CDP and browser bootstrap is disabled "
                        "(CLAUSY_BROWSER_BOOTSTRAP=never). Start a browser with --remote-debugging-port "
                        f"{self.cdp_port} or enable bootstrap. Last error: {last_error}"
                    ) from e
                try:
                    self._bootstrap_browser()
                    self._browser = self._wait_for_cdp(timeout_s=float(os.environ.get("CLAUSY_CDP_CONNECT_TIMEOUT", "20")))
                except Exception as bootstrap_error:
                    raise RuntimeError(
                        "Failed to connect to CDP and automatic browser bootstrap failed. "
                        "Set CLAUSY_BROWSER_BOOTSTRAP=never to require external browser, or set "
                        "CLAUSY_BROWSER_BINARY to a valid Chrome/Chromium binary. "
                        f"Connection error: {last_error}; bootstrap error: {bootstrap_error}"
                    ) from bootstrap_error

            if not self._browser:
                raise RuntimeError(f"Could not connect to Chrome/Chromium over CDP: {last_error}")

            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()

    def switch_profile(self, profile_dir: str | None) -> bool:
        """Switch active browser profile directory; restart browser if changed.

        Returns True when a profile change/restart happened.
        """
        if not _is_safe_profile_path(profile_dir):
            return False
        normalized = os.path.abspath(profile_dir)
        if normalized == self.profile_dir:
            return False

        with self._lock:
            self.profile_dir = normalized
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._pw = None
            self._pages = {}

        self.start()
        return True

    def get_page(self, session_id: str):
        if not session_id:
            session_id = "default"
        with self._lock:
            if not self._browser:
                self.start()
            if session_id in self._pages:
                return self._pages[session_id]

            page = self._context.new_page()
            page.goto(self.home_url, wait_until="domcontentloaded")
            self._pages[session_id] = page
            return page

    def reset_page(self, session_id: str):
        if not session_id:
            session_id = "default"
        with self._lock:
            if session_id in self._pages:
                try:
                    self._pages[session_id].close()
                except Exception:
                    pass
                self._pages.pop(session_id, None)

            page = self._context.new_page()
            page.goto(self.home_url, wait_until="domcontentloaded")
            self._pages[session_id] = page
            return page

    def restart_session(self, session_id: str):
        if not session_id:
            session_id = "default"
        with self._lock:
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._pw = None
            self._pages = {}

        self.start()
        return self.get_page(session_id)

    def new_temp_page(self, url: str):
        with self._lock:
            if not self._browser:
                self.start()
            page = self._context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            return page
