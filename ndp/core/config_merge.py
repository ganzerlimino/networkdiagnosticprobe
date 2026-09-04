"""Merge missing config keys from the commented default template."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_SECTION_RE = re.compile(r"^([A-Za-z0-9_]+):\s*$")
_INDENTED_KEY_RE = re.compile(r"^(\s+)([A-Za-z0-9_]+):\s*(.*)$")


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        keys.add(path)
        if isinstance(value, dict):
            keys.update(_flatten_keys(value, path))
    return keys


def _extract_blocks(default_text: str, missing: set[str]) -> list[str]:
    """Return YAML fragments (value + comment lines) for missing dotted keys."""
    lines = default_text.splitlines()
    blocks: list[str] = []
    current_section: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        section_match = _SECTION_RE.match(line)
        if section_match and not line.startswith(" "):
            current_section = section_match.group(1)
            i += 1
            continue

        key_match = _INDENTED_KEY_RE.match(line)
        if key_match and current_section is not None:
            indent, key, _value = key_match.groups()
            dotted = f"{current_section}.{key}"
            if dotted in missing:
                block = [line]
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith(f"{indent}#"):
                        block.append(nxt)
                        i += 1
                        continue
                    if _INDENTED_KEY_RE.match(nxt) and len(nxt) - len(nxt.lstrip()) == len(indent):
                        break
                    if _SECTION_RE.match(nxt) and not nxt.startswith(" "):
                        break
                    break
                blocks.append("\n".join(block))
                continue
        i += 1
    return blocks


def append_missing_config_keys(config_path: Path, default_path: Path) -> bool:
    """Append missing keys (with comments) without rewriting existing content."""
    if not config_path.is_file() or not default_path.is_file():
        return False

    user_text = config_path.read_text(encoding="utf-8")
    default_text = default_path.read_text(encoding="utf-8")
    user_data = yaml.safe_load(user_text) or {}
    default_data = yaml.safe_load(default_text) or {}
    if not isinstance(user_data, dict) or not isinstance(default_data, dict):
        return False

    missing = _flatten_keys(default_data) - _flatten_keys(user_data)
    if not missing:
        return False

    blocks = _extract_blocks(default_text, missing)
    if not blocks:
        return False

    suffix = "\n\n# --- chiavi aggiunte da install (vedi config.yaml.example) ---\n"
    suffix += "\n".join(blocks)
    suffix += "\n"
    config_path.write_text(user_text.rstrip() + suffix, encoding="utf-8")
    return True
