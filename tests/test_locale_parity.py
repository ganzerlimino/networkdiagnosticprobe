"""Ensure locale bundles stay aligned across it/en/de."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LOCALES = ("it", "en", "de")


def _flatten(data: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "_meta":
                continue
            path = f"{prefix}.{key}" if prefix else key
            out.update(_flatten(value, path))
    else:
        out[prefix] = data
    return out


@pytest.fixture
def locale_keys() -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for code in LOCALES:
        path = REPO / "ndp" / "locale" / f"{code}.json"
        keys[code] = set(_flatten(json.loads(path.read_text(encoding="utf-8"))).keys())
    return keys


def test_locale_key_parity(locale_keys: dict[str, set[str]]) -> None:
    base = locale_keys["it"]
    for code in ("en", "de"):
        missing = sorted(base - locale_keys[code])
        extra = sorted(locale_keys[code] - base)
        assert not missing, f"{code}.json missing keys: {missing[:10]}"
        assert not extra, f"{code}.json extra keys: {extra[:10]}"


def test_theme_names_include_de() -> None:
    catalog = json.loads((REPO / "ndp" / "locale" / "themes.json").read_text(encoding="utf-8"))
    for theme_id, theme in catalog["themes"].items():
        name = theme.get("name", {})
        assert isinstance(name, dict)
        for lang in LOCALES:
            assert lang in name and name[lang], f"{theme_id} missing {lang} name"


def test_scenario_profiles_include_de() -> None:
    import yaml

    data = yaml.safe_load((REPO / "ndp" / "scenarios" / "profiles.yaml").read_text(encoding="utf-8"))
    for scenario_id, payload in data["scenarios"].items():
        for field in ("name", "description"):
            block = payload[field]
            for lang in LOCALES:
                assert lang in block and block[lang], f"{scenario_id}.{field} missing {lang}"
