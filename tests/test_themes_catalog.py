import json
from pathlib import Path

import pytest

from ndp.locale.loader import (
    list_themes,
    load_themes_catalog,
    theme_display_name,
)
from ndp.web.config_schema import config_sections


def test_list_themes_includes_bundled_field_dark() -> None:
    ids = {entry["id"] for entry in list_themes("it")}
    assert "field-dark" in ids


def test_list_themes_localized_name() -> None:
    themes = {entry["id"]: entry["name"] for entry in list_themes("it")}
    assert themes["field-dark"] == "Campo scuro"


def test_theme_display_name_fallback_en() -> None:
    catalog = load_themes_catalog()
    theme = catalog["themes"]["field-dark"]
    assert theme_display_name(theme, "de") in {"Field dark", "Campo scuro"}


def test_config_schema_theme_options_match_catalog() -> None:
    sections = config_sections("it")
    appearance = next(section for section in sections if section["id"] == "appearance")
    theme_field = next(field for field in appearance["fields"] if field["key"] == "ui.theme")  # type: ignore[index]
    catalog_ids = {entry["id"] for entry in list_themes("it")}
    assert set(theme_field["options"]) == catalog_ids  # type: ignore[index]


def test_load_themes_merges_custom_theme(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    system_dir = tmp_path / "locale"
    system_dir.mkdir()
    overlay = {
        "default": "aziendale",
        "themes": {
            "aziendale": {
                "name": {"it": "Aziendale"},
                "color_scheme": "dark",
                "web": {"bg": "#000000", "card": "#111111", "surface": "#101010", "text": "#ffffff", "muted": "#cccccc", "accent": "#0066cc", "accent_text": "#ffffff", "danger": "#ff4444", "border": "#333333", "header_alpha": "0.96", "chart": ["#0066cc"]},
                "tft": {"bg": [0, 0, 0], "header": [20, 20, 20], "text": [255, 255, 255], "muted": [180, 180, 180], "accent": [0, 102, 204]},
            }
        },
    }
    (system_dir / "themes.json").write_text(json.dumps(overlay), encoding="utf-8")
    monkeypatch.setattr("ndp.locale.loader._SYSTEM_LOCALE_DIR", system_dir)

    catalog = load_themes_catalog()
    assert "field-dark" in catalog["themes"]
    assert "aziendale" in catalog["themes"]
    assert catalog["default"] == "aziendale"
    ids = {entry["id"] for entry in list_themes("it")}
    assert "aziendale" in ids
