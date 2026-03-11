# Anonymous provider validation summary — 2026-03-11

Canonical report: `docs/provider-anon-validation-2026-03-11.md`

Final classifications from live browser evidence:

- ChatGPT: works anonymously
- Gemini: works anonymously
- Grok: blocked by captcha/anti-bot (`High Demand` gate on submit)
- Claude: blocked by login
- Perplexity: blocked by login
- Poe: blocked by captcha/anti-bot (login + reCAPTCHA)
- DeepSeek: blocked by login

Clausy end-to-end verification on an anonymous-working provider:

- ChatGPT plain-text path: PASS
- ChatGPT fenced `tool call` path: FAIL

Verification gate for touched code/docs:

```bash
./.venv/bin/python -m pytest -q tests/test_anon_browser_toggle.py tests/test_provider_registry.py
```

Observed:

```text
26 passed in 0.01s
```
