from ndp.discovery.dahua_discover import build_dahua_probe, parse_dahua_response
from ndp.discovery.hikvision_sadp import parse_sadp_probe_match
from ndp.discovery.nas import (
    _parse_asustor,
    _parse_qnap,
    _parse_readynas,
    _parse_synology,
    _parse_wsd_probe_match,
)


def test_build_dahua_probe_header() -> None:
    probe = build_dahua_probe()
    assert probe[0] == 0xA3
    assert b"DHDiscover.search" in probe


def test_parse_dahua_response_device_info() -> None:
    body = (
        '{"method":"client.notifyDevInfo","params":{"deviceInfo":{'
        '"DeviceType":"IPC-HDW5421S","SerialNo":"1F006E4PAX00075",'
        '"HttpPort":80,"Vendor":"Dahua",'
        '"IPv4Address":{"IPAddress":"192.168.1.64"}}}}'
    )
    packet = bytearray(32 + len(body))
    packet[0] = 0xB3
    packet[4:8] = len(body).to_bytes(4, "little")
    packet[32:] = body.encode("utf-8")
    device = parse_dahua_response(bytes(packet), "192.168.1.1")
    assert device is not None
    assert device.host == "192.168.1.64"
    assert device.model == "IPC-HDW5421S"
    assert device.serial == "1F006E4PAX00075"
    assert device.http_port == 80


def test_parse_sadp_probe_match() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<ProbeMatch>
<Uuid>FC25924E-AFE2-49E6-ACC9-F84A6859054D</Uuid>
<DeviceType>IP Camera</DeviceType>
<DeviceDescription>DS-2CD2432F-IW</DeviceDescription>
<DeviceSN>DS-2CD2432F-IW20150126CCCH502126167</DeviceSN>
<MAC>c0-56-e3-fe-42-92</MAC>
<IPv4Address>10.1.1.251</IPv4Address>
<HttpPort>80</HttpPort>
<CommandPort>8000</CommandPort>
<SoftwareVersion>V5.5.0</SoftwareVersion>
</ProbeMatch>"""
    device = parse_sadp_probe_match(xml, "10.1.1.1")
    assert device is not None
    assert device.host == "10.1.1.251"
    assert device.mac == "C0:56:E3:FE:42:92"
    assert device.model == "DS-2CD2432F-IW"
    assert device.serial.endswith("502126167")
    assert device.http_port == 80
    assert device.command_port == 8000


def test_parse_synology_payload() -> None:
    payload = (
        b'{"hostname":"diskstation","ip":"192.168.1.10","model":"DS220+",'
        b'"version":"7.2","serial":"ABC123"}'
    )
    device = _parse_synology(payload, "192.168.1.10")
    assert device is not None
    assert device.name == "diskstation"
    assert device.model == "DS220+"
    assert device.serial == "ABC123"


def test_parse_qnap_payload() -> None:
    payload = b'{"data":{"hostname":"qnap-nas","model":"TS-453D","name":"qnap-nas"}}'
    device = _parse_qnap(payload, "192.168.1.20")
    assert device is not None
    assert device.name == "qnap-nas"
    assert device.model == "TS-453D"


def test_parse_asustor_json() -> None:
    payload = b'{"hostname":"ASUSTOR-NAS","model":"AS6604T","ip":"192.168.1.30","version":"4.2.1"}'
    device = _parse_asustor(payload, "192.168.1.30")
    assert device is not None
    assert device.name == "ASUSTOR-NAS"
    assert device.model == "AS6604T"
    assert device.version == "4.2.1"


def test_parse_readynas_payload() -> None:
    payload = (
        b"\treadynas-01\t192.168.1.40\t"
        b"model!!0!!sn=SER123::fw=6.10.9::descr=ReadyNAS Ultra 4::"
    )
    device = _parse_readynas(payload, "192.168.1.40")
    assert device is not None
    assert device.name == "readynas-01"
    assert device.host == "192.168.1.40"
    assert device.serial == "SER123"
    assert device.version == "6.10.9"


def test_parse_wsd_probe_match_nas_scope() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope">
<SOAP-ENV:Body>
<d:ProbeMatches xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
<d:ProbeMatch>
<d:Scopes>onvif://www.onvif.org/name/TNAS-F2-212 onvif://www.onvif.org/hardware/TerraMaster</d:Scopes>
</d:ProbeMatch>
</d:ProbeMatches>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    device = _parse_wsd_probe_match(xml, "192.168.1.50")
    assert device is not None
    assert device.name == "TNAS-F2-212"
    assert device.host == "192.168.1.50"
