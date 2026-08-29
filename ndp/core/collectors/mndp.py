"""MikroTik Neighbor Discovery Protocol (MNDP) passive collector."""

from __future__ import annotations

import logging
import socket
import struct
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ndp.core.state import NeighborState
from ndp.discovery.host import normalize_mac

logger = logging.getLogger(__name__)

MNDP_PORT = 5678
_DEFAULT_LISTEN_SECONDS = 1.5
_SCAN_LISTEN_SECONDS = 3.0


@dataclass
class MndpDevice:
    identity: str | None = None
    mac: str | None = None
    ipv4: str | None = None
    board: str | None = None
    platform: str | None = None
    version: str | None = None
    interface: str | None = None
    software_id: str | None = None
    uptime_seconds: int | None = None
    last_seen: datetime | None = None
    connected: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.last_seen is not None:
            data["last_seen"] = self.last_seen.isoformat()
        return data

    def to_neighbor_state(self, *, message: str = "ok") -> NeighborState:
        switch_name = str(self.identity or self.board or self.platform or "MikroTik")
        description_parts = [part for part in (self.platform, self.board, self.version) if part]
        if self.software_id:
            description_parts.append(f"id={self.software_id}")
        if self.uptime_seconds is not None:
            description_parts.append(f"uptime={self.uptime_seconds}s")
        return NeighborState(
            protocol="MNDP",
            switch_name=switch_name,
            port_id=self.interface,
            chassis_id=self.mac,
            system_description=", ".join(description_parts) or None,
            software_version=self.version,
            platform=self.platform,
            board=self.board,
            identity=self.identity,
            ipv4_address=self.ipv4,
            age_seconds=self.uptime_seconds,
            last_seen=self.last_seen or datetime.now(timezone.utc),
            available=True,
            message=message,
        )


def _format_mac(raw: bytes) -> str:
    return normalize_mac(":".join(f"{byte:02x}" for byte in raw))


def _format_ipv4(raw: bytes) -> str:
    return ".".join(str(byte) for byte in raw)


def parse_mndp_payload(payload: bytes) -> dict[str, object]:
    """Parse MNDP UDP payload TLV stream."""
    fields: dict[str, object] = {}
    offset = 4  # skip 2-byte header + 2-byte sequence

    while offset + 4 <= len(payload):
        tlv_type, tlv_len = struct.unpack_from("!HH", payload, offset)
        offset += 4
        if offset + tlv_len > len(payload):
            break
        value = payload[offset : offset + tlv_len]
        offset += tlv_len

        if tlv_type == 1 and tlv_len == 6:
            fields["mac"] = _format_mac(value)
        elif tlv_type == 5:
            fields["identity"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 7:
            fields["version"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 8:
            fields["platform"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 10 and tlv_len == 4:
            fields["uptime_seconds"] = struct.unpack("<I", value)[0]
        elif tlv_type == 11:
            fields["software_id"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 12:
            fields["board"] = value.decode("utf-8", errors="replace")
        elif tlv_type in {13, 16}:
            fields["interface"] = value.decode("utf-8", errors="replace")
        elif tlv_type == 17 and tlv_len == 4:
            fields["ipv4"] = _format_ipv4(value)

    return fields


def _fields_to_device(fields: dict[str, object]) -> MndpDevice | None:
    if not fields.get("mac") and not fields.get("identity"):
        return None
    uptime = fields.get("uptime_seconds")
    return MndpDevice(
        identity=str(fields["identity"]) if fields.get("identity") else None,
        mac=str(fields["mac"]) if fields.get("mac") else None,
        ipv4=str(fields["ipv4"]) if fields.get("ipv4") else None,
        board=str(fields["board"]) if fields.get("board") else None,
        platform=str(fields["platform"]) if fields.get("platform") else None,
        version=str(fields["version"]) if fields.get("version") else None,
        interface=str(fields["interface"]) if fields.get("interface") else None,
        software_id=str(fields["software_id"]) if fields.get("software_id") else None,
        uptime_seconds=int(uptime) if isinstance(uptime, int) else None,
        last_seen=datetime.now(timezone.utc),
    )


def _device_key(device: MndpDevice) -> str:
    return device.mac or f"{device.identity}|{device.ipv4}"


def pick_connected_mndp_device(
    devices: list[MndpDevice],
    *,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
) -> MndpDevice | None:
    """Pick the MikroTik device most likely on the NDP Ethernet hop (not whole LAN)."""
    if not devices:
        return None

    gw_mac = normalize_mac(gateway_mac) if gateway_mac else None
    if gw_mac:
        for device in devices:
            if device.mac and normalize_mac(device.mac) == gw_mac:
                device.connected = True
                return device

    if gateway_ip:
        for device in devices:
            if device.ipv4 == gateway_ip:
                device.connected = True
                return device

    return None


def discover_mndp_devices(
    interface: str,
    *,
    listen_seconds: float = _SCAN_LISTEN_SECONDS,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
) -> list[MndpDevice]:
    """Listen for all MNDP announcements visible on the probe interface."""
    devices: dict[str, MndpDevice] = {}
    deadline = datetime.now(timezone.utc).timestamp() + listen_seconds

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        except OSError:
            logger.debug("SO_BINDTODEVICE unavailable for MNDP on %s", interface)
        sock.bind(("", MNDP_PORT))
        sock.settimeout(0.25)
    except OSError as exc:
        logger.debug("MNDP listen unavailable on %s: %s", interface, exc)
        return []

    try:
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                logger.debug("MNDP recv error: %s", exc)
                break

            if len(data) < 8:
                continue

            device = _fields_to_device(parse_mndp_payload(data))
            if device is None:
                continue
            devices[_device_key(device)] = device
    finally:
        sock.close()

    found = list(devices.values())
    connected = pick_connected_mndp_device(found, gateway_ip=gateway_ip, gateway_mac=gateway_mac)
    if connected is not None:
        for device in found:
            device.connected = _device_key(device) == _device_key(connected)
    return sorted(found, key=lambda item: (not item.connected, item.identity or "", item.ipv4 or ""))


def collect_mndp_neighbor(
    interface: str,
    *,
    listen_seconds: float = _DEFAULT_LISTEN_SECONDS,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
) -> NeighborState:
    """Return only the MikroTik device on the local Ethernet hop (if identifiable)."""
    devices = discover_mndp_devices(
        interface,
        listen_seconds=listen_seconds,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
    )
    if not devices:
        return NeighborState(protocol="MNDP", available=False, message="no mndp neighbor")

    connected = next((device for device in devices if device.connected), None)
    if connected is not None:
        return connected.to_neighbor_state(message="ok (dispositivo collegato)")

    if len(devices) == 1:
        devices[0].connected = True
        return devices[0].to_neighbor_state(message="ok (unico dispositivo MNDP)")

    return NeighborState(
        protocol="MNDP",
        available=False,
        message=f"{len(devices)} dispositivi MNDP in LAN; usare tab MikroTik (nessun match gateway)",
    )


def discover_mndp_snapshot(
    interface: str,
    *,
    listen_seconds: float = _SCAN_LISTEN_SECONDS,
    gateway_ip: str | None = None,
    gateway_mac: str | None = None,
) -> dict[str, Any]:
    devices = discover_mndp_devices(
        interface,
        listen_seconds=listen_seconds,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
    )
    connected = next((device for device in devices if device.connected), None)
    return {
        "interface": interface,
        "listen_seconds": listen_seconds,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices),
        "connected_device": connected.to_dict() if connected else None,
        "devices": [device.to_dict() for device in devices],
        "note": (
            "La card Switch usa solo il dispositivo collegato (match MAC/IP gateway). "
            "Questo elenco mostra tutti i MikroTik visibili via broadcast MNDP sulla LAN."
        ),
    }
