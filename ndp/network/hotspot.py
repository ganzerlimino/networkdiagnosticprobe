"""Wi-Fi hotspot for phone access (wlan0 AP + dnsmasq + hostapd)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from ndp.core.config import NdpConfig

logger = logging.getLogger(__name__)

HOTSPOT_DIR = Path("/etc/ndp/hotspot")
RUN_DIR = Path("/run/ndp")
HOTSPOT_WATCH_INTERVAL_SECONDS = 30.0
_CLIENT_CACHE_TTL_SECONDS = 2.0


def hostapd_ctrl_dir() -> Path:
    return RUN_DIR / "hostapd"

_SSID_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_MAC_ADDRESS = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


@dataclass
class HotspotStatus:
    enabled: bool
    active: bool
    interface: str
    ssid: str | None = None
    ip: str | None = None
    web_url: str | None = None
    password: str | None = None
    open_network: bool = False
    channel: int | None = None
    interface_mode: str | None = None
    operstate: str | None = None
    clients_connected: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if data.get("password"):
            data["password_hint"] = "configurata (WPA2)"
            data["password"] = None
        return data


def hostapd_conf_path() -> Path:
    return HOTSPOT_DIR / "hostapd.conf"


def dnsmasq_conf_path() -> Path:
    return HOTSPOT_DIR / "dnsmasq.conf"


def hostapd_pid_path() -> Path:
    return RUN_DIR / "hostapd.pid"


def dnsmasq_pid_path() -> Path:
    return RUN_DIR / "dnsmasq.pid"


def hotspot_state_path() -> Path:
    return RUN_DIR / "hotspot.json"


def _run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=check,
    )


def interface_exists(interface: str) -> bool:
    return Path(f"/sys/class/net/{interface}").exists()


def read_interface_mac(interface: str) -> str:
    path = Path(f"/sys/class/net/{interface}/address")
    if not path.is_file():
        raise FileNotFoundError(f"interfaccia {interface} non trovata")
    return path.read_text(encoding="utf-8").strip().upper()


def read_interface_operstate(interface: str) -> str | None:
    path = Path(f"/sys/class/net/{interface}/operstate")
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()


def read_interface_mode(interface: str) -> str | None:
    if not shutil.which("iw"):
        return None
    result = _run(["iw", "dev", interface, "info"], check=False)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("type "):
            return stripped.split(None, 1)[1].strip()
    return None


def interface_has_ip(interface: str, address: str) -> bool:
    result = _run(["ip", "-j", "addr", "show", "dev", interface], check=False)
    if result.returncode != 0:
        return False
    return address in result.stdout


def list_hotspot_stations(interface: str) -> list[str]:
    """Return MAC addresses of Wi-Fi stations associated to the AP."""
    if not interface_exists(interface):
        return []

    if shutil.which("hostapd_cli") and hostapd_ctrl_dir().is_dir():
        result = _run(
            ["hostapd_cli", "-p", str(hostapd_ctrl_dir()), "-i", interface, "list_sta"],
            check=False,
        )
        if result.returncode == 0 and "FAIL" not in result.stdout:
            stations = [
                line.strip().lower()
                for line in result.stdout.splitlines()
                if _MAC_ADDRESS.match(line.strip())
            ]
            if stations:
                return stations

    if shutil.which("iw"):
        result = _run(["iw", "dev", interface, "station", "dump"], check=False)
        if result.returncode == 0:
            stations: list[str] = []
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith("Station "):
                    mac = stripped.split()[1].lower()
                    if _MAC_ADDRESS.match(mac):
                        stations.append(mac)
            return stations

    return []


_client_cache: dict[str, tuple[float, list[str]]] = {}


def _cached_hotspot_stations(interface: str) -> list[str]:
    now = time.monotonic()
    cached = _client_cache.get(interface)
    if cached and (now - cached[0]) < _CLIENT_CACHE_TTL_SECONDS:
        return cached[1]
    stations = list_hotspot_stations(interface)
    _client_cache[interface] = (now, stations)
    return stations


def clear_hotspot_client_cache_for_tests() -> None:
    _client_cache.clear()


def count_hotspot_clients(config: NdpConfig) -> int:
    if not config.wifi_hotspot_enabled or not _pid_running(hostapd_pid_path()):
        return 0
    return len(_cached_hotspot_stations(config.wifi_hotspot_interface))


@dataclass(frozen=True)
class HotspotFooter:
    lines: tuple[str, ...]
    warn_no_client: bool = False


def _hotspot_client_line(config: NdpConfig, *, active: bool, client_count: int) -> str:
    from ndp.locale.loader import load_locale, translate

    locale = load_locale(config.ui_locale)
    if not active:
        return translate(locale, "tft.hotspot_ap_off") or "AP: off"
    if client_count <= 0:
        return translate(locale, "tft.hotspot_client_none") or "Tel: --"
    if client_count == 1:
        return translate(locale, "tft.hotspot_client_ok") or "Tel: OK"
    return translate(locale, "tft.hotspot_client_multi", count=client_count) or f"Tel: {client_count}"


def hotspot_footer(config: NdpConfig) -> HotspotFooter:
    """Footer lines for the TFT (SSID, web URL, phone/client status)."""
    if not config.wifi_hotspot_enabled or not config.web_enabled:
        return HotspotFooter(lines=())

    host, _ = _parse_cidr(config.wifi_hotspot_ip)
    try:
        ssid = build_ssid(config.wifi_hotspot_ssid_prefix, config.wifi_hotspot_interface)
    except FileNotFoundError:
        ssid = config.wifi_hotspot_ssid_prefix or "NDP"
    active = _pid_running(hostapd_pid_path())
    client_count = count_hotspot_clients(config) if active else 0
    client_line = _hotspot_client_line(config, active=active, client_count=client_count)
    return HotspotFooter(
        lines=(ssid[:18], f"{host}:{config.web_port}", client_line[:22]),
        warn_no_client=active and client_count == 0,
    )


def hotspot_display_lines(config: NdpConfig) -> list[str]:
    """Short connection hints for the framebuffer UI."""
    return list(hotspot_footer(config).lines)


def build_ssid(prefix: str, interface: str) -> str:
    safe_prefix = _SSID_SAFE.sub("", prefix.strip()) or "NDP"
    mac = read_interface_mac(interface).replace(":", "")
    suffix = mac[-4:]
    return f"{safe_prefix}-{suffix}"[:32]


def _prefix_to_netmask(prefix: int) -> str:
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def _parse_cidr(ip: str) -> tuple[str, int]:
    if "/" in ip:
        address, bits = ip.split("/", 1)
        return address, int(bits)
    return ip, 24


def render_hostapd_conf(config: NdpConfig, ssid: str) -> str:
    password = config.wifi_hotspot_password.strip()
    lines = [
        f"interface={config.wifi_hotspot_interface}",
        "driver=nl80211",
        f"ssid={ssid}",
        "hw_mode=g",
        f"channel={config.wifi_hotspot_channel}",
        f"country_code={config.wifi_hotspot_country}",
        "ieee80211n=1",
        "wmm_enabled=1",
        "macaddr_acl=0",
        "auth_algs=1",
        "ignore_broadcast_ssid=0",
        f"ctrl_interface={hostapd_ctrl_dir()}",
        "ctrl_interface_group=0",
    ]
    if password:
        if len(password) < 8:
            raise ValueError("wifi_hotspot.password deve avere almeno 8 caratteri per WPA2")
        lines.extend(
            [
                "wpa=2",
                f"wpa_passphrase={password}",
                "wpa_key_mgmt=WPA-PSK",
                "rsn_pairwise=CCMP",
            ]
        )
    else:
        lines.append("wpa=0")
    return "\n".join(lines) + "\n"


def render_dnsmasq_conf(config: NdpConfig) -> str:
    address, prefix = _parse_cidr(config.wifi_hotspot_ip)
    netmask = _prefix_to_netmask(prefix)
    return (
        f"interface={config.wifi_hotspot_interface}\n"
        "bind-interfaces\n"
        f"dhcp-range={config.wifi_hotspot_dhcp_start},"
        f"{config.wifi_hotspot_dhcp_end},{netmask},24h\n"
        f"dhcp-option=3,{address}\n"
        f"dhcp-option=6,{address}\n"
        "domain=ndp.local\n"
        "log-queries\n"
        "log-dhcp\n"
    )


def write_hotspot_configs(config: NdpConfig) -> str:
    HOTSPOT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    hostapd_ctrl_dir().mkdir(parents=True, exist_ok=True)
    ssid = build_ssid(config.wifi_hotspot_ssid_prefix, config.wifi_hotspot_interface)
    hostapd_conf_path().write_text(render_hostapd_conf(config, ssid), encoding="utf-8")
    dnsmasq_conf_path().write_text(render_dnsmasq_conf(config), encoding="utf-8")
    return ssid


def _pid_running(pid_file: Path) -> bool:
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    try:
        import os

        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_pid(pid_file: Path, name: str) -> None:
    if not _pid_running(pid_file):
        pid_file.unlink(missing_ok=True)
        return
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    try:
        import os

        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    pid_file.unlink(missing_ok=True)
    logger.info("Stopped %s (pid %s)", name, pid)


def _unblock_wifi() -> None:
    if shutil.which("rfkill"):
        _run(["rfkill", "unblock", "all"], check=False)
        _run(["rfkill", "unblock", "wifi"], check=False)
        _run(["rfkill", "unblock", "wlan"], check=False)


def _quiesce_wifi_clients(iface: str) -> None:
    for service in (
        f"wpa_supplicant@{iface}.service",
        "wpa_supplicant.service",
        f"dhcpcd@{iface}.service",
    ):
        _run(["systemctl", "stop", service], check=False)
    _run(["pkill", "-f", f"wpa_supplicant.*{iface}"], check=False)
    if shutil.which("nmcli"):
        _run(["nmcli", "device", "set", iface, "managed", "no"], check=False)
        _run(["nmcli", "radio", "wifi", "on"], check=False)


def _prepare_interface(config: NdpConfig) -> None:
    iface = config.wifi_hotspot_interface
    address, prefix = _parse_cidr(config.wifi_hotspot_ip)
    _unblock_wifi()
    _quiesce_wifi_clients(iface)
    if shutil.which("iw"):
        _run(["iw", "reg", "set", config.wifi_hotspot_country], check=False)
    _run(["ip", "link", "set", iface, "down"], check=False)
    _run(["ip", "addr", "flush", "dev", iface], check=False)
    if shutil.which("iw"):
        _run(["iw", "dev", iface, "set", "type", "__ap"], check=False)
    _run(["ip", "addr", "add", f"{address}/{prefix}", "dev", iface], check=False)
    _run(["ip", "link", "set", iface, "up"], check=False)
    time.sleep(0.3)


def hotspot_health(config: NdpConfig) -> tuple[bool, str]:
    if not config.wifi_hotspot_enabled:
        return True, "disabled"
    if not interface_exists(config.wifi_hotspot_interface):
        return False, f"interfaccia {config.wifi_hotspot_interface} assente"

    iface = config.wifi_hotspot_interface
    if not _pid_running(hostapd_pid_path()):
        return False, "hostapd non attivo"
    if not _pid_running(dnsmasq_pid_path()):
        return False, "dnsmasq non attivo"

    operstate = read_interface_operstate(iface)
    if operstate in {"down", "lowerlayerdown"}:
        return False, f"interfaccia {operstate}"

    mode = read_interface_mode(iface)
    if mode and mode.upper() not in {"AP", "P2P-GO"}:
        return False, f"modalità {mode} invece di AP"

    address, _ = _parse_cidr(config.wifi_hotspot_ip)
    if not interface_has_ip(iface, address):
        return False, f"IP {address} non configurato su {iface}"

    return True, "ok"


def get_status(config: NdpConfig) -> HotspotStatus:
    address, _ = _parse_cidr(config.wifi_hotspot_ip)
    web_url = f"http://{address}:{config.web_port}/"
    iface = config.wifi_hotspot_interface
    operstate = read_interface_operstate(iface) if interface_exists(iface) else None
    mode = read_interface_mode(iface) if interface_exists(iface) else None

    if not config.wifi_hotspot_enabled:
        return HotspotStatus(
            enabled=False,
            active=False,
            interface=iface,
            ip=address,
            web_url=web_url,
            operstate=operstate,
            interface_mode=mode,
            message="Hotspot disabilitato in config",
        )
    if not interface_exists(iface):
        return HotspotStatus(
            enabled=True,
            active=False,
            interface=iface,
            ip=address,
            web_url=web_url,
            operstate=operstate,
            interface_mode=mode,
            message=f"Interfaccia {iface} assente",
        )
    try:
        ssid = build_ssid(config.wifi_hotspot_ssid_prefix, iface)
    except FileNotFoundError as exc:
        return HotspotStatus(
            enabled=True,
            active=False,
            interface=iface,
            ip=address,
            web_url=web_url,
            operstate=operstate,
            interface_mode=mode,
            message=str(exc),
        )

    healthy, health_message = hotspot_health(config)
    client_count = count_hotspot_clients(config) if healthy else 0
    state_file = hotspot_state_path()
    if state_file.is_file():
        try:
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            ssid = str(saved.get("ssid", ssid))
        except json.JSONDecodeError:
            pass

    password = config.wifi_hotspot_password.strip()
    return HotspotStatus(
        enabled=True,
        active=healthy,
        interface=iface,
        ssid=ssid,
        ip=address,
        web_url=web_url,
        password=password or None,
        open_network=not bool(password),
        channel=config.wifi_hotspot_channel,
        operstate=operstate,
        interface_mode=mode,
        clients_connected=client_count,
        message="Attivo" if healthy else health_message,
    )


def stop_hotspot(config: NdpConfig | None = None) -> None:
    _stop_pid(hostapd_pid_path(), "hostapd")
    _stop_pid(dnsmasq_pid_path(), "dnsmasq")
    hotspot_state_path().unlink(missing_ok=True)
    if config is not None and interface_exists(config.wifi_hotspot_interface):
        _run(["ip", "addr", "flush", "dev", config.wifi_hotspot_interface], check=False)
        _run(["ip", "link", "set", config.wifi_hotspot_interface, "down"], check=False)


def start_hotspot(config: NdpConfig) -> HotspotStatus:
    status = get_status(config)
    if not config.wifi_hotspot_enabled:
        return status
    if not interface_exists(config.wifi_hotspot_interface):
        status.message = f"Interfaccia {config.wifi_hotspot_interface} assente"
        return status
    if not shutil.which("hostapd") or not shutil.which("dnsmasq"):
        status.message = "Installa hostapd e dnsmasq (sudo ./scripts/install.sh)"
        return status

    stop_hotspot(config)
    try:
        ssid = write_hotspot_configs(config)
    except ValueError as exc:
        status.message = str(exc)
        return status

    _prepare_interface(config)

    dnsmasq = subprocess.Popen(
        [
            "dnsmasq",
            "-C",
            str(dnsmasq_conf_path()),
            "-x",
            str(dnsmasq_pid_path()),
        ],
    )
    if dnsmasq.poll() is not None:
        status.message = "dnsmasq non avviato"
        return status

    hostapd = _run(
        ["hostapd", "-B", str(hostapd_conf_path()), "-P", str(hostapd_pid_path())],
        check=False,
    )
    if hostapd.returncode != 0 or not _pid_running(hostapd_pid_path()):
        stop_hotspot(config)
        detail = (hostapd.stderr or hostapd.stdout or "").strip()[:200]
        status.message = f"hostapd non avviato: {detail or 'errore sconosciuto'}"
        return status

    time.sleep(0.5)
    healthy, health_message = hotspot_health(config)
    if not healthy:
        stop_hotspot(config)
        status.message = f"hotspot avviato ma non operativo: {health_message}"
        return status

    address, _ = _parse_cidr(config.wifi_hotspot_ip)
    hotspot_state_path().write_text(
        json.dumps(
            {
                "ssid": ssid,
                "ip": address,
                "interface": config.wifi_hotspot_interface,
            }
        ),
        encoding="utf-8",
    )
    logger.info("Hotspot attivo: SSID=%s IP=%s", ssid, address)
    return get_status(config)


def maintain_hotspot(config: NdpConfig) -> HotspotStatus:
    """Restart hotspot when enabled but not healthy."""
    if not config.wifi_hotspot_enabled:
        return get_status(config)
    healthy, reason = hotspot_health(config)
    if healthy:
        return get_status(config)
    logger.warning("Hotspot non operativo (%s), riavvio...", reason)
    return start_hotspot(config)


def ensure_hotspot(config: NdpConfig) -> HotspotStatus:
    """Start or repair hotspot when enabled."""
    return maintain_hotspot(config)


def start_hotspot_watchdog(
    config: NdpConfig,
    stop_event: threading.Event,
    *,
    interval_seconds: float = HOTSPOT_WATCH_INTERVAL_SECONDS,
) -> threading.Thread:
    def _loop() -> None:
        while not stop_event.wait(interval_seconds):
            if not config.wifi_hotspot_enabled:
                continue
            try:
                maintain_hotspot(config)
            except Exception as exc:
                logger.error("Hotspot watchdog error: %s", exc)

    thread = threading.Thread(target=_loop, daemon=True, name="ndp-hotspot-watch")
    thread.start()
    return thread
