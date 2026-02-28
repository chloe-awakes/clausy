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
- provider abstraction layer (ChatGPT + Claude web providers)

Example tool-call notification:

```
Running tool: exec (ls -la)
```

---

## Supported Providers

Implemented:

- ChatGPT Web
- Claude Web

Planned:

- Gemini
- Grok
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

Tool calls are collected and returned to the client.

> ⚠️ Experimental. Browser UIs change often. Use at your own risk.

---

## Requirements

- Python 3.10+
- Google Chrome (or Chromium) with remote debugging enabled
- Playwright
- a logged-in browser session for the target LLM

---

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## Run

### 1) Start Chrome with remote debugging

This creates an isolated Chrome profile in `./profile` (DO NOT commit it).

```bash
open -na "Google Chrome" --args   --remote-debugging-port=9200   --user-data-dir=./profile   --no-first-run   --no-default-browser-check   --disable-session-crashed-bubble
```

Log in to the desired AI service once.

### 2) Start Clausy

```bash
python -m clausy.server
```

Defaults:

- API: `http://127.0.0.1:3108`
- Provider: ChatGPT Web (`CLAUSY_PROVIDER=chatgpt`)

---

## Quick test

Non-streaming:

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
- `CLAUSY_CHATGPT_URL` (default `https://chatgpt.com`)
- `CLAUSY_CLAUDE_URL` (default `https://claude.ai`)
- `CLAUSY_CDP_HOST` (default `127.0.0.1`)
- `CLAUSY_CDP_PORT` (default `9200`)
- `CLAUSY_PROFILE_DIR` (default `./profile`)
- `CLAUSY_SESSION_HEADER` (default `X-Clausy-Session`)
- `CLAUSY_MAX_REPAIRS` (default `2`)
- `CLAUSY_RESET_TURNS` (default `20`)
- `CLAUSY_RESET_SUMMARY_MAX_CHARS` (default `1500`)
- `CLAUSY_BADWORD_FILTER_MODE` (`off|mask|block`, default `off`)
- `CLAUSY_BADWORD_WORDS` (comma-separated words, default empty)
- `CLAUSY_BADWORD_REPLACEMENT` (default `[CENSORED]`)
- `CLAUSY_BADWORD_BLOCK_MESSAGE` (default `Content blocked by safety filter.`)

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

---

## Providers (web UI)

Set:

```
CLAUSY_PROVIDER=chatgpt
CLAUSY_PROVIDER=claude
```

Optional URLs:

- `CLAUSY_CHATGPT_URL=https://chatgpt.com`
- `CLAUSY_CLAUDE_URL=https://claude.ai`

To inspect selectors:

```bash
python scripts/inspect_ui.py --provider claude
```

---

## OpenClaw setup helper (optional)

If you use OpenClaw and want Clausy to be added as a provider automatically, run:

```bash
python scripts/openclaw_install_clausy.py
```

This will:

- add a `clausy` provider pointing to `http://127.0.0.1:3108/v1`
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
