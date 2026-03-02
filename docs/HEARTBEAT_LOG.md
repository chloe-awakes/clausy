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

## 2026-03-02 07:19 (Europe/Berlin)

### Milestone selected (highest-priority unfinished)
Browser LLM Providers → **DeepSeek Web** integration.

### Planner
- Confirmed next unfinished highest-priority roadmap item was `DeepSeek Web`.
- Planned vertical slice:
  1. Add `DeepSeekWebProvider` adapter.
  2. Wire provider into default registry and exports.
  3. Add env URL and model mapping in `/v1/models`.
  4. Extend regression tests.
  5. Update docs and roadmap status.

### Executor
- Added `clausy/providers/deepseek.py` (ChatGPT-style adapter with DeepSeek-focused selectors).
- Wired DeepSeek through:
  - `clausy/providers/registry.py` (`deepseek_url`, provider registration)
  - `clausy/providers/__init__.py`
  - `clausy/server.py` (`CLAUSY_DEEPSEEK_URL`, registry wiring, `/v1/models` mapping to `deepseek-web`)
- Updated docs/config:
  - `.env.example`
  - `README.md` (supported providers + env vars)
  - `ROADMAP.md` (`DeepSeek Web` now checked)
- Extended regression coverage:
  - `tests/test_models_endpoint.py` checks `deepseek -> deepseek-web`
  - `tests/test_server_filter_provider_regressions.py` asserts default registry includes `deepseek`

### Tester/Evaluator
- First targeted run (after adding tests before implementation):
  - `.venv/bin/python -m pytest -q tests/test_models_endpoint.py tests/test_server_filter_provider_regressions.py`
  - **1 failed, 13 passed** (`deepseek` missing in default registry)
- Follow-up fix applied immediately: registry wiring + server model/env updates + provider class.
- Re-run targeted regression:
  - `.venv/bin/python -m pytest -q tests/test_models_endpoint.py tests/test_server_filter_provider_regressions.py`
  - **14 passed**
- Full suite run:
  - `.venv/bin/python -m pytest -q`
  - **83 passed**

### Outcome
- Milestone slice passed and is ready for commit/push.

## 2026-03-02 07:47 (Europe/Berlin)

### Milestone selected (highest-priority unfinished)
Conversation Management → **automatic chat rotation + conversation summarization hardening**.

### Planner
- Confirmed next highest-priority unfinished milestone in `ROADMAP.md` is Conversation Management.
- Chose smallest releasable slice already present in runtime but lacking regression evidence:
  1. Add regression tests for `_post_turn_housekeeping` threshold gating.
  2. Add regression tests for summarize + rotate + turn counter reset behavior.
  3. Add regression test for fallback to `browser.reset_page` when provider "new chat" action fails.
  4. Mark roadmap checkboxes for proven capabilities.

### Executor
- Added `ConversationManagementRegressionTests` in `tests/test_server_filter_provider_regressions.py`:
  - skip housekeeping below threshold,
  - summarize + rotate + reset counter at threshold,
  - fallback page reset when `start_new_chat` fails.
- Updated `ROADMAP.md`:
  - checked `automatic chat rotation`
  - checked `conversation summarization`
  - kept `browser restart after N chats` unchecked.

### Tester/Evaluator
- Targeted regression run:
  - `.venv/bin/python -m pytest -q tests/test_server_filter_provider_regressions.py tests/test_models_endpoint.py`
  - **17 passed**

### Outcome
- Milestone slice passed and is ready for commit/push.

## 2026-03-02 08:20 (Europe/Berlin)

### Milestone selected (highest-priority unfinished)
Observability → **realtime agent logging**.

### Planner
- Confirmed next highest-priority unchecked roadmap item is `realtime agent logging`.
- Planned smallest shippable slice:
  1. Add in-memory event ring buffer and config flags.
  2. Log request/response lifecycle events for `/v1/chat/completions`.
  3. Expose `GET /v1/events` endpoint with `limit/since_id/session_id` filters.
  4. Add regression coverage for event emission/query semantics.
  5. Update docs and roadmap checkbox.

### Executor
- Added event-log runtime in `clausy/server.py`:
  - env config `CLAUSY_EVENT_LOG_ENABLED`, `CLAUSY_EVENT_LOG_MAX_ITEMS`
  - thread-safe ring buffer (`deque`) + monotonic event IDs
  - helper `_log_event(...)` and endpoint `GET /v1/events`
- Wired request/response event emission for API and browser-backed `/v1/chat/completions` paths.
- Updated docs/config:
  - `.env.example` (new event log vars)
  - `README.md` (config + endpoint docs)
  - `ROADMAP.md` (`realtime agent logging` checked)
- Added tests in `tests/test_server_filter_provider_regressions.py`:
  - request+response events emitted for non-stream chat completion
  - `/v1/events` supports `since_id` + `limit` behavior

### Tester/Evaluator
- Targeted regression run:
  - `.venv/bin/python -m pytest -q tests/test_server_filter_provider_regressions.py tests/test_models_endpoint.py`
- Full suite run:
  - `.venv/bin/python -m pytest -q`

### Outcome
- Milestone slice implemented; validation results below determine commit/push readiness.

## 2026-03-02 08:49 (Europe/Berlin)

### Milestone selected (highest-priority unfinished)
Conversation Management → **browser restart after N chats**.

### Planner
- Confirmed next highest-priority unchecked roadmap item was `browser restart after N chats`.
- Planned minimal vertical slice:
  1. Add configurable restart threshold after conversation resets.
  2. Track per-session reset count.
  3. Trigger browser restart when threshold is reached.
  4. Add regression coverage for threshold and restart behavior.
  5. Update docs/config and roadmap checkbox.

### Executor
- Added server config/env support:
  - `CLAUSY_BROWSER_RESTART_EVERY_RESETS` (default `0`, disabled)
  - per-session metadata field `resets_since_restart`
- Extended housekeeping logic in `clausy/server.py`:
  - increments reset counter after each rotation
  - restarts browser session when configured threshold is met
  - resets counter to `0` post-restart
- Added `BrowserPool.restart_session(session_id)` in `clausy/browser.py` to re-establish browser connection and reopen a clean session tab.
- Updated docs/config:
  - `.env.example`
  - `README.md`
  - `ROADMAP.md` (`browser restart after N chats` checked)
- Added/updated tests in `tests/test_server_filter_provider_regressions.py`:
  - reset counter increments without restart by default
  - restart triggers exactly at configured threshold
  - fallback path still resets page and counter updates

### Tester/Evaluator
- Targeted regression run:
  - `.venv/bin/python -m pytest -q tests/test_server_filter_provider_regressions.py tests/test_models_endpoint.py`
  - **20 passed**
- Full suite run:
  - `.venv/bin/python -m pytest -q`
  - **89 passed**

### Outcome
- Milestone slice passed and is ready for commit/push.
