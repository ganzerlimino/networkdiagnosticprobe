import time

from ndp.ping.live import LivePingManager


def test_live_ping_manager_creates_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "ndp.ping.live.ping_host",
        lambda host, **_: type("R", (), {
            "rtt_ms": 12.0, "reachable": True, "message": "ok"
        })(),
    )
    manager = LivePingManager()
    session = manager.create(["8.8.8.8", "1.1.1.1"], interval_seconds=0.1, max_samples=2)
    assert len(session.hosts) == 2
    time.sleep(0.35)
    session.stop()
    events = []
    for event in session.iter_events(timeout=0.1):
        if event.get("type") == "sample":
            events.append(event)
        if len(events) >= 2:
            break
    assert events
    assert events[0]["host"] in {"8.8.8.8", "1.1.1.1"}


def test_live_ping_rejects_too_many_hosts() -> None:
    manager = LivePingManager()
    try:
        manager.create(["1.1.1.1", "8.8.8.8", "9.9.9.9", "1.0.0.1"])
        assert False
    except ValueError:
        pass
