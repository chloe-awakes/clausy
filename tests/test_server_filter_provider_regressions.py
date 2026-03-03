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
        meta = {"turns": server.RESET_TURNS - 1, "summary": "existing", "requests_since_browser_restart": 0}

        server._post_turn_housekeeping("s1", provider, meta)

        mock_get_page.assert_not_called()
        provider.start_new_chat.assert_not_called()
        self.assertEqual(meta["turns"], server.RESET_TURNS - 1)
        self.assertEqual(meta["summary"], "existing")
        self.assertEqual(meta["requests_since_browser_restart"], 1)

    @patch("clausy.server._summarize_session")
    @patch("clausy.server.browser.get_page")
    @patch("clausy.server.browser.restart_session")
    def test_post_turn_housekeeping_summarizes_rotates_and_resets_counter(self, mock_restart, mock_get_page, mock_summarize):
        provider = unittest.mock.Mock()
        page = object()
        mock_get_page.return_value = page
        mock_summarize.return_value = "short summary"
        meta = {"turns": server.RESET_TURNS, "summary": "", "resets_since_restart": 0}

        server._post_turn_housekeeping("s1", provider, meta)

        self.assertEqual(meta["summary"], "short summary")
        self.assertEqual(meta["turns"], 0)
        self.assertEqual(meta["resets_since_restart"], 1)
        provider.start_new_chat.assert_called_once_with(page)
        mock_restart.assert_not_called()

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
        meta = {"turns": server.RESET_TURNS, "summary": "", "resets_since_restart": 0}

        server._post_turn_housekeeping("s1", provider, meta)

        mock_reset_page.assert_called_once_with("s1")
        self.assertEqual(meta["turns"], 0)
        self.assertEqual(meta["resets_since_restart"], 1)


    @patch("clausy.server._summarize_session")
    @patch("clausy.server.browser.get_page")
    @patch("clausy.server.browser.restart_session")
    def test_post_turn_housekeeping_restarts_browser_after_configured_resets(self, mock_restart, mock_get_page, mock_summarize):
        provider = unittest.mock.Mock()
        mock_get_page.return_value = object()
        mock_summarize.return_value = "summary"
        meta = {"turns": server.RESET_TURNS, "summary": "", "resets_since_restart": 1, "requests_since_browser_restart": 0}

        old_threshold = server.BROWSER_RESTART_EVERY_RESETS
        server.BROWSER_RESTART_EVERY_RESETS = 2
        try:
            server._post_turn_housekeeping("s1", provider, meta)
        finally:
            server.BROWSER_RESTART_EVERY_RESETS = old_threshold

        mock_restart.assert_called_once_with("s1")
        self.assertEqual(meta["resets_since_restart"], 0)
        self.assertEqual(meta["requests_since_browser_restart"], 0)

    @patch("clausy.server.browser.get_page")
    @patch("clausy.server.browser.restart_session")
    def test_post_turn_housekeeping_restarts_browser_after_configured_requests(self, mock_restart, mock_get_page):
        provider = unittest.mock.Mock()
        meta = {"turns": 1, "summary": "", "resets_since_restart": 0, "requests_since_browser_restart": 1}

        old_resets = server.BROWSER_RESTART_EVERY_RESETS
        old_requests = server.BROWSER_RESTART_EVERY_REQUESTS
        server.BROWSER_RESTART_EVERY_RESETS = 0
        server.BROWSER_RESTART_EVERY_REQUESTS = 2
        try:
            server._post_turn_housekeeping("s1", provider, meta)
        finally:
            server.BROWSER_RESTART_EVERY_RESETS = old_resets
            server.BROWSER_RESTART_EVERY_REQUESTS = old_requests

        mock_get_page.assert_not_called()
        mock_restart.assert_called_once_with("s1")
        self.assertEqual(meta["requests_since_browser_restart"], 0)


class ModelSwitchingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_provider_candidates_include_primary_then_configured_fallbacks(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        old_chain = server.FALLBACK_CHAIN_RAW
        try:
            server.AUTO_MODEL_SWITCH = True
            server.PROVIDER_NAME = "chatgpt"
            server.FALLBACK_CHAIN_RAW = "grok,claude,chatgpt"
            self.assertEqual(server._provider_candidates("claude-web"), ["claude", "grok", "chatgpt"])
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider
            server.FALLBACK_CHAIN_RAW = old_chain

    def test_provider_candidates_apply_cost_aware_sort_when_enabled(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        old_chain = server.FALLBACK_CHAIN_RAW
        old_cost_aware = server.COST_AWARE_ROUTING
        old_costs_raw = server.PROVIDER_COSTS_RAW
        try:
            server.AUTO_MODEL_SWITCH = False
            server.PROVIDER_NAME = "chatgpt"
            server.FALLBACK_CHAIN_RAW = "grok,claude,openrouter"
            server.COST_AWARE_ROUTING = True
            server.PROVIDER_COSTS_RAW = "chatgpt:5,claude:2,openrouter:1"
            self.assertEqual(server._provider_candidates("chatgpt-web"), ["openrouter", "claude", "chatgpt", "grok"])
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider
            server.FALLBACK_CHAIN_RAW = old_chain
            server.COST_AWARE_ROUTING = old_cost_aware
            server.PROVIDER_COSTS_RAW = old_costs_raw

    def test_provider_candidates_ignore_non_finite_or_negative_costs(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        old_chain = server.FALLBACK_CHAIN_RAW
        old_cost_aware = server.COST_AWARE_ROUTING
        old_costs_raw = server.PROVIDER_COSTS_RAW
        try:
            server.AUTO_MODEL_SWITCH = False
            server.PROVIDER_NAME = "chatgpt"
            server.FALLBACK_CHAIN_RAW = "claude,openrouter,grok"
            server.COST_AWARE_ROUTING = True
            server.PROVIDER_COSTS_RAW = "chatgpt:1,claude:NaN,openrouter:inf,grok:-2"
            self.assertEqual(server._provider_candidates("chatgpt-web"), ["chatgpt", "claude", "openrouter", "grok"])
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider
            server.FALLBACK_CHAIN_RAW = old_chain
            server.COST_AWARE_ROUTING = old_cost_aware
            server.PROVIDER_COSTS_RAW = old_costs_raw

    def test_provider_candidates_fall_back_to_chatgpt_when_config_is_empty(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        old_chain = server.FALLBACK_CHAIN_RAW
        try:
            server.AUTO_MODEL_SWITCH = False
            server.PROVIDER_NAME = ""
            server.FALLBACK_CHAIN_RAW = " , , "
            self.assertEqual(server._provider_candidates(None), ["chatgpt"])
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider
            server.FALLBACK_CHAIN_RAW = old_chain

    def test_provider_candidates_sanitize_invalid_primary_provider_name(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        old_chain = server.FALLBACK_CHAIN_RAW
        try:
            server.AUTO_MODEL_SWITCH = False
            server.PROVIDER_NAME = "chatgpt;rm -rf /"
            server.FALLBACK_CHAIN_RAW = "claude"
            self.assertEqual(server._provider_candidates(None), ["chatgpt", "claude"])
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider
            server.FALLBACK_CHAIN_RAW = old_chain

    def test_provider_candidates_drop_invalid_fallback_tokens(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        old_chain = server.FALLBACK_CHAIN_RAW
        try:
            server.AUTO_MODEL_SWITCH = False
            server.PROVIDER_NAME = "chatgpt"
            server.FALLBACK_CHAIN_RAW = " claude , gpt/4o , ;rm -rf , openrouter , grok:web "
            self.assertEqual(server._provider_candidates(None), ["chatgpt", "claude", "openrouter"])
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider
            server.FALLBACK_CHAIN_RAW = old_chain

    def test_parse_provider_costs_drop_invalid_provider_tokens(self):
        costs = server._parse_provider_costs("chatgpt:1,gpt/4o:0.2,grok:web:0.1,claude:2")
        self.assertEqual(costs, {"chatgpt": 1.0, "claude": 2.0})

    def test_parse_provider_profile_map_drop_invalid_provider_tokens(self):
        profile_map = server._parse_provider_profile_map(
            "chatgpt:./profile-chatgpt,gpt/4o:./profile-openai,grok/web:./profile-grok,claude:./profile-claude"
        )
        self.assertEqual(profile_map, {"chatgpt": "./profile-chatgpt", "claude": "./profile-claude"})

    def test_parse_provider_profile_map_drops_empty_control_and_traversal_like_profiles(self):
        profile_map = server._parse_provider_profile_map(
            "chatgpt:./ok,claude:,grok:\t,poe:../escape,deepseek:..\\escape,gemini:./safe/../../escape,openrouter:./good"
        )
        self.assertEqual(profile_map, {"chatgpt": "./ok", "openrouter": "./good"})


    def test_profile_dir_for_provider_uses_mapping_and_default(self):
        old_default = server.PROFILE_DIR
        old_raw = server.PROFILE_BY_PROVIDER_RAW
        old_rotate_enabled = server.PROFILE_ROTATION_ENABLED
        old_rotate_count = server.PROFILE_ROTATION_COUNT
        try:
            server.PROFILE_DIR = "./profile-default"
            server.PROFILE_BY_PROVIDER_RAW = "claude:./profile-claude,chatgpt:./profile-chatgpt"
            server.PROFILE_ROTATION_ENABLED = False
            server.PROFILE_ROTATION_COUNT = 0
            self.assertEqual(server._profile_dir_for_provider("claude"), "./profile-claude")
            self.assertEqual(server._profile_dir_for_provider("grok"), "./profile-default")
        finally:
            server.PROFILE_DIR = old_default
            server.PROFILE_BY_PROVIDER_RAW = old_raw
            server.PROFILE_ROTATION_ENABLED = old_rotate_enabled
            server.PROFILE_ROTATION_COUNT = old_rotate_count

    def test_profile_dir_for_provider_rotates_when_enabled(self):
        old_default = server.PROFILE_DIR
        old_raw = server.PROFILE_BY_PROVIDER_RAW
        old_rotate_enabled = server.PROFILE_ROTATION_ENABLED
        old_rotate_count = server.PROFILE_ROTATION_COUNT
        old_counter = dict(server._profile_rotation_counter)
        try:
            server.PROFILE_DIR = "./profile-default"
            server.PROFILE_BY_PROVIDER_RAW = "claude:./profile-claude"
            server.PROFILE_ROTATION_ENABLED = True
            server.PROFILE_ROTATION_COUNT = 2
            server._profile_rotation_counter.clear()
            self.assertEqual(server._profile_dir_for_provider("claude"), "./profile-claude-rot1")
            self.assertEqual(server._profile_dir_for_provider("claude"), "./profile-claude-rot2")
            self.assertEqual(server._profile_dir_for_provider("claude"), "./profile-claude-rot1")
        finally:
            server.PROFILE_DIR = old_default
            server.PROFILE_BY_PROVIDER_RAW = old_raw
            server.PROFILE_ROTATION_ENABLED = old_rotate_enabled
            server.PROFILE_ROTATION_COUNT = old_rotate_count
            server._profile_rotation_counter.clear()
            server._profile_rotation_counter.update(old_counter)

    @patch("clausy.server.browser.switch_profile")
    @patch("clausy.server.registry.get")
    @patch("clausy.server.browser.get_page")
    def test_non_stream_switches_browser_profile_for_selected_provider(self, mock_get_page, mock_registry_get, mock_switch_profile):
        provider = unittest.mock.Mock()
        provider.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"
        mock_registry_get.return_value = provider
        mock_get_page.return_value = object()
        mock_switch_profile.return_value = True

        with patch("clausy.server.parse_or_repair_output", return_value={
            "choices": [{"message": {"content": "ok", "tool_calls": []}, "finish_reason": "stop"}]
        }),             patch("clausy.server._sanitize_parsed_response", side_effect=lambda parsed: parsed),             patch("clausy.server._get_meta", return_value={"turns": 0, "summary": ""}),             patch("clausy.server._post_turn_housekeeping"),             patch("clausy.server._profile_dir_for_provider", return_value="./profile-claude"):
            resp = self.client.post(
                "/v1/chat/completions",
                json={"model": "claude-web", "stream": False, "messages": [{"role": "user", "content": "hello"}]},
                headers={"X-Clausy-Session": "switch-profile"},
            )

        self.assertEqual(resp.status_code, 200)
        mock_switch_profile.assert_called()

    def test_resolve_provider_name_uses_model_mapping_when_enabled(self):
        old_auto = server.AUTO_MODEL_SWITCH
        old_provider = server.PROVIDER_NAME
        try:
            server.AUTO_MODEL_SWITCH = True
            server.PROVIDER_NAME = "chatgpt"
            self.assertEqual(server._resolve_provider_name("claude-web"), "claude")
            self.assertEqual(server._resolve_provider_name("openai-api"), "openai")
        finally:
            server.AUTO_MODEL_SWITCH = old_auto
            server.PROVIDER_NAME = old_provider

    def test_non_stream_uses_model_selected_provider(self):
        provider = unittest.mock.Mock()
        provider.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"

        with patch("clausy.server.registry.get", return_value=provider) as mock_registry_get, \
            patch("clausy.server.browser.get_page", return_value=object()), \
            patch("clausy.server.parse_or_repair_output", return_value={
                "choices": [{"message": {"content": "ok", "tool_calls": []}, "finish_reason": "stop"}]
            }), \
            patch("clausy.server._sanitize_parsed_response", side_effect=lambda parsed: parsed), \
            patch("clausy.server._get_meta", return_value={"turns": 0, "summary": ""}), \
            patch("clausy.server._post_turn_housekeeping"):
            old_auto = server.AUTO_MODEL_SWITCH
            old_provider = server.PROVIDER_NAME
            try:
                server.AUTO_MODEL_SWITCH = True
                server.PROVIDER_NAME = "chatgpt"
                resp = self.client.post(
                    "/v1/chat/completions",
                    json={"model": "claude-web", "stream": False, "messages": [{"role": "user", "content": "hello"}]},
                    headers={"X-Clausy-Session": "switch1"},
                )
            finally:
                server.AUTO_MODEL_SWITCH = old_auto
                server.PROVIDER_NAME = old_provider

        self.assertEqual(resp.status_code, 200)
        mock_registry_get.assert_called_with("claude")

    def test_non_stream_falls_back_to_secondary_web_provider_on_primary_failure(self):
        broken = unittest.mock.Mock()
        broken.ensure_ready.side_effect = RuntimeError("primary down")
        fallback = unittest.mock.Mock()
        fallback.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"

        def _get_provider(name):
            return {"chatgpt": broken, "claude": fallback}[name]

        with patch("clausy.server.registry.get", side_effect=_get_provider), \
            patch("clausy.server.browser.get_page", return_value=object()), \
            patch("clausy.server.parse_or_repair_output", return_value={
                "choices": [{"message": {"content": "ok", "tool_calls": []}, "finish_reason": "stop"}]
            }), \
            patch("clausy.server._sanitize_parsed_response", side_effect=lambda parsed: parsed), \
            patch("clausy.server._get_meta", return_value={"turns": 0, "summary": ""}), \
            patch("clausy.server._post_turn_housekeeping"):
            old_auto = server.AUTO_MODEL_SWITCH
            old_provider = server.PROVIDER_NAME
            old_chain = server.FALLBACK_CHAIN_RAW
            try:
                server.AUTO_MODEL_SWITCH = False
                server.PROVIDER_NAME = "chatgpt"
                server.FALLBACK_CHAIN_RAW = "claude"
                resp = self.client.post(
                    "/v1/chat/completions",
                    json={"model": "chatgpt-web", "stream": False, "messages": [{"role": "user", "content": "hello"}]},
                    headers={"X-Clausy-Session": "switch2"},
                )
            finally:
                server.AUTO_MODEL_SWITCH = old_auto
                server.PROVIDER_NAME = old_provider
                server.FALLBACK_CHAIN_RAW = old_chain

        self.assertEqual(resp.status_code, 200)
        broken.ensure_ready.assert_called()
        fallback.ensure_ready.assert_called()

    def test_non_stream_falls_back_from_web_to_api_provider_on_web_failure(self):
        broken_web = unittest.mock.Mock()
        broken_web.ensure_ready.side_effect = RuntimeError("web down")

        api_provider = unittest.mock.Mock()
        api_provider.chat_completion.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "from api fallback"}, "finish_reason": "stop"}]
        }

        with patch("clausy.server.registry.get", return_value=broken_web), \
            patch("clausy.server.browser.get_page", return_value=object()), \
            patch("clausy.server.api_router.get", return_value=api_provider), \
            patch("clausy.server._sanitize_parsed_response", side_effect=lambda parsed: parsed), \
            patch("clausy.server._get_meta", return_value={"turns": 0, "summary": ""}), \
            patch("clausy.server._post_turn_housekeeping"):
            old_auto = server.AUTO_MODEL_SWITCH
            old_provider = server.PROVIDER_NAME
            old_chain = server.FALLBACK_CHAIN_RAW
            try:
                server.AUTO_MODEL_SWITCH = False
                server.PROVIDER_NAME = "chatgpt"
                server.FALLBACK_CHAIN_RAW = "openai"
                resp = self.client.post(
                    "/v1/chat/completions",
                    json={"model": "chatgpt-web", "stream": False, "messages": [{"role": "user", "content": "hello"}]},
                    headers={"X-Clausy-Session": "switch3"},
                )
            finally:
                server.AUTO_MODEL_SWITCH = old_auto
                server.PROVIDER_NAME = old_provider
                server.FALLBACK_CHAIN_RAW = old_chain

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["choices"][0]["message"]["content"], "from api fallback")
        broken_web.ensure_ready.assert_called()
        api_provider.chat_completion.assert_called_once()

    def test_non_stream_falls_back_from_api_to_web_provider_on_api_failure(self):
        broken_api = unittest.mock.Mock()
        broken_api.chat_completion.side_effect = RuntimeError("api down")

        web_provider = unittest.mock.Mock()
        web_provider.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"

        with patch("clausy.server.api_router.get", return_value=broken_api), \
            patch("clausy.server.registry.get", return_value=web_provider), \
            patch("clausy.server.browser.get_page", return_value=object()), \
            patch("clausy.server.parse_or_repair_output", return_value={
                "choices": [{"message": {"content": "from web fallback", "tool_calls": []}, "finish_reason": "stop"}]
            }), \
            patch("clausy.server._sanitize_parsed_response", side_effect=lambda parsed: parsed), \
            patch("clausy.server._get_meta", return_value={"turns": 0, "summary": ""}), \
            patch("clausy.server._post_turn_housekeeping"):
            old_auto = server.AUTO_MODEL_SWITCH
            old_provider = server.PROVIDER_NAME
            old_chain = server.FALLBACK_CHAIN_RAW
            try:
                server.AUTO_MODEL_SWITCH = False
                server.PROVIDER_NAME = "openai"
                server.FALLBACK_CHAIN_RAW = "chatgpt"
                resp = self.client.post(
                    "/v1/chat/completions",
                    json={"model": "openai-api", "stream": False, "messages": [{"role": "user", "content": "hello"}]},
                    headers={"X-Clausy-Session": "switch4"},
                )
            finally:
                server.AUTO_MODEL_SWITCH = old_auto
                server.PROVIDER_NAME = old_provider
                server.FALLBACK_CHAIN_RAW = old_chain

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["choices"][0]["message"]["content"], "from web fallback")
        broken_api.chat_completion.assert_called_once()
        web_provider.ensure_ready.assert_called()


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
        self.assertTrue(events[0]["detail"].get("request_id"))
        self.assertEqual(events[0]["detail"].get("request_id"), events[1]["detail"].get("request_id"))

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

    def test_tool_chains_endpoint_groups_events_by_request_id(self):
        server._event_log.clear()
        server._event_seq = 0

        server._log_event(session_id="s1", event_type="request", detail={"request_id": "req_a"})
        server._log_event(session_id="s1", event_type="tool_call", detail={"request_id": "req_a", "count": 1})
        server._log_event(session_id="s1", event_type="response", detail={"request_id": "req_a"})
        server._log_event(session_id="s1", event_type="request", detail={"request_id": "req_b"})

        resp = self.client.get("/v1/tool_chains?session_id=s1")
        self.assertEqual(resp.status_code, 200)

        chains = resp.get_json()["data"]
        self.assertEqual(len(chains), 2)
        self.assertEqual(chains[0]["request_id"], "req_a")
        self.assertEqual([e["type"] for e in chains[0]["events"]], ["request", "tool_call", "response"])
        self.assertEqual(chains[1]["request_id"], "req_b")

    def test_tool_traces_endpoint_expands_tool_call_details(self):
        server._event_log.clear()
        server._event_seq = 0

        server._log_event(session_id="s1", event_type="request", detail={"request_id": "req_a"})
        server._log_event(
            session_id="s1",
            event_type="tool_call",
            detail={
                "request_id": "req_a",
                "count": 2,
                "calls": [
                    {"id": "call_1", "name": "exec", "arguments_excerpt": '{"command":"ls -la"}'},
                    {"id": "call_2", "name": "web_search", "arguments_excerpt": '{"query":"status"}'},
                ],
            },
        )

        resp = self.client.get("/v1/tool_traces?session_id=s1")
        self.assertEqual(resp.status_code, 200)

        traces = resp.get_json()["data"]
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["request_id"], "req_a")
        self.assertEqual(traces[0]["tool_count"], 2)
        self.assertEqual([c["name"] for c in traces[0]["calls"]], ["exec", "web_search"])

    def test_tool_call_event_contains_structured_calls_for_non_stream(self):
        provider = unittest.mock.Mock()
        provider.get_last_assistant_text.return_value = "<<<CONTENT>>>\nignored"

        with patch("clausy.server.registry.get", return_value=provider), \
            patch("clausy.server.browser.get_page", return_value=object()), \
            patch("clausy.server.parse_or_repair_output", return_value={
                "choices": [{
                    "message": {
                        "content": "ok",
                        "tool_calls": [
                            {
                                "id": "call_a",
                                "type": "function",
                                "function": {"name": "exec", "arguments": '{"command":"pwd"}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }]
            }), \
            patch("clausy.server._sanitize_parsed_response", side_effect=lambda parsed: parsed), \
            patch("clausy.server._get_meta", return_value={"turns": 0, "summary": ""}), \
            patch("clausy.server._post_turn_housekeeping"):
            server._event_log.clear()
            server._event_seq = 0
            resp = self.client.post(
                "/v1/chat/completions",
                json={"model": "chatgpt-web", "stream": False, "messages": [{"role": "user", "content": "run"}]},
                headers={"X-Clausy-Session": "trace1"},
            )

        self.assertEqual(resp.status_code, 200)
        events = self.client.get("/v1/events?session_id=trace1").get_json()["data"]
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0]["detail"].get("count"), 1)
        self.assertEqual(tool_events[0]["detail"].get("calls", [])[0].get("name"), "exec")


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
