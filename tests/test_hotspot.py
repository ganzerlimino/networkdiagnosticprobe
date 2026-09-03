from pathlib import Path

import pytest

from ndp.core.config import NdpConfig
from ndp.network.hotspot import (
    build_ssid,
    get_status,
    hotspot_display_lines,
    hotspot_footer,
    list_hotspot_stations,
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


def test_hotspot_display_lines(wlan_mac: Path) -> None:
    config = NdpConfig(wifi_hotspot_ip="192.168.50.1/24", web_port=8080)
    assert hotspot_display_lines(config) == ["NDP-3456", "192.168.50.1:8080", "Tel: AP off"]


def test_hotspot_footer_warns_without_client(wlan_mac: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = NdpConfig(wifi_hotspot_ip="192.168.50.1/24", web_port=8080)
    monkeypatch.setattr("ndp.network.hotspot._pid_running", lambda _path: True)
    monkeypatch.setattr("ndp.network.hotspot.count_hotspot_clients", lambda _config: 0)
    footer = hotspot_footer(config)
    assert footer.lines[-1] == "Tel: assente"
    assert footer.warn_no_client is True


def test_hotspot_footer_ok_with_client(wlan_mac: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = NdpConfig(wifi_hotspot_ip="192.168.50.1/24", web_port=8080)
    monkeypatch.setattr("ndp.network.hotspot._pid_running", lambda _path: True)
    monkeypatch.setattr("ndp.network.hotspot.count_hotspot_clients", lambda _config: 1)
    footer = hotspot_footer(config)
    assert footer.lines[-1] == "Tel: connesso"
    assert footer.warn_no_client is False


def test_list_hotspot_stations_parses_hostapd_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = tmp_path / "hostapd"
    ctrl.mkdir()
    monkeypatch.setattr("ndp.network.hotspot.interface_exists", lambda _iface: True)
    monkeypatch.setattr("ndp.network.hotspot.hostapd_ctrl_dir", lambda: ctrl)
    monkeypatch.setattr("ndp.network.hotspot.shutil.which", lambda name: name == "hostapd_cli")

    def fake_run(command: list[str], *, check: bool = False):
        assert command[0] == "hostapd_cli"
        assert command[1] == "-p"
        assert command[2] == str(ctrl)
        assert command[-1] == "list_sta"
        return type("Result", (), {"returncode": 0, "stdout": "aa:bb:cc:dd:ee:01\naa:bb:cc:dd:ee:02\n"})()

    monkeypatch.setattr("ndp.network.hotspot._run", fake_run)
    assert list_hotspot_stations("wlan0") == ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"]


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
