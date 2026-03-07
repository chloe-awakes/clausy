from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Any

import requests

from .service_install import SERVICE_LABEL, SYSTEMD_UNIT


_CONFIG_DIR = Path.home() / ".config" / "clausy"
_CONFIG_PATH = _CONFIG_DIR / "config.json"
_PID_PATH = _CONFIG_DIR / "clausy.pid"
_BROWSER_PID_PATH = _CONFIG_DIR / "browser-bootstrap.pid"


def _config_file_path() -> Path:
    return _CONFIG_PATH


def _pid_file_path() -> Path:
    return _PID_PATH


def _browser_pid_file_path() -> Path:
    return _BROWSER_PID_PATH


def _read_config() -> dict[str, str]:
    path = _config_file_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, (str, int, float, bool)):
            out[str(key)] = str(value)
    return out


def _write_config(config: dict[str, str]) -> None:
    path = _config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _coerce_bool(value: str) -> str:
    raw = value.strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return "1"
    if raw in {"0", "false", "no", "off"}:
        return "0"
    raise ValueError("expected on/off")


def _normalize_headless(value: str) -> str:
    raw = value.strip().lower()
    if raw == "auto":
        return "auto"
    return _coerce_bool(raw)


def _normalize_bootstrap(value: str) -> str:
    raw = value.strip().lower()
    if raw in {"auto", "always", "never"}:
        return raw
    raise ValueError("expected one of: auto, always, never")


def _normalize_port(value: str) -> str:
    port = int(value.strip())
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    return str(port)


_SETTINGS: dict[str, dict[str, Any]] = {
    "headless": {
        "env": "CLAUSY_HEADLESS",
        "default": "auto",
        "normalize": _normalize_headless,
    },
    "bootstrap": {
        "env": "CLAUSY_BROWSER_BOOTSTRAP",
        "default": "auto",
        "normalize": _normalize_bootstrap,
    },
    "provider": {
        "env": "CLAUSY_PROVIDER",
        "default": "chatgpt",
        "normalize": lambda v: v.strip().lower(),
    },
    "port": {
        "env": "CLAUSY_PORT",
        "default": "3108",
        "normalize": _normalize_port,
    },
    "auto-install": {
        "env": "CLAUSY_BROWSER_AUTO_INSTALL",
        "default": "1",
        "normalize": _coerce_bool,
    },
    "novnc": {
        "env": "CLAUSY_ENABLE_NOVNC",
        "default": "0",
        "normalize": _coerce_bool,
    },
}

_ALIASES = {
    "autoinstall": "auto-install",
}


def _resolve_key(key: str) -> str:
    candidate = key.strip().lower().replace("_", "-")
    return _ALIASES.get(candidate, candidate)


def _effective_value(name: str, persisted: dict[str, str]) -> tuple[str, str]:
    spec = _SETTINGS[name]
    env_name = spec["env"]
    if env_name in os.environ:
        return str(os.environ[env_name]), "env"
    if name in persisted:
        return str(persisted[name]), "config"
    return str(spec["default"]), "default"


def _apply_effective_env(persisted: dict[str, str]) -> None:
    for name, spec in _SETTINGS.items():
        env_name = spec["env"]
        if env_name in os.environ:
            continue
        value, _ = _effective_value(name, persisted)
        if value != "auto":
            os.environ[env_name] = value


def _print_usage() -> None:
    print("Usage: clausy <command|setting> [value]")
    print("")
    print("Commands:")
    print("  start        Start Clausy in background (opens configured provider page on browser startup)")
    print("  stop         Stop Clausy service/process if running")
    print("  status       Show runtime status and health snapshot")
    print("  config       Show all effective config values")
    print("  chrome       Start Clausy in visible Chrome mode (opens configured provider page on browser startup)")
    print("")
    print("Settings (get/set):")
    print("  headless, bootstrap, provider, port, auto-install, novnc")
    print("  Example: clausy headless off")


def _show_config() -> None:
    persisted = _read_config()
    print(f"config_path={_config_file_path()}")
    for name in _SETTINGS:
        value, source = _effective_value(name, persisted)
        print(f"{name}={value} (source={source})")


def _health_snapshot() -> dict[str, Any]:
    persisted = _read_config()
    port, _ = _effective_value("port", persisted)
    provider, _ = _effective_value("provider", persisted)
    base = f"http://127.0.0.1:{port}"
    health = "down"
    detail = "unreachable"
    try:
        resp = requests.get(f"{base}/health", timeout=1.5)
        if resp.status_code == 200:
            payload = resp.json()
            health = "ok" if payload.get("ok") else "degraded"
            detail = str(payload.get("provider", provider))
        else:
            detail = f"http {resp.status_code}"
    except requests.RequestException:
        pass

    pid_path = _pid_file_path()
    pid = None
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = None

    return {
        "health": health,
        "provider": detail if health != "ok" else provider,
        "port": port,
        "pid": pid,
        "config_path": str(_config_file_path()),
    }


def _show_status() -> None:
    snap = _health_snapshot()
    print(
        f"health={snap['health']} provider={snap['provider']} port={snap['port']} pid={snap['pid'] or '-'}"
    )


def _configure_visible_chrome_mode() -> None:
    os.environ["CLAUSY_BROWSER_BOOTSTRAP"] = "always"
    os.environ["CLAUSY_HEADLESS"] = "0"


def _launch_background(extra_env: dict[str, str] | None = None) -> int:
    persisted = _read_config()
    _apply_effective_env(persisted)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "clausy.server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    pid_path = _pid_file_path()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    print(f"Started Clausy (pid={proc.pid})")
    return 0


def _try_stop_service_manager() -> bool:
    if sys.platform == "darwin":
        result = subprocess.run(["launchctl", "stop", SERVICE_LABEL], capture_output=True, text=True)
        return result.returncode == 0
    if sys.platform.startswith("linux"):
        unit = SYSTEMD_UNIT
        result = subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, text=True)
        return result.returncode == 0
    return False


def _is_expected_managed_browser_process(pid: int, cdp_port: int, profile_dir: str) -> bool:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False

    if result.returncode != 0:
        return False

    cmd = (result.stdout or "").strip()
    if not cmd:
        return False

    return (
        f"--remote-debugging-port={cdp_port}" in cmd
        and f"--user-data-dir={profile_dir}" in cmd
    )


def _stop_managed_browser_if_any() -> bool:
    path = _browser_pid_file_path()
    if not path.exists():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return False

    pid = payload.get("pid")
    cdp_port = payload.get("cdp_port")
    profile_dir = payload.get("profile_dir")
    if not isinstance(pid, int) or not isinstance(cdp_port, int) or not isinstance(profile_dir, str):
        path.unlink(missing_ok=True)
        return False

    stopped = False
    if _is_expected_managed_browser_process(pid, cdp_port, profile_dir):
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped Clausy-managed browser (pid={pid}).")
            stopped = True
        except ProcessLookupError:
            stopped = False

    path.unlink(missing_ok=True)
    return stopped


def _cmd_stop() -> int:
    stopped_service = _try_stop_service_manager()

    pid_path = _pid_file_path()
    if not pid_path.exists():
        stopped_browser = _stop_managed_browser_if_any()
        if stopped_service:
            print("Stopped Clausy service.")
        elif not stopped_browser:
            print("Clausy is not running.")
        return 0

    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid_path.unlink(missing_ok=True)
        _stop_managed_browser_if_any()
        print("Clausy is not running.")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Clausy process (pid={pid}).")
    except ProcessLookupError:
        print("Clausy is not running (stale pid file removed).")
    finally:
        pid_path.unlink(missing_ok=True)

    _stop_managed_browser_if_any()
    return 0


def _cmd_start(chrome_mode: bool = False) -> int:
    if chrome_mode:
        return _launch_background(
            {
                "CLAUSY_BROWSER_BOOTSTRAP": "always",
                "CLAUSY_HEADLESS": "0",
                "CLAUSY_OPEN_PROVIDER_ON_START": "1",
            }
        )
    return _launch_background()


def _handle_setting(args: list[str]) -> int:
    key = _resolve_key(args[0])
    if key not in _SETTINGS:
        print(f"Unknown command/setting: {args[0]}", file=sys.stderr)
        _print_usage()
        return 2

    persisted = _read_config()

    if len(args) == 1:
        value, source = _effective_value(key, persisted)
        print(f"{key}={value} (source={source})")
        return 0

    raw_value = args[1]
    try:
        normalized = _SETTINGS[key]["normalize"](raw_value)
    except (ValueError, TypeError) as exc:
        print(f"Invalid value for {key}: {exc}", file=sys.stderr)
        return 2

    persisted[key] = normalized
    _write_config(persisted)
    print(f"Set {key}={normalized} in {_config_file_path()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        _show_status()
        _print_usage()
        return 0

    cmd = args[0].strip().lower()

    if cmd in {"-h", "--help", "help"}:
        _print_usage()
        return 0

    if cmd in {"-v", "--version", "version"}:
        try:
            print(pkg_version("clausy"))
        except PackageNotFoundError:
            print("0.0.0")
        return 0

    if cmd == "config":
        _show_config()
        return 0

    if cmd == "status":
        _show_status()
        return 0

    if cmd == "start":
        return _cmd_start(chrome_mode=False)

    if cmd == "stop":
        return _cmd_stop()

    if cmd == "chrome":
        return _cmd_start(chrome_mode=True)

    return _handle_setting(args)
