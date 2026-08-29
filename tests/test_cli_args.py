"""CLI argument parsing tests."""

from __future__ import annotations

import pytest

from ndp.main import build_parser


@pytest.mark.parametrize(
    ("argv", "expected_config"),
    [
        (["hotspot", "ensure", "--config", "/etc/ndp/config.yaml"], "/etc/ndp/config.yaml"),
        (["hotspot", "start", "--config", "/tmp/ndp.yaml", "--json"], "/tmp/ndp.yaml"),
        (["discover", "scan", "--config", "/etc/ndp/config.yaml", "--json"], "/etc/ndp/config.yaml"),
        (["test", "display", "--config", "/etc/ndp/config.yaml", "--color", "red"], "/etc/ndp/config.yaml"),
    ],
)
def test_subcommand_accepts_config(argv: list[str], expected_config: str) -> None:
    args = build_parser().parse_args(argv)
    assert str(args.config) == expected_config


def test_hotspot_ensure_sets_command() -> None:
    args = build_parser().parse_args(["hotspot", "ensure", "--config", "/etc/ndp/config.yaml"])
    assert args.command == "hotspot"
    assert args.hotspot_command == "ensure"
