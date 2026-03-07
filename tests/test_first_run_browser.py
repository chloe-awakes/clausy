from __future__ import annotations

from pathlib import Path

import clausy.first_run_browser as first_run_browser


def test_should_auto_open_browser_first_run_when_local_interactive(tmp_path):
    marker = tmp_path / ".clausy-browser-first-run.done"

    assert first_run_browser.should_auto_open_browser(
        marker_path=marker,
        no_browser=False,
        docker_mode=False,
        dry_run=False,
        ci_env=False,
        interactive=True,
        has_gui=True,
    )


def test_should_auto_open_browser_skips_after_marker_exists(tmp_path):
    marker = tmp_path / ".clausy-browser-first-run.done"
    marker.write_text("done\n", encoding="utf-8")

    assert not first_run_browser.should_auto_open_browser(
        marker_path=marker,
        no_browser=False,
        docker_mode=False,
        dry_run=False,
        ci_env=False,
        interactive=True,
        has_gui=True,
    )


def test_should_auto_open_browser_respects_no_browser_flag(tmp_path):
    marker = tmp_path / ".clausy-browser-first-run.done"

    assert not first_run_browser.should_auto_open_browser(
        marker_path=marker,
        no_browser=True,
        docker_mode=False,
        dry_run=False,
        ci_env=False,
        interactive=True,
        has_gui=True,
    )


def test_mark_first_run_creates_parent_and_file(tmp_path):
    marker = tmp_path / "nested" / "marker.done"

    first_run_browser.mark_first_run_complete(marker)

    assert marker.exists()
    assert "auto-opened-browser" in marker.read_text(encoding="utf-8")


def test_build_chrome_launch_env_forces_visible_mode():
    env = first_run_browser.build_chrome_launch_env({"A": "1"})

    assert env["A"] == "1"
    assert env["CLAUSY_BROWSER_BOOTSTRAP"] == "always"
    assert env["CLAUSY_HEADLESS"] == "0"
    assert env["CLAUSY_PORT"] == "3110"


def test_build_chrome_launch_command_uses_clausy_chrome_helper():
    cmd = first_run_browser.build_chrome_launch_command("/tmp/.venv/bin/python")

    assert cmd == ["/tmp/.venv/bin/python", "-m", "clausy", "chrome"]


def test_provider_url_maps_selected_provider():
    assert first_run_browser.provider_url("chatgpt") == "https://chatgpt.com"
    assert first_run_browser.provider_url("claude") == "https://claude.ai"
    assert first_run_browser.provider_url("unknown") == "https://chatgpt.com"


def test_maybe_auto_open_browser_uses_managed_browser_navigation_and_marks_once(tmp_path, monkeypatch):
    marker = tmp_path / "marker.done"
    managed_urls: list[str] = []

    monkeypatch.setattr(first_run_browser, "open_provider_page_in_managed_browser", lambda url: managed_urls.append(url) or True)

    launched = first_run_browser.maybe_auto_open_browser(
        venv_python="/tmp/.venv/bin/python",
        provider="claude",
        marker_path=marker,
        interactive=True,
        has_gui=True,
        ci_env=False,
    )

    assert launched is True
    assert managed_urls == ["https://claude.ai"]
    assert marker.exists()


def test_open_provider_page_in_managed_browser_uses_browserpool_page_goto(monkeypatch):
    captured: dict[str, object] = {}

    class _FakePage:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def goto(self, url: str, wait_until: str = ""):
            self.calls.append((url, wait_until))

    page = _FakePage()

    class _FakePool:
        def __init__(self, *, cdp_host, cdp_port, profile_dir, home_url):
            captured["cdp_host"] = cdp_host
            captured["cdp_port"] = cdp_port
            captured["profile_dir"] = profile_dir
            captured["home_url"] = home_url
            captured["started"] = False

        def start(self):
            captured["started"] = True

        def get_page(self, session_id: str):
            captured["session_id"] = session_id
            return page

    monkeypatch.setenv("CLAUSY_CDP_PORT", "9301")
    monkeypatch.setenv("CLAUSY_PROFILE_DIR", "/tmp/clausy-profile")

    opened = first_run_browser.open_provider_page_in_managed_browser(
        "https://claude.ai",
        browser_pool_factory=_FakePool,
    )

    assert opened is True
    assert captured["started"] is True
    assert captured["cdp_host"] == "127.0.0.1"
    assert captured["cdp_port"] == 9301
    assert captured["profile_dir"] == "/tmp/clausy-profile"
    assert captured["home_url"] == "https://claude.ai"
    assert captured["session_id"] == "first-run-provider"
    assert page.calls == [("https://claude.ai", "domcontentloaded")]


def test_main_open_provider_only_uses_managed_browser_path(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(first_run_browser, "open_provider_page_in_managed_browser", lambda url: calls.append(url) or True)
    monkeypatch.setattr(first_run_browser, "maybe_auto_open_browser", lambda **_kwargs: False)
    monkeypatch.setattr(
        first_run_browser.os.sys,
        "argv",
        [
            "first_run_browser.py",
            "--venv-python",
            "/tmp/.venv/bin/python",
            "--provider",
            "claude",
            "--open-provider-only",
        ],
    )

    rc = first_run_browser.main()

    assert rc == 0
    assert calls == ["https://claude.ai"]


def test_main_open_provider_only_returns_nonzero_when_managed_navigation_fails(monkeypatch, capsys):
    monkeypatch.setattr(first_run_browser, "open_provider_page_in_managed_browser", lambda _url: False)
    monkeypatch.setattr(
        first_run_browser.os.sys,
        "argv",
        [
            "first_run_browser.py",
            "--venv-python",
            "/tmp/.venv/bin/python",
            "--provider",
            "claude",
            "--open-provider-only",
        ],
    )

    rc = first_run_browser.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "ERROR:" in out
    assert "managed browser" in out
    assert "clausy chrome" in out


def test_main_returns_nonzero_when_first_run_managed_navigation_fails(monkeypatch, tmp_path, capsys):
    marker = tmp_path / "marker.done"
    monkeypatch.setattr(first_run_browser, "is_interactive_shell", lambda: True)
    monkeypatch.setattr(first_run_browser, "has_gui_environment", lambda: True)
    monkeypatch.setattr(first_run_browser, "open_provider_page_in_managed_browser", lambda _url: False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(
        first_run_browser.os.sys,
        "argv",
        [
            "first_run_browser.py",
            "--venv-python",
            "/tmp/.venv/bin/python",
            "--provider",
            "claude",
            "--marker-path",
            str(marker),
        ],
    )

    rc = first_run_browser.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "ERROR:" in out
    assert "managed browser" in out
    assert marker.exists() is False
