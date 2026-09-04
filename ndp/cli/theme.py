"""Theme catalog validation CLI."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

from ndp.locale.theme_validate import validate_themes_file, validate_themes_setup


def add_theme_subparser(subparsers: argparse._SubParsersAction) -> None:
    theme = subparsers.add_parser(
        "theme",
        help="Temi colori (validazione JSON)",
    )
    theme_sub = theme.add_subparsers(dest="theme_command", required=True)

    validate = theme_sub.add_parser(
        "validate",
        help="Valida themes.json rispetto a themes.schema.json",
    )
    validate.add_argument(
        "--file",
        type=Path,
        help="File da validare (default: /etc/ndp/locale/themes.json se presente, poi catalogo merge)",
    )
    validate.add_argument(
        "--catalog-only",
        action="store_true",
        help="Valida solo il catalogo merged (come vede ndp a runtime)",
    )
    validate.add_argument("--json", action="store_true", help="Output JSON")


def run_theme_command(args: Namespace) -> int:
    if args.theme_command == "validate":
        return _run_validate(args)
    return 1


def _run_validate(args: Namespace) -> int:
    if args.catalog_only:
        from ndp.locale.theme_validate import validate_runtime_catalog

        report = validate_runtime_catalog()
    elif args.file is not None:
        report = validate_themes_file(args.file)
    else:
        report = validate_themes_setup()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report)

    return 0 if report.ok else 1


def _print_report(report) -> None:
    target = report.file or "n/a"
    print(f"Tema NDP — validazione: {target}")
    if report.schema:
        print(f"Schema : {report.schema}")
    if report.theme_ids:
        print(f"Temi   : {', '.join(report.theme_ids)}")
    for warning in report.warnings:
        print(f"AVVISO : {warning}")
    if report.ok:
        print("Esito  : OK")
        return
    print("Esito  : ERRORE")
    for error in report.errors:
        print(f"  - {error}")
