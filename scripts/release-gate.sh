#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "error: python interpreter not found or not executable: $PYTHON_BIN" >&2
  echo "hint: create the venv first (python3 -m venv .venv && .venv/bin/pip install -e '.[dev]')" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import pytest, build' >/dev/null 2>&1; then
  echo "error: release gate requires pytest and build in the selected interpreter" >&2
  echo "hint: $PYTHON_BIN -m pip install -e '.[dev]'" >&2
  exit 1
fi

echo "==> [1/4] Full test suite"
"$PYTHON_BIN" -m pytest -q

echo "==> [2/4] Targeted routing/provider regression checks"
"$PYTHON_BIN" -m pytest -q \
  tests/test_server_filter_provider_regressions.py \
  tests/test_api_provider_routing.py

echo "==> [3/4] Installer smoke check"
"$PYTHON_BIN" -m clausy.install --dry-run >/dev/null

echo "==> [4/4] Build package"
"$PYTHON_BIN" -m build >/dev/null

echo "release gate: PASS"
