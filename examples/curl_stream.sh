#!/usr/bin/env bash
set -euo pipefail

curl -N http://127.0.0.1:3108/v1/chat/completions   -H 'Content-Type: application/json'   -H 'X-Clausy-Session: demo'   -d '{
    "model":"chatgpt-web",
    "stream": true,
    "messages":[{"role":"user","content":"Explain Docker in 3 short sentences."}]
  }'
