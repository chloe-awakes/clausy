#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="clausy:novnc-smoke"
CONTAINER_NAME="clausy-novnc-smoke-$$"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[smoke] building $IMAGE_TAG"
docker build -t "$IMAGE_TAG" .

echo "[smoke] starting container $CONTAINER_NAME"
docker run -d --name "$CONTAINER_NAME" \
  -p 127.0.0.1:3108:5000 \
  -p 127.0.0.1:6080:6080 \
  -e CLAUSY_BIND=0.0.0.0 \
  -e CLAUSY_PORT=5000 \
  -e CLAUSY_NOVNC_PORT=6080 \
  -e CLAUSY_VNC_PORT=5900 \
  "$IMAGE_TAG" >/dev/null

wait_for() {
  local name="$1"
  local cmd="$2"
  local tries="${3:-40}"
  local sleep_s="${4:-1}"
  local i
  for ((i=1; i<=tries; i++)); do
    if eval "$cmd" >/dev/null 2>&1; then
      echo "[smoke] $name ready"
      return 0
    fi
    sleep "$sleep_s"
  done
  echo "[smoke] $name check failed after $tries attempts"
  return 1
}

wait_for "api health" "curl -fsS http://127.0.0.1:3108/health"
wait_for "noVNC" "curl -fsS http://127.0.0.1:6080/vnc.html | grep -qi novnc"

echo "[smoke] API response"
curl -fsS http://127.0.0.1:3108/health

echo "[smoke] noVNC title probe"
curl -fsS http://127.0.0.1:6080/vnc.html | head -n 5

echo "[smoke] success"
