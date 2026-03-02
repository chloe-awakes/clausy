# 2026-03-02 release gate hardening cycle

## Milestone selected (highest-priority unfinished)
After roadmap completion, the next release-hardening slice is to make revalidation repeatable with a single command and capture evidence.

## Planner
1. Add a reusable release gate script covering full tests, targeted routing/provider checks, installer smoke, and package build.
2. Document the command for operators/contributors.
3. Run the gate and record evidence.
4. Commit/push on `main`.

## Executor
- Added `scripts/release-gate.sh`.
- Documented usage in `README.md` (Testing section).

## Tester/Evaluator
- `scripts/release-gate.sh`
  - Full suite: **113 passed**
  - Targeted routing/provider checks: **40 passed**
  - Installer smoke (`clausy.install --dry-run`): **passed**
  - Build package (`python -m build`): **passed**

## Outcome
- Release gate is now a one-command, repeatable check.
- Evidence captured; ready to commit/push.
