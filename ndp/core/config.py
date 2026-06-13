"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
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
    console_enabled: bool = True
    console_refresh_seconds: float = 5.0
    web_enabled: bool = False
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    log_level: str = "INFO"
    discovery_disconnect_wait_seconds: float = 8.0
    discovery_flush_arp: bool = True
    discovery_verify_replug: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> NdpConfig:
        lldp = data.get("lldp", {})
        ui = data.get("ui", {})
        console = data.get("console", {})
        web = data.get("web", {})
        logging_cfg = data.get("logging", {})
        discovery = data.get("discovery", {})
        return cls(
            interface=str(data.get("interface", "eth0")),
            poll_interval_link_up=float(data.get("poll_interval_link_up", 1)),
            poll_interval_link_down=float(data.get("poll_interval_link_down", 5)),
            lldp_cache_ttl_seconds=int(lldp.get("cache_ttl_seconds", 30)),
            ui_enabled=bool(ui.get("enabled", False)),
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
        )


def load_config(path: Path | None = None) -> NdpConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return NdpConfig.from_mapping(data)

    with BUNDLED_CONFIG_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return NdpConfig.from_mapping(data)
