# Milestone Cycle — One-command install (2026-03-02)

## Milestone
Highest-priority unfinished milestone from `ROADMAP.md`:
- Developer Experience: **one-command install**

## Planner
1. Add a single-command installer entrypoint that bootstraps venv + package + Playwright.
2. Add regression tests for install-step construction.
3. Update README install docs and roadmap status.
4. Run targeted tests, then full test suite.
5. If tests fail once, apply immediate follow-up fix and rerun.

## Executor
- Added installer module: `clausy/install.py` with:
  - `build_install_steps(...)`
  - CLI entrypoint `python -m clausy.install`
  - options: `--venv`, `--skip-playwright`, `--dry-run`
- Added script entrypoint in `pyproject.toml`:
  - `clausy-install = "clausy.install:main"`
- Updated docs:
  - `README.md` install section now starts with one-command bootstrap
  - `ROADMAP.md` marks `one-command install` as complete
- Added tests:
  - `tests/test_install_cli.py`

## Tester / Evaluator
- Initial targeted run:
  - `.venv/bin/python -m pytest -q tests/test_install_cli.py`
  - ❌ 1 failed, 1 passed (assertion expected wrong slice)
- Immediate follow-up fix:
  - corrected expected Playwright command structure in `tests/test_install_cli.py`
- Re-run targeted regression:
  - `.venv/bin/python -m pytest -q tests/test_install_cli.py tests/test_models_endpoint.py tests/test_server_filter_provider_regressions.py`
  - ✅ 35 passed
- Full suite:
  - `.venv/bin/python -m pytest -q`
  - ✅ 111 passed

## Outcome
Milestone slice completed in this cycle:
- one-command installer implemented and documented
- roadmap updated
- tests passing end-to-end
