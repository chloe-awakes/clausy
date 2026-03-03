#!/usr/bin/env sh
set -eu

log() {
  printf '%s\n' "[docker-start] $*"
}

probe_cdp() {
  python - "$1" "$2" <<'PY'
import json
import sys
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])
url = f"http://{host}:{port}/json/version"
try:
    with urllib.request.urlopen(url, timeout=1.5) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
    ws = data.get("webSocketDebuggerUrl")
    if not ws:
        raise RuntimeError("missing webSocketDebuggerUrl")
except Exception:
    sys.exit(1)
sys.exit(0)
PY
}

detect_local_browser() {
  python - <<'PY'
from clausy.browser_runtime import detect_browser_binary

playwright_binary = None
try:
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    playwright_binary = pw.chromium.executable_path
    pw.stop()
except Exception:
    playwright_binary = None

binary = detect_browser_binary(playwright_binary=playwright_binary)
print(binary or "")
PY
}

expand_launch_cmd() {
  python - "$1" "$2" "$3" "$4" <<'PY'
import re
import sys

raw, host, port, profile_dir = sys.argv[1:5]
values = {
    "host": host,
    "port": port,
    "profile_dir": profile_dir,
}

unknown = sorted(set(re.findall(r"\{([^{}]+)\}", raw)) - set(values.keys()))
if unknown:
    print(f"unknown placeholders: {', '.join(unknown)}", file=sys.stderr)
    sys.exit(1)

for key, value in values.items():
    raw = raw.replace("{" + key + "}", value)

print(raw)
PY
}

try_launch_host_browser() {
  host="$1"
  port="$2"
  profile_dir="$3"

  # Explicit override command takes precedence.
  # Use placeholders: {host} {port} {profile_dir}
  if [ -n "${CLAUSY_HOST_BROWSER_LAUNCH_CMD:-}" ]; then
    if ! cmd=$(expand_launch_cmd "$CLAUSY_HOST_BROWSER_LAUNCH_CMD" "$host" "$port" "$profile_dir" 2>/tmp/host-browser-launch.log); then
      log "Host-browser launch command rejected (see /tmp/host-browser-launch.log)"
      return 1
    fi
    log "Attempting host-browser launch via CLAUSY_HOST_BROWSER_LAUNCH_CMD"
    if sh -c "$cmd" >/tmp/host-browser-launch.log 2>&1; then
      log "Host-browser launch command returned success"
      return 0
    fi
    log "Host-browser launch command failed (see /tmp/host-browser-launch.log)"
    return 1
  fi

  # Best-effort auto launch path for environments exposing host launcher into container.
  if command -v open >/dev/null 2>&1; then
    log "Attempting host-browser launch via macOS 'open' command"
    if open -ga "Google Chrome" --args \
      --remote-debugging-address="$host" \
      --remote-debugging-port="$port" \
      --user-data-dir="$profile_dir" \
      --no-first-run \
      --no-default-browser-check \
      --disable-session-crashed-bubble \
      >/tmp/host-browser-launch.log 2>&1; then
      log "Host-browser launch via 'open' returned success"
      return 0
    fi
    log "Host-browser launch via 'open' failed (see /tmp/host-browser-launch.log)"
    return 1
  fi

  log "No host-browser launch mechanism available (set CLAUSY_HOST_BROWSER_LAUNCH_CMD to enable)"
  return 1
}

wait_for_cdp() {
  host="$1"
  port="$2"
  attempts="${3:-24}"
  i=0
  until [ "$i" -ge "$attempts" ]; do
    if probe_cdp "$host" "$port"; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.25
  done
  return 1
}

XVFB_DISPLAY="${DISPLAY:-:99}"
export DISPLAY="$XVFB_DISPLAY"

CDP_HOST="${CLAUSY_CDP_HOST:-host.docker.internal}"
CDP_PORT="${CLAUSY_CDP_PORT:-9200}"
PROFILE_DIR="${CLAUSY_PROFILE_DIR:-/app/profile}"
DRY_RUN="${CLAUSY_DOCKER_START_DRY_RUN:-0}"

mkdir -p "$PROFILE_DIR"

if [ "$DRY_RUN" != "1" ]; then
  Xvfb "$DISPLAY" -screen 0 1366x768x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
  openbox >/tmp/openbox.log 2>&1 &
fi

# Strict precedence:
# 1) actively attempt host-browser launch
# 2) probe/connect host CDP
# 3) local in-container Chromium fallback
RUNTIME_MODE="unknown"

log "Step 1/3: attempting host-browser launch path (${CDP_HOST}:${CDP_PORT})"
if try_launch_host_browser "$CDP_HOST" "$CDP_PORT" "$PROFILE_DIR"; then
  log "Host-browser launch attempt finished"
else
  log "Host-browser launch attempt did not succeed; continuing to probe"
fi

log "Step 2/3: probing configured CDP endpoint ${CDP_HOST}:${CDP_PORT}"
if wait_for_cdp "$CDP_HOST" "$CDP_PORT" 24; then
  RUNTIME_MODE="external-host-cdp"
  log "CDP endpoint reachable at ${CDP_HOST}:${CDP_PORT}; mode=external-host"
else
  log "Configured CDP endpoint unreachable after host launch attempt"
  log "Step 3/3: trying local in-container Chromium fallback"
  BROWSER_BINARY="$(detect_local_browser | tr -d '\r')"
  if [ -n "$BROWSER_BINARY" ] && [ -x "$BROWSER_BINARY" ]; then
    RUNTIME_MODE="local-chromium-fallback"
    LOCAL_CDP_HOST="127.0.0.1"
    log "Local browser detected: $BROWSER_BINARY"

    set -- \
      "$BROWSER_BINARY" \
      "--remote-debugging-address=0.0.0.0" \
      "--remote-debugging-port=${CDP_PORT}" \
      "--user-data-dir=${PROFILE_DIR}" \
      "--no-first-run" \
      "--no-default-browser-check" \
      "--disable-session-crashed-bubble" \
      "--disable-dev-shm-usage"

    case "$(printf '%s' "${CLAUSY_CHROME_NO_SANDBOX:-}" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes|on)
        set -- "$@" "--no-sandbox"
        ;;
    esac

    case "$(printf '%s' "${CLAUSY_HEADLESS:-}" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes|on)
        set -- "$@" "--headless=new" "--disable-gpu"
        ;;
    esac

    if [ "$DRY_RUN" = "1" ]; then
      log "DRY_RUN=1, would start local browser: $*"
      export CLAUSY_CDP_HOST="$LOCAL_CDP_HOST"
    else
      "$@" >/tmp/local-browser.log 2>&1 &
      export CLAUSY_CDP_HOST="$LOCAL_CDP_HOST"
      if wait_for_cdp "$CLAUSY_CDP_HOST" "$CDP_PORT" 40; then
        log "Local browser CDP is ready at ${CLAUSY_CDP_HOST}:${CDP_PORT}"
      else
        log "Local browser started but CDP readiness probe is still failing; Clausy will apply bootstrap policy"
      fi
    fi
  else
    RUNTIME_MODE="cdp-unavailable-no-local-browser"
    log "No local browser found for fallback; Clausy will handle bootstrap policy"
  fi
fi

log "runtime mode selected: $RUNTIME_MODE"

if [ "$DRY_RUN" = "1" ]; then
  log "DRY_RUN=1, skipping Clausy process start"
  exit 0
fi

exec python -m clausy
