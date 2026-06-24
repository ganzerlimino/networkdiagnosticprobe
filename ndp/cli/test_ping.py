"""Ping test CLI."""

from __future__ import annotations

import json
import logging
from argparse import Namespace
from pathlib import Path

from ndp.core.config import load_config
from ndp.ping.service import read_adhoc_host, run_ping_suite, validate_host, write_adhoc_host

logger = logging.getLogger(__name__)


def add_ping_test_subparser(test_sub) -> None:
    ping = test_sub.add_parser("ping", help="ICMP ping verso destinazioni configurate")
    ping.add_argument(
        "--adhoc",
        metavar="HOST",
        help="Imposta host adhoc temporaneo (uno solo) ed esegue il test",
    )
    ping.add_argument(
        "--clear-adhoc",
        action="store_true",
        help="Rimuove l'host adhoc temporaneo",
    )
    ping.add_argument(
        "--set-adhoc",
        metavar="HOST",
        help="Imposta solo l'host adhoc senza eseguire il test",
    )
    ping.add_argument(
        "--list-targets",
        action="store_true",
        help="Elenca le destinazioni che verrebbero testate",
    )
    ping.add_argument(
        "--json",
        action="store_true",
        help="Output JSON",
    )


def run_ping_test_command(args: Namespace, config_path: Path | None, as_json: bool) -> int:
    config = load_config(config_path)
    adhoc_path = Path(config.ping_adhoc_path)
    emit_json = as_json or bool(getattr(args, "json", False))

    if args.clear_adhoc:
        write_adhoc_host(None, adhoc_path)
        print("Host adhoc rimosso.")
        return 0

    if args.set_adhoc:
        host = validate_host(args.set_adhoc)
        write_adhoc_host(host, adhoc_path)
        print(f"Host adhoc impostato: {host}")
        return 0

    if args.adhoc:
        host = validate_host(args.adhoc)
        write_adhoc_host(host, adhoc_path)
        logger.info("Adhoc host set to %s", host)

    if args.list_targets:
        from ndp.core.engine import ProbeEngine

        engine = ProbeEngine(config)
        state = engine.refresh()
        from ndp.ping.service import build_ping_targets

        targets = build_ping_targets(config, gateway=state.ip.gateway, adhoc_path=adhoc_path)
        if emit_json:
            print(json.dumps([{"label": t.label, "host": t.host, "kind": t.kind} for t in targets], indent=2))
        else:
            for target in targets:
                print(f"{target.kind:7} {target.label:16} {target.host}")
        return 0

    from ndp.core.engine import ProbeEngine

    engine = ProbeEngine(config)
    probe = engine.refresh()
    suite = run_ping_suite(config, gateway=probe.ip.gateway, adhoc_path=adhoc_path)

    if emit_json:
        print(json.dumps(suite.to_dict(), indent=2, default=str))
        return 0

    print(f"Adhoc: {read_adhoc_host(adhoc_path) or 'n/a'}")
    for item in suite.results:
        status = "OK" if item.result.reachable else "FAIL"
        rtt = f"{item.result.rtt_ms:.0f} ms" if item.result.rtt_ms is not None else item.result.message
        print(f"{item.label:16} {item.host:16} {status:4} {rtt}")
    return 0
