from pathlib import Path

import pytest
import yaml

from ndp.core.config_io import load_config_text, save_config_text
from ndp.discovery.console import compact_diff_lines
from ndp.discovery.diff import ScanDiff
from ndp.discovery.host import DiscoveredHost


def test_save_and_load_config_text(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    text = "interface: eth1\nui:\n  enabled: true\n"
    save_config_text(path, text)
    assert load_config_text(path) == text
    data = yaml.safe_load(path.read_text())
    assert data["interface"] == "eth1"


def test_save_config_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with pytest.raises(ValueError):
        save_config_text(path, "not: [valid")


def test_compact_diff_lines_probable_match() -> None:
    host = DiscoveredHost(ip="10.0.0.2", mac="aa:bb:cc:dd:ee:02", vendor="Acme")
    diff = ScanDiff(
        offline_hosts=[host],
        online_hosts=[],
        unchanged_hosts=[],
        probable_match=host,
    )
    lines = compact_diff_lines(diff)
    assert lines[0] == "MATCH:"
    assert "10.0.0.2" in lines[1]
