"""First-run browser auto-open helper for installer flows."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

DEFAULT_MARKER_PATH = Path.home() / ".openclaw" / ".clausy-browser-first-run.done"
_BOOTSTRAP_WAIT_SECONDS = 6.0
_BOOTSTRAP_PORT = "3110"


def has_gui_environment() -> bool:
    if os.name == "nt":
        return True
    if os.uname().sysname == "Darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def is_interactive_shell() -> bool:
    return bool(getattr(os.sys.stdout, "isatty", lambda: False)())


def should_auto_open_browser(
    *,
    marker_path: Path,
    no_browser: bool,
    docker_mode: bool,
    dry_run: bool,
    ci_env: bool,
    interactive: bool,
    has_gui: bool,
) -> bool:
    if no_browser or docker_mode or dry_run or ci_env:
        return False
    if not interactive or not has_gui:
        return False
    return not marker_path.exists()


def mark_first_run_complete(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        f"auto-opened-browser {datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )


def build_chrome_launch_command(venv_python: str) -> list[str]:
    return [venv_python, "-m", "clausy", "chrome"]


def build_chrome_launch_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    env["CLAUSY_BROWSER_BOOTSTRAP"] = "always"
    env["CLAUSY_HEADLESS"] = "0"
    env.setdefault("CLAUSY_PORT", _BOOTSTRAP_PORT)
    return env


def _launch_and_detach_chrome_bootstrap(
    command: Sequence[str],
    env: Mapping[str, str],
    wait_seconds: float = _BOOTSTRAP_WAIT_SECONDS,
) -> bool:
    proc = subprocess.Popen(
        list(command),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(env),
        start_new_session=True,
    )

    time.sleep(max(wait_seconds, 0.0))
    if proc.poll() is not None:
        return False

    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    return True


def maybe_auto_open_browser(
    *,
    venv_python: str,
    marker_path: Path = DEFAULT_MARKER_PATH,
    no_browser: bool = False,
    docker_mode: bool = False,
    dry_run: bool = False,
    ci_env: bool | None = None,
    interactive: bool | None = None,
    has_gui: bool | None = None,
) -> bool:
    ci = bool(os.environ.get("CI")) if ci_env is None else ci_env
    is_interactive = is_interactive_shell() if interactive is None else interactive
    gui = has_gui_environment() if has_gui is None else has_gui

    if not should_auto_open_browser(
        marker_path=marker_path,
        no_browser=no_browser,
        docker_mode=docker_mode,
        dry_run=dry_run,
        ci_env=ci,
        interactive=is_interactive,
        has_gui=gui,
    ):
        return False

    command = build_chrome_launch_command(venv_python)
    env = build_chrome_launch_env()
    launched = _launch_and_detach_chrome_bootstrap(command, env)
    if launched:
        mark_first_run_complete(marker_path)
    return launched


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-open visible Chrome once after install")
    parser.add_argument("--venv-python", required=True, help="Path to virtualenv python executable")
    parser.add_argument("--marker-path", default=str(DEFAULT_MARKER_PATH), help="First-run marker file")
    parser.add_argument("--docker", action="store_true", help="Skip browser auto-open in Docker mode")
    parser.add_argument("--dry-run", action="store_true", help="Do not launch browser")
    parser.add_argument("--no-browser", action="store_true", help="Skip browser auto-open")
    args = parser.parse_args()

    launched = maybe_auto_open_browser(
        venv_python=args.venv_python,
        marker_path=Path(args.marker_path),
        no_browser=args.no_browser,
        docker_mode=args.docker,
        dry_run=args.dry_run,
    )
    if launched:
        print("Opened visible Chrome for first-time Clausy login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
