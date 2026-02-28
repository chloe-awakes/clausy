import unittest
from unittest.mock import patch

from clausy.filter import FilterConfig, PrefixMatcher, SecretFilter
from clausy.providers.registry import ProviderRegistry
from clausy.server import app


class ProviderRegistryRegressionTests(unittest.TestCase):
    def test_get_defaults_to_chatgpt_when_name_missing(self):
        registry = ProviderRegistry(providers={"chatgpt": object(), "claude": object()})
        self.assertIs(registry.get(""), registry.providers["chatgpt"])
        self.assertIs(registry.get(None), registry.providers["chatgpt"])

    def test_get_raises_for_unknown_provider(self):
        registry = ProviderRegistry(providers={"chatgpt": object()})
        with self.assertRaises(KeyError):
            registry.get("unknown")


class SecretFilterStreamingRegressionTests(unittest.TestCase):
    def test_stream_split_safe_holds_secret_prefix_across_chunks(self):
        sf = SecretFilter(FilterConfig(max_tail=100))
        sf.known = {"sk-abcdefghijklm"}
        sf._compiled = sf._compile_known_regex()
        sf._matcher = PrefixMatcher(sf.known)

        tail, state = sf.stream_init()
        safe1, tail, state = sf.stream_split_safe(tail, state, "hello sk-ab")
        safe2, tail, state = sf.stream_split_safe(tail, state, "cdefghijklm world")
        flushed, _, _ = sf.stream_flush_tail(tail, state)

        self.assertEqual(safe1, "hello ")
        self.assertEqual(safe2 + flushed, "sk-abcdefghijklm world")


class ServerWebSearchRegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("clausy.server.web_search.search")
    def test_web_search_endpoint_returns_results_instead_of_500(self, mock_search):
        mock_search.return_value = {
            "provider": "brave",
            "query": "hello",
            "results": [
                {"title": "Title", "snippet": "Snippet", "url": "https://example.com"}
            ],
        }

        resp = self.client.post("/v1/web_search", json={"q": "hello"})

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["provider"], "brave")
        self.assertEqual(len(body["results"]), 1)


if __name__ == "__main__":
    unittest.main()
