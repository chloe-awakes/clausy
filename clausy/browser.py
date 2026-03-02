from __future__ import annotations
import os
import time
import threading
import subprocess
from typing import Dict
from playwright.sync_api import sync_playwright

class BrowserPool:
    """Manages a single Chrome instance (CDP) and per-session pages/tabs."""

    def __init__(self, cdp_host: str, cdp_port: int, profile_dir: str, home_url: str):
        self.cdp_host = cdp_host
        self.cdp_port = cdp_port
        self.profile_dir = os.path.abspath(profile_dir)
        self.home_url = home_url

        self._lock = threading.Lock()
        self._pw = None
        self._browser = None
        self._context = None
        self._pages: Dict[str, object] = {}  # session_id -> Page

    def start(self) -> None:
        with self._lock:
            if self._browser:
                return
            self._pw = sync_playwright().start()

            last_error = None
            try:
                self._browser = self._pw.chromium.connect_over_cdp(f"http://{self.cdp_host}:{self.cdp_port}")
            except Exception as e:
                last_error = e
                subprocess.Popen([
                    "open",
                    "-na", "Google Chrome",
                    "--args",
                    f"--remote-debugging-port={self.cdp_port}",
                    f"--user-data-dir={self.profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-session-crashed-bubble",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                for _ in range(30):
                    time.sleep(0.5)
                    try:
                        self._browser = self._pw.chromium.connect_over_cdp(f"http://{self.cdp_host}:{self.cdp_port}")
                        break
                    except Exception as e2:
                        last_error = e2

            if not self._browser:
                raise RuntimeError(f"Could not connect to Chrome over CDP: {last_error}")

            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()

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
        """Close existing tab for this session and open a fresh one."""
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
        """Restart browser connection for stability and reopen this session tab."""
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
    """Open a temporary page (tab) for one-off tasks like web search.
    The caller is responsible for closing the returned page.
    """
    with self._lock:
        if not self._browser:
            self.start()
        page = self._context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        return page
