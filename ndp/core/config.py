"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/ndp/config.yaml")
BUNDLED_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


@dataclass
class NdpConfig:
    interface: str = "eth0"
    poll_interval_link_up: float = 1.0
    poll_interval_link_down: float = 5.0
    lldp_cache_ttl_seconds: int = 30
    ui_enabled: bool = False
    ui_framebuffer: str = "/dev/fb1"
    ui_width: int = 320
    ui_height: int = 240
    ui_sdl_driver: str = "fbcon"
    ui_backend: str = "auto"
    ui_backlight_gpio: int = 18
    ui_backlight_enabled: bool = True
    ui_rgb565_bgr: bool = False
    ui_rgb565_swap_bytes: bool = False
    ui_font_size: int = 14
    ui_fps: int = 20
    ui_input: str = "none"
    ui_auto_cycle_seconds: float = 8.0
    ui_button_previous: int = 23
    ui_button_select: int = 24
    ui_button_next: int = 25
    ui_encoder_clk: int = 5
    ui_encoder_dt: int = 6
    ui_encoder_sw: int = 19
    ui_encoder_steps_per_detent: int = 4
    ui_encoder_sw_debounce_seconds: float = 0.03
    ui_button_debounce_seconds: float = 0.03
    ui_button_trigger_mode: str = "edge"
    ui_button_press_confirm_ms: int = 0
    ui_hint_edge: str = "none"
    ui_content_margin_side: int = 0
    ui_content_text_gap: int = 0
    ui_hint_y_offset: int = 24
    ui_splash_enabled: bool = True
    ui_splash_message: str = "Network Diagnostic Probe"
    ui_splash_min_seconds: float = 1.5
    ui_warmup_on_start: bool = True
    ui_button_poll_hz: int = 200
    ui_line_spacing: int = 6
    console_enabled: bool = True
    console_refresh_seconds: float = 5.0
    web_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    log_level: str = "INFO"
    discovery_disconnect_wait_seconds: float = 8.0
    discovery_flush_arp: bool = True
    discovery_verify_replug: bool = True
    discovery_mndp_listen_seconds: float = 6.0
    discovery_passive_listen_seconds: float = 3.0
    ping_count: int = 2
    ping_timeout_seconds: float = 3.0
    ping_packet_size: int = 56
    ping_custom_targets: list[dict[str, str]] = field(default_factory=list)
    ping_adhoc_path: str = "/var/lib/ndp/ping_adhoc.host"
    wifi_hotspot_enabled: bool = True
    wifi_hotspot_ssid_prefix: str = "NDP"
    wifi_hotspot_password: str = "ndp-probe"
    wifi_hotspot_interface: str = "wlan0"
    wifi_hotspot_ip: str = "192.168.50.1"
    wifi_hotspot_dhcp_start: str = "192.168.50.10"
    wifi_hotspot_dhcp_end: str = "192.168.50.50"
    wifi_hotspot_channel: int = 6
    wifi_hotspot_country: str = "IT"
    source_path: Path | None = field(default=None, repr=False)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> NdpConfig:
        lldp = data.get("lldp", {})
        ui = data.get("ui", {})
        console = data.get("console", {})
        web = data.get("web", {})
        logging_cfg = data.get("logging", {})
        discovery = data.get("discovery", {})
        ping = data.get("ping", {})
        wifi_hotspot = data.get("wifi_hotspot", {})
        custom_targets = ping.get("custom_targets", [])
        if not isinstance(custom_targets, list):
            custom_targets = []
        ui_input = str(ui.get("input", "none"))
        passive_input = ui_input in {"encoder", "none"}
        hint_edge_default = "none" if passive_input else "left"
        margin_default = 0 if passive_input else 28
        return cls(
            interface=str(data.get("interface", "eth0")),
            poll_interval_link_up=float(data.get("poll_interval_link_up", 1)),
            poll_interval_link_down=float(data.get("poll_interval_link_down", 5)),
            lldp_cache_ttl_seconds=int(lldp.get("cache_ttl_seconds", 30)),
            ui_enabled=bool(ui.get("enabled", False)),
            ui_framebuffer=str(ui.get("framebuffer", "/dev/fb1")),
            ui_width=int(ui.get("width", 320)),
            ui_height=int(ui.get("height", 240)),
            ui_sdl_driver=str(ui.get("sdl_driver", "fbcon")),
            ui_backend=str(ui.get("backend", "auto")),
            ui_backlight_gpio=int(ui.get("backlight_gpio", 18)),
            ui_backlight_enabled=bool(ui.get("backlight_enabled", True)),
            ui_rgb565_bgr=bool(ui.get("rgb565_bgr", False)),
            ui_rgb565_swap_bytes=bool(ui.get("rgb565_swap_bytes", False)),
            ui_font_size=int(ui.get("font_size", 14)),
            ui_fps=int(ui.get("fps", 20)),
            ui_input=ui_input,
            ui_auto_cycle_seconds=float(ui.get("auto_cycle_seconds", 8)),
            ui_button_previous=int(ui.get("button_previous", 23)),
            ui_button_select=int(ui.get("button_select", 24)),
            ui_button_next=int(ui.get("button_next", 25)),
            ui_encoder_clk=int(ui.get("encoder_clk", 5)),
            ui_encoder_dt=int(ui.get("encoder_dt", 6)),
            ui_encoder_sw=int(ui.get("encoder_sw", 19)),
            ui_encoder_steps_per_detent=int(ui.get("encoder_steps_per_detent", 4)),
            ui_encoder_sw_debounce_seconds=float(
                ui.get("encoder_sw_debounce_seconds", 0.03)
            ),
            ui_button_debounce_seconds=float(ui.get("button_debounce_seconds", 0.03)),
            ui_button_trigger_mode=str(ui.get("button_trigger_mode", "edge")),
            ui_button_press_confirm_ms=int(ui.get("button_press_confirm_ms", 0)),
            ui_hint_edge=str(ui.get("hint_edge", hint_edge_default)),
            ui_content_margin_side=int(ui.get("content_margin_side", margin_default)),
            ui_content_text_gap=int(ui.get("content_text_gap", 0)),
            ui_hint_y_offset=int(ui.get("hint_y_offset", 24)),
            ui_splash_enabled=bool(ui.get("splash_enabled", True)),
            ui_splash_message=str(ui.get("splash_message", "Network Diagnostic Probe")),
            ui_splash_min_seconds=float(ui.get("splash_min_seconds", 1.5)),
            ui_warmup_on_start=bool(ui.get("warmup_on_start", True)),
            ui_button_poll_hz=int(ui.get("button_poll_hz", 200)),
            ui_line_spacing=int(ui.get("line_spacing", 6)),
            console_enabled=bool(console.get("enabled", True)),
            console_refresh_seconds=float(console.get("refresh_seconds", 5)),
            web_enabled=bool(web.get("enabled", False)),
            web_host=str(web.get("host", "0.0.0.0")),
            web_port=int(web.get("port", 8080)),
            log_level=str(logging_cfg.get("level", "INFO")).upper(),
            discovery_disconnect_wait_seconds=float(
                discovery.get("disconnect_wait_seconds", 8)
            ),
            discovery_flush_arp=bool(discovery.get("flush_arp_before_second_scan", True)),
            discovery_verify_replug=bool(discovery.get("verify_replug", True)),
            discovery_mndp_listen_seconds=float(discovery.get("mndp_listen_seconds", 6)),
            discovery_passive_listen_seconds=float(discovery.get("passive_listen_seconds", 3)),
            ping_count=int(ping.get("count", 2)),
            ping_timeout_seconds=float(ping.get("timeout_seconds", 3)),
            ping_packet_size=int(ping.get("packet_size", 56)),
            ping_custom_targets=[
                {
                    "label": str(item.get("label", "Custom")),
                    "host": str(item.get("host", "")),
                }
                for item in custom_targets[:4]
                if isinstance(item, dict) and item.get("host")
            ],
            ping_adhoc_path=str(ping.get("adhoc_path", "/var/lib/ndp/ping_adhoc.host")),
            wifi_hotspot_enabled=bool(wifi_hotspot.get("enabled", True)),
            wifi_hotspot_ssid_prefix=str(wifi_hotspot.get("ssid_prefix", "NDP")),
            wifi_hotspot_password=str(wifi_hotspot.get("password", "ndp-probe")),
            wifi_hotspot_interface=str(wifi_hotspot.get("interface", "wlan0")),
            wifi_hotspot_ip=str(wifi_hotspot.get("ip", "192.168.50.1")),
            wifi_hotspot_dhcp_start=str(wifi_hotspot.get("dhcp_start", "192.168.50.10")),
            wifi_hotspot_dhcp_end=str(wifi_hotspot.get("dhcp_end", "192.168.50.50")),
            wifi_hotspot_channel=int(wifi_hotspot.get("channel", 6)),
            wifi_hotspot_country=str(wifi_hotspot.get("country", "IT")),
        )


def load_config(path: Path | None = None) -> NdpConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        config = NdpConfig.from_mapping(data)
        config.source_path = config_path
        return config

    with BUNDLED_CONFIG_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    config = NdpConfig.from_mapping(data)
    config.source_path = config_path if path is not None else BUNDLED_CONFIG_PATH
    return config
