"""Controlled system shutdown with status feedback for UI and HTTP clients."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

_SHUTDOWN_DELAY_SECONDS = 3.0
_POWEROFF_COMMAND = ("systemctl", "poweroff")


class ShutdownPhase(str, Enum):
    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    STOPPING_SERVICES = "stopping_services"
    POWERING_OFF = "powering_off"


@dataclass
class ShutdownState:
    phase: ShutdownPhase = ShutdownPhase.IDLE
    message: str = ""
    requested_at: str | None = None


_lock = threading.RLock()
_state = ShutdownState()
_stop_hotspot: Callable[[], None] | None = None
_poweroff_runner: Callable[[], None] | None = None


def configure_shutdown_hooks(
    *,
    stop_hotspot: Callable[[], None] | None = None,
    poweroff_runner: Callable[[], None] | None = None,
) -> None:
    global _stop_hotspot, _poweroff_runner
    _stop_hotspot = stop_hotspot
    _poweroff_runner = poweroff_runner


def shutdown_snapshot() -> dict[str, Any]:
    with _lock:
        payload = asdict(_state)
        payload["phase"] = _state.phase.value
        payload["active"] = _state.phase != ShutdownPhase.IDLE
        return payload


def is_shutting_down() -> bool:
    with _lock:
        return _state.phase != ShutdownPhase.IDLE


def shutdown_message() -> str:
    with _lock:
        return _state.message or "Spegnimento in corso..."


def request_shutdown(*, delay_seconds: float = _SHUTDOWN_DELAY_SECONDS) -> dict[str, Any]:
    with _lock:
        if _state.phase != ShutdownPhase.IDLE:
            return shutdown_snapshot()
        _state.phase = ShutdownPhase.IN_PROGRESS
        _state.message = "Spegnimento in corso..."
        _state.requested_at = datetime.now(timezone.utc).isoformat()

    thread = threading.Thread(
        target=_run_shutdown,
        args=(max(delay_seconds, 1.0),),
        daemon=True,
        name="ndp-shutdown",
    )
    thread.start()
    return shutdown_snapshot()


def _set_phase(phase: ShutdownPhase, message: str) -> None:
    with _lock:
        _state.phase = phase
        _state.message = message


def _run_shutdown(delay_seconds: float) -> None:
    logger.warning("System shutdown requested; power-off in %.1fs", delay_seconds)
    time.sleep(delay_seconds)

    _set_phase(ShutdownPhase.STOPPING_SERVICES, "Arresto servizi in corso...")
    if _stop_hotspot is not None:
        try:
            _stop_hotspot()
        except Exception as exc:
            logger.warning("Hotspot stop during shutdown failed: %s", exc)

    _set_phase(ShutdownPhase.POWERING_OFF, "Spegnimento sistema...")
    time.sleep(1.0)

    logger.warning("Issuing poweroff command")
    try:
        if _poweroff_runner is not None:
            _poweroff_runner()
        else:
            subprocess.Popen(list(_POWEROFF_COMMAND))  # noqa: S603
    except OSError as exc:
        logger.error("Poweroff command failed: %s", exc)
        _set_phase(ShutdownPhase.IDLE, f"Spegnimento fallito: {exc}")


def reset_shutdown_state_for_tests() -> None:
    global _state
    with _lock:
        _state = ShutdownState()
