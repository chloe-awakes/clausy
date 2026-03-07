import json
from pathlib import Path

from clausy import openclaw_install


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "models": {
                    "providers": {
                        "openai": {
                            "baseUrl": "https://api.openai.com/v1",
                            "models": ["gpt-4o"],
                        }
                    }
                },
                "agents": {"defaults": {"model": {"primary": "openai/gpt-4o"}}},
            }
        ),
        encoding="utf-8",
    )


def test_installer_writes_current_provider_schema_and_primary(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)

    monkeypatch.setattr("sys.argv", ["openclaw_install", "--config", str(cfg_path), "--model", "chatgpt-web"])
    rc = openclaw_install.main()

    assert rc == 0

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    clausy = cfg["models"]["providers"]["clausy"]

    assert clausy["baseUrl"] == "http://127.0.0.1:3108/v1"
    assert clausy["models"] == ["chatgpt-web"]
    assert "type" not in clausy
    assert "baseURL" not in clausy

    assert cfg["agents"]["defaults"]["model"]["primary"] == "local/clausy"


def test_installer_does_not_introduce_legacy_models_keys(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    _write_config(cfg_path)

    monkeypatch.setattr("sys.argv", ["openclaw_install", "--config", str(cfg_path)])
    rc = openclaw_install.main()

    assert rc == 0

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    models = cfg["models"]
    assert "aliases" not in models
    assert "default" not in models
