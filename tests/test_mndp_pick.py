from ndp.core.collectors.mndp import MndpDevice, pick_connected_mndp_device


def test_pick_connected_mndp_by_gateway_mac() -> None:
    devices = [
        MndpDevice(identity="router-a", mac="aa:bb:cc:dd:ee:01", ipv4="192.168.1.1"),
        MndpDevice(identity="switch-core", mac="aa:bb:cc:dd:ee:02", ipv4="192.168.1.254"),
    ]
    picked = pick_connected_mndp_device(devices, gateway_mac="aa:bb:cc:dd:ee:02")
    assert picked is not None
    assert picked.identity == "switch-core"
    assert picked.connected is True


def test_pick_connected_mndp_by_gateway_ip() -> None:
    devices = [
        MndpDevice(identity="router-a", mac="aa:bb:cc:dd:ee:01", ipv4="192.168.1.10"),
        MndpDevice(identity="switch-core", mac="aa:bb:cc:dd:ee:02", ipv4="192.168.1.1"),
    ]
    picked = pick_connected_mndp_device(devices, gateway_ip="192.168.1.1")
    assert picked is not None
    assert picked.identity == "switch-core"


def test_pick_connected_mndp_returns_none_when_ambiguous() -> None:
    devices = [
        MndpDevice(identity="mt1", mac="aa:bb:cc:dd:ee:01", ipv4="192.168.1.10"),
        MndpDevice(identity="mt2", mac="aa:bb:cc:dd:ee:02", ipv4="192.168.1.11"),
    ]
    assert pick_connected_mndp_device(devices, gateway_ip="192.168.1.99") is None
