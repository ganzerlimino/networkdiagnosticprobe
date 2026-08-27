"""NDP service entry point."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from ndp import __version__
from ndp.cli.discover import add_discover_subparser, run_discover_command
from ndp.cli.hotspot import add_hotspot_subparser, run_hotspot_command
from ndp.cli.test_display import add_test_subparser, run_test_command
from ndp.console import render_status
from ndp.core.config import load_config
from ndp.core.engine import ProbeEngine
from ndp.core.ping_state import PingSuiteState
from ndp.core.state import ProbeState

logger = logging.getLogger(__name__)
_STOP_REQUESTED = False


def _handle_signal(signum: int, _frame: object) -> None:
    global _STOP_REQUESTED
    logger.info("Received signal %s, shutting down", signum)
    _STOP_REQUESTED = True


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run_once(config_path: Path | None, as_json: bool) -> int:
    config = load_config(config_path)
    _configure_logging(config.log_level)
    engine = ProbeEngine(config)
    state = engine.refresh()

    if as_json:
        print(json.dumps(state.to_dict(), default=str, indent=2))
    else:
        print(render_status(state))
    return 0


def run_web_only(config_path: Path | None) -> int:
    config = load_config(config_path)
    _configure_logging(config.log_level)

    from ndp.web.server import resolve_config_path, start_web_server

    engine = ProbeEngine(config)
    lock = threading.Lock()
    state = engine.refresh()

    def get_state() -> ProbeState:
        with lock:
            return state

    config_file = config.source_path or resolve_config_path(config_path)

    def _set_ping(suite: PingSuiteState) -> None:
        nonlocal state
        with lock:
            state.ping = suite

    start_web_server(
        config,
        config_file,
        get_state,
        on_ping_complete=_set_ping,
    )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("NDP %s web-only on %s:%s", __version__, config.web_host, config.web_port)
    while not _STOP_REQUESTED:
        with lock:
            state = engine.refresh()
        time.sleep(engine.poll_interval())

    logger.info("NDP stopped")
    return 0


def run_service(config_path: Path | None) -> int:
    config = load_config(config_path)
    _configure_logging(config.log_level)

    if config.ui_enabled:
        from ndp.ui.app import run_ui

        logger.info("NDP %s UI mode on %s", __version__, config.ui_framebuffer)
        return run_ui(config)

    if config.web_enabled:
        return run_web_only(config_path)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    engine = ProbeEngine(config)
    last_console_print = 0.0

    logger.info(
        "NDP %s started on interface %s",
        __version__,
        config.interface,
    )

    while not _STOP_REQUESTED:
        state = engine.refresh()

        if config.console_enabled:
            now = time.monotonic()
            if now - last_console_print >= config.console_refresh_seconds:
                print(render_status(state), flush=True)
                print("-" * 40, flush=True)
                last_console_print = now

        if config.web_enabled:
            logger.debug("Web UI runs with the Pygame UI or web-only service loop")

        time.sleep(engine.poll_interval())

    logger.info("NDP stopped")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ndp",
        description="Network Diagnostic Probe service",
    )
    parser.add_argument("--version", action="version", version=f"ndp {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config YAML (default: /etc/ndp/config.yaml or bundled default)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect probe status once and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output (with --once or discover)",
    )

    subparsers = parser.add_subparsers(dest="command")
    add_discover_subparser(subparsers)
    add_hotspot_subparser(subparsers)
    add_test_subparser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "discover":
        return run_discover_command(args, args.config)

    if args.command == "hotspot":
        return run_hotspot_command(args, args.config)

    if args.command == "test":
        return run_test_command(args, args.config)

    if args.once:
        return run_once(args.config, args.json)

    if args.command is not None:
        parser.error(f"Unknown command: {args.command}")

    return run_service(args.config)


if __name__ == "__main__":
    sys.exit(main())
