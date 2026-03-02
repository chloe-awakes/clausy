"""One-command local installer for Clausy development/runtime setup."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List


def _venv_python(venv_dir: str) -> str:
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def build_install_steps(venv_dir: str = ".venv", include_playwright: bool = True) -> List[List[str]]:
    py = _venv_python(venv_dir)
    steps: List[List[str]] = [
        [sys.executable, "-m", "venv", venv_dir],
        [py, "-m", "pip", "install", "-U", "pip"],
        [py, "-m", "pip", "install", "."],
    ]
    if include_playwright:
        steps.append([py, "-m", "playwright", "install", "chromium"])
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Clausy in one command")
    parser.add_argument("--venv", default=".venv", help="Virtualenv directory (default: .venv)")
    parser.add_argument(
        "--skip-playwright",
        action="store_true",
        help="Skip Playwright browser install step",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    args = parser.parse_args()

    steps = build_install_steps(args.venv, include_playwright=not args.skip_playwright)

    if args.dry_run:
        for step in steps:
            print(" ".join(step))
        return 0

    for step in steps:
        subprocess.run(step, check=True)

    print("Clausy install complete.")
    print(f"Activate your venv: source {args.venv}/bin/activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
