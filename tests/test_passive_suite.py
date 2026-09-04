from unittest.mock import MagicMock

from ndp.discovery import passive_suite


def test_passive_suite_runs_phases_in_parallel(monkeypatch) -> None:
    import time

    delays: dict[str, float] = {
        "l2": 0.4,
        "dhcp": 0.4,
        "snmp": 0.2,
        "mdns": 0.2,
        "ssdp": 0.2,
        "l2_probe": 0.15,
    }
    started: list[tuple[str, float]] = []

    def _track(name: str, delay: float):
        def _run(*_args, **_kwargs):
            started.append((name, time.monotonic()))
            time.sleep(delay)
            if name in {"l2", "dhcp"}:
                mock = MagicMock()
                mock.to_dict.return_value = {"hits": []}
                return mock
            if name == "snmp":
                return {"available": False, "message": "skip", "result": None}
            if name == "l2_probe":
                hit = MagicMock()
                hit.to_dict.return_value = {"protocol": "FDP", "frame_count": 1}
                return [hit]
            return {"service_count": 0, "services": []} if name == "mdns" else {"device_count": 0, "devices": []}

        return _run

    monkeypatch.setattr(passive_suite, "sniff_passive_protocols", _track("l2", delays["l2"]))
    monkeypatch.setattr(passive_suite, "sniff_dhcp_option82", _track("dhcp", delays["dhcp"]))
    monkeypatch.setattr(passive_suite, "probe_snmp_snapshot", _track("snmp", delays["snmp"]))
    monkeypatch.setattr(passive_suite, "discover_mdns_snapshot", _track("mdns", delays["mdns"]))
    monkeypatch.setattr(passive_suite, "discover_ssdp_snapshot", _track("ssdp", delays["ssdp"]))
    monkeypatch.setattr(passive_suite, "probe_l2_protocols", _track("l2_probe", delays["l2_probe"]))

    t0 = time.monotonic()
    result = passive_suite.run_passive_check_suite("eth0", listen_seconds=3.0)
    elapsed = time.monotonic() - t0

    assert result["parallel"] is True
    assert len(started) == 6
    assert elapsed < 1.0
    assert result["duration_seconds"] < 1.0
    assert result["listen_seconds"] == 3.0
