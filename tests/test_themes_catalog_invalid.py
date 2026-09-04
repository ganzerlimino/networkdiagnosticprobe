import json
from pathlib import Path

import pytest

from ndp.locale.loader import load_themes_catalog


def test_load_themes_from_install_root_when_pip_bundle_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_locale = tmp_path / "ndp" / "locale"
    install_locale.mkdir(parents=True)
    bundled = {
        "version": 1,
        "default": "field-dark",
        "themes": {"field-dark": {"name": {"it": "Campo scuro"}, "web": {}, "tft": {}}},
    }
    (install_locale / "themes.json").write_text(json.dumps(bundled), encoding="utf-8")

    empty_pkg = tmp_path / "pkg" / "locale"
    empty_pkg.mkdir(parents=True)
    monkeypatch.setattr("ndp.locale.loader._INSTALL_ROOT", tmp_path)
    monkeypatch.setattr("ndp.locale.loader._BUNDLED_DIR", empty_pkg)
    monkeypatch.setattr("ndp.locale.loader._SYSTEM_LOCALE_DIR", tmp_path / "empty-etc")

    catalog = load_themes_catalog()
    assert "field-dark" in catalog["themes"]


def test_load_themes_catalog_ignores_invalid_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    system_dir = tmp_path / "locale"
    system_dir.mkdir()
    (system_dir / "themes.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr("ndp.locale.loader._SYSTEM_LOCALE_DIR", system_dir)

    catalog = load_themes_catalog()
    assert "field-dark" in catalog["themes"]
