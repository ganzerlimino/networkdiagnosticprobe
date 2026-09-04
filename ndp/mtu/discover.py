"""Decremental MTU discovery using ping with DF (do not fragment)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from queue import Empty, Queue

from ndp.core.collectors.ping import ping_mtu_probe

logger = logging.getLogger(__name__)

DEFAULT_START_MTU = 1500
DEFAULT_MIN_MTU = 576


def mtu_payload_for_mtu(mtu: int) -> int:
    """ICMP data bytes for an IPv4 MTU (20-byte IP header + 8-byte ICMP)."""
    return max(0, mtu - 28)


@dataclass
class MtuDiscoverySession:
    session_id: str
    host: str
    interface: str
    start_mtu: int = DEFAULT_START_MTU
    min_mtu: int = DEFAULT_MIN_MTU
    timeout_seconds: float = 2.0
    events: Queue[dict[str, object]] = field(default_factory=Queue)
    active: bool = True
    result_mtu: int | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"ndp-mtu-{self.host}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.active = False
        self.events.put({"type": "stopped", "session_id": self.session_id})

    def _run(self) -> None:
        try:
            for mtu in range(self.start_mtu, self.min_mtu - 1, -1):
                if self._stop.is_set():
                    break
                payload = mtu_payload_for_mtu(mtu)
                result = ping_mtu_probe(
                    self.host,
                    payload_size=payload,
                    interface=self.interface,
                    timeout_seconds=self.timeout_seconds,
                )
                event = {
                    "type": "probe",
                    "mtu": mtu,
                    "payload_size": payload,
                    "reachable": result.reachable,
                    "message": result.message,
                    "rtt_ms": result.rtt_ms,
                }
                self.events.put(event)
                if result.reachable:
                    self.result_mtu = mtu
                    self.events.put(
                        {
                            "type": "result",
                            "host": self.host,
                            "mtu": mtu,
                            "payload_size": payload,
                            "message": f"MTU massimo rilevato: {mtu}",
                        }
                    )
                    break
                time.sleep(0.05)
            else:
                self.events.put(
                    {
                        "type": "result",
                        "host": self.host,
                        "mtu": None,
                        "message": f"Nessun MTU utilizzabile tra {self.start_mtu} e {self.min_mtu}",
                    }
                )
        finally:
            self.active = False
            self.events.put({"type": "done", "session_id": self.session_id, "mtu": self.result_mtu})

    def iter_events(self, timeout: float = 1.0) -> Iterator[dict[str, object]]:
        while self.active or not self.events.empty():
            try:
                yield self.events.get(timeout=timeout)
            except Empty:
                yield {"type": "keepalive", "timestamp": time.time()}
            if self._stop.is_set() and self.events.empty():
                break


class MtuDiscoveryManager:
    def __init__(self) -> None:
        self._sessions: dict[str, MtuDiscoverySession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        host: str,
        *,
        interface: str,
        start_mtu: int = DEFAULT_START_MTU,
        min_mtu: int = DEFAULT_MIN_MTU,
        timeout_seconds: float = 2.0,
    ) -> MtuDiscoverySession:
        session = MtuDiscoverySession(
            session_id=uuid.uuid4().hex[:12],
            host=host,
            interface=interface,
            start_mtu=max(576, min(9000, start_mtu)),
            min_mtu=max(576, min(start_mtu, min_mtu)),
            timeout_seconds=timeout_seconds,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        session.start()
        return session

    def get(self, session_id: str) -> MtuDiscoverySession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def stop(self, session_id: str) -> bool:
        session = self.get(session_id)
        if session is None:
            return False
        session.stop()
        return True

    def stop_all(self) -> None:
        with self._lock:
            session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            self.stop(session_id)


def discover_mtu_sync(
    host: str,
    *,
    interface: str,
    start_mtu: int = DEFAULT_START_MTU,
    min_mtu: int = DEFAULT_MIN_MTU,
    timeout_seconds: float = 2.0,
) -> int | None:
    for mtu in range(start_mtu, min_mtu - 1, -1):
        payload = mtu_payload_for_mtu(mtu)
        result = ping_mtu_probe(
            host,
            payload_size=payload,
            interface=interface,
            timeout_seconds=timeout_seconds,
        )
        if result.reachable:
            return mtu
    return None
