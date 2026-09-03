"""Pygame screen rendering helpers."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from ndp.core.state import ProbeState


def _hotspot_hint_lines(config: object | None, web_port: int) -> list[str]:
    if config is None:
        return [f"Web  :{web_port}"]
    try:
        from ndp.network.hotspot import hotspot_display_lines

        lines = hotspot_display_lines(config)  # type: ignore[arg-type]
        return lines or [f"Web  :{web_port}"]
    except Exception:
        return [f"Web  :{web_port}"]


@lru_cache(maxsize=8)
def _locale_bundle(locale_code: str) -> dict[str, Any]:
    from ndp.locale.loader import load_locale

    return load_locale(locale_code)


def _t(config: object | None, key: str, **variables: object) -> str:
    from ndp.locale.loader import translate

    code = getattr(config, "ui_locale", "it") if config is not None else "it"
    return translate(_locale_bundle(str(code)), key, **variables)


def _label(config: object | None, name: str) -> str:
    text = _t(config, f"tft.labels.{name}")
    return text if text != f"tft.labels.{name}" else name


def tft_text(config: object | None, key: str, **variables: object) -> str:
    return _t(config, key, **variables)


def shutdown_palette() -> dict[str, tuple[int, int, int]]:
    """High-visibility red palette for TFT shutdown (independent of UI theme)."""
    return {
        "bg": (96, 0, 0),
        "header": (200, 0, 0),
        "text": (255, 255, 255),
        "muted": (255, 220, 180),
        "accent": (255, 220, 0),
        "stripe": (255, 255, 255),
    }


def shutdown_phase_message(phase: str, config: object | None = None) -> str:
    key = {
        "stopping_services": "tft.shutdown_stopping",
        "powering_off": "tft.shutdown_poweroff",
    }.get(phase, "tft.shutdown_message")
    return _t(config, key)


def shutdown_lines(message: str | None = None, config: object | None = None) -> list[str]:
    return [
        _t(config, "tft.shutdown_title"),
        message or _t(config, "tft.shutdown_message"),
        "",
        _t(config, "tft.shutdown_warn1"),
        _t(config, "tft.shutdown_warn2"),
    ]


class ScreenId(Enum):
    HOME = 0
    SWITCH = 1
    NETWORK = 2
    PING = 3
    SYSTEM = 4
    DISCOVER = 5


def screen_title(screen: ScreenId, config: object | None = None) -> str:
    key = f"tft.screens.{screen.name.lower()}"
    text = _t(config, key)
    return text if text != key else screen.name.title()


SCREEN_TITLES = {
    ScreenId.HOME: "Home",
    ScreenId.SWITCH: "Switch",
    ScreenId.NETWORK: "Network",
    ScreenId.PING: "Ping",
    ScreenId.SYSTEM: "System",
    ScreenId.DISCOVER: "Discover",
}


def screen_ids_for_mode(interactive: bool) -> list[ScreenId]:
    """Display-only mode skips the Discover wizard screen."""
    if interactive:
        return list(ScreenId)
    return [screen for screen in ScreenId if screen != ScreenId.DISCOVER]


def next_screen(
    current: ScreenId,
    step: int = 1,
    *,
    screens: list[ScreenId] | None = None,
) -> ScreenId:
    values = screens or list(ScreenId)
    index = (values.index(current) + step) % len(values)
    return values[index]


def _fmt(value: object, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _ping_line(label: str, host: str, reachable: bool, rtt_ms: float | None, message: str) -> str:
    short_label = label[:6]
    short_host = host[:12]
    if reachable and rtt_ms is not None:
        return f"{short_label} {short_host} {rtt_ms:.0f}ms"
    return f"{short_label} {short_host} FAIL"


def lines_for_screen(
    screen: ScreenId,
    state: ProbeState,
    *,
    interactive: bool = False,
    web_port: int = 8080,
    config: object | None = None,
) -> list[str]:
    if screen == ScreenId.HOME:
        ip = "n/a"
        if state.ip.addresses:
            first = state.ip.addresses[0]
            ip = f"{first.address}/{first.prefixlen}"
        link = _t(config, "common.up") if state.link.carrier else _t(config, "common.down")
        return [
            f"{_label(config, 'link'):<6} {link}",
            f"{_label(config, 'host'):<6} {_fmt(state.system.hostname)}",
            f"{_label(config, 'ip'):<6} {ip}",
            f"{_label(config, 'mac'):<6} {_fmt(state.link.mac_address)}",
        ]

    if screen == ScreenId.SWITCH:
        if not state.link.carrier:
            return [_t(config, "tft.link_down"), _t(config, "tft.plug_cable")]
        if state.neighbor.available:
            lines = [
                f"{_label(config, 'proto'):<6} {_fmt(state.neighbor.protocol)}",
                f"{_label(config, 'switch'):<6} {_fmt(state.neighbor.switch_name)}",
                f"{_label(config, 'port'):<6} {_fmt(state.neighbor.port_id)}",
                f"{_label(config, 'vlan'):<6} {_fmt(state.neighbor.vlan_id)}",
            ]
            if state.neighbor.med_capabilities:
                lines.append(f"MED    {_fmt(state.neighbor.med_capabilities)}")
            if state.neighbor.poe_status:
                lines.append(f"PoE    {_fmt(state.neighbor.poe_status)}")
            return lines
        lines = [_t(config, "tft.no_neighbor"), _fmt(state.neighbor.message, _t(config, "tft.waiting"))]
        for entry in getattr(state, "neighbors", []) or []:
            if entry.available:
                continue
            proto = _fmt(entry.protocol, "?")
            lines.append(f"{proto} {_fmt(entry.message)}")
        return lines[:8]

    if screen == ScreenId.NETWORK:
        lines = []
        if state.ip.addresses:
            for addr in state.ip.addresses[:2]:
                lines.append(f"{addr.family} {addr.address}/{addr.prefixlen}")
        else:
            lines.append(_t(config, "tft.no_ip"))
        lines.append(f"{_label(config, 'gw'):<3} {_fmt(state.ip.gateway)}")
        dns = ", ".join(state.ip.dns_servers[:2]) if state.ip.dns_servers else "n/a"
        lines.append(f"{_label(config, 'dns'):<3} {dns}")
        if state.link.speed_mbps:
            lines.append(f"Link {state.link.speed_mbps} Mbps")
        return lines[:5]

    if screen == ScreenId.PING:
        if state.ping.running:
            return [_t(config, "tft.ping_running"), "", state.ping.message]
        if not state.ping.results:
            adhoc = state.ping.adhoc_host or "n/a"
            lines = [
                "8.8.8.8 + 1.1.1.1",
                f"{_label(config, 'adhoc')}: {adhoc[:16]}",
                "",
            ]
            if interactive:
                lines.extend([_t(config, "tft.run_ping"), "ndp test ping", "--adhoc HOST"])
            else:
                lines.append(_t(config, "tft.run_from_phone", port=web_port))
            return lines
        lines = [
            _ping_line(
                item.label,
                item.host,
                item.result.reachable,
                item.result.rtt_ms,
                item.result.message,
            )
            for item in state.ping.results[:6]
        ]
        if state.ping.adhoc_host:
            lines.append(f"{_label(config, 'adhoc')} {state.ping.adhoc_host[:16]}")
        if interactive:
            lines.append(_t(config, "tft.repeat"))
        return lines[:7]

    if screen == ScreenId.SYSTEM:
        uptime = _fmt(state.system.uptime_seconds, "n/a")
        if state.system.uptime_seconds is not None:
            uptime = f"{int(state.system.uptime_seconds)} s"
        temp = _fmt(state.system.cpu_temperature_c, "n/a")
        if state.system.cpu_temperature_c is not None:
            temp = f"{state.system.cpu_temperature_c:.1f} C"

        lines = [
            f"{_label(config, 'host'):<6} {_fmt(state.system.hostname)}",
            f"{_label(config, 'up'):<6} {uptime}",
            f"{_label(config, 'temp'):<6} {temp}",
            f"{_label(config, 'if'):<6} {state.interface}",
        ]
        if interactive:
            lines.append(_t(config, "tft.ndp_ready"))
        else:
            lines.extend(_hotspot_hint_lines(config, web_port)[:2])
        return lines

    if screen == ScreenId.DISCOVER:
        if interactive:
            return [_t(config, "tft.discover_screen")]
        return [
            "Up/Down scan",
            _t(config, "tft.updown_phone"),
            _t(config, "tft.updown_cli"),
            "ndp discover updown",
        ]

    return []
