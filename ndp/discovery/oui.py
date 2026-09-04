"""MAC vendor lookup with bundled, system and learned OUI tables."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUI_PATHS = (
    Path("/usr/share/arp-scan/ieee-oui.txt"),
    Path("/usr/local/share/arp-scan/ieee-oui.txt"),
    Path("/usr/share/misc/oui.txt"),
)

BUNDLED_OUI_PATH = Path(__file__).resolve().parent.parent / "data" / "oui_bundled.txt"
LEARNED_OUI_PATH = Path("/var/lib/ndp/oui_learned.json")

EWON_OUIS = frozenset({"00:05:F5", "00:1E:C0"})
WEINTEK_OUIS = frozenset({"00:90:E8"})

_lock = threading.RLock()
_system_map: dict[str, str] | None = None
_bundled_map: dict[str, str] | None = None
_learned_map: dict[str, dict[str, str]] | None = None
_loaded_at: datetime | None = None


def _parse_oui_file(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path.is_file():
        return mapping
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        prefix, vendor = line.split("\t", 1)
        mapping[prefix.strip().upper()] = vendor.strip()
    return mapping


def _load_learned() -> dict[str, dict[str, str]]:
    if not LEARNED_OUI_PATH.is_file():
        return {}
    try:
        payload = json.loads(LEARNED_OUI_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read learned OUI file: %s", exc)
        return {}
    entries = payload.get("entries", payload)
    if not isinstance(entries, dict):
        return {}
    return {
        str(prefix).upper(): value
        for prefix, value in entries.items()
        if isinstance(value, dict) and value.get("vendor")
    }


def _save_learned() -> None:
    if _learned_map is None:
        return
    try:
        LEARNED_OUI_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": _learned_map,
        }
        LEARNED_OUI_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist learned OUI entries: %s", exc)


def _ensure_loaded(*, force: bool = False) -> None:
    global _system_map, _bundled_map, _learned_map, _loaded_at
    if not force and _system_map is not None and _bundled_map is not None and _learned_map is not None:
        return
    system: dict[str, str] = {}
    for path in OUI_PATHS:
        system.update(_parse_oui_file(path))
    _system_map = system
    _bundled_map = _parse_oui_file(BUNDLED_OUI_PATH)
    _learned_map = _load_learned()
    _loaded_at = datetime.now(timezone.utc)


def reload_oui_database() -> dict[str, Any]:
    with _lock:
        _ensure_loaded(force=True)
        return oui_snapshot()


def _mac_prefix(mac: str) -> str | None:
    cleaned = mac.replace(":", "").replace("-", "").upper()
    if len(cleaned) < 6:
        return None
    prefix = cleaned[:6]
    return f"{prefix[0:2]}:{prefix[2:4]}:{prefix[4:6]}"


def lookup_vendor(mac: str) -> str | None:
    prefix = _mac_prefix(mac)
    if prefix is None:
        return None
    with _lock:
        _ensure_loaded()
        assert _learned_map is not None
        assert _system_map is not None
        assert _bundled_map is not None
        learned = _learned_map.get(prefix)
        if learned:
            return learned.get("vendor")
        if prefix in _system_map:
            return _system_map[prefix]
        return _bundled_map.get(prefix)


def lookup_vendor_source(mac: str) -> tuple[str | None, str | None]:
    prefix = _mac_prefix(mac)
    if prefix is None:
        return None, None
    with _lock:
        _ensure_loaded()
        assert _learned_map is not None
        assert _system_map is not None
        assert _bundled_map is not None
        learned = _learned_map.get(prefix)
        if learned:
            return learned.get("vendor"), learned.get("source", "learned")
        if prefix in _system_map:
            return _system_map[prefix], "system"
        if prefix in _bundled_map:
            return _bundled_map[prefix], "bundled"
        return None, None


def record_vendor(mac: str, vendor: str, *, source: str = "arp-scan") -> bool:
    prefix = _mac_prefix(mac)
    if prefix is None or not vendor.strip():
        return False
    with _lock:
        _ensure_loaded()
        assert _learned_map is not None
        existing = _learned_map.get(prefix, {})
        if existing.get("vendor") == vendor.strip() and existing.get("source") == source:
            return False
        _learned_map[prefix] = {
            "vendor": vendor.strip(),
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_learned()
        return True


def record_vendors_from_hosts(hosts: list[object]) -> int:
    recorded = 0
    for host in hosts:
        mac = getattr(host, "mac", None)
        vendor = getattr(host, "vendor", None)
        if mac and vendor:
            if record_vendor(str(mac), str(vendor), source=getattr(host, "source", "arp-scan")):
                recorded += 1
    return recorded


def is_ewon_mac(mac: str) -> bool:
    prefix = _mac_prefix(mac)
    return prefix in EWON_OUIS if prefix else False


def is_weintek_mac(mac: str) -> bool:
    prefix = _mac_prefix(mac)
    return prefix in WEINTEK_OUIS if prefix else False


def oui_table(*, search: str = "", limit: int = 500) -> list[dict[str, str]]:
    query = search.strip().lower()
    with _lock:
        _ensure_loaded()
        assert _learned_map is not None
        assert _system_map is not None
        assert _bundled_map is not None
        rows: dict[str, dict[str, str]] = {}
        for prefix, vendor in _system_map.items():
            rows[prefix] = {"prefix": prefix, "vendor": vendor, "source": "system"}
        for prefix, vendor in _bundled_map.items():
            rows.setdefault(prefix, {"prefix": prefix, "vendor": vendor, "source": "bundled"})
        for prefix, meta in _learned_map.items():
            rows[prefix] = {
                "prefix": prefix,
                "vendor": meta.get("vendor", ""),
                "source": meta.get("source", "learned"),
            }
    items = list(rows.values())
    if query:
        items = [
            row
            for row in items
            if query in row["prefix"].lower() or query in row["vendor"].lower()
        ]
    items.sort(key=lambda row: row["prefix"])
    return items[: max(1, min(limit, 5000))]


def oui_snapshot() -> dict[str, Any]:
    with _lock:
        _ensure_loaded()
        assert _system_map is not None
        assert _bundled_map is not None
        assert _learned_map is not None
        return {
            "loaded_at": _loaded_at.isoformat() if _loaded_at else None,
            "counts": {
                "system": len(_system_map),
                "bundled": len(_bundled_map),
                "learned": len(_learned_map),
                "total_unique": len(
                    set(_system_map) | set(_bundled_map) | set(_learned_map)
                ),
            },
            "paths": {
                "bundled": str(BUNDLED_OUI_PATH),
                "learned": str(LEARNED_OUI_PATH),
                "system": [str(path) for path in OUI_PATHS if path.is_file()],
            },
            "industrial_ouis": {
                "ewon": sorted(EWON_OUIS),
                "weintek": sorted(WEINTEK_OUIS),
            },
        }
