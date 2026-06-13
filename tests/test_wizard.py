from ndp.discovery.host import DiscoveredHost, ScanSnapshot
from ndp.discovery.wizard import DiscoveryConfig, UpDownWizard


def test_updown_wizard_full_flow(monkeypatch) -> None:
    baseline = ScanSnapshot(
        interface="eth0",
        hosts=[
            DiscoveredHost(ip="10.0.0.1", mac="aa:bb:cc:dd:ee:01"),
            DiscoveredHost(ip="10.0.0.2", mac="aa:bb:cc:dd:ee:02"),
        ],
    )
    after = ScanSnapshot(
        interface="eth0",
        hosts=[DiscoveredHost(ip="10.0.0.1", mac="aa:bb:cc:dd:ee:01")],
    )
    verify = ScanSnapshot(
        interface="eth0",
        hosts=[
            DiscoveredHost(ip="10.0.0.1", mac="aa:bb:cc:dd:ee:01"),
            DiscoveredHost(ip="10.0.0.2", mac="aa:bb:cc:dd:ee:02"),
        ],
    )

    scans = iter([baseline, after, verify])

    def fake_scan(_interface: str) -> ScanSnapshot:
        return next(scans)

    prompts = iter(["", ""])
    outputs: list[str] = []

    monkeypatch.setattr("ndp.discovery.wizard.scan_hosts", fake_scan)
    monkeypatch.setattr("ndp.discovery.wizard.flush_arp_cache", lambda _iface: True)
    monkeypatch.setattr("ndp.discovery.wizard.time.sleep", lambda _s: None)

    wizard = UpDownWizard(
        interface="eth0",
        config=DiscoveryConfig(
            disconnect_wait_seconds=2,
            flush_arp_before_second_scan=True,
            verify_replug=True,
            countdown_step_seconds=0,
        ),
        prompt=lambda _msg: next(prompts),
        output=outputs.append,
        sleep=lambda _s: None,
    )

    result = wizard.run()

    assert result.diff.offline_count == 1
    assert result.diff.probable_match is not None
    assert result.diff.probable_match.ip == "10.0.0.2"
    assert len(result.confirmed_hosts) == 1
    assert any("Cache ARP svuotata" in line for line in outputs)
