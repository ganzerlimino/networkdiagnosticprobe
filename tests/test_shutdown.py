from unittest.mock import MagicMock, patch

from ndp.system.shutdown import (
    ShutdownPhase,
    request_shutdown,
    reset_shutdown_state_for_tests,
    shutdown_snapshot,
)


def setup_function() -> None:
    reset_shutdown_state_for_tests()


def test_shutdown_snapshot_idle() -> None:
    payload = shutdown_snapshot()
    assert payload["phase"] == ShutdownPhase.IDLE.value
    assert payload["active"] is False


def test_request_shutdown_starts_in_progress() -> None:
    mock_thread = MagicMock()
    with patch("ndp.system.shutdown.threading.Thread", return_value=mock_thread):
        payload = request_shutdown(delay_seconds=5.0)
    assert payload["phase"] == ShutdownPhase.IN_PROGRESS.value
    assert payload["active"] is True
    assert "Spegnimento" in payload["message"]
    mock_thread.start.assert_called_once()


def test_request_shutdown_is_idempotent() -> None:
    mock_thread = MagicMock()
    with patch("ndp.system.shutdown.threading.Thread", return_value=mock_thread):
        first = request_shutdown(delay_seconds=5.0)
        second = request_shutdown(delay_seconds=5.0)
    assert first["phase"] == ShutdownPhase.IN_PROGRESS.value
    assert second["phase"] == ShutdownPhase.IN_PROGRESS.value
    mock_thread.start.assert_called_once()
