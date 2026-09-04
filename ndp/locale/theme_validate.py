"""Validate NDP theme JSON files against themes.schema.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ndp.locale.loader import _INSTALL_ROOT, _SYSTEM_LOCALE_DIR, load_themes_catalog


@dataclass
class ThemeValidationReport:
    ok: bool
    file: str | None = None
    schema: str | None = None
    theme_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "file": self.file,
            "schema": self.schema,
            "theme_ids": self.theme_ids,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def resolve_themes_schema_path() -> Path | None:
    candidates = (
        _SYSTEM_LOCALE_DIR / "themes.schema.json",
        _INSTALL_ROOT / "docs" / "themes.schema.json",
        _INSTALL_ROOT / "ndp" / "locale" / "themes.schema.json",
        Path(__file__).resolve().parent / "themes.schema.json",
        Path(__file__).resolve().parents[2] / "docs" / "themes.schema.json",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object at root")
    return data


def _validate_with_schema(path: Path, schema_path: Path) -> list[str]:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("Install jsonschema: pip install jsonschema") from exc

    payload = _load_json(path)
    schema = _load_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        errors.append(f"{path}: {location}: {error.message}")
    return errors


def validate_themes_file(path: Path, *, schema_path: Path | None = None) -> ThemeValidationReport:
    report = ThemeValidationReport(ok=False, file=str(path))
    if not path.is_file():
        report.errors.append(f"File not found: {path}")
        return report

    schema = schema_path or resolve_themes_schema_path()
    if schema is None:
        report.errors.append("themes.schema.json not found (re-run install.sh)")
        return report
    report.schema = str(schema)

    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"{path}: invalid JSON: {exc}")
        return report

    try:
        report.errors.extend(_validate_with_schema(path, schema))
    except (OSError, ValueError, RuntimeError) as exc:
        report.errors.append(str(exc))
        return report

    themes = _load_json(path).get("themes", {})
    if isinstance(themes, dict):
        report.theme_ids = sorted(str(key) for key in themes.keys())

    report.ok = not report.errors
    return report


def validate_runtime_catalog() -> ThemeValidationReport:
    report = ThemeValidationReport(ok=False, file="merged-catalog")
    try:
        catalog = load_themes_catalog()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report.errors.append(f"load_themes_catalog failed: {exc}")
        return report

    themes = catalog.get("themes", {})
    if not isinstance(themes, dict) or not themes:
        report.errors.append("Merged catalog has no themes")
        return report

    report.theme_ids = sorted(str(key) for key in themes.keys())
    default = catalog.get("default")
    if default and default not in themes:
        report.warnings.append(f"default theme '{default}' is not defined in catalog")

    report.ok = True
    return report


def validate_themes_setup(custom_path: Path | None = None) -> ThemeValidationReport:
    """Validate custom themes file (if any) and merged runtime catalog."""
    custom = custom_path or (_SYSTEM_LOCALE_DIR / "themes.json")

    if custom.is_file():
        file_report = validate_themes_file(custom)
        if not file_report.ok:
            return file_report
        catalog_report = validate_runtime_catalog()
        if not catalog_report.ok:
            file_report.errors.extend(catalog_report.errors)
            file_report.ok = False
            return file_report
        file_report.theme_ids = catalog_report.theme_ids
        file_report.warnings.extend(catalog_report.warnings)
        return file_report

    catalog_report = validate_runtime_catalog()
    catalog_report.warnings.append(
        f"No custom themes file at {custom}; using bundled catalog only"
    )
    return catalog_report
