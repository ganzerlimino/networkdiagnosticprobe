import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def themes_schema() -> dict:
    jsonschema = pytest.importorskip("jsonschema")
    path = REPO / "docs" / "themes.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_bundled_themes_json_matches_schema(themes_schema: dict) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    catalog = json.loads((REPO / "ndp" / "locale" / "themes.json").read_text(encoding="utf-8"))
    jsonschema.validate(catalog, themes_schema)


def test_aziendale_example_matches_schema(themes_schema: dict) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    example = json.loads(
        (REPO / "docs" / "examples" / "themes-aziendale.example.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(example, themes_schema)
