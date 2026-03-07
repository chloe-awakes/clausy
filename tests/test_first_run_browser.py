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


def test_build_provider_open_command_for_macos(monkeypatch):
    monkeypatch.setattr(first_run_browser.os, "name", "posix")
    monkeypatch.setattr(first_run_browser.os, "uname", lambda: type("U", (), {"sysname": "Darwin"})())

    cmd = first_run_browser.build_provider_open_command("https://chatgpt.com")

    assert cmd == ["open", "-a", "Google Chrome", "https://chatgpt.com"]


def test_provider_manual_open_command_for_macos_uses_chrome_app(monkeypatch):
    monkeypatch.setattr(first_run_browser.os, "name", "posix")
    monkeypatch.setattr(first_run_browser.os, "uname", lambda: type("U", (), {"sysname": "Darwin"})())

    cmd = first_run_browser.provider_manual_open_command("https://chatgpt.com")

    assert cmd == "open -a 'Google Chrome' https://chatgpt.com"


def test_build_provider_open_command_for_linux(monkeypatch):
    monkeypatch.setattr(first_run_browser.os, "name", "posix")
    monkeypatch.setattr(first_run_browser.os, "uname", lambda: type("U", (), {"sysname": "Linux"})())

    cmd = first_run_browser.build_provider_open_command("https://chatgpt.com")

    assert cmd == ["xdg-open", "https://chatgpt.com"]


def test_build_provider_open_command_for_windows():
    cmd = first_run_browser.build_provider_open_command("https://chatgpt.com", platform="nt")

    assert cmd == ["cmd", "/c", "start", "", "https://chatgpt.com"]


def test_maybe_auto_open_browser_opens_selected_provider_and_marks_once(tmp_path, monkeypatch):
    marker = tmp_path / "marker.done"
    launches: list[tuple[list[str], dict[str, str]]] = []
    opened_urls: list[str] = []

    def _fake_launch(command, env, wait_seconds=0.0):
        launches.append((list(command), dict(env)))
        return True

    monkeypatch.setattr(first_run_browser, "_launch_and_detach_chrome_bootstrap", _fake_launch)
    monkeypatch.setattr(first_run_browser, "open_provider_page_with_fallback", lambda url: opened_urls.append(url) or True)

    launched = first_run_browser.maybe_auto_open_browser(
        venv_python="/tmp/.venv/bin/python",
        provider="claude",
        marker_path=marker,
        interactive=True,
        has_gui=True,
        ci_env=False,
    )

    assert launched is True
    assert launches == [(["/tmp/.venv/bin/python", "-m", "clausy", "chrome"], first_run_browser.build_chrome_launch_env())]
    assert opened_urls == ["https://claude.ai"]
    assert marker.exists()


def test_open_provider_page_with_fallback_prints_manual_command_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(first_run_browser, "open_provider_page", lambda _url: False)
    monkeypatch.setattr(
        first_run_browser,
        "provider_manual_open_command",
        lambda _url: "open https://chatgpt.com",
    )

    opened = first_run_browser.open_provider_page_with_fallback("https://chatgpt.com")

    out = capsys.readouterr().out
    assert opened is False
    assert "Could not auto-open provider URL" in out
    assert "open https://chatgpt.com" in out


def test_open_provider_page_with_fallback_silent_on_success(monkeypatch, capsys):
    monkeypatch.setattr(first_run_browser, "open_provider_page", lambda _url: True)

    opened = first_run_browser.open_provider_page_with_fallback("https://chatgpt.com")

    out = capsys.readouterr().out
    assert opened is True
    assert out == ""


def test_main_open_provider_only_uses_fallback_path(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(first_run_browser, "open_provider_page_with_fallback", lambda url: calls.append(url) or True)
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
