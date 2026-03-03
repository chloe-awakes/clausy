#!/usr/bin/env python3
"""Inspect a provider UI in an existing Chrome instance (CDP).

Usage:
  python scripts/inspect_ui.py --provider claude
  python scripts/inspect_ui.py --provider chatgpt --cdp-port 9200

Notes:
- Starts no browser. You must run Chrome with --remote-debugging-port and a user-data-dir.
- This prints candidate locators for input/send/output and a short snippet to help tune selectors.
"""
from __future__ import annotations

import argparse
import os
import textwrap
from playwright.sync_api import sync_playwright

from clausy.providers import ProviderRegistry

def _snip(s: str, n: int = 240) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s[:n] + ("…" if len(s) > n else "")

def _env_int(raw: str | None, default: int) -> int:
    try:
        return int(str(raw).strip()) if raw is not None and str(raw).strip() else default
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=os.environ.get("CLAUSY_PROVIDER", "chatgpt"))
    ap.add_argument("--chatgpt-url", default=os.environ.get("CLAUSY_CHATGPT_URL", "https://chatgpt.com"))
    ap.add_argument("--claude-url", default=os.environ.get("CLAUSY_CLAUDE_URL", "https://claude.ai"))
    ap.add_argument("--cdp-host", default=os.environ.get("CLAUSY_CDP_HOST", "127.0.0.1"))
    ap.add_argument("--cdp-port", type=int, default=_env_int(os.environ.get("CLAUSY_CDP_PORT"), 9200))
    args = ap.parse_args()

    reg = ProviderRegistry.default(chatgpt_url=args.chatgpt_url, claude_url=args.claude_url)
    provider = reg.get(args.provider)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://{args.cdp_host}:{args.cdp_port}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        print(f"Provider: {provider.name}")
        print(f"URL: {getattr(provider, 'url', '(n/a)')}")
        provider.ensure_ready(page)

        # Try to locate elements (best-effort by calling provider private helpers when available)
        inp = getattr(provider, "_find_input", lambda p: None)(page)
        send = getattr(provider, "_find_send_button", lambda p: None)(page)
        turns = getattr(provider, "_find_turns", lambda p: None)(page)

        print("\n--- Candidates ---")
        if inp is not None:
            try:
                print("Input:", _snip(inp.first.evaluate("e => e.outerHTML")) if hasattr(inp, "first") else _snip(inp.evaluate("e => e.outerHTML")))
            except Exception:
                print("Input: (found)")
        else:
            print("Input: (not found)")

        if send is not None:
            try:
                print("Send:", _snip(send.evaluate("e => e.outerHTML")))
            except Exception:
                print("Send: (found)")
        else:
            print("Send: (not found)")

        if turns is not None:
            try:
                print("Turns count:", turns.count())
                if turns.count() > 0:
                    last = turns.nth(turns.count()-1)
                    print("Last turn snippet:", _snip(last.inner_text()))
            except Exception:
                print("Turns: (found)")
        else:
            print("Turns: (not found)")

        print("\nTip: If something is '(not found)', open DevTools and inspect the input/button to add a small override selector in the provider.")
        browser.close()

if __name__ == "__main__":
    main()
