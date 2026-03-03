# Release Gate Revalidation Cycle 22

Date: 2026-03-03 06:15 (Europe/Berlin)

## Scope
Provider/routing/runtime hardening follow-up focused on sanitizing invalid primary provider config.

## Planner
- Identify a high-value edge case not yet guarded in provider selection.
- Add regression coverage first for unsafe/invalid primary provider names.
- Implement minimal runtime guard and re-run full release gate.

## Executor
- Hardened `clausy/server.py` in `_provider_candidates`:
  - if resolved primary provider token is empty **or invalid** (fails `_FALLBACK_TOKEN_RE`), force safe fallback to `chatgpt`.
- Added regression test:
  - `ModelSwitchingRegressionTests.test_provider_candidates_sanitize_invalid_primary_provider_name`

## Tester/Evaluator
- Targeted test run:
  - `tests/test_server_filter_provider_regressions.py::ModelSwitchingRegressionTests::test_provider_candidates_sanitize_invalid_primary_provider_name`
  - **passed**
- Release gate run (`scripts/release-gate.sh`):
  - Full suite: **151 passed**
  - Targeted routing/provider checks: **46 passed**
  - Installer smoke check: **passed**
  - Build package: **passed**
  - Overall gate: **PASS**

## Outcome
- Provider selection now rejects malformed primary provider config values and safely normalizes to `chatgpt`.
- No regressions observed; ready for commit/push on `main`.
