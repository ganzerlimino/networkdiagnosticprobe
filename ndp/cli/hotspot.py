"""NDP Wi-Fi hotspot"""

from __future__ import annotations

import argparse
import json
from argparse import Namespace

from ndp.cli.parser_common import config_parent_parser
from ndp.core.config import load_config
from ndp.network.hotspot import ensure_hotspot, get_status, start_hotspot, stop_hotspot


def add_hotspot_subparser(subparsers: argparse._SubParsersAction) -> None:
    config_parent = config_parent_parser()
    hotspot = subparsers.add_parser(
        "hotspot",
        help="Wi-Fi hotspot per accesso telefono",
        parents=[config_parent],
    )
    hotspot_sub = hotspot.add_subparsers(dest="hotspot_command", required=True)

    start = hotspot_sub.add_parser(
        "start",
        help="Avvia hotspot (hostapd + dnsmasq)",
        parents=[config_parent],
    )
    start.add_argument("--json", action="store_true", help="Output JSON")

    hotspot_sub.add_parser(
        "stop",
        help="Ferma hotspot",
        parents=[config_parent],
    )
    ensure = hotspot_sub.add_parser(
        "ensure",
        help="Avvia solo se abilitato e non attivo",
        parents=[config_parent],
    )
    ensure.add_argument("--json", action="store_true")

    status = hotspot_sub.add_parser(
        "status",
        help="Stato hotspot",
        parents=[config_parent],
    )
    status.add_argument("--json", action="store_true")


def _print_status(status: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(status.to_dict(), indent=2))
        return
    data = status.to_dict()
    print(f"Enabled : {data['enabled']}")
    print(f"Active  : {data['active']}")
    print(f"SSID    : {data.get('ssid') or 'n/a'}")
    print(f"URL     : {data.get('web_url') or 'n/a'}")
    if data.get("open_network"):
        print("Auth    : rete aperta")
    elif data.get("password_hint"):
        print(f"Auth    : {data['password_hint']}")
    print(f"Message : {data.get('message', '')}")


def run_hotspot_command(args: Namespace, config_path) -> int:
    config_path = config_path or getattr(args, "config", None)
    config = load_config(config_path)
    if args.hotspot_command == "start":
        status = start_hotspot(config)
    elif args.hotspot_command == "stop":
        stop_hotspot(config)
        status = get_status(config)
    elif args.hotspot_command == "ensure":
        status = ensure_hotspot(config)
    elif args.hotspot_command == "status":
        status = get_status(config)
    else:
        return 1

    as_json = getattr(args, "json", False)
    _print_status(status, as_json)
    if args.hotspot_command in {"status", "stop"}:
        return 0
    if not config.wifi_hotspot_enabled:
        return 0
    return 0 if status.active else 1
