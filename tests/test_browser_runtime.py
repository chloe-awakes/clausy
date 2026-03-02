import os
import unittest
from unittest.mock import Mock, patch

from clausy.browser import BrowserPool
from clausy.browser_runtime import BrowserRuntimeConfig, build_browser_launch_command, detect_browser_binary


class BrowserRuntimeDetectionTests(unittest.TestCase):
    def test_detect_browser_binary_prefers_env_override(self):
        with patch.dict(os.environ, {"CLAUSY_BROWSER_BINARY": "/custom/chrome"}, clear=False):
            got = detect_browser_binary(which=lambda _: None, platform="linux", playwright_binary=None)
        self.assertEqual(got, "/custom/chrome")

    def test_detect_browser_binary_uses_which_candidates(self):
        with patch.dict(os.environ, {}, clear=False):
            got = detect_browser_binary(
                which=lambda name: "/usr/bin/chromium" if name == "chromium" else None,
                platform="linux",
                playwright_binary=None,
            )
        self.assertEqual(got, "/usr/bin/chromium")

    def test_build_browser_launch_command_contains_cdp_and_profile(self):
        cfg = BrowserRuntimeConfig(
            cdp_host="127.0.0.1",
            cdp_port=9222,
            profile_dir="/tmp/profile",
            headless=False,
            extra_args=["--disable-gpu"],
        )
        cmd = build_browser_launch_command("/usr/bin/chromium", cfg)
        self.assertEqual(cmd[0], "/usr/bin/chromium")
        self.assertIn("--remote-debugging-port=9222", cmd)
        self.assertIn("--user-data-dir=/tmp/profile", cmd)
        self.assertIn("--disable-gpu", cmd)


class BrowserPoolBootstrapTests(unittest.TestCase):
    @patch("clausy.browser.subprocess.Popen")
    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    @patch("clausy.browser.BrowserPool._bootstrap_browser")
    @patch("clausy.browser.sync_playwright")
    def test_start_fails_with_actionable_error_when_bootstrap_disabled(
        self,
        mock_sync_playwright,
        mock_bootstrap,
        mock_connect,
        mock_popen,
    ):
        pw = Mock()
        pw.chromium = Mock()
        mock_sync_playwright.return_value.start.return_value = pw
        mock_connect.side_effect = RuntimeError("cdp unavailable")

        with patch.dict(os.environ, {"CLAUSY_BROWSER_BOOTSTRAP": "never"}, clear=False):
            pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile", home_url="https://chatgpt.com")
            with self.assertRaises(RuntimeError) as ctx:
                pool.start()

        self.assertIn("bootstrap is disabled", str(ctx.exception).lower())
        mock_bootstrap.assert_not_called()
        mock_popen.assert_not_called()

    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    @patch("clausy.browser.BrowserPool._bootstrap_browser")
    @patch("clausy.browser.sync_playwright")
    def test_start_bootstraps_and_retries_cdp(
        self,
        mock_sync_playwright,
        mock_bootstrap,
        mock_connect,
    ):
        pw = Mock()
        browser = Mock()
        browser.contexts = []
        browser.new_context.return_value = Mock()
        pw.chromium = Mock()
        mock_sync_playwright.return_value.start.return_value = pw
        mock_connect.side_effect = [RuntimeError("first"), browser]

        with patch.dict(os.environ, {"CLAUSY_BROWSER_BOOTSTRAP": "always"}, clear=False):
            pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile", home_url="https://chatgpt.com")
            pool.start()

        mock_bootstrap.assert_called_once()
        self.assertEqual(mock_connect.call_count, 2)


class BrowserPoolProfileSwitchTests(unittest.TestCase):
    @patch("clausy.browser.BrowserPool.start")
    def test_switch_profile_restarts_when_profile_changes(self, mock_start):
        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile-a", home_url="https://chatgpt.com")
        pool._browser = Mock()
        pool._pw = Mock()
        changed = pool.switch_profile("./profile-b")
        self.assertTrue(changed)
        self.assertTrue(pool.profile_dir.endswith("profile-b"))
        mock_start.assert_called_once()

    @patch("clausy.browser.BrowserPool.start")
    def test_switch_profile_noop_when_same_profile(self, mock_start):
        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile-a", home_url="https://chatgpt.com")
        changed = pool.switch_profile("./profile-a")
        self.assertFalse(changed)
        mock_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
