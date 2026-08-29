from ndp.mtu.discover import mtu_payload_for_mtu


def test_mtu_payload_for_ipv4() -> None:
    assert mtu_payload_for_mtu(1500) == 1472
    assert mtu_payload_for_mtu(576) == 548


def test_mtu_payload_non_negative() -> None:
    assert mtu_payload_for_mtu(100) == 72
