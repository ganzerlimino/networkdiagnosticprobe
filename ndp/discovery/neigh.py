"""Resolve L2 MAC addresses from the kernel neighbor table."""

from __future__ import annotations

from ndp.core.subprocess_runner import CommandError, run_json_command
from ndp.discovery.host import normalize_mac


def lookup_neighbor_mac(interface: str, ip: str) -> str | None:
    if not ip:
        return None
    try:
        data = run_json_command(["ip", "-j", "neigh", "show", "dev", interface])
    except (CommandError, FileNotFoundError):
        return None
    if not isinstance(data, list):
        return None
    for entry in data:
        if str(entry.get("dst")) != ip:
            continue
        lladdr = entry.get("lladdr")
        if not lladdr:
            continue
        state = str(entry.get("state", "")).upper()
        if "FAILED" in state or "INCOMPLETE" in state:
            continue
        return normalize_mac(str(lladdr))
    return None
