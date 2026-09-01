"""Load locale strings and color themes."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_BUNDLED_DIR = Path(__file__).resolve().parent
_SYSTEM_LOCALE_DIR = Path("/etc/ndp/locale")
_BUILTIN_LOCALES = ("it", "en")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {path}")
    return data


def _merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if key == "_meta":
            merged[key] = value
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def _locale_path(code: str) -> Path | None:
    normalized = code.strip().lower().replace("_", "-")
    if not normalized:
        return None
    custom = _SYSTEM_LOCALE_DIR / f"{normalized}.json"
    if custom.is_file():
        return custom
    bundled = _BUNDLED_DIR / f"{normalized}.json"
    if bundled.is_file():
        return bundled
    return None


def list_locales() -> list[dict[str, str]]:
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for directory in (_SYSTEM_LOCALE_DIR, _BUNDLED_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            if path.name == "themes.json":
                continue
            code = path.stem.lower()
            if code in seen:
                continue
            seen.add(code)
            try:
                meta = _load_json(path).get("_meta", {})
            except (OSError, json.JSONDecodeError, ValueError):
                meta = {}
            entries.append(
                {
                    "code": code,
                    "name": str(meta.get("name", code)),
                }
            )
    return entries


def load_locale(code: str = "it") -> dict[str, Any]:
    path = _locale_path(code)
    if path is None:
        path = _BUNDLED_DIR / "it.json"
    locale = _load_json(path)
    fallback = str(locale.get("_meta", {}).get("fallback", "en"))
    if fallback and fallback != path.stem:
        fallback_path = _locale_path(fallback)
        if fallback_path and fallback_path != path:
            locale = _merge_dict(_load_json(fallback_path), locale)
    return locale


def translate(locale: dict[str, Any], key: str, **variables: object) -> str:
    current: Any = locale
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return key
        current = current[part]
    if not isinstance(current, str):
        return key
    text = current
    for name, value in variables.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def load_themes_catalog() -> dict[str, Any]:
    for path in (_SYSTEM_LOCALE_DIR / "themes.json", _BUNDLED_DIR / "themes.json"):
        if path.is_file():
            return _load_json(path)
    raise FileNotFoundError("themes.json not found")


def get_theme(theme_id: str) -> dict[str, Any] | None:
    catalog = load_themes_catalog()
    themes = catalog.get("themes", {})
    if not isinstance(themes, dict):
        return None
    return themes.get(theme_id)


def resolve_theme_id(theme_id: str | None) -> str:
    catalog = load_themes_catalog()
    default = str(catalog.get("default", "field-dark"))
    themes = catalog.get("themes", {})
    if isinstance(themes, dict) and theme_id in themes:
        return str(theme_id)
    return default


def tft_palette(theme_id: str | None) -> dict[str, tuple[int, int, int]]:
    theme = get_theme(resolve_theme_id(theme_id))
    if not theme:
        return {
            "bg": (12, 18, 32),
            "header": (24, 36, 64),
            "text": (235, 240, 255),
            "muted": (140, 155, 180),
            "accent": (80, 200, 120),
        }
    tft = theme.get("tft", {})
    def _rgb(key: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
        raw = tft.get(key, default) if isinstance(tft, dict) else default
        if isinstance(raw, list) and len(raw) == 3:
            return int(raw[0]), int(raw[1]), int(raw[2])
        return default

    return {
        "bg": _rgb("bg", (12, 18, 32)),
        "header": _rgb("header", (24, 36, 64)),
        "text": _rgb("text", (235, 240, 255)),
        "muted": _rgb("muted", (140, 155, 180)),
        "accent": _rgb("accent", (80, 200, 120)),
    }
