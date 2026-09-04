"""ICMP ping collector."""

from __future__ import annotations

import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from ndp.core.ping_state import PingResult

_PACKET_LOSS_RE = re.compile(r"(\d+(?:\.\d+)?)%\s+packet loss")
_RTT_AVG_RE = re.compile(
    r"(?:rtt min/avg/max/(?:mdev|stddev) = [\d.]+/)([\d.]+)/",
    re.IGNORECASE,
)


def ping_host(
    host: str,
    *,
    count: int = 2,
    timeout_seconds: float = 2.0,
    interface: str | None = None,
    packet_size: int = 56,
) -> PingResult:
    if not shutil.which("ping"):
        return PingResult(
            host=host,
            reachable=False,
            packets_sent=0,
            packets_received=0,
            packet_loss_pct=100.0,
            rtt_ms=None,
            message="ping command not found",
        )

    wait_seconds = max(1, int(timeout_seconds))
    command = [
        "ping",
        "-c",
        str(max(1, count)),
        "-W",
        str(wait_seconds),
        "-s",
        str(max(0, int(packet_size))),
    ]
    if interface:
        command.extend(["-I", interface])
    command.append(host)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(timeout_seconds * max(1, count) + 2.0, 5.0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PingResult(
            host=host,
            reachable=False,
            packets_sent=count,
            packets_received=0,
            packet_loss_pct=100.0,
            rtt_ms=None,
            message="timeout",
        )

    output = f"{completed.stdout}\n{completed.stderr}"
    return _parse_ping_output(host, count, output, completed.returncode)


def _parse_ping_output(host: str, count: int, output: str, returncode: int) -> PingResult:
    loss_match = _PACKET_LOSS_RE.search(output)
    packet_loss = float(loss_match.group(1)) if loss_match else 100.0
    rtt_match = _RTT_AVG_RE.search(output)
    rtt_ms = float(rtt_match.group(1)) if rtt_match else None

    received = int(round(count * (1.0 - packet_loss / 100.0)))
    reachable = packet_loss < 100.0 and returncode == 0

    if "Name or service not known" in output:
        message = "unknown host"
        reachable = False
    elif reachable:
        message = "ok"
    elif packet_loss >= 100.0:
        message = "unreachable"
    else:
        message = f"loss {packet_loss:.0f}%"

    return PingResult(
        host=host,
        reachable=reachable,
        packets_sent=count,
        packets_received=received,
        packet_loss_pct=packet_loss,
        rtt_ms=rtt_ms,
        message=message,
    )


def ping_mtu_probe(
    host: str,
    *,
    payload_size: int,
    interface: str | None = None,
    timeout_seconds: float = 2.0,
) -> PingResult:
    """Single ping with DF (do not fragment) for MTU discovery."""
    if not shutil.which("ping"):
        return PingResult(
            host=host,
            reachable=False,
            packets_sent=0,
            packets_received=0,
            packet_loss_pct=100.0,
            rtt_ms=None,
            message="ping command not found",
        )

    wait_seconds = max(1, int(timeout_seconds))
    command = [
        "ping",
        "-c",
        "1",
        "-W",
        str(wait_seconds),
        "-M",
        "do",
        "-s",
        str(max(0, int(payload_size))),
    ]
    if interface:
        command.extend(["-I", interface])
    command.append(host)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(timeout_seconds + 2.0, 5.0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PingResult(
            host=host,
            reachable=False,
            packets_sent=1,
            packets_received=0,
            packet_loss_pct=100.0,
            rtt_ms=None,
            message="timeout",
        )

    output = f"{completed.stdout}\n{completed.stderr}"
    result = _parse_ping_output(host, 1, output, completed.returncode)
    if result.reachable:
        return result

    lowered = output.lower()
    if "message too long" in lowered or "frag needed" in lowered or "packet too big" in lowered:
        result.message = "troppo grande (DF)"
    elif "100% packet loss" in lowered or not result.reachable:
        result.message = "non raggiungibile"
    return result


def ping_hosts_parallel(
    hosts: list[str],
    *,
    count: int = 2,
    timeout_seconds: float = 2.0,
    max_workers: int = 3,
    interface: str | None = None,
    packet_size: int = 56,
) -> dict[str, PingResult]:
    """Ping up to max_workers hosts concurrently."""
    unique_hosts = list(dict.fromkeys(host.strip() for host in hosts if host.strip()))
    if not unique_hosts:
        return {}

    workers = min(max(1, max_workers), len(unique_hosts), 8)
    results: dict[str, PingResult] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                ping_host,
                host,
                count=count,
                timeout_seconds=timeout_seconds,
                interface=interface,
                packet_size=packet_size,
            ): host
            for host in unique_hosts
        }
        for future in as_completed(futures):
            host = futures[future]
            results[host] = future.result()

    return results
