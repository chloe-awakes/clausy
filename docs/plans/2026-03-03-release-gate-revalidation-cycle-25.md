# Release Gate Revalidation Cycle 25

Date: 2026-03-03 07:33 (Europe/Berlin)

## Scope
Immediate continuation on latest `main`: add CI parity by executing the same local release gate entrypoint (`scripts/release-gate.sh`) in CI, then re-run the gate locally and record evidence.

## Planner
- Add a CI workflow step that invokes `scripts/release-gate.sh` directly (single-source local/CI gate logic).
- Ensure CI prepares the same expected runtime (`.venv` + `pip install -e '.[dev]'`).
- Re-run local release gate and capture outcomes.

## Executor
- Added `.github/workflows/ci.yml` with `push`/`pull_request` triggers.
- CI job provisions Python 3.12, creates `.venv`, installs `-e '.[dev]'`, and runs:
  - `scripts/release-gate.sh`
- This keeps gate behavior centralized in one script for both local and CI paths.

## Tester/Evaluator
- Local post-change run (`scripts/release-gate.sh`):
  - Full suite: **180 passed, 8 subtests passed**
  - Targeted routing/provider checks: **54 passed**
  - Installer smoke check: **passed**
  - Build package: **passed**
  - Overall gate: **PASS**

## Outcome
- CI now executes the same release-gate script used locally, reducing drift risk.
- Release gate remains green after the CI parity addition.
