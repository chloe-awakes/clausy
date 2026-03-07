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
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--docker] [--dry-run] [--no-service]" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

VENV_PY="${VENV_DIR}/bin/python"

"${VENV_PY}" -m pip install -U pip

if [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
  "${VENV_PY}" -m pip install "${REPO_ROOT}"
else
  "${VENV_PY}" -m pip install --upgrade --force-reinstall "${GIT_PACKAGE_URL}"
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

SELECTED_BASE_URL="http://127.0.0.1:3108/v1"

echo
echo "Clausy install complete."
echo "OpenClaw provider configured for: ${SELECTED_BASE_URL}"
echo "A backup of ~/.openclaw/openclaw.json is created before non-dry-run writes."
