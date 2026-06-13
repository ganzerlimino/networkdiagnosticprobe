from ndp.discovery.arp import _parse_arp_scan_output


def test_parse_arp_scan_output() -> None:
    sample = (FIXTURES / "arp_scan_sample.txt").read_text(encoding="utf-8")
    hosts = _parse_arp_scan_output(sample, "eth0")

    assert len(hosts) == 3
    assert hosts[0].ip == "192.168.1.1"
    assert hosts[0].mac == "aa:bb:cc:dd:ee:01"
    assert hosts[0].vendor == "Router Corp"
    assert hosts[1].ip == "192.168.1.45"
    assert hosts[2].mac == "cc:dd:ee:ff:00:03"


FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"
