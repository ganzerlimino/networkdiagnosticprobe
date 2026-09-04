import json
from pathlib import Path

import pytest

from ndp.locale.loader import load_themes_catalog


def test_load_themes_catalog_ignores_invalid_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    system_dir = tmp_path / "locale"
    system_dir.mkdir()
    (system_dir / "themes.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr("ndp.locale.loader._SYSTEM_LOCALE_DIR", system_dir)

    catalog = load_themes_catalog()
    assert "field-dark" in catalog["themes"]
