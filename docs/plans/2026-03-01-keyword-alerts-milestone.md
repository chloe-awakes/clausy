# Keyword Alerts (Email/Telegram) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement configurable keyword-alerting for suspicious content so Clausy can notify operators via Telegram/email when matched terms appear in requests/responses/tool calls.

**Architecture:** Add a small alerting module that (1) parses env config, (2) detects keyword hits in selected text surfaces, (3) rate-limits duplicate alerts per session/keyword, and (4) delivers notifications via Telegram Bot API and SMTP email. Integrate this into `server.py` after request parsing and after parsed completion output (including tool calls), while keeping alert failures non-blocking.

**Tech Stack:** Python stdlib (`smtplib`, `email.message`, `time`, `threading`) + existing `requests` dependency.

---

## Milestone Selection Rationale

Highest-priority unfinished milestone for release-readiness is **Security & Filtering → keyword alerts (email / telegram)**:
- It is explicitly listed in `ROADMAP.md` under security.
- Security/operator visibility is more release-critical than new providers/features.
- Adjacent mechanisms (secret filtering, bad-word filter, tool-password gating) already exist, making this an incremental, high-impact completion.

---

### Task 1: Add alerting config + detector module

**Files:**
- Create: `clausy/alerts.py`
- Test: `tests/test_keyword_alerts.py`

**Step 1: Write failing config parse tests**
- `test_alert_config_disabled_by_default`
- `test_alert_config_parses_keywords_and_channels`
- `test_alert_config_rejects_empty_keywords`

**Step 2: Run tests to verify failures**
Run: `pytest -q tests/test_keyword_alerts.py -k config`
Expected: FAIL (module/symbols missing)

**Step 3: Implement minimal config model + parser**
- `KeywordAlertConfig` dataclass with:
  - `enabled`, `keywords`, `case_sensitive`, `max_alerts_per_window`, `window_seconds`
  - telegram settings (`bot_token`, `chat_id`, `api_base`)
  - smtp settings (`host`, `port`, `username`, `password`, `from_addr`, `to_addrs`, `starttls`)
- `load_keyword_alert_config_from_env()`

**Step 4: Re-run config tests**
Run: `pytest -q tests/test_keyword_alerts.py -k config`
Expected: PASS

**Step 5: Commit**
`git commit -m "feat(alerts): add keyword alert config parsing"`

---

### Task 2: Add keyword matching + dedupe/rate limiting

**Files:**
- Modify: `clausy/alerts.py`
- Test: `tests/test_keyword_alerts.py`

**Step 1: Write failing detector tests**
- `test_detector_matches_case_insensitive_by_default`
- `test_detector_respects_case_sensitive_mode`
- `test_detector_returns_matched_keywords_once`
- `test_rate_limiter_suppresses_duplicates_within_window`

**Step 2: Run tests to verify failures**
Run: `pytest -q tests/test_keyword_alerts.py -k detector`
Expected: FAIL

**Step 3: Implement detector + limiter**
- `KeywordDetector.match(text) -> list[str]`
- `AlertRateLimiter.should_send(session_id, keyword, now)`

**Step 4: Re-run detector tests**
Run: `pytest -q tests/test_keyword_alerts.py -k detector`
Expected: PASS

**Step 5: Commit**
`git commit -m "feat(alerts): add keyword detection and rate limiting"`

---

### Task 3: Add Telegram + email notifier transports

**Files:**
- Modify: `clausy/alerts.py`
- Test: `tests/test_keyword_alerts.py`

**Step 1: Write failing notifier tests**
- `test_telegram_notifier_posts_message` (mock `requests.post`)
- `test_email_notifier_sends_message` (mock `smtplib.SMTP`)
- `test_notifier_failures_do_not_raise`

**Step 2: Run tests to verify failures**
Run: `pytest -q tests/test_keyword_alerts.py -k notifier`
Expected: FAIL

**Step 3: Implement notifiers**
- `TelegramNotifier.send(alert)`
- `EmailNotifier.send(alert)`
- `AlertDispatcher` fan-out to enabled channels, swallow/log transport exceptions

**Step 4: Re-run notifier tests**
Run: `pytest -q tests/test_keyword_alerts.py -k notifier`
Expected: PASS

**Step 5: Commit**
`git commit -m "feat(alerts): add telegram and email transports"`

---

### Task 4: Integrate alerting into chat pipeline

**Files:**
- Modify: `clausy/server.py`
- Modify: `clausy/__init__.py` (if exports needed)
- Test: `tests/test_server_filter_provider_regressions.py`
- Test: `tests/test_chat_completions_contracts.py`

**Step 1: Write failing integration tests**
- Alert on matched inbound user message keyword
- Alert on matched assistant content keyword (non-stream)
- Alert on matched tool-call payload keyword
- No duplicate alerts during window
- No API response regression if alert transport fails

**Step 2: Run targeted tests to verify failures**
Run: `pytest -q tests/test_server_filter_provider_regressions.py -k alert`
Expected: FAIL

**Step 3: Implement minimal integration in `server.py`**
- Initialize alert config/services once at module load
- Build candidate texts:
  - user messages from incoming request
  - parsed assistant content
  - serialized tool calls
- On match, dispatch alert asynchronously or inline non-blocking path
- Include metadata: session id, provider, matched keywords, direction (`request|response|tool_call`), short excerpt

**Step 4: Re-run integration tests**
Run: `pytest -q tests/test_server_filter_provider_regressions.py -k alert`
Expected: PASS

**Step 5: Commit**
`git commit -m "feat(server): integrate keyword alerts in chat pipeline"`

---

### Task 5: Docs + env examples + release verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `ROADMAP.md`

**Step 1: Write failing/docs validation checks**
- Ensure env vars documented in README and `.env.example`
- Mark roadmap item complete

**Step 2: Implement docs updates**
Add env vars:
- `CLAUSY_KEYWORD_ALERTS_ENABLED=1|0`
- `CLAUSY_KEYWORD_ALERTS_KEYWORDS=token,password,secret`
- `CLAUSY_KEYWORD_ALERTS_CASE_SENSITIVE=0|1`
- `CLAUSY_KEYWORD_ALERTS_WINDOW_SECONDS=300`
- `CLAUSY_KEYWORD_ALERTS_MAX_PER_WINDOW=1`
- Telegram: `CLAUSY_ALERT_TELEGRAM_BOT_TOKEN`, `CLAUSY_ALERT_TELEGRAM_CHAT_ID`, `CLAUSY_ALERT_TELEGRAM_API_BASE`
- Email: `CLAUSY_ALERT_EMAIL_SMTP_HOST`, `CLAUSY_ALERT_EMAIL_SMTP_PORT`, `CLAUSY_ALERT_EMAIL_USERNAME`, `CLAUSY_ALERT_EMAIL_PASSWORD`, `CLAUSY_ALERT_EMAIL_FROM`, `CLAUSY_ALERT_EMAIL_TO`, `CLAUSY_ALERT_EMAIL_STARTTLS`

**Step 3: Full verification run**
Run: `.venv/bin/python -m pytest -q`
Expected: PASS

**Step 4: Commit**
`git commit -m "docs: document keyword alerting and mark roadmap milestone done"`

---

## Executor Brief

Implement **Keyword Alerts (email + telegram)** exactly as above, with strict TDD order:
1. `clausy/alerts.py` foundation (config + detector + limiter + notifiers)
2. `server.py` integration points for request/response/tool-call scanning
3. docs and roadmap completion

Guardrails:
- Alerting must never break `/v1/chat/completions` responses.
- Keep all network failures in notifier path swallowed/logged.
- Avoid extra dependencies beyond stdlib + current `requests`.
- Keep changes DRY and minimally invasive.

**Executor Done Criteria**
- New tests in `tests/test_keyword_alerts.py` pass.
- Integration alert tests pass.
- Existing contract/filter/routing tests still pass.
- README + `.env.example` + ROADMAP updated.
- No regression in stream/non-stream API behavior.

---

## Tester Brief

Validate implementation as release gate for this milestone.

### Functional checks
- Keyword hits in user input trigger exactly one alert per window/session.
- Keyword hits in assistant content trigger alerts.
- Keyword hits inside tool-call args trigger alerts.
- Case-sensitive and case-insensitive behavior matches config.
- No duplicate spam within limiter window.

### Reliability checks
- Simulate Telegram failure and SMTP failure; API response still succeeds.
- Confirm no uncaught exceptions in logs from alerting path.
- Confirm disabled mode produces zero alert attempts.

### Regression checks
Run:
- `.venv/bin/python -m pytest -q -m contract`
- `.venv/bin/python -m pytest -q -m filtering`
- `.venv/bin/python -m pytest -q -m routing`
- `.venv/bin/python -m pytest -q`

**Tester Done Criteria**
- All above commands pass.
- Manual spot-check confirms alert metadata includes session id, provider, keyword, direction, excerpt.
- `ROADMAP.md` marks keyword alerts complete.
- Milestone can be declared release-ready from security-alerting standpoint.
