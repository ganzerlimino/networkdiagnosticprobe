from ndp.discovery.diff import ScanDiff, confirm_reappearance, diff_snapshots
from ndp.discovery.host import DiscoveredHost, ScanSnapshot


def _host(ip: str, mac: str) -> DiscoveredHost:
    return DiscoveredHost(ip=ip, mac=mac)


def test_diff_snapshots_offline_and_probable_match() -> None:
    baseline = ScanSnapshot(
        interface="eth0",
        hosts=[
            _host("10.0.0.1", "aa:bb:cc:dd:ee:01"),
            _host("10.0.0.2", "aa:bb:cc:dd:ee:02"),
        ],
    )
    after = ScanSnapshot(
        interface="eth0",
        hosts=[_host("10.0.0.1", "aa:bb:cc:dd:ee:01")],
    )

    result = diff_snapshots(baseline, after)

    assert isinstance(result, ScanDiff)
    assert result.offline_count == 1
    assert result.probable_match is not None
    assert result.probable_match.ip == "10.0.0.2"


def test_diff_snapshots_multiple_offline_no_probable_match() -> None:
    baseline = ScanSnapshot(
        interface="eth0",
        hosts=[
            _host("10.0.0.1", "aa:bb:cc:dd:ee:01"),
            _host("10.0.0.2", "aa:bb:cc:dd:ee:02"),
        ],
    )
    after = ScanSnapshot(interface="eth0", hosts=[])

    result = diff_snapshots(baseline, after)

    assert result.offline_count == 2
    assert result.probable_match is None


def test_confirm_reappearance() -> None:
    offline = [_host("10.0.0.2", "aa:bb:cc:dd:ee:02")]
    verify = ScanSnapshot(
        interface="eth0",
        hosts=[
            _host("10.0.0.1", "aa:bb:cc:dd:ee:01"),
            _host("10.0.0.2", "aa:bb:cc:dd:ee:02"),
        ],
    )

    confirmed = confirm_reappearance(offline, verify)

    assert len(confirmed) == 1
    assert confirmed[0].mac == "aa:bb:cc:dd:ee:02"
