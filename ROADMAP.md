
# Clausy Roadmap

## Core Architecture

- [x] OpenAI-compatible Chat Completions API proxy
- [x] SSE streaming responses
- [x] Tool-call passthrough for OpenClaw
- [x] Tool-call user notification (e.g. "Running tool: exec (ls -la)")

---

## Security & Filtering

- [x] API key detection and filtering
- [x] Streaming-safe secret detection
- [x] Tail-buffer algorithm for chunk-boundary detection
- [x] Fail-safe streaming policies

Planned:

- [ ] child-safe / bad-word filtering
- [ ] keyword alerts (email / telegram)
- [ ] password-protected tool execution

---

## Browser LLM Providers

Implemented:

- [x] ChatGPT Web provider
- [x] Claude Web provider

Planned:

- [ ] Gemini
- [ ] Grok
- [ ] Perplexity
- [ ] Poe
- [ ] DeepSeek Web

---

## Conversation Management

Planned:

- [ ] automatic chat rotation
- [ ] conversation summarization
- [ ] browser restart after N chats

---

## Observability

Planned:

- [ ] realtime agent logging
- [ ] tool-chain visualization
- [ ] execution traces for tool calls

---

## Model Control

Planned:

- [ ] automatic model switching
- [ ] fallback chains (local → cloud → backup)
- [ ] cost-aware routing

---

## Browser Automation

Planned:

- [ ] automatic browser profile switching
- [ ] automatic browser restart
- [ ] anti-detection profile rotation

---

## LLM Connectivity

Already supported:

- [x] browser-based LLM backends

Planned:

- [ ] OpenAI API
- [ ] Anthropic API
- [ ] Gemini API
- [ ] OpenRouter
- [ ] Ollama

---

## Web Search Integration

Planned:

- [ ] web search proxy

Possible backends:

- Brave
- SearX
- Tavily
- Perplexity

---

## Developer Experience

Completed:

- [x] GitHub-ready project structure
- [x] installable Python project

Planned:

- [ ] Docker image
- [ ] one-command install
- [ ] pip package
