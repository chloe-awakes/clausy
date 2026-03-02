# Heartbeat Execution Log

## 2026-03-02 06:49 (Europe/Berlin)

### Milestone selected (highest-priority unfinished)
Browser LLM Providers → **Poe** integration.

### Planner
- Confirmed first unchecked item in `ROADMAP.md` was `Poe`.
- Planned minimal vertical slice:
  1. Add `PoeWebProvider` adapter.
  2. Register provider in runtime registry and env config.
  3. Expose model id in `/v1/models`.
  4. Add regression coverage.
  5. Update docs and roadmap checkbox.

### Executor
- Added `clausy/providers/poe.py` (ChatGPT-style adapter with Poe selectors/fallbacks).
- Wired Poe provider through:
  - `clausy/providers/registry.py`
  - `clausy/providers/__init__.py`
  - `clausy/server.py` (`CLAUSY_POE_URL`, provider registry wiring, model mapping to `poe-web`)
- Updated config/docs:
  - `.env.example`
  - `README.md`
  - `ROADMAP.md` (`Poe` now checked)
- Added/updated tests:
  - `tests/test_models_endpoint.py` adds Poe model assertion
  - `tests/test_server_filter_provider_regressions.py` ensures default registry includes Poe

### Tester/Evaluator
- Targeted regression run:
  - `.venv/bin/python -m pytest -q tests/test_models_endpoint.py tests/test_server_filter_provider_regressions.py`
  - **13 passed**
- Full suite run:
  - `.venv/bin/python -m pytest -q`
  - **82 passed**

### Outcome
- Milestone slice passed and is ready for commit/push.
