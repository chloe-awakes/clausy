"""Install and auto-start Clausy as a per-user background service."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


SERVICE_LABEL = "com.clausy.gateway"
SYSTEMD_UNIT = "clausy.service"


@dataclass(frozen=True)
class ServicePlan:
    kind: str
    unit_path: Path
    content: str


def _plist_content(repo_root: Path, venv_python: Path, home: Path) -> str:
    log_dir = home / "Library/Logs"
    log_out = log_dir / "clausy.log"
    log_err = log_dir / "clausy.err.log"
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>clausy</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{cwd}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{stdout}</string>
  <key>StandardErrorPath</key>
  <string>{stderr}</string>
</dict>
</plist>
""".format(
        label=SERVICE_LABEL,
        python=venv_python,
        cwd=repo_root,
        stdout=log_out,
        stderr=log_err,
    )


def _systemd_content(repo_root: Path, venv_python: Path) -> str:
    return """[Unit]
Description=Clausy OpenAI-compatible gateway
After=network-online.target

[Service]
Type=simple
WorkingDirectory={cwd}
ExecStart={python} -m clausy
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
""".format(
        cwd=repo_root,
        python=venv_python,
    )


def build_service_plan(
    system_name: Optional[str] = None,
    home: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    venv_python: Optional[Path] = None,
) -> Optional[ServicePlan]:
    sys_name = (system_name or platform.system()).strip()
    home_dir = home or Path.home()
    root = (repo_root or Path.cwd()).resolve()
    py = (venv_python or (root / ".venv/bin/python")).resolve()

    if sys_name == "Darwin":
        unit_path = home_dir / "Library/LaunchAgents" / f"{SERVICE_LABEL}.plist"
        return ServicePlan(kind="launchd", unit_path=unit_path, content=_plist_content(root, py, home_dir))

    if sys_name == "Linux":
        unit_path = home_dir / ".config/systemd/user" / SYSTEMD_UNIT
        return ServicePlan(kind="systemd", unit_path=unit_path, content=_systemd_content(root, py))

    return None


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def install_plan(
    plan: ServicePlan,
    runner: Callable[[list[str], bool], None] = subprocess.run,
) -> None:
    _write_text(plan.unit_path, plan.content)

    if plan.kind == "launchd":
        try:
            runner(["launchctl", "unload", str(plan.unit_path)], check=True)
        except subprocess.CalledProcessError:
            pass
        runner(["launchctl", "load", "-w", str(plan.unit_path)], check=True)
        return

    if plan.kind == "systemd":
        runner(["systemctl", "--user", "daemon-reload"], check=True)
        runner(["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT], check=True)
        runner(["systemctl", "--user", "restart", SYSTEMD_UNIT], check=True)
        return

    raise ValueError(f"Unsupported service kind: {plan.kind}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install and auto-start Clausy user service")
    ap.add_argument("--venv-python", default=".venv/bin/python", help="Path to venv python executable")
    ap.add_argument("--repo-root", default=".", help="Repo root / service working directory")
    ap.add_argument("--dry-run", action="store_true", help="Print service file and actions without writing")
    ap.add_argument("--no-service", action="store_true", help="Skip service setup")
    args = ap.parse_args()

    if args.no_service:
        print("Skipping service setup (--no-service).")
        return 0

    plan = build_service_plan(repo_root=Path(args.repo_root), venv_python=Path(args.venv_python))
    if plan is None:
        print(f"Skipping service setup: unsupported platform '{platform.system()}'.")
        return 0

    if args.dry_run:
        print(f"Would write: {plan.unit_path}")
        print(plan.content)
        if plan.kind == "launchd":
            print(f"Would run: launchctl unload {plan.unit_path}")
            print(f"Would run: launchctl load -w {plan.unit_path}")
        else:
            print("Would run: systemctl --user daemon-reload")
            print(f"Would run: systemctl --user enable --now {SYSTEMD_UNIT}")
            print(f"Would run: systemctl --user restart {SYSTEMD_UNIT}")
        return 0

    try:
        install_plan(plan)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"WARNING: service setup failed: {exc}", file=sys.stderr)
        return 0

    print(f"Installed {plan.kind} service: {plan.unit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
