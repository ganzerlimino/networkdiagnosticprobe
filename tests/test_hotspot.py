from pathlib import Path

import pytest

from ndp.core.config import NdpConfig
from ndp.network.hotspot import (
    build_ssid,
    get_status,
    render_dnsmasq_conf,
    render_hostapd_conf,
    write_hotspot_configs,
)


@pytest.fixture
def wlan_mac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sys_path = tmp_path / "sys" / "class" / "net" / "wlan0"
    sys_path.mkdir(parents=True)
    mac_file = sys_path / "address"
    mac_file.write_text("b8:27:eb:12:34:56\n", encoding="utf-8")

    original = Path

    def fake_path(value: str) -> Path:
        if value == "/sys/class/net/wlan0/address":
            return mac_file
        if value == "/sys/class/net/wlan0":
            return sys_path
        return original(value)

    monkeypatch.setattr("ndp.network.hotspot.Path", fake_path)
    monkeypatch.setattr("ndp.network.hotspot.interface_exists", lambda iface: iface == "wlan0")
    return mac_file


def test_build_ssid_from_mac(wlan_mac: Path) -> None:
    assert build_ssid("NDP", "wlan0") == "NDP-3456"


def test_render_hostapd_wpa2() -> None:
    config = NdpConfig(wifi_hotspot_password="ndp-probe", wifi_hotspot_country="IT")
    text = render_hostapd_conf(config, "NDP-TEST")
    assert "ssid=NDP-TEST" in text
    assert "wpa=2" in text
    assert "country_code=IT" in text


def test_render_hostapd_open_network() -> None:
    config = NdpConfig(wifi_hotspot_password="")
    text = render_hostapd_conf(config, "NDP-OPEN")
    assert "wpa=0" in text


def test_render_dnsmasq_conf() -> None:
    config = NdpConfig()
    text = render_dnsmasq_conf(config)
    assert "interface=wlan0" in text
    assert "dhcp-range=192.168.50.10,192.168.50.50" in text
    assert "dhcp-option=3,192.168.50.1" in text


def test_write_hotspot_configs(wlan_mac: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr("ndp.network.hotspot.HOTSPOT_DIR", tmp_path)
    monkeypatch.setattr("ndp.network.hotspot.RUN_DIR", run_dir)
    config = NdpConfig()
    ssid = write_hotspot_configs(config)
    assert ssid == "NDP-3456"
    assert (tmp_path / "hostapd.conf").is_file()
    assert (tmp_path / "dnsmasq.conf").is_file()

def test_get_status_disabled() -> None:
    config = NdpConfig(wifi_hotspot_enabled=False)
    status = get_status(config)
    assert status.enabled is False
    assert status.web_url == "http://192.168.50.1:8080/"
