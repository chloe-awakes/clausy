# Milestone Cycle — Release gate revalidation (2026-03-03, cycle 40)

## Milestone selected
Complete non-server env-hardening sweep for startup-time parsing edge-cases in `clausy/filter.py`:
- boolean coercion robustness (`CLAUSY_FILTER_SCAN_OPENCLAW`, `CLAUSY_FILTER_PREFIX_PATTERNS`)
- list coercion robustness (`CLAUSY_BADWORD_WORDS`)
- preserve existing bounded numeric behavior already hardened in cycle 39

Goal: avoid surprising bool coercions and fragile list parsing at startup while keeping safe defaults.

## TDD plan
1. Add focused regressions for bool/list parsing in filter env loaders.
2. Run tests first and confirm failures (RED).
3. Implement minimal bool/list env parser helpers in `clausy/filter.py`.
4. Re-run targeted tests and full release gate.

## RED (failing first)
Ran:
- `./.venv/bin/pytest -q tests/test_filter_env_coercion.py`

Observed failures (expected):
- `CLAUSY_FILTER_SCAN_OPENCLAW=" OFF "` was treated as `True` (should coerce to `False`)
- `CLAUSY_FILTER_PREFIX_PATTERNS=" ON "` was treated as `False` (should coerce to `True`)
- invalid bool token produced no warning
- profanity word list did not split semicolon/newline separated values

## GREEN (minimal fix)
Implemented in `clausy/filter.py`:
- added `_env_bool(...)` with strict true/false token sets and warning+default fallback on invalid values
- added `_env_list(...)` for robust env list splitting on `,`, `;`, and newlines
- switched `load_filter_config_from_env()` to `_env_bool(...)` for:
  - `CLAUSY_FILTER_SCAN_OPENCLAW` (default `True`)
  - `CLAUSY_FILTER_PREFIX_PATTERNS` (default `False`)
- switched `load_profanity_filter_config_from_env()` to `_env_list(..., lowercase=True)` for `CLAUSY_BADWORD_WORDS`

Added focused tests in `tests/test_filter_env_coercion.py`:
- OFF token parsing (case-insensitive)
- ON token parsing (case-insensitive)
- invalid bool token warning fallback
- semicolon/newline/csv list coercion for profanity words

## Verification
Targeted checks:
- `./.venv/bin/pytest -q tests/test_filter_env_coercion.py tests/test_filter_env_int_parsing.py tests/test_server_filter_provider_regressions.py::FilterConfigPathSafetyRegressionTests tests/test_profanity_filter.py`
- Result: **PASS** (12 passed)

Release gate:
- `./scripts/release-gate.sh`
- Result:
  - Full suite: 198 passed, 8 subtests passed
  - Targeted suite: 56 passed
  - Installer smoke: PASS
  - Build: PASS
  - Overall: **PASS**

## Outcome
- Filter startup env parsing is now robust for bool/list coercion edge cases.
- Invalid bool values now log warnings and safely fall back to defaults.
- Non-server env-hardening sweep (bool/list + bounded numeric) is complete for `clausy/filter.py`.
- Release gate remains green.
