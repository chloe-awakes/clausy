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
                            "models": [{"id": "gpt-4o"}],
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
    assert clausy["models"] == [{"id": "chatgpt-web"}]
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


def test_installer_migrates_legacy_contaminated_config(monkeypatch, tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(
        json.dumps(
            {
                "models": {
                    "aliases": {"fast": "clausy/chatgpt-web"},
                    "default": "fast",
                    "providers": {
                        "clausy": {
                            "baseURL": "http://legacy.invalid/v1",
                            "models": ["chatgpt-web", {"id": "existing-object", "label": "Existing"}],
                            "type": "openai",
                        }
                    },
                },
                "agents": {"defaults": {"model": {"primary": "openai/gpt-4o"}}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("sys.argv", ["openclaw_install", "--config", str(cfg_path), "--model", "new-model"])
    rc = openclaw_install.main()

    assert rc == 0

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    models = cfg["models"]
    assert "aliases" not in models
    assert "default" not in models

    clausy = models["providers"]["clausy"]
    assert clausy["baseUrl"] == "http://127.0.0.1:3108/v1"
    assert "baseURL" not in clausy
    assert "type" not in clausy

    assert clausy["models"] == [
        {"id": "chatgpt-web"},
        {"id": "existing-object", "label": "Existing"},
        {"id": "new-model"},
    ]

    assert cfg["agents"]["defaults"]["model"]["primary"] == "local/clausy"
