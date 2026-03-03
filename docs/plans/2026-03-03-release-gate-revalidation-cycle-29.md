# Milestone Cycle — Release gate revalidation (2026-03-03, cycle 29)

## Milestone selected
Continue env-integer hardening for remaining raw call sites in `clausy/server.py`:
- `CLAUSY_PROFILE_ROTATION_COUNT`
- `CLAUSY_EVENT_LOG_MAX_ITEMS`

Goal: eliminate raw `int(os.environ.get(...))` startup hazards, enforce bounded defaults, and lock behavior with focused regression tests.

## TDD plan
1. Add regression tests that exercise these env vars via `importlib.reload(server)`.
2. Run the new tests first and confirm failure against pre-fix behavior.
3. Replace raw int parsing with `_env_int_bounded(...)` at both call sites.
4. Re-run targeted tests.
5. Run full `scripts/release-gate.sh`.

## RED (failing first)
Ran:
- `.venv/bin/pytest -q tests/test_server_env_bounded_callsites.py`

Observed failures (expected):
- invalid `CLAUSY_PROFILE_ROTATION_COUNT=oops` crashed module reload (`ValueError`)
- out-of-range `CLAUSY_EVENT_LOG_MAX_ITEMS=10001` was accepted instead of falling back

## GREEN (minimal fix)
Implemented in `clausy/server.py`:
- `PROFILE_ROTATION_COUNT` now uses `_env_int_bounded(...)`:
  - default `0`, range `0..1000`
- `EVENT_LOG_MAX_ITEMS` now uses `_env_int_bounded(...)`:
  - default `500`, range `1..10000`

Added focused regression tests in `tests/test_server_env_bounded_callsites.py`:
- invalid rotation count falls back + warning
- out-of-range event log max falls back + warning
- upper boundary event log max (`10000`) is accepted

## Verification
Targeted regression checks:
- `.venv/bin/pytest -q tests/test_server_env_bounded_callsites.py tests/test_server_env_int_parsing.py`
- Result: **PASS** (6 passed)

Release gate:
- `scripts/release-gate.sh`
- Result:
  - Full suite: 191 passed, 8 subtests passed
  - Targeted suite: 56 passed
  - Installer smoke: PASS
  - Build: PASS
  - Overall: **PASS**

## Outcome
- Remaining raw env-int call sites in server config are now bounded and fail-safe.
- Invalid/malicious env values no longer crash startup or silently permit oversized event buffer settings.
- Regression coverage added for both call sites; release gate remains green.
