"""Network port scan and DNS diagnostics."""

from ndp.scan.dns import (
    GatewayCheckResult,
    NetworkDiagnosticsResult,
    check_dns_server,
    check_gateway,
    resolve_hostname,
    run_network_diagnostics,
)
from ndp.scan.ports import PortScanResult, parse_custom_ports, scan_ports
from ndp.scan.profiles import profiles_catalog

__all__ = [
    "GatewayCheckResult",
    "NetworkDiagnosticsResult",
    "PortScanResult",
    "check_dns_server",
    "check_gateway",
    "parse_custom_ports",
    "profiles_catalog",
    "resolve_hostname",
    "run_network_diagnostics",
    "scan_ports",
]
