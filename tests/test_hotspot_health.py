from pathlib import Path

import pytest

from ndp.core.config import NdpConfig
from ndp.network.hotspot import hotspot_health, maintain_hotspot


def test_hotspot_health_requires_hostapd(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NdpConfig(wifi_hotspot_enabled=True, wifi_hotspot_interface="wlan0")
    monkeypatch.setattr("ndp.network.hotspot.interface_exists", lambda _iface: True)
    monkeypatch.setattr("ndp.network.hotspot._pid_running", lambda _path: False)
    healthy, message = hotspot_health(config)
    assert healthy is False
    assert "hostapd" in message


def test_hotspot_health_ok_when_ap_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NdpConfig(wifi_hotspot_enabled=True, wifi_hotspot_interface="wlan0")
    monkeypatch.setattr("ndp.network.hotspot.interface_exists", lambda _iface: True)
    monkeypatch.setattr("ndp.network.hotspot._pid_running", lambda _path: True)
    monkeypatch.setattr("ndp.network.hotspot.read_interface_operstate", lambda _iface: "up")
    monkeypatch.setattr("ndp.network.hotspot.read_interface_mode", lambda _iface: "AP")
    monkeypatch.setattr("ndp.network.hotspot.interface_has_ip", lambda _iface, _ip: True)
    healthy, message = hotspot_health(config)
    assert healthy is True
    assert message == "ok"


def test_maintain_hotspot_restarts_when_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    config = NdpConfig(wifi_hotspot_enabled=True)
    calls = {"start": 0}

    monkeypatch.setattr("ndp.network.hotspot.hotspot_health", lambda _config: (False, "hostapd non attivo"))

    def fake_start(_config: NdpConfig):
        calls["start"] += 1
        from ndp.network.hotspot import HotspotStatus

        return HotspotStatus(
            enabled=True,
            active=True,
            interface="wlan0",
            ssid="NDP-TEST",
            message="Attivo",
        )

    monkeypatch.setattr("ndp.network.hotspot.start_hotspot", fake_start)
    status = maintain_hotspot(config)
    assert calls["start"] == 1
    assert status.active is True
