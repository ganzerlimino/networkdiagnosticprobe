from pathlib import Path

from ndp.core.config_merge import append_missing_config_keys


def test_append_missing_keys_preserves_existing_text(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    default_path = tmp_path / "default.yaml"
    config_path.write_text(
        "interface: eth0\nui:\n  enabled: true\n# mio commento\n",
        encoding="utf-8",
    )
    default_path.write_text(
        """interface: eth0
# iface

ui:
  enabled: false
  # ui off
  font_size: 14
  # font
""",
        encoding="utf-8",
    )

    changed = append_missing_config_keys(config_path, default_path)
    assert changed is True
    text = config_path.read_text(encoding="utf-8")
    assert "# mio commento" in text
    assert "font_size: 14" in text
    assert "# font" in text
    assert "interface: eth0" in text.splitlines()[0]


def test_append_missing_noop_when_complete(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    default_path = tmp_path / "default.yaml"
    content = "interface: eth0\n"
    config_path.write_text(content, encoding="utf-8")
    default_path.write_text(content, encoding="utf-8")
    assert append_missing_config_keys(config_path, default_path) is False
