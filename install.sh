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

is_yes() {
  local v="${1:-}"
  v="$(printf '%s' "$v" | tr '[:upper:]' '[:lower:]')"
  [[ -z "$v" || "$v" == "y" || "$v" == "yes" ]]
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
  prompt_read chromium_input "Install Chromium fallback now? [Y/n] " || true
  if is_yes "${chromium_input:-}"; then
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

if is_interactive; then
  prompt_read add_path_input "Add Clausy to PATH in shell rc? [y/N] " || true
  add_path_normalized="$(printf '%s' "${add_path_input:-}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${add_path_normalized}" == "y" || "${add_path_normalized}" == "yes" ]]; then
    append_path_to_shell_rc "${VENV_BIN_PATH}" || true
    PATH_PERSISTED=1
  fi
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
if [[ "${PATH_PERSISTED}" -eq 0 ]]; then
  echo "Use Clausy immediately in this shell:"
  echo "  export PATH=\"${VENV_BIN_PATH}:\$PATH\""
  echo
fi

echo "Quick commands:"
echo "  clausy = status and help"
echo "  clausy start/stop"
echo "  clausy chrome = starts chrome with clausy"
