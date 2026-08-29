"""Discovery protocol support matrix for API/UI."""

from __future__ import annotations

from typing import Any


def protocol_catalog() -> dict[str, Any]:
    return {
        "protocols": [
            {
                "id": "lldp",
                "name": "LLDP",
                "status": "active",
                "mode": "passive",
                "notes": "Via lldpd/lldpctl; include TLV base e LLDP-MED/PoE quando presenti.",
            },
            {
                "id": "cdp",
                "name": "CDP",
                "status": "active",
                "mode": "passive",
                "notes": "Ricevuto da lldpd quando lo switch Cisco trasmette CDP.",
            },
            {
                "id": "mndp",
                "name": "MNDP",
                "status": "active",
                "mode": "passive",
                "notes": "Card Switch = solo dispositivo collegato (match gateway). Tab MikroTik = tutta la LAN.",
            },
            {
                "id": "mdns",
                "name": "mDNS",
                "status": "active",
                "mode": "active",
                "notes": "Query _services._dns-sd._udp.local sulla LAN.",
            },
            {
                "id": "ssdp",
                "name": "SSDP",
                "status": "active",
                "mode": "active",
                "notes": "M-SEARCH UPnP su 239.255.255.250:1900.",
            },
            {
                "id": "fdp",
                "name": "FDP",
                "status": "probe",
                "mode": "passive",
                "notes": "Rilevamento frame ethertype 0x2000 (Foundry/Brocade); senza parser TLV.",
            },
            {
                "id": "edp",
                "name": "EDP",
                "status": "probe",
                "mode": "passive",
                "notes": "Rilevamento frame ethertype 0xEEEE (Extreme); senza parser TLV.",
            },
            {
                "id": "lltd",
                "name": "LLTD",
                "status": "probe",
                "mode": "passive",
                "notes": "Rilevamento frame ethertype 0x88D9 (Windows LLTD); senza mapper topologia.",
            },
            {
                "id": "bfd",
                "name": "BFD",
                "status": "unsupported",
                "mode": "n/a",
                "notes": "BFD è un protocollo di sessione router-router, non neighbor discovery L2.",
            },
            {
                "id": "stp",
                "name": "STP/RSTP/MSTP",
                "status": "active",
                "mode": "passive",
                "notes": "Sniff BPDU bridge-group su eth0 (tab Passive check).",
            },
            {
                "id": "lacp",
                "name": "LACP",
                "status": "active",
                "mode": "passive",
                "notes": "Sniff slow-protocols multicast 01:80:c2:00:00:02.",
            },
            {
                "id": "vlan",
                "name": "VLAN/ISL/VTP",
                "status": "active",
                "mode": "passive",
                "notes": "802.1Q/Q-in-Q, ISL e VTP Cisco via sniff passivo.",
            },
            {
                "id": "igmp",
                "name": "IGMP",
                "status": "active",
                "mode": "passive",
                "notes": "Membership query/report IPv4 multicast.",
            },
            {
                "id": "snmp",
                "name": "SNMP",
                "status": "active",
                "mode": "active",
                "notes": "GET sysDescr UDP/161; verifica UDP/162.",
            },
            {
                "id": "dhcp82",
                "name": "DHCP Option 82",
                "status": "active",
                "mode": "passive",
                "notes": "Sniff Relay Agent Information nei pacchetti DHCP.",
            },
        ]
    }
