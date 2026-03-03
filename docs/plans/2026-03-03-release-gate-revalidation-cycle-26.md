# Milestone Cycle — Release gate revalidation (2026-03-03, cycle 26)

## Milestone selected
Security/runtime hardening follow-up on browser profile path safety:
- Reject absolute profile paths in `CLAUSY_PROFILE_DIR` and `CLAUSY_PROFILE_BY_PROVIDER`.
- Keep profile switching constrained to safe relative paths.

## TDD plan
1. Add regression tests first for absolute-path rejection.
2. Verify tests fail on current `main`.
3. Implement minimal runtime guard.
4. Re-run targeted tests, then full release gate.

## RED (failing first)
Ran:
- `.venv/bin/python -m pytest -q tests/test_server_filter_provider_regressions.py -k "absolute_paths or when_absolute"`

Observed:
- 2 failing tests (expected): absolute paths were accepted before hardening.

## GREEN (minimal fix)
Implemented in `clausy/server.py`:
- `_is_safe_profile_path` now rejects absolute paths via:
  - `os.path.isabs(value)` (POSIX/host-native)
  - Windows drive absolute pattern `^[a-zA-Z]:[\\/]`

## Verification
Targeted regression:
- `.venv/bin/python -m pytest -q tests/test_server_filter_provider_regressions.py -k "absolute_paths or when_absolute"`
- Result: **PASS** (2 passed)

Focused suite:
- `.venv/bin/python -m pytest -q tests/test_server_filter_provider_regressions.py`
- Result: **PASS** (45 passed)

Release gate:
- `scripts/release-gate.sh`
- Result:
  - Full suite: 182 passed, 8 subtests passed
  - Targeted suite: 56 passed
  - Installer smoke: PASS
  - Build: PASS
  - Overall: **PASS**

## Outcome
- Absolute profile path injection is now blocked consistently for default and provider-mapped profile directories.
- Release gate remains green after hardening.
