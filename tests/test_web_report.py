from ndp.core.state import IpState, LinkState, ProbeState, SystemState
from ndp.web.report import build_report


def test_build_report_status_section() -> None:
    state = ProbeState(
        interface="eth0",
        link=LinkState(carrier=True, mac_address="aa:bb:cc:dd:ee:ff"),
        ip=IpState(gateway="10.0.0.1"),
        system=SystemState(hostname="ndp"),
    )
    report = build_report(state, section="status", version="0.8.0")
    assert report["subject"] == "NDP — Stato rete"
    assert "10.0.0.1" in report["body"]
    assert "ndp" in report["body"]


def test_build_report_all() -> None:
    state = ProbeState(interface="eth0")
    report = build_report(state, section="all", version="0.8.0")
    assert report["subject"] == "NDP — Report completo"
    assert "LINK" in report["body"]
    assert "PING" in report["body"]
