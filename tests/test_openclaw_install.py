import json
import re
from pathlib import Path

from clausy import openclaw_install


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "models": {
                    "providers": {},
                },
                "agents": {"defaults": {"model": {"primary": "openai/gpt-4o"}}},
            }
        ),
        encoding="utf-8",
    )


def _read_provider_base_url(path: Path) -> str:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return cfg["models"]["providers"]["clausy"]["baseUrl"]


def test_default_base_url_constant_is_3108():
    assert openclaw_install.DEFAULT_BASE_URL == "http://127.0.0.1:3108/v1"


def test_cli_default_uses_3108(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)

    monkeypatch.setattr(
        "sys.argv",
        ["openclaw_install", "--config", str(cfg_path)],
    )

    rc = openclaw_install.main()

    assert rc == 0
    assert _read_provider_base_url(cfg_path) == "http://127.0.0.1:3108/v1"


def test_cli_docker_still_uses_3108_by_default(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)

    monkeypatch.setattr(
        "sys.argv",
        ["openclaw_install", "--config", str(cfg_path), "--docker"],
    )

    rc = openclaw_install.main()

    assert rc == 0
    assert _read_provider_base_url(cfg_path) == "http://127.0.0.1:3108/v1"


def test_cli_explicit_base_url_overrides_docker(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)

    custom = "http://127.0.0.1:9999/v1"
    monkeypatch.setattr(
        "sys.argv",
        [
            "openclaw_install",
            "--config",
            str(cfg_path),
            "--docker",
            "--base-url",
            custom,
        ],
    )

    rc = openclaw_install.main()

    assert rc == 0
    assert _read_provider_base_url(cfg_path) == custom


def test_non_dry_run_creates_timestamped_backup(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)

    monkeypatch.setattr("sys.argv", ["openclaw_install", "--config", str(cfg_path)])

    rc = openclaw_install.main()

    assert rc == 0
    backups = list(tmp_path.glob("openclaw.json.bak.*"))
    assert len(backups) == 1
    assert re.fullmatch(r"openclaw\.json\.bak\.\d{8}_\d{6}", backups[0].name)


def test_dry_run_does_not_write_or_create_backup(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)
    before = cfg_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        ["openclaw_install", "--config", str(cfg_path), "--dry-run"],
    )

    rc = openclaw_install.main()

    assert rc == 0
    assert cfg_path.read_text(encoding="utf-8") == before
    assert list(tmp_path.glob("openclaw.json.bak.*")) == []
