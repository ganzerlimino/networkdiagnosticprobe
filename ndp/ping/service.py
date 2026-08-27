"""Ping target list, adhoc host, and suite runner."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from ndp.core.collectors.ping import ping_host, ping_hosts_parallel
from ndp.core.config import NdpConfig
from ndp.core.ping_state import PingSuiteState, PingTarget, PingTargetResult

logger = logging.getLogger(__name__)

DEFAULT_ADHOC_PATH = Path("/var/lib/ndp/ping_adhoc.host")
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9._:-]+$")
_BUILTIN_TARGETS = (
    ("Google DNS", "8.8.8.8"),
    ("Cloudflare", "1.1.1.1"),
)


def validate_host(host: str) -> str:
    cleaned = host.strip()
    if not cleaned or len(cleaned) > 253:
        raise ValueError("host non valido")
    if cleaned in {"gateway", "@gateway"}:
        return cleaned
    if not _HOSTNAME_RE.match(cleaned):
        raise ValueError(f"host non valido: {host}")
    return cleaned


def read_adhoc_host(path: Path | None = None) -> str | None:
    file_path = path or DEFAULT_ADHOC_PATH
    if not file_path.is_file():
        return None
    host = file_path.read_text(encoding="utf-8").strip()
    return host or None


def write_adhoc_host(host: str | None, path: Path | None = None) -> None:
    file_path = path or DEFAULT_ADHOC_PATH
    if host is None or host == "":
        if file_path.is_file():
            file_path.unlink()
        return
    validated = validate_host(host)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(validated + "\n", encoding="utf-8")


def resolve_host(raw_host: str, gateway: str | None) -> str | None:
    if raw_host in {"gateway", "@gateway"}:
        return gateway
    return raw_host


def build_ping_targets(
    config: NdpConfig,
    *,
    gateway: str | None = None,
    adhoc_path: Path | None = None,
) -> list[PingTarget]:
    targets: list[PingTarget] = [
        PingTarget(label=label, host=host, kind="builtin") for label, host in _BUILTIN_TARGETS
    ]

    for entry in config.ping_custom_targets[:4]:
        label = str(entry.get("label", entry.get("host", "Custom")))[:24]
        raw_host = str(entry.get("host", "")).strip()
        if not raw_host:
            continue
        resolved = resolve_host(raw_host, gateway)
        if not resolved:
            continue
        targets.append(PingTarget(label=label, host=resolved, kind="custom"))

    adhoc = read_adhoc_host(adhoc_path)
    if adhoc:
        targets.append(PingTarget(label="Adhoc", host=adhoc, kind="adhoc"))

    return targets


def run_ping_suite(
    config: NdpConfig,
    *,
    gateway: str | None = None,
    adhoc_path: Path | None = None,
    extra_hosts: list[str] | None = None,
) -> PingSuiteState:
    state = PingSuiteState()
    state.adhoc_host = read_adhoc_host(adhoc_path)
    state.running = True
    state.message = "Ping in corso..."

    targets = build_ping_targets(config, gateway=gateway, adhoc_path=adhoc_path)
    if extra_hosts:
        for index, raw_host in enumerate(extra_hosts[:3]):
            host = raw_host.strip()
            if not host:
                continue
            resolved = resolve_host(host, gateway) or host
            targets.append(
                PingTarget(label=f"Live{index + 1}", host=resolved, kind="live")
            )

    host_to_target = {target.host: target for target in targets}
    parallel_results = ping_hosts_parallel(
        list(host_to_target.keys()),
        count=config.ping_count,
        timeout_seconds=config.ping_timeout_seconds,
        max_workers=3,
    )

    results: list[PingTargetResult] = []
    for target in targets:
        result = parallel_results.get(target.host)
        if result is None:
            continue
        logger.info("Ping %s (%s) -> %s", target.label, target.host, result.message)
        results.append(
            PingTargetResult(
                label=target.label,
                host=target.host,
                kind=target.kind,
                result=result,
            )
        )

    state.results = results
    state.running = False
    state.last_run_at = datetime.now(timezone.utc)
    state.message = "Completato"
    return state


def run_ping_hosts(
    config: NdpConfig,
    hosts: list[str],
    *,
    gateway: str | None = None,
) -> PingSuiteState:
    """Ping 1–3 arbitrary hosts concurrently."""
    state = PingSuiteState()
    state.running = True
    state.message = "Ping in corso..."

    targets: list[PingTarget] = []
    for index, raw_host in enumerate(hosts[:3]):
        host = raw_host.strip()
        if not host:
            continue
        resolved = resolve_host(host, gateway) or host
        targets.append(PingTarget(label=f"Host{index + 1}", host=resolved, kind="live"))

    parallel_results = ping_hosts_parallel(
        [target.host for target in targets],
        count=config.ping_count,
        timeout_seconds=config.ping_timeout_seconds,
        max_workers=3,
    )

    results: list[PingTargetResult] = []
    for target in targets:
        result = parallel_results.get(target.host)
        if result is None:
            continue
        results.append(
            PingTargetResult(
                label=target.label,
                host=target.host,
                kind=target.kind,
                result=result,
            )
        )

    state.results = results
    state.running = False
    state.last_run_at = datetime.now(timezone.utc)
    state.message = "Completato"
    return state
