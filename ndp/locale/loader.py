"""Load locale strings and color themes."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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


def translate_config_field(
    locale: dict[str, Any],
    field_key: str,
    part: str,
    *,
    fallback: str = "",
) -> str:
    """Resolve config.fields.<dotted-key>.label|help (field keys contain dots)."""
    config = locale.get("config")
    if not isinstance(config, dict):
        return fallback or f"config.fields.{field_key}.{part}"
    fields = config.get("fields")
    if not isinstance(fields, dict):
        return fallback or f"config.fields.{field_key}.{part}"
    entry = fields.get(field_key)
    if not isinstance(entry, dict):
        return fallback or f"config.fields.{field_key}.{part}"
    value = entry.get(part)
    if isinstance(value, str) and value:
        return value
    return fallback or f"config.fields.{field_key}.{part}"


def load_themes_catalog() -> dict[str, Any]:
    bundled_path = _BUNDLED_DIR / "themes.json"
    if not bundled_path.is_file():
        raise FileNotFoundError("themes.json not found")
    catalog = _load_json(bundled_path)
    system_path = _SYSTEM_LOCALE_DIR / "themes.json"
    if system_path.is_file():
        try:
            overlay = _load_json(system_path)
            catalog = _merge_themes_catalog(catalog, overlay)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid custom themes file %s (%s); using bundled catalog", system_path, exc)
    return catalog


def _merge_themes_catalog(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key in ("version", "default"):
        if key in overlay:
            merged[key] = overlay[key]
    base_themes = merged.setdefault("themes", {})
    overlay_themes = overlay.get("themes", {})
    if not isinstance(base_themes, dict):
        base_themes = {}
        merged["themes"] = base_themes
    if isinstance(overlay_themes, dict):
        for theme_id, theme in overlay_themes.items():
            if (
                theme_id in base_themes
                and isinstance(theme, dict)
                and isinstance(base_themes.get(theme_id), dict)
            ):
                base_themes[theme_id] = _merge_dict(base_themes[theme_id], theme)  # type: ignore[arg-type]
            else:
                base_themes[theme_id] = theme
    return merged


def theme_display_name(theme: dict[str, Any], locale_code: str = "it") -> str:
    name = theme.get("name")
    locale = locale_code.strip().lower().split("-")[0] or "it"
    if isinstance(name, dict):
        for key in (locale, "it", "en"):
            if key in name and name[key]:
                return str(name[key])
        for value in name.values():
            if value:
                return str(value)
        return ""
    if isinstance(name, str):
        return name
    return ""


def list_themes(locale_code: str = "it") -> list[dict[str, str]]:
    catalog = load_themes_catalog()
    themes = catalog.get("themes", {})
    if not isinstance(themes, dict):
        return []
    entries: list[dict[str, str]] = []
    for theme_id in sorted(themes.keys()):
        theme = themes[theme_id]
        if not isinstance(theme, dict):
            continue
        label = theme_display_name(theme, locale_code) or str(theme_id)
        entries.append({"id": str(theme_id), "name": label})
    return entries


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
