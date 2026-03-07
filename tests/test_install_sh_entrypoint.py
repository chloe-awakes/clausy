from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "install.sh"


def test_install_sh_exists_at_repo_root():
    assert INSTALL_SH.exists()


def test_install_sh_has_shebang_and_strict_mode():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in content


def test_install_sh_installs_clausy_and_runs_openclaw_wiring():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert "-m venv" in content
    assert ".venv" in content
    assert "-m pip install" in content
    assert "-m clausy.openclaw_install" in content


def test_install_sh_supports_forwarding_docker_flag():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--docker' in content
    assert 'OPENCLAW_ARGS+=("--docker")' in content


def test_install_sh_supports_forwarding_dry_run_flag():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--dry-run' in content
    assert 'OPENCLAW_ARGS+=("--dry-run")' in content


def test_install_sh_handles_empty_openclaw_args_under_nounset():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'if [[ ${#OPENCLAW_ARGS[@]} -gt 0 ]]; then' in content
    assert '"${VENV_PY}" -m clausy.openclaw_install "${OPENCLAW_ARGS[@]}"' in content
    assert '"${VENV_PY}" -m clausy.openclaw_install' in content


def test_install_sh_is_safe_when_bash_source_is_unset():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SCRIPT_PATH="${BASH_SOURCE[0]:-${0:-}}"' in content


def test_install_sh_falls_back_to_github_install_when_not_in_repo_checkout():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'GIT_PACKAGE_URL="git+https://github.com/chloe-awakes/clausy.git"' in content
    assert '"${VENV_PY}" -m pip install "${GIT_PACKAGE_URL}"' in content
