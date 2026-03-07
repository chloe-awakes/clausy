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
    assert "-m clausy.service_install" in content


def test_install_sh_supports_forwarding_docker_flag():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--docker' in content
    assert 'OPENCLAW_ARGS+=("--docker")' in content


def test_install_sh_reports_consistent_openclaw_base_url_for_docker_and_non_docker():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SELECTED_BASE_URL="http://127.0.0.1:3108/v1"' in content
    assert '5000/v1' not in content


def test_install_sh_supports_forwarding_dry_run_flag():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--dry-run' in content
    assert 'OPENCLAW_ARGS+=("--dry-run")' in content


def test_install_sh_supports_no_service_flag():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--no-service' in content
    assert 'SERVICE_ARGS+=("--no-service")' in content


def test_install_sh_supports_no_browser_flag():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--no-browser' in content
    assert 'BROWSER_ARGS+=("--no-browser")' in content


def test_install_sh_invokes_first_run_browser_helper():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'clausy.first_run_browser' in content
    assert '"--provider" "${provider_choice}"' in content


def test_install_sh_explicitly_retries_provider_open_after_first_run_helper():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert '--open-provider-only' in content
    assert 'if is_interactive && [[ "${NO_BROWSER}" -eq 0 ]] && [[ "${DOCKER_MODE}" -eq 0 ]] && [[ "${DRY_RUN}" -eq 0 ]]; then' in content


def test_install_sh_prompts_for_provider_when_interactive():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'prompt_read provider_input "Select provider' in content
    assert '"${VENV_PY}" -m clausy provider "${provider_choice}"' in content


def test_install_sh_uses_dev_tty_for_prompts_when_stdin_is_piped():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'if [[ -r /dev/tty ]]; then' in content
    assert 'exec 3</dev/tty' in content
    assert 'read -r -u "${TTY_PROMPT_FD}" -p' in content


def test_install_sh_prompts_for_optional_chromium_install_when_interactive():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'prompt_read chromium_input "Install Chromium fallback now? [y/N] "' in content
    assert 'if [[ "${chromium_normalized}" == "y" || "${chromium_normalized}" == "yes" ]]; then' in content
    assert '"${VENV_PY}" -m playwright install chromium' in content


def test_install_sh_supports_optional_path_rc_append_without_duplicates():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'prompt_read add_path_input "Add Clausy to PATH in shell rc? [y/N] "' in content
    assert 'if is_interactive && [[ "${SHIM_ON_PATH}" -eq 0 ]]; then' in content
    assert 'append_path_to_shell_rc' in content
    assert 'grep -Fqs' in content


def test_install_sh_prints_immediate_path_export_when_not_persisted():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'PATH_PERSISTED=0' in content
    assert 'Use Clausy immediately in this shell:' in content
    assert 'IMMEDIATE_PATH_EXPORT="export PATH=\\"${VENV_BIN_PATH}:\\$PATH\\""' in content
    assert 'echo "  ${IMMEDIATE_PATH_EXPORT}"' in content


def test_install_sh_prints_one_shot_clausy_command_when_interactive_and_path_not_persisted():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'if is_interactive && [[ "${PATH_PERSISTED}" -eq 0 ]]; then' in content
    assert 'Run Clausy now without editing PATH:' in content
    assert 'echo "  ${VENV_BIN_PATH}/clausy"' in content


def test_install_sh_prints_post_install_command_help_block():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'clausy = status and help' in content
    assert 'clausy start/stop' in content
    assert 'clausy chrome = starts chrome with clausy' in content


def test_install_sh_attempts_global_clausy_shim_creation_with_path_fallbacks():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SHIM_CANDIDATE_PATHS=(' in content
    assert '/usr/local/bin' in content
    assert '/opt/homebrew/bin' in content
    assert '/usr/bin' in content
    assert 'ln -sfn "${target}" "${shim_path}"' in content


def test_install_sh_skips_path_shell_rc_prompt_when_global_shim_is_already_on_path():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SHIM_ON_PATH=0' in content
    assert 'if [[ "${SHIM_STATUS}" == "created" || "${SHIM_STATUS}" == "created-with-sudo" ]]; then' in content
    assert 'if path_contains_dir "$(dirname "${SHIM_PATH}")"; then' in content
    assert 'if is_interactive && [[ "${SHIM_ON_PATH}" -eq 0 ]]; then' in content


def test_install_sh_handles_non_writable_shim_locations_without_hanging_noninteractive_mode():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'SHIM_STATUS="not-attempted"' in content
    assert 'if is_interactive; then' in content
    assert 'Skipping global clausy shim creation (non-interactive mode).' in content
    assert 'Could not install global shim automatically.' in content


def test_install_sh_summarizes_shim_result_with_actionable_fallback():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'Global clausy command shim:' in content
    assert 'Use Clausy immediately in this shell:' in content
    assert 'Add Clausy to PATH in shell rc? [y/N]' in content


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
    assert '"${VENV_PY}" -m pip install --upgrade --force-reinstall "${GIT_PACKAGE_URL}"' in content


def test_install_sh_guards_service_install_when_module_missing():
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert 'find_spec("clausy.service_install")' in content
    assert 'WARNING: clausy.service_install is not available in this environment.' in content
    assert 'Skipping service setup and continuing install success.' in content
