"""Concurrent live ping sessions with SSE-friendly event queues."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from queue import Empty, Queue

from ndp.core.collectors.ping import ping_host

logger = logging.getLogger(__name__)

MAX_HOSTS = 3
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_MAX_SAMPLES = 60


@dataclass
class LivePingSample:
    host: str
    seq: int
    rtt_ms: float | None
    reachable: bool
    message: str
    timestamp: float

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "seq": self.seq,
            "rtt_ms": self.rtt_ms,
            "reachable": self.reachable,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class LivePingSession:
    session_id: str
    hosts: list[str]
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    max_samples: int = DEFAULT_MAX_SAMPLES
    events: Queue[dict[str, object]] = field(default_factory=Queue)
    active: bool = True
    _stop: threading.Event = field(default_factory=threading.Event)
    _threads: list[threading.Thread] = field(default_factory=list)

    def start(self) -> None:
        for host in self.hosts:
            thread = threading.Thread(
                target=self._ping_loop,
                args=(host,),
                daemon=True,
                name=f"ndp-live-ping-{host}",
            )
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.active = False
        self.events.put({"type": "done", "session_id": self.session_id})

    def _ping_loop(self, host: str) -> None:
        seq = 0
        while not self._stop.is_set() and seq < self.max_samples:
            started = time.monotonic()
            result = ping_host(host, count=1, timeout_seconds=2.0)
            seq += 1
            sample = LivePingSample(
                host=host,
                seq=seq,
                rtt_ms=result.rtt_ms,
                reachable=result.reachable,
                message=result.message,
                timestamp=time.time(),
            )
            self.events.put({"type": "sample", **sample.to_dict()})
            elapsed = time.monotonic() - started
            wait = max(0.0, self.interval_seconds - elapsed)
            if self._stop.wait(wait):
                break
        if self.active:
            self.events.put({"type": "host_done", "host": host, "samples": seq})

    def iter_events(self, timeout: float = 1.0) -> Iterator[dict[str, object]]:
        while self.active or not self.events.empty():
            try:
                yield self.events.get(timeout=timeout)
            except Empty:
                yield {"type": "keepalive", "timestamp": time.time()}
            if self._stop.is_set() and self.events.empty():
                break


class LivePingManager:
    def __init__(self) -> None:
        self._sessions: dict[str, LivePingSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        hosts: list[str],
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        max_samples: int = DEFAULT_MAX_SAMPLES,
    ) -> LivePingSession:
        cleaned = [host.strip() for host in hosts if host.strip()]
        if not cleaned:
            raise ValueError("almeno un host richiesto")
        if len(cleaned) > MAX_HOSTS:
            raise ValueError(f"massimo {MAX_HOSTS} host in contemporanea")
        cleaned = cleaned[:MAX_HOSTS]

        session = LivePingSession(
            session_id=uuid.uuid4().hex[:12],
            hosts=cleaned,
            interval_seconds=max(0.2, interval_seconds),
            max_samples=max(1, min(max_samples, 300)),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        session.start()
        return session

    def get(self, session_id: str) -> LivePingSession | None:
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
