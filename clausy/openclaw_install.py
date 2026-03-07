"""Add Clausy as an OpenAI-compatible provider to OpenClaw config."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

DEFAULT_CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")
DEFAULT_BASE_URL = "http://127.0.0.1:3108/v1"
DOCKER_BASE_URL = "http://127.0.0.1:5000/v1"
DEFAULT_MODEL_ID = "chatgpt-web"


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _backup(path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.bak.{ts}"
    shutil.copy2(path, backup)
    return backup


def _ensure_dict(root: Dict[str, Any], key: str) -> Dict[str, Any]:
    if key not in root or not isinstance(root.get(key), dict):
        root[key] = {}
    return root[key]


def _normalize_provider_models(raw_models: Any) -> List[Dict[str, Any]]:
    """Normalize provider models to schema-compatible list[object]."""
    normalized: List[Dict[str, Any]] = []
    if not isinstance(raw_models, list):
        return normalized

    for item in raw_models:
        if isinstance(item, str):
            model_id = item.strip()
            if model_id:
                normalized.append({"id": model_id})
            continue

        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                model_obj = dict(item)
                model_obj["id"] = model_id.strip()
                normalized.append(model_obj)

    return normalized


def _install(
    cfg: Dict[str, Any],
    base_url: str,
    model_id: str,
    provider_name: str = "clausy",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Mutate cfg: add provider and set primary/default. Returns (old_primary, new_primary)."""
    agents = _ensure_dict(cfg, "agents")
    defaults = _ensure_dict(agents, "defaults")
    model_defaults = _ensure_dict(defaults, "model")

    previous_primary = model_defaults.get("primary")

    models = _ensure_dict(cfg, "models")
    models.pop("aliases", None)
    models.pop("default", None)

    providers = _ensure_dict(models, "providers")
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        provider = {}

    normalized_models = _normalize_provider_models(provider.get("models"))
    existing_ids = {m["id"] for m in normalized_models}
    if model_id not in existing_ids:
        normalized_models.append({"id": model_id})

    provider.update(
        {
            "baseUrl": base_url,
            "models": normalized_models,
        }
    )
    provider.pop("type", None)
    provider.pop("baseURL", None)

    providers[provider_name] = provider

    primary_ref = f"local/{provider_name}"
    model_defaults["primary"] = primary_ref

    return ({"primary": previous_primary} if previous_primary else {}), {"primary": primary_ref}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="Path to openclaw.json (default: ~/.openclaw/openclaw.json)",
    )
    ap.add_argument(
        "--base-url",
        default=None,
        help=f"Clausy OpenAI base URL override (default local: {DEFAULT_BASE_URL}; docker: {DOCKER_BASE_URL})",
    )
    ap.add_argument(
        "--docker",
        action="store_true",
        help="Use Docker Clausy base URL (http://127.0.0.1:5000/v1) unless --base-url is set",
    )
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help="Model id to register in provider model list (default: chatgpt-web)",
    )
    ap.add_argument("--provider", default="clausy", help="Provider name to register (default: clausy)")
    ap.add_argument("--dry-run", action="store_true", help="Print the updated config without writing")
    args = ap.parse_args()

    path = os.path.expanduser(args.config)
    if not os.path.exists(path):
        print(f"ERROR: config not found: {path}", file=sys.stderr)
        return 2

    effective_base_url = args.base_url if args.base_url else (DOCKER_BASE_URL if args.docker else DEFAULT_BASE_URL)

    cfg = _load_json(path)
    old_primary, new_primary = _install(cfg, effective_base_url, args.model, args.provider)

    if args.dry_run:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return 0

    backup = _backup(path)
    _atomic_write(path, cfg)

    print(f"Updated: {path}")
    print(f"Backup:  {backup}")
    if old_primary:
        print("Previous primary preserved under existing config keys")
    print(f"New primary: {new_primary['primary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
