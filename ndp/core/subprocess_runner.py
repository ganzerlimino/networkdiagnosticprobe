"""Thin subprocess wrapper for testability."""

from __future__ import annotations

import json
import subprocess
from typing import Any


class CommandError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Command failed ({returncode}): {' '.join(command)}\n{stderr.strip()}"
        )


def run_command(command: list[str], timeout: float = 10.0) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(command, result.returncode, result.stderr)
    return result.stdout


def run_json_command(command: list[str], timeout: float = 10.0) -> Any:
    output = run_command(command, timeout=timeout)
    return json.loads(output or "null")
