"""Modbus TCP device identification (Read Device Identification, FC 0x2B / MEI 0x0E)."""

from __future__ import annotations

import socket
import struct
from dataclasses import asdict, dataclass
from typing import Any

_OBJECT_LABELS = {
    0x00: "vendor_name",
    0x01: "product_code",
    0x02: "revision",
    0x03: "vendor_url",
    0x04: "product_name",
    0x05: "model_name",
    0x06: "user_application_name",
}


@dataclass
class ModbusIdentifyResult:
    host: str
    port: int = 502
    reachable: bool = False
    unit_id: int | None = None
    conformity_level: int | None = None
    objects: dict[str, str] | None = None
    summary: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_read_device_id_request(unit_id: int = 0xFF) -> bytes:
    pdu = bytes([0x2B, 0x0E, 0x01, 0x00])
    mbap = struct.pack(">HHH", 0x0001, 0, len(pdu) + 1) + bytes([unit_id & 0xFF])
    return mbap + pdu


def parse_modbus_device_id_response(payload: bytes) -> dict[str, Any]:
    """Parse Modbus TCP Read Device Identification response (FC 0x2B / MEI 0x0E)."""
    if len(payload) < 13:
        raise ValueError("response too short")
    if payload[7] != 0x2B or payload[8] != 0x0E:
        raise ValueError("unexpected function or MEI type")
    if payload[9] != 0x01:
        raise ValueError("unexpected read device id code")

    conformity_level = payload[10]
    object_count = payload[13]
    objects: dict[str, str] = {}
    offset = 14
    for _ in range(object_count):
        if offset + 2 > len(payload):
            break
        object_id = payload[offset]
        length = payload[offset + 1]
        offset += 2
        if offset + length > len(payload):
            break
        raw = payload[offset : offset + length]
        offset += length
        key = _OBJECT_LABELS.get(object_id, f"object_{object_id:02x}")
        try:
            objects[key] = raw.decode("utf-8", errors="replace").strip()
        except UnicodeDecodeError:
            objects[key] = raw.hex()

    return {
        "conformity_level": conformity_level,
        "objects": objects,
    }


def identify_modbus_tcp(
    host: str,
    *,
    port: int = 502,
    timeout_seconds: float = 2.0,
    unit_ids: tuple[int, ...] = (0xFF, 0x01, 0x00),
) -> ModbusIdentifyResult:
    last_error: str | None = None
    for unit_id in unit_ids:
        request = _build_read_device_id_request(unit_id)
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
                sock.settimeout(timeout_seconds)
                sock.sendall(request)
                header = _recv_exact(sock, 7, timeout_seconds)
                if len(header) < 7:
                    last_error = "incomplete MBAP header"
                    continue
                length = struct.unpack(">H", header[4:6])[0]
                body = _recv_exact(sock, length, timeout_seconds)
                payload = header + body
        except OSError as exc:
            last_error = str(exc)
            continue

        try:
            parsed = parse_modbus_device_id_response(payload)
        except ValueError as exc:
            last_error = str(exc)
            continue

        objects = parsed["objects"]
        summary_parts = [
            objects.get("vendor_name"),
            objects.get("product_name") or objects.get("model_name"),
            objects.get("revision"),
        ]
        summary = " · ".join(part for part in summary_parts if part) or None
        return ModbusIdentifyResult(
            host=host,
            port=port,
            reachable=True,
            unit_id=unit_id,
            conformity_level=parsed["conformity_level"],
            objects=objects,
            summary=summary,
        )

    return ModbusIdentifyResult(
        host=host,
        port=port,
        reachable=False,
        error=last_error or "identify failed",
    )


def _recv_exact(sock: socket.socket, size: int, timeout_seconds: float) -> bytes:
    sock.settimeout(timeout_seconds)
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
