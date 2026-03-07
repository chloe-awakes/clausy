from __future__ import annotations

import os
import sys

from .server import main as server_main


def _configure_visible_chrome_mode() -> None:
    os.environ["CLAUSY_BROWSER_BOOTSTRAP"] = "always"
    os.environ["CLAUSY_HEADLESS"] = "0"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "chrome":
        _configure_visible_chrome_mode()

    server_main()
    return 0
