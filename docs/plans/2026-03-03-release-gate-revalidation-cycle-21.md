# Release Gate Revalidation Cycle 21

Date: 2026-03-03 05:44 (Europe/Berlin)

## Scope
Provider/routing/runtime hardening follow-up focused on cost-aware routing input sanitation.

## Planner
- Identify a high-value hardening edge case in provider routing.
- Add regression coverage first for malformed/unsafe provider cost values.
- Implement minimal runtime guard and re-run the full release gate.

## Executor
- Added provider-cost sanitation in `clausy/server.py`:
  - ignore non-finite values (`NaN`, `inf`)
  - ignore negative costs
- Added regression test:
  - `ModelSwitchingRegressionTests.test_provider_candidates_ignore_non_finite_or_negative_costs`

## Tester/Evaluator
- Targeted test run:
  - `tests/test_server_filter_provider_regressions.py::ModelSwitchingRegressionTests::test_provider_candidates_ignore_non_finite_or_negative_costs`
  - **passed**
- Release gate run (`scripts/release-gate.sh`):
  - Full suite: **116 passed**
  - Targeted routing/provider checks: **41 passed**
  - Installer smoke check: **passed**
  - Build package: **passed**
  - Overall gate: **PASS**

## Outcome
- Cost-aware provider routing is now robust against malformed or adversarial numeric cost config values.
- No regressions observed; ready for commit/push on `main`.
