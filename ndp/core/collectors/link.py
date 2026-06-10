"""Ethernet link status collector."""

from __future__ import annotations

import re
from pathlib import Path

from ndp.core.state import LinkState
from ndp.core.subprocess_runner import CommandError, run_command


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _parse_ethtool(output: str) -> tuple[int | None, str | None]:
    speed = None
    duplex = None
    speed_match = re.search(r"\bSpeed:\s*(\d+)Mb/s", output)
    if speed_match:
        speed = int(speed_match.group(1))
    duplex_match = re.search(r"\bDuplex:\s*(\S+)", output)
    if duplex_match:
        duplex = duplex_match.group(1)
    return speed, duplex


def collect_link_state(interface: str) -> LinkState:
    operstate = _read_text(Path(f"/sys/class/net/{interface}/operstate")) or "unknown"
    carrier_raw = _read_text(Path(f"/sys/class/net/{interface}/carrier"))
    carrier = carrier_raw == "1"
    mac_address = _read_text(Path(f"/sys/class/net/{interface}/address"))

    speed = None
    duplex = None
    if carrier:
        try:
            ethtool_output = run_command(["ethtool", interface])
            speed, duplex = _parse_ethtool(ethtool_output)
        except (CommandError, FileNotFoundError):
            speed_raw = _read_text(Path(f"/sys/class/net/{interface}/speed"))
            if speed_raw and speed_raw.isdigit() and int(speed_raw) > 0:
                speed = int(speed_raw)

    return LinkState(
        operstate=operstate,
        carrier=carrier,
        speed_mbps=speed,
        duplex=duplex,
        mac_address=mac_address,
    )
