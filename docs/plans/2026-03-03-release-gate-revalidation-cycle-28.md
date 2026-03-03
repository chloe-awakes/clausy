# Milestone Cycle — Release gate revalidation (2026-03-03, cycle 28)

## Milestone selected
Runtime hardening continuation for remaining env int parsing hotspots:
- `CLAUSY_PORT`
- `CLAUSY_MAX_REPAIRS`
- reset/restart thresholds:
  - `CLAUSY_RESET_TURNS`
  - `CLAUSY_RESET_SUMMARY_MAX_CHARS`
  - `CLAUSY_BROWSER_RESTART_EVERY_RESETS`
  - `CLAUSY_BROWSER_RESTART_EVERY_REQUESTS`

Goal: bounded fail-safe parsing + diagnostics + regression tests.

## TDD plan
1. Add regression tests for bounded integer parsing helper behavior.
2. Run tests first and confirm failure (helper absent).
3. Implement generic bounded int parser and wire all target env vars.
4. Re-run targeted tests.
5. Run full `scripts/release-gate.sh`.

## RED (failing first)
Ran:
- `.venv/bin/pytest -q tests/test_server_env_int_parsing.py`

Observed:
- 3 failing tests (expected): `AttributeError` because `clausy.server` did not yet expose `_env_int_bounded`.

## GREEN (minimal fix)
Implemented in `clausy/server.py`:
- Added `_env_int_bounded(raw, var_name, default, min_value, max_value)`.
  - Empty/missing → default.
  - Invalid integer → warning + default.
  - Out-of-range → warning + default.
  - In-range → parsed value.
- Refactored `_env_port(...)` to use `_env_int_bounded(..., min=1, max=65535)`.
- Switched `CLAUSY_PORT` from raw `int(...)` to `_env_port(...)`.
- Switched `CLAUSY_MAX_REPAIRS` to bounded parse (`0..20`, default `2`).
- Switched reset/restart thresholds to bounded parse:
  - `RESET_TURNS`: `1..1000` (default `20`)
  - `RESET_SUMMARY_MAX_CHARS`: `100..20000` (default `1500`)
  - `BROWSER_RESTART_EVERY_RESETS`: `0..100000` (default `0`)
  - `BROWSER_RESTART_EVERY_REQUESTS`: `0..100000` (default `0`)

## Verification
Targeted regression checks:
- `PYTHONPATH=. .venv/bin/pytest -q tests/test_server_env_int_parsing.py tests/test_server_cdp_port_env.py`
- Result: **PASS** (6 passed)

Release gate:
- `scripts/release-gate.sh`
- Result:
  - Full suite: 188 passed, 8 subtests passed
  - Targeted suite: 56 passed
  - Installer smoke: PASS
  - Build: PASS
  - Overall: **PASS**

## Outcome
- All requested env-int hotspots now parse safely with bounded fallback behavior and operator-visible diagnostics.
- Invalid or out-of-range env values no longer risk startup exceptions for these settings.
- Release gate remains green after hardening.
