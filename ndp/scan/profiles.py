"""TCP port profiles for NDP scans."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortDefinition:
    port: int
    service: str
    protocol: str = "tcp"


# IT / infrastruttura generica
STANDARD_PORTS: tuple[PortDefinition, ...] = (
    PortDefinition(21, "FTP"),
    PortDefinition(22, "SSH"),
    PortDefinition(23, "Telnet"),
    PortDefinition(25, "SMTP"),
    PortDefinition(53, "DNS"),
    PortDefinition(80, "HTTP"),
    PortDefinition(110, "POP3"),
    PortDefinition(143, "IMAP"),
    PortDefinition(135, "MS-RPC"),
    PortDefinition(139, "NetBIOS"),
    PortDefinition(443, "HTTPS"),
    PortDefinition(445, "SMB"),
    PortDefinition(161, "SNMP"),
    PortDefinition(389, "LDAP"),
    PortDefinition(636, "LDAPS"),
    PortDefinition(3389, "RDP"),
    PortDefinition(5900, "VNC"),
    PortDefinition(8080, "HTTP-ALT"),
    PortDefinition(8443, "HTTPS-ALT"),
)

# OT / ICS — protocolli industriali comuni
INDUSTRIAL_PORTS: tuple[PortDefinition, ...] = (
    PortDefinition(102, "S7comm/ISO-TSAP"),
    PortDefinition(502, "Modbus TCP"),
    PortDefinition(1883, "MQTT"),
    PortDefinition(8883, "MQTT-TLS"),
    PortDefinition(2222, "EtherNet/IP-IO"),
    PortDefinition(2404, "IEC 60870-5-104"),
    PortDefinition(2455, "CODESYS-scan"),
    PortDefinition(4840, "OPC UA"),
    PortDefinition(5006, "MELSEC-Q"),
    PortDefinition(5007, "MELSEC-Q-UDP"),
    PortDefinition(5094, "HART-IP"),
    PortDefinition(9600, "Omron FINS"),
    PortDefinition(11740, "CODESYS"),
    PortDefinition(20000, "DNP3"),
    PortDefinition(34962, "PROFINET-DCP"),
    PortDefinition(34963, "PROFINET"),
    PortDefinition(34964, "PROFINET-IO"),
    PortDefinition(44818, "EtherNet/IP"),
    PortDefinition(47808, "BACnet/IP"),
)

PROFILE_NAMES = {
    "standard": "Porte standard",
    "industrial": "Porte industriali",
    "custom": "Porte custom",
}

GATEWAY_QUICK_PORTS: tuple[PortDefinition, ...] = (
    PortDefinition(53, "DNS"),
    PortDefinition(80, "HTTP"),
    PortDefinition(443, "HTTPS"),
    PortDefinition(445, "SMB"),
)


def profile_ports(profile: str, custom_ports: list[int] | None = None) -> list[PortDefinition]:
    if profile == "standard":
        return list(STANDARD_PORTS)
    if profile == "industrial":
        return list(INDUSTRIAL_PORTS)
    if profile == "custom":
        if not custom_ports:
            return []
        return [
            PortDefinition(port=port, service=f"TCP/{port}")
            for port in sorted(set(custom_ports))
        ]
    raise ValueError(f"profilo sconosciuto: {profile}")


def profiles_catalog() -> dict[str, object]:
    def _serialize(items: tuple[PortDefinition, ...]) -> list[dict[str, object]]:
        return [
            {"port": item.port, "service": item.service, "protocol": item.protocol}
            for item in items
        ]

    return {
        "profiles": {
            key: {
                "label": label,
                "ports": _serialize(
                    STANDARD_PORTS if key == "standard" else INDUSTRIAL_PORTS
                ),
            }
            for key, label in PROFILE_NAMES.items()
            if key != "custom"
        },
        "custom": {
            "label": PROFILE_NAMES["custom"],
            "max_ports": 24,
            "hint": "Es. 80,443,502,4840",
        },
        "industrial_notes": [
            "Modbus TCP (502), MQTT (1883/8883), OPC UA (4840)",
            "S7comm (102), EtherNet/IP (44818), PROFINET (34962+)",
            "BACnet/IP (47808), DNP3 (20000), IEC-104 (2404)",
            "CODESYS, MELSEC, Omron FINS, HART-IP",
            "Weintek HMI Search UDP/59999-60000, eWON IPCONF UDP/1507",
        ],
    }
