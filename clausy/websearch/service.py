from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

ProviderName = Literal["brave", "google"]

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str  # provider

def _clip(s: str, n: int = 400) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[:n] + "…")

class WebSearchError(RuntimeError):
    pass

class WebSearchService:
    """Simple web-search wrapper with Brave Search API and Google Custom Search JSON API.

    This module uses official HTTP APIs (no scraping).

    Env vars:
      - CLAUSY_WEBSEARCH_PROVIDER=brave|google (default: brave)
      - BRAVE_SEARCH_API_KEY (required for brave)
      - GOOGLE_CSE_API_KEY (required for google)
      - GOOGLE_CSE_CX (required for google)
    """

    def __init__(self) -> None:
        self.default_provider: ProviderName = os.environ.get("CLAUSY_WEBSEARCH_PROVIDER", "brave").strip().lower()  # type: ignore[assignment]
        if self.default_provider not in ("brave", "google"):
            self.default_provider = "brave"

    def search(
        self,
        q: str,
        provider: Optional[ProviderName] = None,
        count: int = 5,
        offset: int = 0,
        safe: str = "moderate",
        lang: Optional[str] = None,
        country: Optional[str] = None,
        timeout_s: float = 20.0,
    ) -> Dict[str, Any]:
        prov: ProviderName = (provider or self.default_provider)  # type: ignore[assignment]
        prov = prov.lower()  # type: ignore[assignment]
        count = max(1, min(int(count), 10))

        if prov == "brave":
            results = self._search_brave(q=q, count=count, offset=offset, safe=safe, lang=lang, country=country, timeout_s=timeout_s)
        elif prov == "google":
            results = self._search_google(q=q, count=count, offset=offset, safe=safe, lang=lang, country=country, timeout_s=timeout_s)
        else:
            raise WebSearchError(f"Unknown provider: {prov}")

        return {
            "provider": prov,
            "query": q,
            "count": count,
            "offset": offset,
            "safe": safe,
            "results": [r.__dict__ for r in results],
        }

    def _search_brave(
        self,
        q: str,
        count: int,
        offset: int,
        safe: str,
        lang: Optional[str],
        country: Optional[str],
        timeout_s: float,
    ) -> List[SearchResult]:
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            raise WebSearchError("BRAVE_SEARCH_API_KEY is not set")

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params: Dict[str, Any] = {"q": q, "count": count, "offset": max(0, int(offset)), "safesearch": safe}
        if lang:
            params["search_lang"] = lang
        if country:
            # Brave uses country in request headers for location; keep it simple: set a query param if present.
            # (Their docs mention location hints via headers; this is a minimal implementation.)
            params["country"] = country

        resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
        if resp.status_code != 200:
            raise WebSearchError(f"Brave search failed: HTTP {resp.status_code}: {_clip(resp.text, 500)}")

        data = resp.json()
        items = []
        web = (data or {}).get("web", {}) or {}
        for it in (web.get("results") or [])[:count]:
            title = (it.get("title") or "").strip()
            u = (it.get("url") or "").strip()
            snippet = (it.get("description") or it.get("snippet") or "").strip()
            if title and u:
                items.append(SearchResult(title=title, url=u, snippet=_clip(snippet), source="brave"))
        return items

    def _search_google(
        self,
        q: str,
        count: int,
        offset: int,
        safe: str,
        lang: Optional[str],
        country: Optional[str],
        timeout_s: float,
    ) -> List[SearchResult]:
        api_key = os.environ.get("GOOGLE_CSE_API_KEY", "").strip()
        cx = os.environ.get("GOOGLE_CSE_CX", "").strip()
        if not api_key or not cx:
            raise WebSearchError("GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX must be set for provider=google")

        url = "https://www.googleapis.com/customsearch/v1"
        # Google start is 1-based; each page is up to 10
        start = max(1, int(offset) + 1)
        params: Dict[str, Any] = {
            "key": api_key,
            "cx": cx,
            "q": q,
            "num": count,  # 1..10
            "start": start,
        }
        # Google's safe: off|active
        if safe and safe.lower() in ("strict", "moderate", "active", "on", "true", "1"):
            params["safe"] = "active"
        if lang:
            params["lr"] = f"lang_{lang}"
        if country:
            params["gl"] = country

        resp = requests.get(url, params=params, timeout=timeout_s)
        if resp.status_code != 200:
            raise WebSearchError(f"Google search failed: HTTP {resp.status_code}: {_clip(resp.text, 500)}")

        data = resp.json()
        items = []
        for it in (data or {}).get("items", [])[:count]:
            title = (it.get("title") or "").strip()
            u = (it.get("link") or "").strip()
            snippet = (it.get("snippet") or "").strip()
            if title and u:
                items.append(SearchResult(title=title, url=u, snippet=_clip(snippet), source="google"))
        return items
