"""First-run browser auto-open helper for installer flows."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .browser import BrowserPool

DEFAULT_MARKER_PATH = Path.home() / ".openclaw" / ".clausy-browser-first-run.done"
_BOOTSTRAP_WAIT_SECONDS = 6.0
_BOOTSTRAP_PORT = "3110"
_PROVIDER_URLS: dict[str, str] = {
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "grok": "https://grok.com",
    "gemini_web": "https://gemini.google.com",
    "perplexity": "https://www.perplexity.ai",
    "poe": "https://poe.com",
    "deepseek": "https://chat.deepseek.com",
    "openai": "https://platform.openai.com",
    "anthropic": "https://console.anthropic.com",
    "ollama": "http://127.0.0.1:11434",
    "gemini": "https://aistudio.google.com",
    "openrouter": "https://openrouter.ai",
}


def has_gui_environment() -> bool:
    if os.name == "nt":
        return True
    if os.uname().sysname == "Darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def is_interactive_shell() -> bool:
    return bool(getattr(os.sys.stdout, "isatty", lambda: False)())


def auto_open_skip_reason(
    *,
    marker_path: Path,
    no_browser: bool,
    docker_mode: bool,
    dry_run: bool,
    ci_env: bool,
    interactive: bool,
    has_gui: bool,
) -> str | None:
    if no_browser:
        return "--no-browser requested"
    if docker_mode:
        return "docker mode"
    if dry_run:
        return "dry-run mode"
    if ci_env:
        return "CI environment"
    if not interactive:
        return "non-interactive shell"
    if not has_gui:
        return "no GUI environment"
    if marker_path.exists():
        return "already completed once"
    return None


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
    return auto_open_skip_reason(
        marker_path=marker_path,
        no_browser=no_browser,
        docker_mode=docker_mode,
        dry_run=dry_run,
        ci_env=ci_env,
        interactive=interactive,
        has_gui=has_gui,
    ) is None


def mark_first_run_complete(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        f"auto-opened-browser {datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )


def build_chrome_launch_command(venv_python: str) -> list[str]:
    return [venv_python, "-m", "clausy", "chrome"]


def provider_url(provider_name: str | None) -> str:
    key = (provider_name or "chatgpt").strip().lower()
    return _PROVIDER_URLS.get(key, _PROVIDER_URLS["chatgpt"])


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def open_provider_page_in_managed_browser(
    url: str,
    *,
    browser_pool_factory: Callable[..., BrowserPool] = BrowserPool,
) -> bool:
    cdp_host = (os.environ.get("CLAUSY_CDP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    cdp_port = _env_int("CLAUSY_CDP_PORT", 9200)
    profile_dir = (os.environ.get("CLAUSY_PROFILE_DIR") or "./profile").strip() or "./profile"

    try:
        browser = browser_pool_factory(
            cdp_host=cdp_host,
            cdp_port=cdp_port,
            profile_dir=profile_dir,
            home_url=url,
        )
        browser.start()
        page = browser.get_page("first-run-provider")
        page.goto(url, wait_until="domcontentloaded")
    except Exception:
        return False
    return True


def build_provider_open_command(url: str, *, platform: str | None = None) -> list[str]:
    os_name = os.name if platform is None else platform
    if os_name == "nt":
        return ["cmd", "/c", "start", "", url]
    if os.uname().sysname == "Darwin":
        return ["open", "-a", "Google Chrome", url]
    return ["xdg-open", url]


def open_provider_page(url: str) -> bool:
    command = build_provider_open_command(url)
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        return False
    return True


def provider_manual_open_command(url: str) -> str:
    command = build_provider_open_command(url)
    return " ".join(shlex.quote(part) for part in command)


def open_provider_page_with_fallback(url: str) -> bool:
    if open_provider_page(url):
        return True

    print("Could not auto-open provider URL. Run this command manually:")
    print(f"  {provider_manual_open_command(url)}")
    return False


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
    provider: str = "chatgpt",
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

    if not open_provider_page_in_managed_browser(provider_url(provider)):
        return False

    mark_first_run_complete(marker_path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-open visible Chrome once after install")
    parser.add_argument("--venv-python", required=True, help="Path to virtualenv python executable")
    parser.add_argument("--provider", default="chatgpt", help="Selected provider name")
    parser.add_argument("--marker-path", default=str(DEFAULT_MARKER_PATH), help="First-run marker file")
    parser.add_argument("--docker", action="store_true", help="Skip browser auto-open in Docker mode")
    parser.add_argument("--dry-run", action="store_true", help="Do not launch browser")
    parser.add_argument("--no-browser", action="store_true", help="Skip browser auto-open")
    parser.add_argument(
        "--open-provider-only",
        action="store_true",
        help="Only open selected provider URL (no one-time marker semantics)",
    )
    args = parser.parse_args()

    url = provider_url(args.provider)

    if args.open_provider_only:
        if not open_provider_page_in_managed_browser(url):
            open_provider_page_with_fallback(url)
        return 0

    marker_path = Path(args.marker_path)
    launched = maybe_auto_open_browser(
        venv_python=args.venv_python,
        provider=args.provider,
        marker_path=marker_path,
        no_browser=args.no_browser,
        docker_mode=args.docker,
        dry_run=args.dry_run,
    )
    if launched:
        print("Opened provider URL in Clausy-managed browser for first-time login.")
    else:
        skip_reason = auto_open_skip_reason(
            marker_path=marker_path,
            no_browser=args.no_browser,
            docker_mode=args.docker,
            dry_run=args.dry_run,
            ci_env=bool(os.environ.get("CI")),
            interactive=is_interactive_shell(),
            has_gui=has_gui_environment(),
        )
        if skip_reason:
            print(f"Skipping first-run browser auto-open: {skip_reason}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
