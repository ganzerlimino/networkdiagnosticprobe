"""FastAPI server for remote configuration and probe status."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

from ndp.core.config import DEFAULT_CONFIG_PATH, NdpConfig
from ndp.core.config_io import load_config_mapping, load_config_text, save_config_mapping, save_config_text
from ndp.core.ping_state import PingSuiteState
from ndp.core.state import ProbeState
from ndp.discovery.wizard import UpDownResult
from ndp.mtu.discover import MtuDiscoveryManager
from ndp.ping.live import LivePingManager
from ndp.ping.service import run_ping_hosts, run_ping_suite, validate_host
from ndp.scan.dns import NetworkDiagnosticsResult, resolve_hostname, run_network_diagnostics
from ndp.scan.ports import PortScanResult, parse_custom_ports, scan_ports
from ndp.scan.profiles import profiles_catalog
from ndp.ui.discovery_session import DiscoveryUISession
from ndp.web.config_schema import (
    coerce_field_value,
    config_sections,
    get_nested_value,
    set_nested_value,
)
from ndp.web.api_models import (
    AdhocPayload,
    ConfigPayload,
    ConfigValuesPayload,
    DnsLookupPayload,
    LivePingPayload,
    MtuDiscoverPayload,
    NetworkCheckPayload,
    PingRunPayload,
    PortScanPayload,
    ServiceRestartPayload,
)
from ndp.web.report import build_report

logger = logging.getLogger(__name__)

_DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


def create_app(
    config: NdpConfig,
    config_path: Path,
    get_state: Callable[[], ProbeState],
    *,
    on_ping_complete: Callable[[PingSuiteState], None] | None = None,
    on_adhoc_changed: Callable[[], None] | None = None,
) -> object:
    from fastapi import Body, FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, StreamingResponse

    app = FastAPI(title="NDP", version="0.13")
    discovery = DiscoveryUISession(config)
    live_pings = LivePingManager()
    mtu_discovery = MtuDiscoveryManager()
    discovery_result: UpDownResult | None = None
    last_scan_result: PortScanResult | None = None
    last_network_diag: NetworkDiagnosticsResult | None = None

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _DASHBOARD_HTML

    @app.get("/api/status")
    def api_status() -> dict[str, object]:
        return get_state().to_dict()

    @app.get("/api/config")
    def api_get_config() -> dict[str, str]:
        return {"yaml": load_config_text(config_path)}

    @app.put("/api/config")
    def api_put_config(body: ConfigPayload = Body()) -> dict[str, object]:
        try:
            save_config_text(config_path, body.yaml)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info("Configuration updated via web UI at %s", config_path)
        return {"ok": True, "path": str(config_path)}

    @app.get("/api/config/schema")
    def api_config_schema() -> dict[str, object]:
        return {"sections": config_sections()}

    @app.get("/api/config/values")
    def api_config_values() -> dict[str, object]:
        data = load_config_mapping(config_path)
        values: dict[str, object] = {}
        for section in config_sections():
            for field in section["fields"]:  # type: ignore[index]
                key = str(field["key"])
                values[key] = get_nested_value(data, key)
        return {"values": values, "yaml": load_config_text(config_path)}

    @app.put("/api/config/values")
    def api_put_config_values(body: ConfigValuesPayload = Body()) -> dict[str, object]:
        data = load_config_mapping(config_path)
        try:
            for section in config_sections():
                for field in section["fields"]:  # type: ignore[index]
                    key = str(field["key"])
                    if key not in body.values:
                        continue
                    set_nested_value(
                        data,
                        key,
                        coerce_field_value(str(field["type"]), body.values[key]),
                    )
            password = get_nested_value(data, "wifi_hotspot.password")
            if password is not None:
                cleaned = str(password).strip()
                if cleaned and len(cleaned) < 8:
                    raise ValueError("Password hotspot: minimo 8 caratteri (o lascia vuoto per rete aperta)")
            save_config_mapping(config_path, data)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "path": str(config_path), "restart_services": ["ndp", "ndp-hotspot"]}

    @app.post("/api/services/restart")
    def api_services_restart(body: ServiceRestartPayload = Body()) -> dict[str, object]:
        import subprocess

        for service in body.services:
            subprocess.run(["systemctl", "restart", service], check=False)
        return {"ok": True, "services": body.services}

    @app.post("/api/hotspot/restart")
    def api_hotspot_restart() -> dict[str, object]:
        import subprocess

        from ndp.core.config import load_config
        from ndp.network.hotspot import ensure_hotspot, stop_hotspot

        fresh = load_config(config_path)
        stop_hotspot(fresh)
        subprocess.run(["rfkill", "unblock", "all"], check=False)
        status = ensure_hotspot(fresh)
        return status.to_dict()

    @app.get("/api/version")
    def api_version() -> dict[str, str]:
        from ndp import __version__

        return {"version": __version__, "interface": config.interface}

    @app.get("/api/report")
    def api_report(section: str = "all") -> dict[str, str]:
        from ndp import __version__

        return build_report(
            get_state(),
            section=section,
            discovery_result=discovery_result,
            scan_result=last_scan_result,
            network_diag=last_network_diag,
            version=__version__,
        )

    @app.get("/api/ping")
    def api_ping_status() -> dict[str, object]:
        return get_state().ping.to_dict()

    @app.post("/api/ping/run")
    def api_ping_run(body: PingRunPayload | None = Body(default=None)) -> dict[str, object]:
        state = get_state()
        hosts = None
        if body and body.hosts:
            try:
                hosts = [validate_host(host) for host in body.hosts if str(host).strip()]
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if hosts:
            suite = run_ping_hosts(config, hosts, gateway=state.ip.gateway)
        else:
            suite = run_ping_suite(
                config,
                gateway=state.ip.gateway,
                adhoc_path=Path(config.ping_adhoc_path),
            )
        if on_ping_complete is not None:
            on_ping_complete(suite)
        return suite.to_dict()

    @app.post("/api/ping/live/start")
    def api_ping_live_start(body: LivePingPayload = Body()) -> dict[str, object]:
        try:
            hosts = [validate_host(host) for host in body.hosts]
            session = live_pings.create(
                hosts,
                interval_seconds=body.interval,
                max_samples=body.max_samples,
                interface=config.interface,
                packet_size=config.ping_packet_size,
                timeout_seconds=config.ping_timeout_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"session_id": session.session_id, "hosts": session.hosts}

    @app.get("/api/ping/live/{session_id}/events")
    def api_ping_live_events(session_id: str) -> StreamingResponse:
        session = live_pings.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="sessione non trovata")

        def generate() -> Iterator[str]:
            for event in session.iter_events():
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") == "done":
                    break

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/ping/live/{session_id}/stop")
    def api_ping_live_stop(session_id: str) -> dict[str, object]:
        if not live_pings.stop(session_id):
            raise HTTPException(status_code=404, detail="sessione non trovata")
        return {"ok": True}

    @app.put("/api/ping/adhoc")
    def api_ping_set_adhoc(body: AdhocPayload = Body()) -> dict[str, object]:
        from ndp.ping.service import validate_host, write_adhoc_host

        try:
            host = validate_host(body.host)
            write_adhoc_host(host, Path(config.ping_adhoc_path))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if on_adhoc_changed is not None:
            on_adhoc_changed()
        return {"ok": True, "host": host}

    @app.delete("/api/ping/adhoc")
    def api_ping_clear_adhoc() -> dict[str, object]:
        from ndp.ping.service import write_adhoc_host

        write_adhoc_host(None, Path(config.ping_adhoc_path))
        if on_adhoc_changed is not None:
            on_adhoc_changed()
        return {"ok": True}

    @app.get("/api/discover/scan")
    def api_discover_scan() -> dict[str, object]:
        from ndp.discovery.arp import scan_hosts

        try:
            snapshot = scan_hosts(config.interface)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.get("/api/discover/protocols")
    def api_discover_protocols() -> dict[str, object]:
        from ndp.discovery.protocols import protocol_catalog

        return protocol_catalog()

    @app.get("/api/discover/services")
    def api_discover_services() -> dict[str, object]:
        from ndp.discovery.ethertype_probe import probe_l2_snapshot
        from ndp.discovery.mdns import discover_mdns_snapshot
        from ndp.discovery.ssdp import discover_ssdp_snapshot

        return {
            "interface": config.interface,
            "mdns": discover_mdns_snapshot(config.interface),
            "ssdp": discover_ssdp_snapshot(config.interface),
            "l2_probes": probe_l2_snapshot(config.interface),
        }

    @app.get("/api/discover/updown")
    def api_discover_updown_status() -> dict[str, object]:
        nonlocal discovery_result
        payload = discovery.to_api_dict()
        if payload.get("phase") == "done" and discovery.result is not None:
            discovery_result = discovery.result
        return payload

    @app.post("/api/discover/updown/start")
    def api_discover_updown_start() -> dict[str, object]:
        nonlocal discovery_result
        if discovery.is_idle():
            discovery_result = None
            discovery.start()
        return discovery.to_api_dict()

    @app.post("/api/discover/updown/continue")
    def api_discover_updown_continue() -> dict[str, object]:
        discovery.on_select()
        return discovery.to_api_dict()

    @app.post("/api/discover/updown/skip")
    def api_discover_updown_skip() -> dict[str, object]:
        discovery.on_next_skip()
        return discovery.to_api_dict()

    @app.post("/api/discover/updown/cancel")
    def api_discover_updown_cancel() -> dict[str, object]:
        discovery.cancel()
        return discovery.to_api_dict()

    @app.post("/api/discover/updown/reset")
    def api_discover_updown_reset() -> dict[str, object]:
        nonlocal discovery_result
        discovery.reset()
        discovery_result = None
        return discovery.to_api_dict()

    @app.get("/api/hotspot/status")
    def api_hotspot_status() -> dict[str, object]:
        from ndp.network.hotspot import get_status

        return get_status(config).to_dict()

    @app.get("/api/scan/profiles")
    def api_scan_profiles() -> dict[str, object]:
        return profiles_catalog()

    @app.post("/api/scan/ports")
    def api_scan_ports(body: PortScanPayload = Body()) -> dict[str, object]:
        nonlocal last_scan_result
        try:
            validate_host(body.host)
            custom_ports = None
            if body.profile == "custom":
                custom_ports = parse_custom_ports(body.ports)
                if not custom_ports:
                    raise ValueError("specificare almeno una porta custom")
            result = scan_ports(
                body.host,
                body.profile,
                custom_ports=custom_ports,
                timeout_seconds=body.timeout_ms / 1000.0,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        last_scan_result = result
        return result.to_dict()

    @app.get("/api/network/dns")
    def api_dns_lookup(hostname: str) -> dict[str, object]:
        if not hostname.strip():
            raise HTTPException(status_code=400, detail="hostname richiesto")
        return resolve_hostname(hostname).to_dict()

    @app.post("/api/network/check")
    def api_network_check(body: NetworkCheckPayload | None = Body(default=None)) -> dict[str, object]:
        nonlocal last_network_diag
        state = get_state()
        hostnames = []
        if body and body.hostnames:
            hostnames = [name.strip() for name in body.hostnames if name.strip()]
        else:
            hostnames = ["gateway"]
        if body is None or body.include_gateway:
            if state.ip.gateway and "gateway" not in hostnames:
                hostnames.append(state.ip.gateway)

        resolved_names: list[str] = []
        for name in hostnames:
            if name == "gateway" and state.ip.gateway:
                resolved_names.append(state.ip.gateway)
            else:
                resolved_names.append(name)

        diag = run_network_diagnostics(
            hostnames=resolved_names,
            dns_servers=state.ip.dns_servers,
            gateway=state.ip.gateway if (body is None or body.include_gateway) else None,
        )
        last_network_diag = diag
        return diag.to_dict()

    @app.post("/api/mtu/discover/start")
    def api_mtu_discover_start(body: MtuDiscoverPayload = Body()) -> dict[str, object]:
        try:
            host = validate_host(body.host)
            session = mtu_discovery.create(
                host,
                interface=config.interface,
                start_mtu=body.start_mtu,
                min_mtu=body.min_mtu,
                timeout_seconds=config.ping_timeout_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"session_id": session.session_id, "host": host, "interface": config.interface}

    @app.get("/api/mtu/discover/{session_id}/events")
    def api_mtu_discover_events(session_id: str) -> StreamingResponse:
        session = mtu_discovery.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="sessione non trovata")

        def generate() -> Iterator[str]:
            for event in session.iter_events():
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") in {"done", "stopped"}:
                    break

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/mtu/discover/{session_id}/stop")
    def api_mtu_discover_stop(session_id: str) -> dict[str, object]:
        if not mtu_discovery.stop(session_id):
            raise HTTPException(status_code=404, detail="sessione non trovata")
        return {"ok": True}

    @app.on_event("shutdown")
    def _shutdown_live_ping() -> None:
        live_pings.stop_all()
        mtu_discovery.stop_all()

    return app


def start_web_server(
    config: NdpConfig,
    config_path: Path,
    get_state: Callable[[], ProbeState],
    *,
    on_ping_complete: Callable[[PingSuiteState], None] | None = None,
    on_adhoc_changed: Callable[[], None] | None = None,
) -> threading.Thread:
    import uvicorn

    app = create_app(
        config,
        config_path,
        get_state,
        on_ping_complete=on_ping_complete,
        on_adhoc_changed=on_adhoc_changed,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.web_host,
            port=config.web_port,
            log_level="warning",
        )
    )

    def _run() -> None:
        logger.info("Web UI on http://%s:%s", config.web_host, config.web_port)
        server.run()

    thread = threading.Thread(target=_run, daemon=True, name="ndp-web")
    thread.start()
    return thread


def resolve_config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    return DEFAULT_CONFIG_PATH
