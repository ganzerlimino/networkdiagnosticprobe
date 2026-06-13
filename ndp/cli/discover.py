"""Discovery CLI commands."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

from ndp.core.config import NdpConfig, load_config
from ndp.discovery.arp import flush_arp_cache, scan_hosts
from ndp.discovery.console import render_diff, render_snapshot, render_updown_result
from ndp.discovery.diff import diff_snapshots
from ndp.discovery.host import DiscoveredHost, ScanSnapshot
from ndp.discovery.wizard import DiscoveryConfig, UpDownWizard


def _discovery_config_from_ndp(config: NdpConfig) -> DiscoveryConfig:
    return DiscoveryConfig(
        disconnect_wait_seconds=config.discovery_disconnect_wait_seconds,
        flush_arp_before_second_scan=config.discovery_flush_arp,
        verify_replug=config.discovery_verify_replug,
    )


def _load_snapshot(path: Path) -> ScanSnapshot:
    data = json.loads(path.read_text(encoding="utf-8"))
    hosts = [DiscoveredHost(**item) for item in data.get("hosts", [])]
    return ScanSnapshot(
        interface=data["interface"],
        hosts=hosts,
        source=data.get("source", "imported"),
    )


def add_discover_subparser(subparsers: argparse._SubParsersAction) -> None:
    discover = subparsers.add_parser(
        "discover",
        help="Network host discovery utilities",
    )
    discover_sub = discover.add_subparsers(dest="discover_command", required=True)

    scan = discover_sub.add_parser("scan", help="Run a single ARP/network scan")
    scan.add_argument("--interface", help="Network interface (default: from config)")
    scan.add_argument("--json", action="store_true", help="JSON output")
    scan.add_argument("--save", type=Path, help="Save snapshot JSON to file")

    diff_cmd = discover_sub.add_parser("diff", help="Diff two saved snapshots")
    diff_cmd.add_argument("baseline", type=Path, help="Baseline snapshot JSON")
    diff_cmd.add_argument("current", type=Path, help="Current snapshot JSON")
    diff_cmd.add_argument("--json", action="store_true", help="JSON diff output")

    flush = discover_sub.add_parser("flush-arp", help="Flush ARP cache on interface")
    flush.add_argument("--interface", help="Network interface (default: from config)")

    updown = discover_sub.add_parser(
        "updown",
        help="Guided Up/Down wizard (baseline → unplug → flush → rescan → verify)",
    )
    updown.add_argument("--interface", help="Network interface (default: from config)")
    updown.add_argument("--json", action="store_true", help="JSON result output")
    updown.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip step 5 (replug verification)",
    )


def run_discover_command(args: Namespace, config_path: Path | None) -> int:
    config = load_config(config_path)
    interface = getattr(args, "interface", None) or config.interface

    if args.discover_command == "scan":
        snapshot = scan_hosts(interface)
        if args.save:
            args.save.write_text(
                json.dumps(snapshot.to_dict(), indent=2),
                encoding="utf-8",
            )
        if args.json:
            print(json.dumps(snapshot.to_dict(), indent=2))
        else:
            print(render_snapshot(snapshot))
        return 0

    if args.discover_command == "flush-arp":
        ok = flush_arp_cache(interface)
        print(f"ARP cache flush on {interface}: {'ok' if ok else 'failed'}")
        return 0 if ok else 1

    if args.discover_command == "diff":
        baseline = _load_snapshot(args.baseline)
        current = _load_snapshot(args.current)
        result = diff_snapshots(baseline, current)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(render_diff(result))
        return 0

    if args.discover_command == "updown":
        wizard = UpDownWizard(
            interface=interface,
            config=_discovery_config_from_ndp(config),
            skip_verify=args.skip_verify,
        )
        result = wizard.run()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print()
            print(render_updown_result(result))
        return 0

    return 1
