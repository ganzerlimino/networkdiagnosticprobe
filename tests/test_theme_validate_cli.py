"""Theme validation CLI and library tests."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from ndp.cli.theme import run_theme_command
from ndp.locale.theme_validate import (
    resolve_themes_schema_path,
    validate_runtime_catalog,
    validate_themes_file,
    validate_themes_setup,
)
from ndp.main import build_parser

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def themes_schema_path() -> Path:
    path = resolve_themes_schema_path()
    assert path is not None
    return path


def test_resolve_themes_schema_path_finds_repo_schema() -> None:
    path = resolve_themes_schema_path()
    assert path is not None
    assert path.name == "themes.schema.json"


def test_validate_bundled_themes_file_ok(themes_schema_path: Path) -> None:
    pytest.importorskip("jsonschema")
    report = validate_themes_file(REPO / "ndp" / "locale" / "themes.json", schema_path=themes_schema_path)
    assert report.ok
    assert "field-dark" in report.theme_ids
    assert not report.errors


def test_validate_example_themes_file_ok(themes_schema_path: Path) -> None:
    pytest.importorskip("jsonschema")
    report = validate_themes_file(
        REPO / "docs" / "examples" / "themes-aziendale.example.json",
        schema_path=themes_schema_path,
    )
    assert report.ok
    assert "aziendale" in report.theme_ids


def test_validate_invalid_json(tmp_path: Path, themes_schema_path: Path) -> None:
    bad = tmp_path / "themes.json"
    bad.write_text("{not-json", encoding="utf-8")
    report = validate_themes_file(bad, schema_path=themes_schema_path)
    assert not report.ok
    assert any("invalid JSON" in error for error in report.errors)


def test_validate_schema_violation(tmp_path: Path, themes_schema_path: Path) -> None:
    pytest.importorskip("jsonschema")
    bad = tmp_path / "themes.json"
    bad.write_text(
        json.dumps(
            {
                "themes": {
                    "bad-theme": {
                        "name": {"it": "Bad"},
                        "color_scheme": "dark",
                        "web": {"bg": "not-a-hex"},
                        "tft": {"bg": [0, 0, 0], "header": [1, 1, 1], "text": [2, 2, 2], "muted": [3, 3, 3], "accent": [4, 4, 4]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    report = validate_themes_file(bad, schema_path=themes_schema_path)
    assert not report.ok
    assert report.errors


def test_validate_missing_file(tmp_path: Path, themes_schema_path: Path) -> None:
    report = validate_themes_file(tmp_path / "missing.json", schema_path=themes_schema_path)
    assert not report.ok
    assert any("File not found" in error for error in report.errors)


def test_validate_runtime_catalog_ok() -> None:
    report = validate_runtime_catalog()
    assert report.ok
    assert "field-dark" in report.theme_ids


def test_validate_themes_setup_without_custom_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ndp.locale.theme_validate._SYSTEM_LOCALE_DIR", tmp_path / "locale")
    report = validate_themes_setup()
    assert report.ok
    assert any("No custom themes file" in warning for warning in report.warnings)


def test_cli_validate_ok_exit_0(themes_schema_path: Path) -> None:
    pytest.importorskip("jsonschema")
    args = Namespace(
        theme_command="validate",
        file=REPO / "ndp" / "locale" / "themes.json",
        catalog_only=False,
        json=False,
    )
    assert run_theme_command(args) == 0


def test_cli_validate_invalid_exit_1(tmp_path: Path, themes_schema_path: Path) -> None:
    pytest.importorskip("jsonschema")
    bad = tmp_path / "themes.json"
    bad.write_text('{"themes": {}}', encoding="utf-8")
    args = Namespace(theme_command="validate", file=bad, catalog_only=False, json=False)
    assert run_theme_command(args) == 1


def test_cli_validate_json_output(capsys, themes_schema_path: Path) -> None:
    pytest.importorskip("jsonschema")
    args = Namespace(
        theme_command="validate",
        file=REPO / "ndp" / "locale" / "themes.json",
        catalog_only=False,
        json=True,
    )
    assert run_theme_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "field-dark" in payload["theme_ids"]


def test_cli_catalog_only() -> None:
    args = Namespace(theme_command="validate", file=None, catalog_only=True, json=False)
    assert run_theme_command(args) == 0


def test_parser_accepts_theme_validate() -> None:
    args = build_parser().parse_args(["theme", "validate", "--json"])
    assert args.command == "theme"
    assert args.theme_command == "validate"
    assert args.json is True
