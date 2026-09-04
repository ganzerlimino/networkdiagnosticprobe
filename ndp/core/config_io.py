"""Read/write NDP YAML configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ndp.core.config import NdpConfig


def load_config_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def save_config_mapping(path: Path, data: dict[str, Any]) -> None:
    NdpConfig.from_mapping(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle, default_flow_style=False, sort_keys=False)


def load_config_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def save_config_text(path: Path, text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("Config root must be a YAML mapping")
    save_config_mapping(path, data)
    return data
