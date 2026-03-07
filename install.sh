#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-${0:-}}"
if [[ -n "${SCRIPT_PATH}" && -f "${SCRIPT_PATH}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
else
  SCRIPT_DIR="$(pwd)"
fi

REPO_ROOT="${SCRIPT_DIR}"
GIT_PACKAGE_URL="git+https://github.com/chloe-awakes/clausy.git"
VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

DOCKER_MODE=0
DRY_RUN=0
NO_SERVICE=0
NO_BROWSER=0
PATH_PERSISTED=0
SHIM_STATUS="not-attempted"
SHIM_PATH=""
SHIM_ON_PATH=0
SHIM_CANDIDATE_PATHS=(
  "/usr/local/bin"
  "/opt/homebrew/bin"
  "/usr/bin"
  "${HOME}/.local/bin"
)

HEALTH_ENDPOINT="${CLAUSY_HEALTH_ENDPOINT:-http://127.0.0.1:3108/health}"
HEALTH_RETRY_ATTEMPTS="${CLAUSY_HEALTH_RETRY_ATTEMPTS:-8}"
HEALTH_RETRY_DELAY_SECONDS="${CLAUSY_HEALTH_RETRY_DELAY_SECONDS:-1}"
HEALTHCHECK_CONNECT_TIMEOUT_SECONDS="${CLAUSY_HEALTHCHECK_CONNECT_TIMEOUT_SECONDS:-1.5}"
HEALTHCHECK_READ_TIMEOUT_SECONDS="${CLAUSY_HEALTHCHECK_READ_TIMEOUT_SECONDS:-2.5}"

TTY_PROMPT_FD=""

init_prompt_fd() {
  if [[ -t 0 ]]; then
    TTY_PROMPT_FD="0"
    return 0
  fi
  if [[ -r /dev/tty ]]; then
    exec 3</dev/tty
    TTY_PROMPT_FD="3"
    return 0
  fi
  TTY_PROMPT_FD=""
  return 1
}

is_interactive() {
  [[ -n "${TTY_PROMPT_FD}" && -t 1 ]]
}

prompt_read() {
  local __var_name="$1"
  local __prompt="$2"
  local __value=""
  if [[ -z "${TTY_PROMPT_FD}" ]]; then
    printf -v "${__var_name}" '%s' ""
    return 1
  fi

  if [[ "${TTY_PROMPT_FD}" == "0" ]]; then
    read -r -p "${__prompt}" __value || true
  else
    read -r -u "${TTY_PROMPT_FD}" -p "${__prompt}" __value || true
  fi
  printf -v "${__var_name}" '%s' "${__value}"
  return 0
}

path_contains_dir() {
  local candidate_dir="$1"
  local old_ifs="${IFS}"
  local path_part=""
  IFS=':'
  for path_part in ${PATH:-}; do
    if [[ "${path_part}" == "${candidate_dir}" ]]; then
      IFS="${old_ifs}"
      return 0
    fi
  done
  IFS="${old_ifs}"
  return 1
}

append_path_to_shell_rc() {
  local path_entry="$1"
  local shell_name
  shell_name="$(basename "${SHELL:-}")"

  local rc_file=""
  local line=""

  case "$shell_name" in
    zsh)
      rc_file="${HOME}/.zshrc"
      line="export PATH=\"${path_entry}:\$PATH\""
      ;;
    bash)
      rc_file="${HOME}/.bashrc"
      line="export PATH=\"${path_entry}:\$PATH\""
      ;;
    fish)
      rc_file="${HOME}/.config/fish/config.fish"
      line="set -gx PATH \"${path_entry}\" \$PATH"
      ;;
    *)
      echo "Unsupported shell '${shell_name}'. Add this to your shell config manually:" >&2
      echo "  export PATH=\"${path_entry}:\$PATH\"" >&2
      return 1
      ;;
  esac

  mkdir -p "$(dirname "${rc_file}")"
  touch "${rc_file}"

  if grep -Fqs "${path_entry}" "${rc_file}"; then
    echo "PATH already contains Clausy venv in ${rc_file}"
    return 0
  fi

  printf '\n%s\n' "${line}" >> "${rc_file}"
  echo "Added Clausy PATH entry to ${rc_file}"
  return 0
}

try_create_global_shim() {
  local target="$1"
  local with_sudo="${2:-0}"
  local candidate_dir=""
  local shim_path=""

  for candidate_dir in "${SHIM_CANDIDATE_PATHS[@]}"; do
    if [[ "${candidate_dir}" == "${HOME}"/* ]] && [[ ! -d "${candidate_dir}" ]]; then
      mkdir -p "${candidate_dir}" || true
    fi

    [[ -d "${candidate_dir}" ]] || continue
    shim_path="${candidate_dir}/clausy"

    if ln -sfn "${target}" "${shim_path}" 2>/dev/null; then
      SHIM_STATUS="created"
      SHIM_PATH="${shim_path}"
      return 0
    fi

    if [[ "${with_sudo}" -eq 1 ]] && command -v sudo >/dev/null 2>&1; then
      if sudo ln -sfn "${target}" "${shim_path}" >/dev/null 2>&1; then
        SHIM_STATUS="created-with-sudo"
        SHIM_PATH="${shim_path}"
        return 0
      fi
    fi
  done

  return 1
}

check_health_endpoint_once() {
  local endpoint="$1"
  local connect_timeout_seconds="$2"
  local read_timeout_seconds="$3"
  "${VENV_PY}" - "$endpoint" "$connect_timeout_seconds" "$read_timeout_seconds" <<'PY'
import json
import socket
import sys
import urllib.error
import urllib.request

endpoint = sys.argv[1]
connect_timeout = float(sys.argv[2])
read_timeout = float(sys.argv[3])
timeout = connect_timeout + read_timeout

try:
  req = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
  with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
    if resp.status != 200:
      sys.exit(1)
    payload = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
    if isinstance(payload, dict) and bool(payload.get('ok')):
      sys.exit(0)
except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, TimeoutError, ValueError, json.JSONDecodeError):
  pass

sys.exit(1)
PY
}

run_health_check_with_retries() {
  local endpoint="$1"
  local attempts="$2"
  local delay_seconds="$3"
  local connect_timeout_seconds="$4"
  local read_timeout_seconds="$5"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    if check_health_endpoint_once "$endpoint" "$connect_timeout_seconds" "$read_timeout_seconds"; then
      return 0
    fi
    if (( i < attempts )); then
      sleep "$delay_seconds"
    fi
  done
  return 1
}

while (($#)); do
  case "$1" in
    --docker)
      DOCKER_MODE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-service)
      NO_SERVICE=1
      shift
      ;;
    --no-browser)
      NO_BROWSER=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--docker] [--dry-run] [--no-service] [--no-browser]" >&2
      exit 2
      ;;
  esac
done

init_prompt_fd || true

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

VENV_PY="${VENV_DIR}/bin/python"
VENV_BIN_PATH="$(cd "${VENV_DIR}/bin" && pwd)"

if try_create_global_shim "${VENV_BIN_PATH}/clausy" 0; then
  :
else
  SHIM_STATUS="failed"
  if is_interactive; then
    prompt_read shim_sudo_input "Could not write global clausy shim. Try with sudo where needed? [y/N] " || true
    shim_sudo_normalized="$(printf '%s' "${shim_sudo_input:-}" | tr '[:upper:]' '[:lower:]')"
    if [[ "${shim_sudo_normalized}" == "y" || "${shim_sudo_normalized}" == "yes" ]]; then
      if try_create_global_shim "${VENV_BIN_PATH}/clausy" 1; then
        :
      else
        SHIM_STATUS="failed"
      fi
    fi
  else
    echo "Skipping global clausy shim creation (non-interactive mode)."
  fi
fi

if [[ "${SHIM_STATUS}" == "created" || "${SHIM_STATUS}" == "created-with-sudo" ]]; then
  if path_contains_dir "$(dirname "${SHIM_PATH}")"; then
    SHIM_ON_PATH=1
    PATH_PERSISTED=1
  fi
fi

"${VENV_PY}" -m pip install -U pip

if [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
  "${VENV_PY}" -m pip install "${REPO_ROOT}"
else
  "${VENV_PY}" -m pip install --upgrade --force-reinstall "${GIT_PACKAGE_URL}"
fi

provider_choice="chatgpt"
if is_interactive; then
  prompt_read provider_input "Select provider [chatgpt/claude/grok/gemini_web/perplexity/poe/deepseek/openai/anthropic/ollama/gemini/openrouter] (default: chatgpt): " || true
  if [[ -n "${provider_input:-}" ]]; then
    provider_choice="${provider_input}"
  fi
  "${VENV_PY}" -m clausy provider "${provider_choice}" || true
fi

OPENCLAW_ARGS=()
if [[ "${DOCKER_MODE}" -eq 1 ]]; then
  OPENCLAW_ARGS+=("--docker")
fi
if [[ "${DRY_RUN}" -eq 1 ]]; then
  OPENCLAW_ARGS+=("--dry-run")
fi

if [[ ${#OPENCLAW_ARGS[@]} -gt 0 ]]; then
  "${VENV_PY}" -m clausy.openclaw_install "${OPENCLAW_ARGS[@]}"
else
  "${VENV_PY}" -m clausy.openclaw_install
fi

SERVICE_ARGS=("--venv-python" "${VENV_PY}" "--repo-root" "${REPO_ROOT}")
if [[ "${DRY_RUN}" -eq 1 ]]; then
  SERVICE_ARGS+=("--dry-run")
fi
if [[ "${NO_SERVICE}" -eq 1 ]]; then
  SERVICE_ARGS+=("--no-service")
fi

if "${VENV_PY}" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec("clausy.service_install") else 1)'; then
  if [[ ${#SERVICE_ARGS[@]} -gt 0 ]]; then
    "${VENV_PY}" -m clausy.service_install "${SERVICE_ARGS[@]}"
  else
    "${VENV_PY}" -m clausy.service_install
  fi
else
  echo "WARNING: clausy.service_install is not available in this environment." >&2
  echo "Skipping service setup and continuing install success." >&2
fi

if is_interactive && [[ "${NO_BROWSER}" -eq 0 ]]; then
  prompt_read chromium_input "Install Chromium fallback now? [y/N] " || true
  chromium_normalized="$(printf '%s' "${chromium_input:-}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${chromium_normalized}" == "y" || "${chromium_normalized}" == "yes" ]]; then
    "${VENV_PY}" -m playwright install chromium || true
  fi
fi

BROWSER_ARGS=("--venv-python" "${VENV_PY}" "--provider" "${provider_choice}")
if [[ "${DOCKER_MODE}" -eq 1 ]]; then
  BROWSER_ARGS+=("--docker")
fi
if [[ "${DRY_RUN}" -eq 1 ]]; then
  BROWSER_ARGS+=("--dry-run")
fi
if [[ "${NO_BROWSER}" -eq 1 ]]; then
  BROWSER_ARGS+=("--no-browser")
fi

if "${VENV_PY}" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec("clausy.first_run_browser") else 1)'; then
  "${VENV_PY}" -m clausy.first_run_browser "${BROWSER_ARGS[@]}" || true
  if is_interactive && [[ "${NO_BROWSER}" -eq 0 ]] && [[ "${DOCKER_MODE}" -eq 0 ]] && [[ "${DRY_RUN}" -eq 0 ]]; then
    "${VENV_PY}" -m clausy.first_run_browser --venv-python "${VENV_PY}" --provider "${provider_choice}" --open-provider-only || true
  fi
fi

if is_interactive && [[ "${SHIM_ON_PATH}" -eq 0 ]]; then
  prompt_read add_path_input "Add Clausy to PATH in shell rc? [y/N] " || true
  add_path_normalized="$(printf '%s' "${add_path_input:-}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${add_path_normalized}" == "y" || "${add_path_normalized}" == "yes" ]]; then
    append_path_to_shell_rc "${VENV_BIN_PATH}" || true
    PATH_PERSISTED=1
  fi
fi

CLAUSY_RUNNER=("${VENV_BIN_PATH}/clausy")
if [[ ! -x "${CLAUSY_RUNNER[0]}" ]]; then
  CLAUSY_RUNNER=("${VENV_PY}" "-m" "clausy")
fi
CLAUSY_COMMAND_DISPLAY="${CLAUSY_RUNNER[*]}"

RUNTIME_HEALTH_OK=0
RUNTIME_HEALTH_STATUS_LINE=""
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Skipping runtime health check in --dry-run mode."
else
  if run_health_check_with_retries "${HEALTH_ENDPOINT}" "${HEALTH_RETRY_ATTEMPTS}" "${HEALTH_RETRY_DELAY_SECONDS}" "${HEALTHCHECK_CONNECT_TIMEOUT_SECONDS}" "${HEALTHCHECK_READ_TIMEOUT_SECONDS}"; then
    RUNTIME_HEALTH_OK=1
  else
    echo "Auto-repair: restarting Clausy-managed runtime once."
    "${CLAUSY_RUNNER[@]}" stop >/dev/null 2>&1 || true
    "${CLAUSY_RUNNER[@]}" start >/dev/null 2>&1 || true
    if run_health_check_with_retries "${HEALTH_ENDPOINT}" "${HEALTH_RETRY_ATTEMPTS}" "${HEALTH_RETRY_DELAY_SECONDS}" "${HEALTHCHECK_CONNECT_TIMEOUT_SECONDS}" "${HEALTHCHECK_READ_TIMEOUT_SECONDS}"; then
      RUNTIME_HEALTH_OK=1
    fi
  fi

  RUNTIME_HEALTH_STATUS_LINE="$("${CLAUSY_RUNNER[@]}" status 2>/dev/null || true)"
fi

if [[ "${TTY_PROMPT_FD}" == "3" ]]; then
  exec 3<&-
fi

SELECTED_BASE_URL="http://127.0.0.1:3108/v1"

echo
echo "Clausy install complete."
echo "OpenClaw provider configured for: ${SELECTED_BASE_URL}"
echo "A backup of ~/.openclaw/openclaw.json is created before non-dry-run writes."
echo

echo "Global clausy command shim:"
if [[ "${SHIM_STATUS}" == "created" || "${SHIM_STATUS}" == "created-with-sudo" ]]; then
  echo "  installed at ${SHIM_PATH}"
else
  echo "  not installed"
  echo "  Could not install global shim automatically."
fi

echo
if [[ "${PATH_PERSISTED}" -eq 0 ]]; then
  IMMEDIATE_PATH_EXPORT="export PATH=\"${VENV_BIN_PATH}:\$PATH\""
  echo "Use Clausy immediately in this shell:"
  echo "  ${IMMEDIATE_PATH_EXPORT}"
  if is_interactive && [[ "${PATH_PERSISTED}" -eq 0 ]]; then
    echo "Run Clausy now without editing PATH:"
    echo "  ${VENV_BIN_PATH}/clausy"
  fi
  echo
fi

if [[ "${DRY_RUN}" -eq 0 ]]; then
  runtime_pid="-"
  runtime_port="3108"
  if [[ "${RUNTIME_HEALTH_STATUS_LINE}" =~ pid=([^[:space:]]+) ]]; then
    runtime_pid="${BASH_REMATCH[1]}"
  fi
  if [[ "${RUNTIME_HEALTH_STATUS_LINE}" =~ port=([^[:space:]]+) ]]; then
    runtime_port="${BASH_REMATCH[1]}"
  fi

  if [[ "${RUNTIME_HEALTH_OK}" -eq 1 ]]; then
    echo "Clausy runtime health: ok (pid=${runtime_pid} port=${runtime_port} endpoint=${HEALTH_ENDPOINT})"
  else
    echo "WARNING: Clausy runtime health check still failing after auto-repair."
    echo "Endpoint checked: ${HEALTH_ENDPOINT}"
    echo "Next steps:"
    echo "  ${CLAUSY_COMMAND_DISPLAY} stop"
    echo "  ${CLAUSY_COMMAND_DISPLAY} start"
    echo "  ${CLAUSY_COMMAND_DISPLAY} status"
  fi
  echo
fi

echo "Quick commands:"
echo "  clausy = status and help"
echo "  clausy start/stop"
echo "  clausy chrome = starts chrome with clausy"
