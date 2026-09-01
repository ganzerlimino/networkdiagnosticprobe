"""Operational scenario presets for discovery scans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_BUNDLED = Path(__file__).resolve().parent / "profiles.yaml"
_SYSTEM = Path("/etc/ndp/scenarios/profiles.yaml")


def _profiles_path() -> Path:
    if _SYSTEM.is_file():
        return _SYSTEM
    return _BUNDLED


def load_scenarios_catalog() -> dict[str, Any]:
    path = _profiles_path()
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid scenarios file: {path}")
    return data


def resolve_scenario_id(scenario_id: str | None) -> str:
    catalog = load_scenarios_catalog()
    scenarios = catalog.get("scenarios", {})
    default = str(catalog.get("default", "impianto"))
    if isinstance(scenarios, dict) and scenario_id in scenarios:
        return str(scenario_id)
    return default


def list_scenarios() -> list[dict[str, Any]]:
    catalog = load_scenarios_catalog()
    scenarios = catalog.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return []
    default = str(catalog.get("default", "impianto"))
    rows: list[dict[str, Any]] = []
    for scenario_id, payload in scenarios.items():
        if not isinstance(payload, dict):
            continue
        rows.append({"id": scenario_id, "default": scenario_id == default, **payload})
    return rows


def get_scenario(scenario_id: str | None) -> dict[str, Any]:
    catalog = load_scenarios_catalog()
    scenarios = catalog.get("scenarios", {})
    default = str(catalog.get("default", "impianto"))
    key = resolve_scenario_id(scenario_id or default)
    if not isinstance(scenarios, dict):
        return {"id": key}
    payload = scenarios.get(key, {})
    if not isinstance(payload, dict):
        payload = {}
    return {"id": key, **payload}


def scenario_timeouts(scenario_id: str | None) -> dict[str, float | bool]:
    scenario = get_scenario(scenario_id)
    return {
        "industrial_timeout_seconds": float(scenario.get("industrial_timeout_seconds", 3)),
        "include_port_profile": bool(scenario.get("include_port_profile", False)),
        "passive_listen_seconds": float(scenario.get("passive_listen_seconds", 3)),
        "printer_timeout_seconds": float(scenario.get("printer_timeout_seconds", 4)),
        "nas_timeout_seconds": float(scenario.get("nas_timeout_seconds", 4)),
        "camera_timeout_seconds": float(scenario.get("camera_timeout_seconds", 4)),
    }
