# Milestone Cycle — Release gate revalidation (2026-03-03, cycle 27)

## Milestone selected
Runtime hardening follow-up for CDP port config safety:
- Make `CLAUSY_CDP_PORT` parsing resilient to invalid and out-of-range values.
- Fail safe to default port `9200`.
- Emit clear diagnostics when fallback is applied.

## TDD plan
1. Add regression tests for invalid/out-of-range/valid port parsing behavior.
2. Verify tests fail first on current code (missing helper/parsing guard).
3. Implement minimal parsing helper and wire it into server config.
4. Re-run targeted tests and then full release gate.

## RED (failing first)
Ran:
- `.venv/bin/pytest -q tests/test_server_cdp_port_env.py`

Observed:
- 3 failing tests (expected): `clausy.server` had no `_env_port` guard helper and no protected parse path.

## GREEN (minimal fix)
Implemented in `clausy/server.py`:
- Added `_env_port(raw, var_name, default)` helper.
  - Empty/missing value: use default.
  - Non-integer: warning + default.
  - Out-of-range (`<1` or `>65535`): warning + default.
  - Valid range: use parsed value.
- Switched config binding to:
  - `CDP_PORT = _env_port(os.environ.get("CLAUSY_CDP_PORT"), var_name="CLAUSY_CDP_PORT", default=9200)`
- Added logger diagnostics via module logger for fallback cases.

## Verification
Targeted regression:
- `.venv/bin/python -m pytest -q tests/test_server_cdp_port_env.py`
- Result: **PASS** (3 passed)

Release gate:
- `scripts/release-gate.sh`
- Result:
  - Full suite: 185 passed, 8 subtests passed
  - Targeted suite: 56 passed
  - Installer smoke: PASS
  - Build: PASS
  - Overall: **PASS**

## Outcome
- Invalid or out-of-range `CLAUSY_CDP_PORT` values no longer crash/poison startup parsing.
- Service falls back to safe default `9200` and logs clear diagnostics for operators.
- Release gate remains green after hardening.
