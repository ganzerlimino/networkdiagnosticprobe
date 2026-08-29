"""Shared argparse helpers for NDP CLI subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config YAML (default: /etc/ndp/config.yaml or bundled default)",
    )


def config_parent_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    add_config_argument(parent)
    return parent
