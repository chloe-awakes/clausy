#!/usr/bin/env python3
"""Compatibility wrapper for the packaged installer command.

Preferred:
  clausy-openclaw-install
  python -m clausy.openclaw_install

This script remains for repository-local usage.
"""

from clausy.openclaw_install import main


if __name__ == "__main__":
    raise SystemExit(main())
