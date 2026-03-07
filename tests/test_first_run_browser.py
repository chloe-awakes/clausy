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
