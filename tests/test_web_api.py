from pathlib import Path

from fastapi.testclient import TestClient

from ndp.core.config import NdpConfig
from ndp.core.state import ProbeState
from ndp.web.server import create_app


def _client() -> TestClient:
    app = create_app(NdpConfig(), Path("/tmp/ndp-config.yaml"), lambda: ProbeState(interface="eth0"))
    return TestClient(app)


def test_ping_live_start_returns_json() -> None:
    client = _client()
    response = client.post(
        "/api/ping/live/start",
        json={"hosts": ["127.0.0.1"], "interval": 1.0, "max_samples": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "session_id" in payload
    client.post(f"/api/ping/live/{payload['session_id']}/stop")


def test_mtu_discover_start_returns_json() -> None:
    client = _client()
    response = client.post(
        "/api/mtu/discover/start",
        json={"host": "127.0.0.1", "start_mtu": 1500, "min_mtu": 576},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "session_id" in payload
    client.post(f"/api/mtu/discover/{payload['session_id']}/stop")


def test_scan_ports_returns_json() -> None:
    client = _client()
    response = client.post(
        "/api/scan/ports",
        json={"host": "127.0.0.1", "profile": "standard", "timeout_ms": 500},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["host"] == "127.0.0.1"


def test_discover_protocols_catalog() -> None:
    client = _client()
    response = client.get("/api/discover/protocols")
    assert response.status_code == 200
    names = {item["id"] for item in response.json()["protocols"]}
    assert {"lldp", "mndp", "mdns", "ssdp", "bfd", "stp", "snmp", "dhcp82"}.issubset(names)


def test_discover_industrial_endpoint_returns_json() -> None:
    client = _client()
    response = client.get("/api/discover/industrial?timeout_seconds=1")
    assert response.status_code == 200
    payload = response.json()
    assert "weintek" in payload
    assert "ewon" in payload
    assert "device_count" in payload


def test_discover_oui_endpoint_returns_json() -> None:
    client = _client()
    response = client.get("/api/discover/oui?search=HMS&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert "entries" in payload
    assert "counts" in payload


def test_discover_oui_refresh_endpoint() -> None:
    client = _client()
    response = client.post("/api/discover/oui/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert "counts" in payload


def test_passive_check_endpoint_returns_json() -> None:
    client = _client()
    response = client.get("/api/discover/passive-check?listen_seconds=1")
    assert response.status_code == 200
    payload = response.json()
    assert "l2_passive" in payload
    assert "dhcp_option82" in payload
    assert "snmp" in payload
