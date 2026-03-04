from __future__ import annotations

from unittest.mock import patch

from clausy.websearch.service import WebSearchService


def test_search_provider_argument_with_whitespace_is_normalized() -> None:
    svc = WebSearchService()
    with patch.object(svc, "_search_google", return_value=[]):
        res = svc.search(q="test", provider="  GOOGLE  ")
    assert res["provider"] == "google"


def test_search_provider_argument_blank_falls_back_to_default_provider() -> None:
    with patch.dict("os.environ", {"CLAUSY_WEBSEARCH_PROVIDER": "google"}, clear=False):
        svc = WebSearchService()
    with patch.object(svc, "_search_google", return_value=[]):
        res = svc.search(q="test", provider="   ")
    assert res["provider"] == "google"


def test_search_provider_argument_invalid_token_falls_back_to_default_provider() -> None:
    with patch.dict("os.environ", {"CLAUSY_WEBSEARCH_PROVIDER": "google"}, clear=False):
        svc = WebSearchService()
    with patch.object(svc, "_search_google", return_value=[]):
        res = svc.search(q="test", provider="bing")
    assert res["provider"] == "google"
