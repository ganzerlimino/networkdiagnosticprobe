from ndp.core.collectors.ping import _parse_ping_output, ping_host
from ndp.core.config import NdpConfig
from ndp.ping.service import build_ping_targets, validate_host, write_adhoc_host


def test_parse_ping_success() -> None:
    output = """
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=21.4 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=117 time=22.1 ms

--- 8.8.8.8 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 1001ms
rtt min/avg/max/mdev = 21.400/21.750/22.100/0.350 ms
"""
    result = _parse_ping_output("8.8.8.8", 2, output, 0)
    assert result.reachable is True
    assert result.rtt_ms == 21.75
    assert result.packet_loss_pct == 0.0


def test_parse_ping_unreachable() -> None:
    output = """
2 packets transmitted, 0 received, 100% packet loss, time 1012ms
"""
    result = _parse_ping_output("1.1.1.1", 2, output, 1)
    assert result.reachable is False
    assert result.packet_loss_pct == 100.0


def test_build_ping_targets_builtin_custom_adhoc(tmp_path) -> None:
    adhoc = tmp_path / "adhoc.host"
    write_adhoc_host("203.0.113.10", adhoc)
    config = NdpConfig(
        ping_custom_targets=[
            {"label": "Gateway", "host": "gateway"},
            {"label": "LAN", "host": "10.0.0.50"},
        ]
    )
    targets = build_ping_targets(config, gateway="10.0.0.1", adhoc_path=adhoc)
    hosts = [t.host for t in targets]
    assert hosts[:2] == ["8.8.8.8", "1.1.1.1"]
    assert "10.0.0.1" in hosts
    assert "10.0.0.50" in hosts
    assert "203.0.113.10" in hosts
    assert len([t for t in targets if t.kind == "custom"]) == 2
    assert len([t for t in targets if t.kind == "adhoc"]) == 1


def test_custom_targets_capped_at_four() -> None:
    config = NdpConfig(
        ping_custom_targets=[
            {"label": f"T{n}", "host": f"10.0.0.{n}"} for n in range(10)
        ]
    )
    targets = build_ping_targets(config)
    custom = [t for t in targets if t.kind == "custom"]
    assert len(custom) == 4


def test_validate_host_rejects_invalid() -> None:
    try:
        validate_host("not valid!")
        assert False
    except ValueError:
        pass


def test_ping_host_missing_command(monkeypatch) -> None:
    monkeypatch.setattr("ndp.core.collectors.ping.shutil.which", lambda _name: None)
    result = ping_host("8.8.8.8")
    assert result.reachable is False
    assert "not found" in result.message
