#!/usr/bin/env bash
set -euo pipefail

curl http://127.0.0.1:3108/v1/chat/completions   -H 'Content-Type: application/json'   -H 'X-Clausy-Session: demo'   -d '{
    "model":"chatgpt-web",
    "stream": false,
    "messages":[{"role":"user","content":"Say hello in one sentence."}]
  }'
