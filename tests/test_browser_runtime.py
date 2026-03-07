import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clausy.browser import BrowserPool
from clausy.browser_runtime import (
    BrowserRuntimeConfig,
    build_browser_launch_command,
    detect_browser_binary,
    parse_browser_extra_args,
)


class BrowserRuntimeDetectionTests(unittest.TestCase):
    @patch("clausy.browser_runtime.os.path.isfile", return_value=True)
    @patch("clausy.browser_runtime.os.access", return_value=True)
    def test_detect_browser_binary_prefers_env_override(self, _mock_access, _mock_isfile):
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

    def test_detect_browser_binary_rejects_unsafe_env_override_and_falls_back(self):
        with patch.dict(os.environ, {"CLAUSY_BROWSER_BINARY": "../escape/chrome"}, clear=False):
            got = detect_browser_binary(
                which=lambda name: "/usr/bin/chromium" if name == "chromium" else None,
                platform="linux",
                playwright_binary=None,
            )
        self.assertEqual(got, "/usr/bin/chromium")

    @patch("clausy.browser_runtime.os.path.isfile")
    @patch("clausy.browser_runtime.os.access")
    def test_detect_browser_binary_rejects_non_executable_env_override_and_falls_back(self, mock_access, mock_isfile):
        mock_isfile.return_value = False
        mock_access.return_value = False
        with patch.dict(os.environ, {"CLAUSY_BROWSER_BINARY": "/missing/chrome"}, clear=False):
            got = detect_browser_binary(
                which=lambda name: "/usr/bin/chromium" if name == "chromium" else None,
                platform="linux",
                playwright_binary=None,
            )
        self.assertEqual(got, "/usr/bin/chromium")

    def test_detect_browser_binary_ignores_unsafe_playwright_binary_and_falls_back(self):
        with patch.dict(os.environ, {}, clear=False):
            got = detect_browser_binary(
                which=lambda name: "/usr/bin/chromium" if name == "chromium" else None,
                platform="linux",
                playwright_binary="../pw/chrome",
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


class BrowserRuntimeExtraArgsTests(unittest.TestCase):
    def test_parse_browser_extra_args_splits_valid_flags(self):
        got = parse_browser_extra_args("--window-size=1280,720 --lang=en-US")
        self.assertEqual(got, ["--window-size=1280,720", "--lang=en-US"])

    def test_parse_browser_extra_args_rejects_shellish_payload_and_falls_back_empty(self):
        got = parse_browser_extra_args("--lang=en-US ; rm -rf /")
        self.assertEqual(got, [])

    def test_parse_browser_extra_args_rejects_disallowed_flag_and_falls_back_empty(self):
        got = parse_browser_extra_args("--user-data-dir=/tmp/evil --lang=en-US")
        self.assertEqual(got, [])


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


class BrowserPoolCdpTimeoutParsingTests(unittest.TestCase):
    @patch("clausy.browser.BrowserPool._wait_for_cdp")
    @patch("clausy.browser.BrowserPool._bootstrap_browser")
    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    @patch("clausy.browser.sync_playwright")
    def test_start_uses_valid_in_range_timeout_value(
        self,
        mock_sync_playwright,
        mock_connect,
        mock_bootstrap,
        mock_wait_for_cdp,
    ):
        pw = Mock()
        browser = Mock()
        browser.contexts = []
        browser.new_context.return_value = Mock()
        pw.chromium = Mock()
        mock_sync_playwright.return_value.start.return_value = pw

        mock_connect.side_effect = RuntimeError("first")
        mock_wait_for_cdp.return_value = browser

        with patch.dict(
            os.environ,
            {"CLAUSY_BROWSER_BOOTSTRAP": "always", "CLAUSY_CDP_CONNECT_TIMEOUT": "25"},
            clear=False,
        ):
            pool = BrowserPool(
                cdp_host="127.0.0.1",
                cdp_port=9200,
                profile_dir="./profile",
                home_url="https://chatgpt.com",
            )
            pool.start()

        mock_bootstrap.assert_called_once()
        mock_wait_for_cdp.assert_called_once_with(timeout_s=25.0)

    @patch("clausy.browser.BrowserPool._wait_for_cdp")
    @patch("clausy.browser.BrowserPool._bootstrap_browser")
    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    @patch("clausy.browser.sync_playwright")
    def test_start_accepts_timeout_range_boundaries(
        self,
        mock_sync_playwright,
        mock_connect,
        mock_bootstrap,
        mock_wait_for_cdp,
    ):
        pw = Mock()
        browser = Mock()
        browser.contexts = []
        browser.new_context.return_value = Mock()
        pw.chromium = Mock()
        mock_sync_playwright.return_value.start.return_value = pw

        valid_values = ["0.1", "300"]

        for valid in valid_values:
            mock_connect.reset_mock()
            mock_wait_for_cdp.reset_mock()
            mock_connect.side_effect = RuntimeError("first")
            mock_wait_for_cdp.return_value = browser

            with self.subTest(timeout=valid):
                with patch.dict(
                    os.environ,
                    {"CLAUSY_BROWSER_BOOTSTRAP": "always", "CLAUSY_CDP_CONNECT_TIMEOUT": valid},
                    clear=False,
                ):
                    pool = BrowserPool(
                        cdp_host="127.0.0.1",
                        cdp_port=9200,
                        profile_dir="./profile",
                        home_url="https://chatgpt.com",
                    )
                    pool.start()

                mock_bootstrap.assert_called()
                mock_wait_for_cdp.assert_called_once_with(timeout_s=float(valid))

    @patch("clausy.browser.BrowserPool._wait_for_cdp")
    @patch("clausy.browser.BrowserPool._bootstrap_browser")
    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    @patch("clausy.browser.sync_playwright")
    def test_start_rejects_invalid_timeout_values_and_falls_back_to_default(
        self,
        mock_sync_playwright,
        mock_connect,
        mock_bootstrap,
        mock_wait_for_cdp,
    ):
        pw = Mock()
        browser = Mock()
        browser.contexts = []
        browser.new_context.return_value = Mock()
        pw.chromium = Mock()
        mock_sync_playwright.return_value.start.return_value = pw

        invalid_values = ["abc", "-1", "0", "999999", "0.099", "300.001"]

        for invalid in invalid_values:
            mock_connect.reset_mock()
            mock_wait_for_cdp.reset_mock()
            mock_connect.side_effect = RuntimeError("first")
            mock_wait_for_cdp.return_value = browser

            with self.subTest(timeout=invalid):
                with patch.dict(
                    os.environ,
                    {"CLAUSY_BROWSER_BOOTSTRAP": "always", "CLAUSY_CDP_CONNECT_TIMEOUT": invalid},
                    clear=False,
                ):
                    pool = BrowserPool(
                        cdp_host="127.0.0.1",
                        cdp_port=9200,
                        profile_dir="./profile",
                        home_url="https://chatgpt.com",
                    )
                    pool.start()

                mock_bootstrap.assert_called()
                mock_wait_for_cdp.assert_called_once_with(timeout_s=20.0)


class BrowserPoolAutoInstallTests(unittest.TestCase):
    @patch("clausy.browser.subprocess.Popen")
    @patch("clausy.browser.detect_browser_binary")
    @patch("clausy.browser.install_playwright_chromium")
    def test_bootstrap_uses_existing_browser_without_auto_install(
        self,
        mock_install_playwright,
        mock_detect_browser_binary,
        mock_popen,
    ):
        mock_detect_browser_binary.return_value = "/usr/bin/chromium"

        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9222, profile_dir="./profile", home_url="https://chatgpt.com")
        pool._pw = Mock()
        pool._pw.chromium.executable_path = "/pw/chromium"

        pool._bootstrap_browser()

        mock_install_playwright.assert_not_called()
        mock_popen.assert_called_once()

    @patch("clausy.browser.subprocess.Popen")
    @patch("clausy.browser.detect_browser_binary")
    @patch("clausy.browser.install_playwright_chromium")
    def test_bootstrap_attempts_auto_install_once_then_proceeds(
        self,
        mock_install_playwright,
        mock_detect_browser_binary,
        mock_popen,
    ):
        mock_detect_browser_binary.side_effect = [None, "/installed/chromium"]

        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9222, profile_dir="./profile", home_url="https://chatgpt.com")
        pool._pw = Mock()
        pool._pw.chromium.executable_path = "/pw/chromium"

        pool._bootstrap_browser()

        mock_install_playwright.assert_called_once_with(python_executable=None)
        self.assertEqual(mock_detect_browser_binary.call_count, 2)
        mock_popen.assert_called_once()

    @patch("clausy.browser.detect_browser_binary", return_value=None)
    @patch("clausy.browser.install_playwright_chromium", side_effect=RuntimeError("install failed"))
    def test_bootstrap_returns_actionable_error_when_auto_install_fails(
        self,
        _mock_install_playwright,
        _mock_detect_browser_binary,
    ):
        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9222, profile_dir="./profile", home_url="https://chatgpt.com")
        pool._pw = Mock()
        pool._pw.chromium.executable_path = "/pw/chromium"

        with self.assertRaises(RuntimeError) as ctx:
            pool._bootstrap_browser()

        msg = str(ctx.exception)
        self.assertIn("auto-install", msg.lower())
        self.assertIn("CLAUSY_BROWSER_BINARY", msg)

    @patch("clausy.browser.subprocess.Popen")
    @patch("clausy.browser.detect_browser_binary", return_value="/usr/bin/chromium")
    @patch("clausy.browser.BrowserPool._browser_pid_file_path")
    def test_bootstrap_writes_managed_browser_pid_metadata(self, mock_pid_path, _mock_detect_browser_binary, mock_popen):
        class _Proc:
            pid = 9898

        pid_file = Path("/tmp/clausy-browser-pid.json")
        mock_pid_path.return_value = pid_file
        mock_popen.return_value = _Proc()

        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9222, profile_dir="./profile", home_url="https://chatgpt.com")
        pool._pw = Mock()
        pool._pw.chromium.executable_path = "/pw/chromium"

        with patch("pathlib.Path.write_text") as mock_write_text:
            pool._bootstrap_browser()

        payload = json.loads(mock_write_text.call_args.args[0])
        self.assertEqual(payload["pid"], 9898)
        self.assertEqual(payload["cdp_port"], 9222)
        self.assertTrue(payload["profile_dir"].endswith("profile"))

    @patch("clausy.browser.subprocess.Popen")
    @patch("clausy.browser.detect_browser_binary", return_value="/usr/bin/chromium")
    @patch("clausy.browser.BrowserPool._browser_pid_file_path")
    def test_bootstrap_ignores_pid_metadata_write_failure(self, mock_pid_path, _mock_detect_browser_binary, mock_popen):
        class _Proc:
            pid = 9898

        mock_pid_path.return_value = Path("/tmp/clausy-browser-pid.json")
        mock_popen.return_value = _Proc()

        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9222, profile_dir="./profile", home_url="https://chatgpt.com")
        pool._pw = Mock()
        pool._pw.chromium.executable_path = "/pw/chromium"

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            pool._bootstrap_browser()

        mock_popen.assert_called_once()


class BrowserPoolStartupNavigationTests(unittest.TestCase):
    @patch("clausy.browser.sync_playwright")
    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    def test_start_reuses_first_existing_page_for_provider_navigation(self, mock_connect, mock_sync_playwright):
        page = Mock()
        context = Mock()
        context.pages = [page]

        browser = Mock()
        browser.contexts = [context]

        pw = Mock()
        pw.chromium = Mock()

        mock_connect.return_value = browser
        mock_sync_playwright.return_value.start.return_value = pw

        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile", home_url="https://claude.ai")
        pool.start()

        context.new_page.assert_not_called()
        page.goto.assert_called_once_with("https://claude.ai", wait_until="domcontentloaded")

    @patch("clausy.browser.sync_playwright")
    @patch("clausy.browser.BrowserPool._connect_over_cdp")
    def test_get_page_reuses_existing_first_page_for_first_session(self, mock_connect, mock_sync_playwright):
        page = Mock()
        context = Mock()
        context.pages = [page]

        browser = Mock()
        browser.contexts = [context]

        pw = Mock()
        pw.chromium = Mock()

        mock_connect.return_value = browser
        mock_sync_playwright.return_value.start.return_value = pw

        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile", home_url="https://claude.ai")
        pool.start()
        session_page = pool.get_page("abc")

        self.assertIs(session_page, page)
        context.new_page.assert_not_called()
        self.assertIs(pool._pages["abc"], page)


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

    @patch("clausy.browser.BrowserPool.start")
    def test_switch_profile_ignores_unsafe_path(self, mock_start):
        pool = BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="./profile-a", home_url="https://chatgpt.com")
        changed = pool.switch_profile("../escape")
        self.assertFalse(changed)
        self.assertTrue(pool.profile_dir.endswith("profile-a"))
        mock_start.assert_not_called()

    def test_constructor_rejects_unsafe_profile_path(self):
        with self.assertRaises(ValueError):
            BrowserPool(cdp_host="127.0.0.1", cdp_port=9200, profile_dir="../escape", home_url="https://chatgpt.com")


if __name__ == "__main__":
    unittest.main()
