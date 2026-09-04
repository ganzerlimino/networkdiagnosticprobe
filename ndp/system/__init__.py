"""System-level operations (shutdown, power management)."""

from ndp.system.shutdown import (
    is_shutting_down,
    request_shutdown,
    shutdown_snapshot,
)

__all__ = ["is_shutting_down", "request_shutdown", "shutdown_snapshot"]
