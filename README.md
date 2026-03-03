# Clausy

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-experimental-orange)

**Clausy is an OpenAI-compatible LLM proxy that lets agent frameworks talk to browser-based AI systems like ChatGPT and Claude.**

It exposes a standard OpenAI API while internally routing requests to browser-based LLM interfaces using Playwright and Chrome DevTools.

This allows tools that expect an OpenAI API (for example OpenClaw) to work with **web-based AI systems without requiring official API access.**

---

## Why Clausy?

Many powerful AI systems are only accessible through **web interfaces**, while developer tools and agent frameworks expect a **stable API**.

Clausy bridges that gap.

It translates between:

- **OpenAI-compatible APIs** used by tools and agents
- **browser-based AI interfaces** used by modern LLM services

This enables systems that are **independent of any single AI provider**.

---

## Architecture

```
Client / Agent (OpenClaw)
        │
        │  OpenAI API
        ▼
┌─────────────────┐
│     Clausy      │
│   LLM Gateway   │
└────────┬────────┘
         │
         │ Playwright + CDP
         ▼
 ┌───────────────┐
 │ Browser LLMs  │
 │ ChatGPT       │
 │ Claude        │
 │ Gemini (soon) │
 └───────────────┘
```

Clausy behaves like a normal LLM server externally but internally communicates with browser-based AI interfaces.

---

## Features

- OpenAI-compatible endpoint: `POST /v1/chat/completions`
- streaming responses (SSE)
- tool-call passthrough
- tool-call user notification (e.g. `Running tool: exec (ls -la)`)
- per-session browser tabs (`X-Clausy-Session` header)
- secret filtering and leak prevention
- provider abstraction layer (ChatGPT + Claude + Grok + Gemini web providers)

Example tool-call notification:

```
Running tool: exec (ls -la)
```

---

## Supported Providers

Implemented:

- ChatGPT Web
- Claude Web
- Grok Web
- Gemini Web

Implemented:

- Perplexity
- Poe
- DeepSeek Web

---

## How it works

Clausy exposes an **OpenAI-compatible API** to clients.

Internally it communicates with browser LLMs using a simple marker protocol:

```
<<<CONTENT>>>
plain text response (streamed)
```

or

```
<<<TOOLS>>>
```json
{"tool_calls":[...]}
```

For tool calls, `tool_calls[].function.arguments` must be a JSON-encoded **object** string.
Tool calls are collected and returned to the client.

> ⚠️ Experimental. Browser UIs change often. Use at your own risk.

---

## Requirements

- Python 3.10+
- Playwright
- a logged-in browser session for the target LLM

Clausy now performs runtime browser detection and startup:
- tries existing CDP endpoint first (`CLAUSY_CDP_HOST`/`CLAUSY_CDP_PORT`)
- if unavailable, bootstraps Chrome/Chromium automatically by default (`CLAUSY_BROWSER_BOOTSTRAP=auto`)
- supports explicit binary override with `CLAUSY_BROWSER_BINARY`

---

## Install

One-command bootstrap (recommended):

```bash
python -m clausy.install
```

Equivalent manual steps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install .
playwright install chromium
```

`requirements.txt` is kept as a convenience mirror of the canonical dependencies in `pyproject.toml`.

---

## Run

### 1) Start Clausy (auto-bootstrap path)

```bash
python -m clausy
```

On a fresh machine, Clausy will try to connect to CDP first, then auto-launch a detected Chrome/Chromium binary if CDP is not already available.

### Optional: manually start Chrome with remote debugging

This creates an isolated Chrome profile in `./profile` (DO NOT commit it).

```bash
open -na "Google Chrome" --args \
  --remote-debugging-port=9200 \
  --user-data-dir=./profile \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble
```

Log in to the desired AI service once.

### 2) Verify service

```bash
python -m clausy
```

Defaults:

- API: `http://127.0.0.1:3108`
- Provider: ChatGPT Web (`CLAUSY_PROVIDER=chatgpt`)

### Ops probes

- Liveness: `GET /health`
- Readiness: `GET /ready`

Example:

```bash
curl -s http://127.0.0.1:3108/health | jq
curl -s http://127.0.0.1:3108/ready | jq
```

### Docker

Container startup now uses strict runtime precedence:

1. **Attempt host-browser launch path first** (outside container) and probe configured CDP endpoint.
2. If host launch/probe fails, **fallback to local in-container Chromium** and continue.

Container startup still uses `Xvfb + openbox` to provide a Docker-compatible headful display for local Chromium CDP mode.

#### Mode A: External host Chrome (preferred)

Run host Chrome with remote debugging (example on macOS host):

```bash
open -na "Google Chrome" --args \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port=9200 \
  --user-data-dir="$HOME/.clausy-host-profile" \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble
```

Then run Clausy container pointing to host CDP:

```bash
docker build -t clausy .
docker run --rm -p 5000:5000 \
  --add-host=host.docker.internal:host-gateway \
  -e CLAUSY_BIND=0.0.0.0 \
  -e CLAUSY_PORT=5000 \
  -e CLAUSY_CDP_HOST=host.docker.internal \
  -e CLAUSY_CDP_PORT=9200 \
  -e CLAUSY_BROWSER_BOOTSTRAP=auto \
  -e CLAUSY_HOST_BROWSER_LAUNCH_CMD='true' \
  -v "$(pwd)/profile:/app/profile" \
  clausy
```

Notes:
- `CLAUSY_HOST_BROWSER_LAUNCH_CMD` is an optional best-effort command executed by container startup before probing CDP.
- If omitted/unavailable, startup still probes `CLAUSY_CDP_HOST:CLAUSY_CDP_PORT` then falls back automatically.

#### Mode B: Self-contained container Chromium (fallback/standalone)

If external host Chrome is unavailable, startup script launches local Chromium in-container with CDP flags (`--remote-debugging-address/port`, `--user-data-dir`) and proceeds.

You can force this path by setting an unreachable host endpoint (or by leaving host launch command unavailable) and keeping `CLAUSY_BROWSER_BOOTSTRAP=auto`.

### Docker Compose

```bash
docker compose up --build
```

Compose defaults target host Chrome first (`host.docker.internal:9200`) and retain in-container fallback capability automatically.

Operational details: `docs/runbook-browser-runtime.md`.

---

## Quick test

Non-streaming (local default port 3108; use 5000 if running via Docker/Compose):

```bash
curl http://127.0.0.1:3108/v1/chat/completions   -H 'Content-Type: application/json'   -H 'X-Clausy-Session: demo'   -d '{
    "model":"chatgpt-web",
    "stream": false,
    "messages":[{"role":"user","content":"Say hello in one sentence."}]
  }'
```

Streaming (SSE):

```bash
curl -N http://127.0.0.1:3108/v1/chat/completions   -H 'Content-Type: application/json'   -H 'X-Clausy-Session: demo'   -d '{
    "model":"chatgpt-web",
    "stream": true,
    "messages":[{"role":"user","content":"Explain Docker in 3 short sentences."}]
  }'
```

---

## Configuration

Environment variables:

- `CLAUSY_PORT` (default `3108`)
- `CLAUSY_BIND` (default `0.0.0.0`)
- `CLAUSY_PROVIDER` (default `chatgpt`)
- `CLAUSY_AUTO_MODEL_SWITCH` (`0|1`, default `1`): auto-route each request by incoming model id (for example `claude-web` → Claude provider, `openai-api` → OpenAI API provider)
- `CLAUSY_FALLBACK_CHAIN` (optional comma-separated provider names): ordered fallback providers to try when the selected provider fails (example: `ollama,openai,openrouter`)
- `CLAUSY_COST_AWARE_ROUTING` (`0|1`, default `0`): reorder primary+fallback candidates by configured provider cost (lowest first)
- `CLAUSY_PROVIDER_COSTS` (optional comma-separated `provider:cost` map): used when cost-aware routing is enabled (example: `ollama:0.1,openai:2.0,openrouter:3.5`)
- `CLAUSY_CHATGPT_URL` (default `https://chatgpt.com`)
- `CLAUSY_CLAUDE_URL` (default `https://claude.ai`)
- `CLAUSY_GROK_URL` (default `https://grok.com`)
- `CLAUSY_GEMINI_WEB_URL` (default `https://gemini.google.com`)
- `CLAUSY_PERPLEXITY_URL` (default `https://www.perplexity.ai`)
- `CLAUSY_POE_URL` (default `https://poe.com`)
- `CLAUSY_DEEPSEEK_URL` (default `https://chat.deepseek.com`)
- `ALLOW_ANON_BROWSER` (`0|1`, default `0`): when `1`, ChatGPT/Claude/Grok web providers attempt guest/unauth flow first and only return auth error when the page is actually login-blocked.
- `CLAUSY_CDP_HOST` (default `127.0.0.1`)
- `CLAUSY_CDP_PORT` (default `9200`)
- `CLAUSY_PROFILE_DIR` (default `./profile`)
- `CLAUSY_PROFILE_BY_PROVIDER` (optional comma-separated `provider:path` map): switch browser user-data profile automatically by selected web provider (example: `chatgpt:./profile-chatgpt,claude:./profile-claude`)
- `CLAUSY_PROFILE_ROTATION_ENABLED` (`0|1`, default `0`) enables anti-detection profile rotation for browser providers
- `CLAUSY_PROFILE_ROTATION_COUNT` (default `0`) number of rotating profile suffixes (`<profile>-rot1..rotN`); values `0`/`1` disable effective rotation
- `CLAUSY_BROWSER_BOOTSTRAP` (`auto|always|never`, default `auto`)
- `CLAUSY_BROWSER_BINARY` (optional absolute path to Chrome/Chromium binary)
- `CLAUSY_BROWSER_ARGS` (optional extra browser args, space-separated)
- `CLAUSY_CDP_CONNECT_TIMEOUT` (seconds, default `20`; valid range `0.1..300`, invalid values fall back to default)
- `CLAUSY_HOST_BROWSER_LAUNCH_CMD` (optional; startup command executed in container before CDP probe, placeholders supported: `{host}` `{port}` `{profile_dir}`)
- `CLAUSY_CHROME_NO_SANDBOX` (`0|1`, default `0`)
- `CLAUSY_HEADLESS` (`0|1`, default `0`)
- `CLAUSY_SESSION_HEADER` (default `X-Clausy-Session`)
- `CLAUSY_MAX_REPAIRS` (default `2`)
- `CLAUSY_RESET_TURNS` (default `20`)
- `CLAUSY_RESET_SUMMARY_MAX_CHARS` (default `1500`)
- `CLAUSY_BROWSER_RESTART_EVERY_RESETS` (default `0`) restarts the browser connection after N conversation resets (`0` disables)
- `CLAUSY_BROWSER_RESTART_EVERY_REQUESTS` (default `0`) restarts the browser connection after N completed requests per session (`0` disables)
- `CLAUSY_EVENT_LOG_ENABLED` (`0|1`, default `1`) enables in-memory request/response event logging
- `CLAUSY_EVENT_LOG_MAX_ITEMS` (default `500`) ring-buffer size for `/v1/events`
- `CLAUSY_TOOL_PASSWORD` (optional; when set, tool calls are only returned if password header matches)
- `CLAUSY_TOOL_PASSWORD_HEADER` (default `X-Clausy-Tool-Password`)
- `CLAUSY_TOOL_PASSWORD_MESSAGE` (default `Tool execution is password-protected. Provide a valid tool password to continue.`)
- `CLAUSY_BADWORD_FILTER_MODE` (`off|mask|block`, default `off`)
- `CLAUSY_BADWORD_WORDS` (comma-separated words, default empty)
- `CLAUSY_BADWORD_REPLACEMENT` (default `[CENSORED]`)
- `CLAUSY_BADWORD_BLOCK_MESSAGE` (default `Content blocked by safety filter.`)
- `CLAUSY_KEYWORD_ALERTS_ENABLED` (`1|0`, default `0`)
- `CLAUSY_KEYWORD_ALERTS_KEYWORDS` (comma-separated keywords)
- `CLAUSY_KEYWORD_ALERTS_CASE_SENSITIVE` (`1|0`, default `0`)
- `CLAUSY_KEYWORD_ALERTS_WINDOW_SECONDS` (default `300`)
- `CLAUSY_KEYWORD_ALERTS_MAX_PER_WINDOW` (default `1`)
- `CLAUSY_ALERT_TELEGRAM_BOT_TOKEN`, `CLAUSY_ALERT_TELEGRAM_CHAT_ID`, `CLAUSY_ALERT_TELEGRAM_API_BASE`
- `CLAUSY_ALERT_EMAIL_SMTP_HOST`, `CLAUSY_ALERT_EMAIL_SMTP_PORT`, `CLAUSY_ALERT_EMAIL_USERNAME`, `CLAUSY_ALERT_EMAIL_PASSWORD`, `CLAUSY_ALERT_EMAIL_FROM`, `CLAUSY_ALERT_EMAIL_TO`, `CLAUSY_ALERT_EMAIL_STARTTLS`

---

## Secret filtering (optional)

Clausy can filter secrets in both directions:

- **Outbound** (before sending prompts to the web LLM UI)
- **Inbound** (before returning content/tool calls to the client)

Default mode is `smart`:

- Outbound: filters only **known local secrets** collected from ENV and (optionally) `~/.openclaw/**`
- Inbound: filters known local secrets **plus** hard patterns (private keys, Bearer tokens, JWT-like tokens)

Environment variables:

- `CLAUSY_FILTER_MODE=smart|both|outbound|off` (default: `smart`)
- `CLAUSY_FILTER_SCAN_OPENCLAW=1|0` (default: `1`)
- `CLAUSY_FILTER_SCAN_PATHS=~/.openclaw` (comma-separated; default: `~/.openclaw`)
- `CLAUSY_FILTER_MAX_BYTES=2000000`
- `CLAUSY_FILTER_MAX_TAIL=32768`
- `CLAUSY_FILTER_PREFIX_PATTERNS=1|0` (optional paranoia mode)

Notes:

- Your browser profile is **never scanned**
- Clausy masks secrets like `abc…xyz`.

If streaming tail exceeds `CLAUSY_FILTER_MAX_TAIL`, Clausy emits:

```
[FILTERED_MAX_TAIL_REACHED]
```

If a stream ends while holding more than half of a known secret prefix, Clausy emits:

```
[FILTERED_PARTIAL_SECRET_FLUSH]
```

### Child-safe / bad-word filtering

Optional second-stage text filtering can mask or block configured words in outbound responses and web-search snippets.

Set:

- `CLAUSY_BADWORD_FILTER_MODE=off|mask|block`
- `CLAUSY_BADWORD_WORDS=word1,word2,word3`
- `CLAUSY_BADWORD_REPLACEMENT=[CENSORED]` (mask mode)
- `CLAUSY_BADWORD_BLOCK_MESSAGE=Content blocked by safety filter.` (block mode)

### Keyword alerts (optional)

Clausy can notify operators when configured keywords appear in user input, assistant output, or tool-call payloads.

Set:

- `CLAUSY_KEYWORD_ALERTS_ENABLED=1`
- `CLAUSY_KEYWORD_ALERTS_KEYWORDS=token,password,secret`
- `CLAUSY_KEYWORD_ALERTS_CASE_SENSITIVE=0`
- `CLAUSY_KEYWORD_ALERTS_WINDOW_SECONDS=300`
- `CLAUSY_KEYWORD_ALERTS_MAX_PER_WINDOW=1`

Telegram channel:

- `CLAUSY_ALERT_TELEGRAM_BOT_TOKEN=...`
- `CLAUSY_ALERT_TELEGRAM_CHAT_ID=...`
- `CLAUSY_ALERT_TELEGRAM_API_BASE=https://api.telegram.org` (optional)

Email channel:

- `CLAUSY_ALERT_EMAIL_SMTP_HOST=smtp.example.com`
- `CLAUSY_ALERT_EMAIL_SMTP_PORT=587`
- `CLAUSY_ALERT_EMAIL_USERNAME=...`
- `CLAUSY_ALERT_EMAIL_PASSWORD=...`
- `CLAUSY_ALERT_EMAIL_FROM=clausy@example.com`
- `CLAUSY_ALERT_EMAIL_TO=ops@example.com,security@example.com`
- `CLAUSY_ALERT_EMAIL_STARTTLS=1`

Alert transport failures are swallowed and logged so `/v1/chat/completions` responses are never blocked by notifier issues.

---

## Providers (web UI)

Set:

```
CLAUSY_PROVIDER=chatgpt
CLAUSY_PROVIDER=claude
CLAUSY_PROVIDER=grok
CLAUSY_PROVIDER=gemini_web
CLAUSY_PROVIDER=perplexity
CLAUSY_PROVIDER=poe
CLAUSY_PROVIDER=deepseek
```

## Providers (API mode)

Clausy can also proxy direct HTTP providers via OpenAI-compatible `/v1/chat/completions`.

Set one of:

```
CLAUSY_PROVIDER=openai
CLAUSY_PROVIDER=anthropic
CLAUSY_PROVIDER=ollama
CLAUSY_PROVIDER=gemini
CLAUSY_PROVIDER=openrouter
```

Required env vars:

- OpenAI: `CLAUSY_OPENAI_API_KEY`, optional `CLAUSY_OPENAI_BASE_URL`
- Anthropic: `CLAUSY_ANTHROPIC_API_KEY`, optional `CLAUSY_ANTHROPIC_BASE_URL`
- Ollama: optional `CLAUSY_OLLAMA_API_KEY`, optional `CLAUSY_OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`)
- Gemini: `CLAUSY_GEMINI_API_KEY`, optional `CLAUSY_GEMINI_BASE_URL` (default `https://generativelanguage.googleapis.com/v1beta`)
- OpenRouter: `CLAUSY_OPENROUTER_API_KEY`, optional `CLAUSY_OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`), optional `CLAUSY_OPENROUTER_SITE_URL`, optional `CLAUSY_OPENROUTER_APP_NAME`

Notes:
- Non-stream responses are normalized into OpenAI Chat Completions JSON shape.
- Streaming responses are emitted as OpenAI-compatible SSE chunks (`data: ...`, `data: [DONE]`).
- Ollama mode targets native Ollama `/api/chat` and normalizes to OpenAI-compatible responses.
- Browser providers (`chatgpt`, `claude`, `grok`, `gemini_web`, `perplexity`, `poe`, `deepseek`) are unchanged.
- With `CLAUSY_AUTO_MODEL_SWITCH=1`, Clausy can keep one default provider while automatically routing requests by `model` (`chatgpt-web`, `claude-web`, `openai-api`, etc.).
- If `CLAUSY_FALLBACK_CHAIN` is set, Clausy retries providers in that order when the primary provider errors (first successful provider wins).
- If `CLAUSY_COST_AWARE_ROUTING=1`, Clausy reorders the candidate list (`primary + fallback chain`) by `CLAUSY_PROVIDER_COSTS` so cheaper providers are attempted first.
- If `CLAUSY_PROFILE_BY_PROVIDER` is configured, Clausy automatically switches browser profile directories when provider routing changes (for isolated sessions/cookies per provider).
- If `CLAUSY_PROFILE_ROTATION_ENABLED=1` and `CLAUSY_PROFILE_ROTATION_COUNT>1`, Clausy round-robins profile directories per provider (`<base>-rot1..rotN`) to reduce repeated fingerprint/session reuse.
- If `CLAUSY_BROWSER_RESTART_EVERY_REQUESTS` is set to `N>0`, Clausy restarts the browser connection automatically after every N completed requests per session (in addition to `CLAUSY_BROWSER_RESTART_EVERY_RESETS`).

Optional URLs:

- `CLAUSY_CHATGPT_URL=https://chatgpt.com`
- `CLAUSY_CLAUDE_URL=https://claude.ai`
- `CLAUSY_GROK_URL=https://grok.com`
- `CLAUSY_GEMINI_WEB_URL=https://gemini.google.com`
- `CLAUSY_PERPLEXITY_URL=https://www.perplexity.ai`
- `CLAUSY_POE_URL=https://poe.com`
- `CLAUSY_DEEPSEEK_URL=https://chat.deepseek.com`

To inspect selectors:

```bash
python scripts/inspect_ui.py --provider claude
```

---

## OpenClaw setup helper (optional)

If you use OpenClaw and want Clausy to be added as a provider automatically, run:

```bash
# installed CLI (recommended)
clausy-openclaw-install

# module form
python -m clausy.openclaw_install

# repo-local compatibility wrapper
python scripts/openclaw_install_clausy.py
```

This will:

- add a `clausy` provider (default base URL `http://127.0.0.1:5000/v1`, override with `--base-url`)
- set it as the default/primary model
- keep all existing config and save the previous primary under `models.aliases["previous-primary*"]`

Use `--dry-run` to preview changes.

---

## Security notes

- Your Chrome profile contains cookies and session data. Keep it private.
- This project automates third-party web UIs. Consider rate limits and account policies.

---

## Testing

Run all tests offline:

```bash
.venv/bin/python -m pytest -q
```

Run the full release gate (tests + targeted routing/provider checks + install/build smoke):

```bash
scripts/release-gate.sh
```

Run grouped suites:

```bash
# API contract (stream/non-stream + tool-call shape)
.venv/bin/python -m pytest -q -m contract

# profanity + secret filtering behavior
.venv/bin/python -m pytest -q -m filtering

# provider routing behavior
.venv/bin/python -m pytest -q -m routing
```

These tests use local fixtures/test doubles and do not require browser login or network access.

### CI

GitHub Actions workflow: `.github/workflows/ci.yml`

It runs on pushes/PRs and performs:

- offline pytest suite
- package build (`python -m build`)
- import smoke check

## Documentation

- `VISION.md`
- `ROADMAP.md`

---

## License

MIT (see `LICENSE`).


---

## Web Search (optional)

Clausy includes a simple web-search proxy endpoint:

```bash
POST /v1/web_search
```

Providers:
- `brave` (default): requires `BRAVE_SEARCH_API_KEY`
- `google`: requires `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX`

Example:

```bash
curl http://127.0.0.1:3108/v1/web_search \
  -H 'Content-Type: application/json' \
  -d '{"q":"open source llm proxy","provider":"brave","count":5}'
```

Notes:
- Clausy uses **official HTTP APIs**, not scraping.

---

## Web Search

Clausy supports web search via **official APIs** (recommended) and via **browser UI scraping** (best-effort).

### API mode (recommended)

`POST /v1/web_search` with `mode="api"` uses:

- Brave Search API (`provider="brave"`, requires `BRAVE_SEARCH_API_KEY`)
- Google Custom Search JSON API (`provider="google"`, requires `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX`)

### Browser mode (no API keys)

`mode="browser"` opens the provider website in the existing Chrome instance (CDP) and scrapes the results.

Providers:

- `provider="google_web"` (scrapes Google Search results page)
- `provider="brave_web"` (scrapes Brave Search results page)

Example:

```bash
curl http://127.0.0.1:3108/v1/web_search \
  -H 'Content-Type: application/json' \
  -d '{"q":"open source llm proxy","mode":"browser","provider":"google_web","count":5}'
```

Notes:
- Browser scraping is inherently less stable (DOM changes, consent screens).
- Respect provider terms and rate limits.

---

## Realtime event log (optional)

Clausy can expose a lightweight in-memory event feed for observability:

```bash
GET /v1/events?limit=100&since_id=0&session_id=<optional>
```

Returns recent `request` / `response` / `tool_call` events from a ring buffer.
Use this for basic local monitoring and troubleshooting.

For grouped tool-chain visualization per completion request:

```bash
GET /v1/tool_chains?limit=50&since_id=0&session_id=<optional>
```

Each chain is grouped by `request_id` and includes the ordered event timeline.

For flat tool execution traces (one item per `tool_call` event):

```bash
GET /v1/tool_traces?limit=100&since_id=0&session_id=<optional>
```

Each trace includes `request_id`, `tool_count`, and structured `calls` with tool name + arguments excerpt.
