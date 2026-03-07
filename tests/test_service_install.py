from __future__ import annotations

from pathlib import Path

from clausy import service_install


def test_darwin_plan_generates_launchagent_plist():
    plan = service_install.build_service_plan(
        system_name="Darwin",
        home=Path("/Users/alice"),
        repo_root=Path("/opt/clausy"),
        venv_python=Path("/opt/clausy/.venv/bin/python"),
    )

    assert plan is not None
    assert plan.kind == "launchd"
    assert plan.unit_path == Path("/Users/alice/Library/LaunchAgents/com.clausy.gateway.plist")
    assert "<string>/opt/clausy/.venv/bin/python</string>" in plan.content
    assert "<string>-m</string>" in plan.content
    assert "<string>clausy</string>" in plan.content
    assert "<key>WorkingDirectory</key>" in plan.content
    assert "<string>/opt/clausy</string>" in plan.content


def test_linux_plan_generates_systemd_user_unit():
    plan = service_install.build_service_plan(
        system_name="Linux",
        home=Path("/home/alice"),
        repo_root=Path("/opt/clausy"),
        venv_python=Path("/opt/clausy/.venv/bin/python"),
    )

    assert plan is not None
    assert plan.kind == "systemd"
    assert plan.unit_path == Path("/home/alice/.config/systemd/user/clausy.service")
    assert "ExecStart=/opt/clausy/.venv/bin/python -m clausy" in plan.content
    assert "WorkingDirectory=/opt/clausy" in plan.content
    assert "WantedBy=default.target" in plan.content


def test_unsupported_platform_returns_none_plan():
    plan = service_install.build_service_plan(
        system_name="Windows",
        home=Path("/Users/alice"),
        repo_root=Path("/opt/clausy"),
        venv_python=Path("/opt/clausy/.venv/bin/python"),
    )

    assert plan is None


def test_install_plan_runs_expected_launchd_commands(tmp_path):
    plan = service_install.build_service_plan(
        system_name="Darwin",
        home=tmp_path,
        repo_root=tmp_path / "repo",
        venv_python=tmp_path / "repo/.venv/bin/python",
    )
    assert plan is not None

    calls: list[list[str]] = []

    def _runner(cmd: list[str], check: bool = True) -> None:
        calls.append(cmd)
        if cmd[:2] == ["launchctl", "unload"]:
            raise service_install.subprocess.CalledProcessError(1, cmd)

    service_install.install_plan(plan, runner=_runner)

    assert plan.unit_path.exists()
    assert ["launchctl", "unload", str(plan.unit_path)] in calls
    assert ["launchctl", "load", "-w", str(plan.unit_path)] in calls


def test_install_plan_runs_expected_systemd_commands(tmp_path):
    plan = service_install.build_service_plan(
        system_name="Linux",
        home=tmp_path,
        repo_root=tmp_path / "repo",
        venv_python=tmp_path / "repo/.venv/bin/python",
    )
    assert plan is not None

    calls: list[list[str]] = []

    def _runner(cmd: list[str], check: bool = True) -> None:
        calls.append(cmd)

    service_install.install_plan(plan, runner=_runner)

    assert plan.unit_path.exists()
    assert ["systemctl", "--user", "daemon-reload"] in calls
    assert ["systemctl", "--user", "enable", "--now", "clausy.service"] in calls
    assert ["systemctl", "--user", "restart", "clausy.service"] in calls
