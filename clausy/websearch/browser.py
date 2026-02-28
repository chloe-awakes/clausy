from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from ..browser import BrowserPool
from .service import SearchResult, WebSearchError, _clip

BrowserProviderName = Literal["google_web", "brave_web"]

def _encode_q(q: str) -> str:
    return urllib.parse.quote_plus(q)

class WebSearchBrowserService:
    """Web search via browser UI (scraping) using the existing CDP Chrome.

    This is less stable than official APIs (DOM changes, consent screens), but requires no API keys.
    """

    def __init__(self, browser: BrowserPool) -> None:
        self.browser = browser

    def search(
        self,
        q: str,
        provider: BrowserProviderName,
        count: int = 5,
        offset: int = 0,
        safe: str = "moderate",
        lang: Optional[str] = None,
        country: Optional[str] = None,
        timeout_ms: int = 25_000,
    ) -> List[SearchResult]:
        count = max(1, min(int(count), 10))
        offset = max(0, int(offset))

        if provider == "google_web":
            url = self._google_url(q=q, safe=safe, lang=lang, country=country, start=offset)
            return self._scrape_google(url=url, count=count, timeout_ms=timeout_ms)
        if provider == "brave_web":
            url = self._brave_url(q=q, safe=safe, lang=lang, country=country, offset=offset)
            return self._scrape_brave(url=url, count=count, timeout_ms=timeout_ms)

        raise WebSearchError(f"Unknown browser provider: {provider}")

    def _google_url(self, q: str, safe: str, lang: Optional[str], country: Optional[str], start: int) -> str:
        params = {"q": q}
        if lang:
            params["hl"] = lang
        if country:
            params["gl"] = country
        if safe in ("strict", "on", "active"):
            params["safe"] = "active"
        if start:
            params["start"] = str(start)
        return "https://www.google.com/search?" + urllib.parse.urlencode(params)

    def _brave_url(self, q: str, safe: str, lang: Optional[str], country: Optional[str], offset: int) -> str:
        # Brave Search public UI
        params = {"q": q}
        # Brave supports 'offset' on some pages; keep best-effort
        if offset:
            params["offset"] = str(offset)
        # Language/country best-effort; Brave UI varies
        if lang:
            params["lang"] = lang
        if country:
            params["country"] = country
        if safe in ("strict", "on"):
            params["safesearch"] = "strict"
        elif safe in ("off", "none"):
            params["safesearch"] = "off"
        return "https://search.brave.com/search?" + urllib.parse.urlencode(params)

    def _scrape_google(self, url: str, count: int, timeout_ms: int) -> List[SearchResult]:
        page = self.browser.new_temp_page(url)
        try:
            # Sometimes a consent page appears; try to proceed best-effort.
            try:
                page.wait_for_selector("#search", timeout=timeout_ms)
            except Exception:
                # Try clicking common consent buttons (best effort, multilingual)
                for sel in [
                    "button:has-text('I agree')",
                    "button:has-text('Accept all')",
                    "button:has-text('Accept')",
                    "button:has-text('Ich stimme zu')",
                    "button:has-text('Alle akzeptieren')",
                    "button:has-text('Zustimmen')",
                ]:
                    try:
                        b = page.locator(sel)
                        if b.count() > 0 and b.first.is_enabled():
                            b.first.click()
                            break
                    except Exception:
                        pass
                page.wait_for_selector("#search", timeout=timeout_ms)

            results: List[SearchResult] = []
            links = page.locator("#search a:has(h3)")
            n = min(links.count(), 30)
            for i in range(n):
                if len(results) >= count:
                    break
                a = links.nth(i)
                try:
                    title = a.locator("h3").inner_text(timeout=1000).strip()
                    href = a.get_attribute("href") or ""
                    if not href or href.startswith("/"):
                        continue
                    # Snippet: try nearest result container
                    snippet = ""
                    try:
                        container = a.locator("xpath=ancestor::div[@data-snf]").first
                        snippet = container.inner_text(timeout=1000).strip()
                    except Exception:
                        try:
                            container = a.locator("xpath=ancestor::div[.//h3][1]").first
                            snippet = container.inner_text(timeout=1000).strip()
                        except Exception:
                            snippet = ""
                    snippet = _clip(snippet, 400)
                    results.append(SearchResult(title=_clip(title, 200), url=href, snippet=snippet, source="google_web"))
                except Exception:
                    continue
            return results
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _scrape_brave(self, url: str, count: int, timeout_ms: int) -> List[SearchResult]:
        page = self.browser.new_temp_page(url)
        try:
            # Wait for results area
            try:
                page.wait_for_selector("main", timeout=timeout_ms)
            except Exception:
                pass

            results: List[SearchResult] = []
            # Brave commonly uses result cards with title links; use robust selector
            candidates = [
                "a:has(h3)",
                "a[data-testid*='result']",
                "a[href]:has-text('')",
            ]
            links = None
            for sel in candidates:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        links = loc
                        break
                except Exception:
                    continue
            if links is None:
                return []

            n = min(links.count(), 50)
            for i in range(n):
                if len(results) >= count:
                    break
                a = links.nth(i)
                try:
                    href = a.get_attribute("href") or ""
                    if not href.startswith("http"):
                        continue
                    title = ""
                    try:
                        h3 = a.locator("h3")
                        if h3.count() > 0:
                            title = h3.first.inner_text(timeout=1000).strip()
                        else:
                            title = a.inner_text(timeout=1000).strip()
                    except Exception:
                        title = ""
                    title = _clip(title, 200).strip()
                    if not title:
                        continue
                    snippet = ""
                    try:
                        container = a.locator("xpath=ancestor::*[self::div or self::article][1]").first
                        snippet = _clip(container.inner_text(timeout=1000).strip(), 400)
                    except Exception:
                        snippet = ""
                    results.append(SearchResult(title=title, url=href, snippet=snippet, source="brave_web"))
                except Exception:
                    continue
            return results
        finally:
            try:
                page.close()
            except Exception:
                pass
