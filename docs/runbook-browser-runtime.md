# Browser Runtime Runbook

## Fresh machine behavior

On startup, Clausy performs browser runtime checks in this order:

1. Try to connect to `http://$CLAUSY_CDP_HOST:$CLAUSY_CDP_PORT`
2. If unavailable and bootstrap enabled (`CLAUSY_BROWSER_BOOTSTRAP=auto|always`), detect browser binary
3. Launch Chrome/Chromium with deterministic CDP flags and retry connection
4. If still unavailable, fail fast with actionable guidance

## Key flags

- `CLAUSY_BROWSER_BOOTSTRAP=auto|always|never` (default: `auto`)
- `CLAUSY_BROWSER_BINARY=/absolute/path/to/chrome` (optional override)
- `CLAUSY_BROWSER_ARGS="--arg1 --arg2"` (optional extra browser args)
- `CLAUSY_CDP_CONNECT_TIMEOUT=20` seconds
- `CLAUSY_CHROME_NO_SANDBOX=1` (only for constrained runtimes)
- `CLAUSY_HEADLESS=0|1`

## Docker/headful-CDP strategy

The Docker image launches:

- `Xvfb` virtual display (`:99`)
- `openbox` window manager
- `python -m clausy`

This allows headful Chromium with CDP in containerized environments.

## Failure modes and actions

- **`bootstrap is disabled`**: start Chrome manually with `--remote-debugging-port` or set `CLAUSY_BROWSER_BOOTSTRAP=auto`
- **`no Chrome/Chromium binary was found`**: set `CLAUSY_BROWSER_BINARY` or install with `python -m playwright install chromium`
- **CDP timeout after bootstrap**: raise `CLAUSY_CDP_CONNECT_TIMEOUT`, inspect container logs (`/tmp/xvfb.log`, `/tmp/openbox.log`)
