from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable


_BOOTSTRAP_MODES = {"auto", "always", "never"}
_PATH_TRAVERSAL_SEGMENT_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)")
_SHELL_META_RE = re.compile(r"[;&|`$<>]")
_DISALLOWED_BROWSER_ARG_PREFIXES = (
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--user-data-dir",
    "--headless",
)


@dataclass(frozen=True)
class BrowserRuntimeConfig:
    cdp_host: str
    cdp_port: int
    profile_dir: str
    headless: bool = False
    extra_args: list[str] = field(default_factory=list)


def parse_bootstrap_mode(raw: str | None) -> str:
    mode = (raw or "auto").strip().lower()
    return mode if mode in _BOOTSTRAP_MODES else "auto"


def parse_browser_extra_args(raw: str | None) -> list[str]:
    """Parse CLAUSY_BROWSER_ARGS safely.

    Rejects the entire payload and returns [] when tokens are malformed,
    shell-like, or attempt to override managed runtime flags.
    """
    value = (raw or "").strip()
    if not value:
        return []

    try:
        tokens = shlex.split(value)
    except ValueError:
        return []

    for token in tokens:
        if not token or any(ord(ch) < 32 or ord(ch) == 127 for ch in token):
            return []
        if _SHELL_META_RE.search(token):
            return []
        if token.startswith("-") and token.startswith(_DISALLOWED_BROWSER_ARG_PREFIXES):
            return []

    return tokens


def _is_safe_path(value: str | None) -> bool:
    if not value:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    if _PATH_TRAVERSAL_SEGMENT_RE.search(value):
        return False
    return True


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def detect_browser_binary(
    *,
    which: Callable[[str], str | None] = shutil.which,
    platform: str = sys.platform,
    playwright_binary: str | None = None,
) -> str | None:
    override = (os.environ.get("CLAUSY_BROWSER_BINARY") or "").strip()
    if override and _is_safe_path(override) and os.path.isabs(override) and _is_executable_file(override):
        return override

    candidates: list[str] = []
    if playwright_binary and _is_safe_path(playwright_binary) and os.path.isabs(playwright_binary):
        candidates.append(playwright_binary)

    if platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )

    candidates.extend(["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"])

    for candidate in candidates:
        if os.path.isabs(candidate):
            if _is_safe_path(candidate) and _is_executable_file(candidate):
                return candidate
            continue
        resolved = which(candidate)
        if resolved and _is_safe_path(resolved):
            return resolved
    return None


def is_playwright_auto_install_enabled(raw: str | None = None) -> bool:
    value = (os.environ.get("CLAUSY_BROWSER_AUTO_INSTALL") if raw is None else raw) or "1"
    return value.strip().lower() in {"1", "true", "yes", "on"}


def install_playwright_chromium(*, python_executable: str | None = None) -> None:
    python_bin = (python_executable or "").strip() or sys.executable
    cmd = [python_bin, "-m", "playwright", "install", "chromium"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Failed to auto-install Playwright Chromium. "
            "Run 'python -m playwright install chromium' manually and retry. "
            f"Command exited with code {exc.returncode}."
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Python executable for Playwright auto-install was not found. "
            "Set CLAUSY_BROWSER_BINARY to an existing Chrome/Chromium binary or "
            "run 'python -m playwright install chromium' manually."
        ) from exc


def build_browser_launch_command(binary: str, cfg: BrowserRuntimeConfig) -> list[str]:
    args = [
        binary,
        f"--remote-debugging-address={cfg.cdp_host}",
        f"--remote-debugging-port={cfg.cdp_port}",
        f"--user-data-dir={cfg.profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-dev-shm-usage",
    ]

    if cfg.headless:
        args.extend(["--headless=new", "--disable-gpu"])

    no_sandbox = (os.environ.get("CLAUSY_CHROME_NO_SANDBOX") or "").strip().lower()
    if no_sandbox in {"1", "true", "yes", "on"}:
        args.append("--no-sandbox")

    if cfg.extra_args:
        args.extend(cfg.extra_args)
    return args
