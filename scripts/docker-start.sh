#!/usr/bin/env sh
set -eu

XVFB_DISPLAY="${DISPLAY:-:99}"
export DISPLAY="$XVFB_DISPLAY"

Xvfb "$DISPLAY" -screen 0 1366x768x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
openbox >/tmp/openbox.log 2>&1 &

exec python -m clausy
