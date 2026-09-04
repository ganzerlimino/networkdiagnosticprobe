"""Snapshot comparison for Up/Down discovery."""

from __future__ import annotations

from dataclasses import dataclass

from ndp.discovery.host import DiscoveredHost, ScanSnapshot


@dataclass
class ScanDiff:
    offline_hosts: list[DiscoveredHost]
    online_hosts: list[DiscoveredHost]
    unchanged_hosts: list[DiscoveredHost]
    probable_match: DiscoveredHost | None = None

    @property
    def offline_count(self) -> int:
        return len(self.offline_hosts)

    def to_dict(self) -> dict[str, object]:
        return {
            "offline_count": self.offline_count,
            "online_count": len(self.online_hosts),
            "unchanged_count": len(self.unchanged_hosts),
            "probable_match": (
                self.probable_match.to_dict() if self.probable_match else None
            ),
            "offline_hosts": [host.to_dict() for host in self.offline_hosts],
            "online_hosts": [host.to_dict() for host in self.online_hosts],
        }


def diff_snapshots(baseline: ScanSnapshot, current: ScanSnapshot) -> ScanDiff:
    baseline_by_mac = baseline.by_mac()
    current_by_mac = current.by_mac()

    baseline_macs = set(baseline_by_mac)
    current_macs = set(current_by_mac)

    offline_macs = baseline_macs - current_macs
    online_macs = current_macs - baseline_macs
    unchanged_macs = baseline_macs & current_macs

    offline_hosts = [baseline_by_mac[mac] for mac in sorted(offline_macs)]
    online_hosts = [current_by_mac[mac] for mac in sorted(online_macs)]
    unchanged_hosts = [baseline_by_mac[mac] for mac in sorted(unchanged_macs)]

    probable_match = offline_hosts[0] if len(offline_hosts) == 1 else None

    return ScanDiff(
        offline_hosts=offline_hosts,
        online_hosts=online_hosts,
        unchanged_hosts=unchanged_hosts,
        probable_match=probable_match,
    )


def confirm_reappearance(
    offline_hosts: list[DiscoveredHost],
    verify_snapshot: ScanSnapshot,
) -> list[DiscoveredHost]:
    verify_macs = verify_snapshot.macs()
    return [host for host in offline_hosts if host.mac in verify_macs]
