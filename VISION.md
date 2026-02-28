
# Clausy Vision

Clausy is a lightweight **OpenAI-compatible LLM proxy** designed to connect agent frameworks (such as OpenClaw) to **browser-based AI systems** like ChatGPT or Claude.

Instead of talking directly to an API, agents interact with Clausy exactly like they would with a normal LLM server. Clausy then forwards requests to different backends — including browser interfaces — while adding filtering, automation, and orchestration capabilities.

---

## The Problem

Modern AI systems increasingly expose their capabilities primarily through **web interfaces rather than public APIs**.

At the same time, agent frameworks and developer tools expect a **stable API endpoint**.

This creates a mismatch:

Agents → expect APIs  
AI systems → provide web interfaces

---

## The Idea

Clausy bridges this gap.

It allows any system that speaks the **OpenAI API protocol** to interact with:

- ChatGPT
- Claude
- Gemini
- Grok
- other browser-based AI systems

without requiring official API access.

Clausy acts as a **universal compatibility layer** between agent frameworks and AI interfaces.

---

## Core Principles

### API Compatibility

Clausy exposes a standard endpoint:

```
/v1/chat/completions
```

Existing tools and agent frameworks can connect without modification.

---

### Browser-based LLM Backends

Clausy can use web interfaces as LLM providers, including:

- ChatGPT Web
- Claude Web
- Gemini Web

This allows interaction with models even when **no official API exists**.

---

### Security-first Design

Clausy includes built-in protections:

- API key detection and filtering
- streaming-safe secret detection
- secret masking across chunk boundaries

This prevents sensitive information from leaking into model responses.

---

### Agent Orchestration Layer

Clausy can serve as a control point between agents and LLMs.

Potential capabilities include:

- tool-call validation
- agent monitoring
- multi-model orchestration
- human approval workflows

---

## Long-term Vision

Instead of building systems around a **single model provider**, developers can build around a **stable interface**.

Clausy decides **which model or backend actually performs the work**.

This enables:

- flexible LLM routing
- browser-based AI access
- secure agent orchestration
