from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

_DEFAULTS: dict[str, Any] = {
    "model": "claude-sonnet-4-6",
    "sensitive_paths": ["auth/", "payments/", "db/queries/"],
    "max_iterations": 20,
}


def load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return dict(_DEFAULTS)
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(_DEFAULTS)
    merged.update(data)
    return merged


def get_sensitive_paths() -> list[str]:
    paths = load_config().get("sensitive_paths") or []
    return [str(p) for p in paths]


def get_model() -> str:
    return str(load_config().get("model") or _DEFAULTS["model"])


def get_max_iterations() -> int:
    val = load_config().get("max_iterations")
    try:
        return int(val)
    except (TypeError, ValueError):
        return int(_DEFAULTS["max_iterations"])
