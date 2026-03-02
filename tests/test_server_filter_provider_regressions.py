import unittest
from unittest.mock import patch

from clausy.filter import FilterConfig, PrefixMatcher, SecretFilter
from clausy.providers.registry import ProviderRegistry
import clausy.server as server
from clausy.server import app


class ProviderRegistryRegressionTests(unittest.TestCase):
    def test_get_defaults_to_chatgpt_when_name_missing(self):
        registry = ProviderRegistry(providers={"chatgpt": object(), "claude": object(), "grok": object()})
        self.assertIs(registry.get(""), registry.providers["chatgpt"])
        self.assertIs(registry.get(None), registry.providers["chatgpt"])

    def test_get_raises_for_unknown_provider(self):
        registry = ProviderRegistry(providers={"chatgpt": object()})
        with self.assertRaises(KeyError):
            registry.get("unknown")

    def test_default_registry_includes_grok_poe_and_deepseek_providers(self):
        registry = ProviderRegistry.default(chatgpt_url="https://chatgpt.com", claude_url="https://claude.ai", grok_url="https://grok.com")
        self.assertIn("grok", registry.providers)
        self.assertIn("poe", registry.providers)
        self.assertIn("deepseek", registry.providers)


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

    @patch("clausy.server.web_search.search")
    @patch("clausy.server.web_search_browser.search")
    def test_web_search_endpoint_browser_mode_uses_browser_service(self, mock_browser_search, mock_api_search):
        mock_browser_search.return_value = [
            unittest.mock.Mock(title="T", snippet="S", url="https://example.com", source="google_web")
        ]

        resp = self.client.post(
            "/v1/web_search",
            json={"q": "hello", "mode": "browser", "provider": "google_web", "count": 1},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["provider"], "google_web")
        self.assertEqual(len(body["results"]), 1)
        mock_browser_search.assert_called_once()
        mock_api_search.assert_not_called()

    def test_web_search_endpoint_browser_mode_rejects_invalid_provider(self):
        resp = self.client.post(
            "/v1/web_search",
            json={"q": "hello", "mode": "browser", "provider": "brave"},
        )

        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertEqual(body["error"]["type"], "invalid_request_error")


class ConversationManagementRegressionTests(unittest.TestCase):
    @patch("clausy.server.browser.get_page")
    def test_post_turn_housekeeping_skips_below_threshold(self, mock_get_page):
        provider = unittest.mock.Mock()
        meta = {"turns": server.RESET_TURNS - 1, "summary": "existing"}

        server._post_turn_housekeeping("s1", provider, meta)

        mock_get_page.assert_not_called()
        provider.start_new_chat.assert_not_called()
        self.assertEqual(meta["turns"], server.RESET_TURNS - 1)
        self.assertEqual(meta["summary"], "existing")

    @patch("clausy.server._summarize_session")
    @patch("clausy.server.browser.get_page")
    def test_post_turn_housekeeping_summarizes_rotates_and_resets_counter(self, mock_get_page, mock_summarize):
        provider = unittest.mock.Mock()
        page = object()
        mock_get_page.return_value = page
        mock_summarize.return_value = "short summary"
        meta = {"turns": server.RESET_TURNS, "summary": ""}

        server._post_turn_housekeeping("s1", provider, meta)

        self.assertEqual(meta["summary"], "short summary")
        self.assertEqual(meta["turns"], 0)
        provider.start_new_chat.assert_called_once_with(page)

    @patch("clausy.server._summarize_session")
    @patch("clausy.server.browser.reset_page")
    @patch("clausy.server.browser.get_page")
    def test_post_turn_housekeeping_falls_back_to_reset_page_when_new_chat_fails(
        self,
        mock_get_page,
        mock_reset_page,
        mock_summarize,
    ):
        provider = unittest.mock.Mock()
        page = object()
        mock_get_page.return_value = page
        mock_summarize.return_value = "summary"
        provider.start_new_chat.side_effect = RuntimeError("ui changed")
        meta = {"turns": server.RESET_TURNS, "summary": ""}

        server._post_turn_housekeeping("s1", provider, meta)

        mock_reset_page.assert_called_once_with("s1")
        self.assertEqual(meta["turns"], 0)


class EventLogRegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("clausy.server._post_turn_housekeeping")
    @patch("clausy.server._get_meta")
    @patch("clausy.server._sanitize_parsed_response")
    @patch("clausy.server.parse_or_repair_output")
    @patch("clausy.server.browser.get_page")
    @patch("clausy.server.registry.get")
    def test_chat_completion_appends_request_and_response_events(
        self,
        mock_registry_get,
        mock_get_page,
        mock_parse,
        mock_sanitize,
        mock_get_meta,
        mock_housekeeping,
    ):
        provider = unittest.mock.Mock()
        provider.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"
        mock_registry_get.return_value = provider
        mock_get_page.return_value = object()
        mock_get_meta.return_value = {"turns": 0, "summary": ""}
        mock_parse.return_value = {
            "choices": [{"message": {"content": "ok", "tool_calls": []}, "finish_reason": "stop"}]
        }
        mock_sanitize.side_effect = lambda parsed: parsed

        server._event_log.clear()
        server._event_seq = 0

        resp = self.client.post(
            "/v1/chat/completions",
            json={"model": "chatgpt-web", "stream": False, "messages": [{"role": "user", "content": "hello"}]},
            headers={"X-Clausy-Session": "ev1"},
        )

        self.assertEqual(resp.status_code, 200)

        ev_resp = self.client.get("/v1/events?session_id=ev1")
        self.assertEqual(ev_resp.status_code, 200)
        events = ev_resp.get_json()["data"]
        self.assertEqual([e["type"] for e in events], ["request", "response"])

    def test_events_endpoint_supports_since_id_and_limit(self):
        server._event_log.clear()
        server._event_seq = 0
        server._log_event(session_id="s1", event_type="request", detail={})
        server._log_event(session_id="s1", event_type="response", detail={})
        server._log_event(session_id="s1", event_type="response", detail={})

        resp = self.client.get("/v1/events?since_id=1&limit=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], 3)


class KeywordAlertsIntegrationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("clausy.server._trigger_keyword_alerts")
    @patch("clausy.server._post_turn_housekeeping")
    @patch("clausy.server._get_meta")
    @patch("clausy.server._sanitize_parsed_response")
    @patch("clausy.server.parse_or_repair_output")
    @patch("clausy.server.browser.get_page")
    @patch("clausy.server.registry.get")
    def test_non_stream_emits_request_response_and_tool_alerts(
        self,
        mock_registry_get,
        mock_get_page,
        mock_parse,
        mock_sanitize,
        mock_get_meta,
        mock_housekeeping,
        mock_trigger,
    ):
        provider = unittest.mock.Mock()
        provider.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"
        mock_registry_get.return_value = provider
        mock_get_page.return_value = object()
        mock_get_meta.return_value = {"turns": 0, "summary": ""}
        mock_parse.return_value = {
            "choices": [{"message": {"content": "contains secret", "tool_calls": [{"id": "1"}]}, "finish_reason": "tool_calls"}]
        }
        mock_sanitize.side_effect = lambda parsed: parsed

        resp = self.client.post(
            "/v1/chat/completions",
            json={"model": "chatgpt-web", "stream": False, "messages": [{"role": "user", "content": "my token here"}]},
            headers={"X-Clausy-Session": "s1"},
        )

        self.assertEqual(resp.status_code, 200)
        dirs = [c.kwargs.get("direction") for c in mock_trigger.call_args_list]
        self.assertIn("request", dirs)
        self.assertIn("response", dirs)
        self.assertIn("tool_call", dirs)

    def test_trigger_alert_failures_do_not_raise(self):
        orig_cfg = server.keyword_alert_config
        orig_detector = server.keyword_detector
        orig_limiter = server.alert_rate_limiter
        orig_dispatcher = server.alert_dispatcher
        try:
            server.keyword_alert_config = unittest.mock.Mock(enabled=True)
            server.keyword_detector = unittest.mock.Mock(match=lambda _t: ["token"])
            server.alert_rate_limiter = unittest.mock.Mock(should_send=lambda *_a, **_k: True)

            class _Bad:
                def send(self, _alert):
                    raise RuntimeError("fail")

            server.alert_dispatcher = _Bad()
            server._trigger_keyword_alerts(session_id="s1", provider="chatgpt", direction="request", text="token")
        finally:
            server.keyword_alert_config = orig_cfg
            server.keyword_detector = orig_detector
            server.alert_rate_limiter = orig_limiter
            server.alert_dispatcher = orig_dispatcher


if __name__ == "__main__":
    unittest.main()
