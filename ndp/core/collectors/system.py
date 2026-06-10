"""Host system metrics collector."""

from __future__ import annotations

from pathlib import Path

from ndp.core.state import SystemState


def _read_float(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def collect_system_state() -> SystemState:
    hostname = None
    try:
        hostname = Path("/etc/hostname").read_text(encoding="utf-8").strip()
    except OSError:
        pass

    uptime_seconds = _read_float(Path("/proc/uptime"))

    cpu_temperature_c = None
    for thermal_zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        temp = _read_float(thermal_zone / "temp")
        if temp is not None:
            cpu_temperature_c = temp / 1000.0
            break

    return SystemState(
        hostname=hostname,
        uptime_seconds=uptime_seconds,
        cpu_temperature_c=cpu_temperature_c,
    )
