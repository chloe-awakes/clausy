# Milestone Cycle — Release gate revalidation (2026-03-03, cycle 39)

## Milestone selected
Continue env-integer hardening outside `clausy/server.py`, focusing on `clausy/filter.py` and remaining helper scripts:
- `CLAUSY_FILTER_MAX_BYTES`
- `CLAUSY_FILTER_MAX_TAIL`
- script startup parse in `scripts/inspect_ui.py` for `CLAUSY_CDP_PORT`

Goal: remove raw env-int parsing crash hazards and preserve safe bounded defaults with focused regressions.

## TDD plan
1. Add filter env-int regression tests first.
2. Run tests and confirm failure on current raw parse behavior.
3. Replace raw `int(os.environ.get(...))` in filter config load with bounded parser + warnings.
4. Re-run targeted tests.
5. Run full `scripts/release-gate.sh`.

## RED (failing first)
Ran:
- `./.venv/bin/pytest -q tests/test_filter_env_int_parsing.py`

Observed failures (expected):
- `CLAUSY_FILTER_MAX_BYTES=oops` raised `ValueError` during config load
- `CLAUSY_FILTER_MAX_TAIL=0` was accepted (unsafe) instead of bounded fallback

## GREEN (minimal fix)
Implemented in `clausy/filter.py`:
- added module logger
- added `_env_int_bounded(...)` helper (same bounded semantics as server-side hardening)
- replaced raw integer parsing in `load_filter_config_from_env()`:
  - `CLAUSY_FILTER_MAX_BYTES`: default `2_000_000`, range `1..200_000_000`
  - `CLAUSY_FILTER_MAX_TAIL`: default `32_768`, range `1..2_000_000`

Added focused tests in `tests/test_filter_env_int_parsing.py`:
- invalid max-bytes falls back + warning
- out-of-range max-tail falls back + warning
- valid values pass without warnings

Also hardened script startup path:
- `scripts/inspect_ui.py` now uses `_env_int(...)` for `CLAUSY_CDP_PORT` default parsing (prevents crash on invalid env when script starts)

## Verification
Targeted checks:
- `./.venv/bin/pytest -q tests/test_filter_env_int_parsing.py tests/test_server_filter_provider_regressions.py::FilterConfigPathSafetyRegressionTests`
- Result: **PASS** (5 passed)

Release gate:
- `./scripts/release-gate.sh`
- Result:
  - Full suite: 194 passed, 8 subtests passed
  - Targeted suite: 56 passed
  - Installer smoke: PASS
  - Build: PASS
  - Overall: **PASS**

## Outcome
- Filter env-int call sites are now bounded and fail-safe.
- Invalid env values no longer crash filter config load.
- Existing path-safety behavior remains intact and verified.
- Release gate remains green after hardening.
