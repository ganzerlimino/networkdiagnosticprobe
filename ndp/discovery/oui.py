"""MAC vendor lookup from arp-scan IEEE OUI database."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

OUI_PATHS = (
    Path("/usr/share/arp-scan/ieee-oui.txt"),
    Path("/usr/local/share/arp-scan/ieee-oui.txt"),
    Path("/usr/share/misc/oui.txt"),
)


@lru_cache(maxsize=1)
def _load_oui_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in OUI_PATHS:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" not in line:
                continue
            prefix, vendor = line.split("\t", 1)
            mapping[prefix.strip().upper()] = vendor.strip()
    return mapping


def lookup_vendor(mac: str) -> str | None:
    cleaned = mac.replace(":", "").replace("-", "").upper()
    if len(cleaned) < 6:
        return None

    oui_map = _load_oui_map()
    if not oui_map:
        return None

    prefix = cleaned[:6]
    dotted = f"{prefix[0:2]}:{prefix[2:4]}:{prefix[4:6]}"
    return oui_map.get(dotted) or oui_map.get(prefix)
