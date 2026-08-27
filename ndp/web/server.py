"""FastAPI server for remote configuration and probe status."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

from ndp.core.config import DEFAULT_CONFIG_PATH, NdpConfig
from ndp.core.config_io import load_config_text, save_config_text
from ndp.core.ping_state import PingSuiteState
from ndp.core.state import ProbeState
from ndp.discovery.wizard import UpDownResult
from ndp.ping.live import LivePingManager
from ndp.ping.service import run_ping_hosts, run_ping_suite, validate_host
from ndp.scan.dns import NetworkDiagnosticsResult, resolve_hostname, run_network_diagnostics
from ndp.scan.ports import PortScanResult, parse_custom_ports, scan_ports
from ndp.scan.profiles import profiles_catalog
from ndp.ui.discovery_session import DiscoveryUISession
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
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, StreamingResponse
    from pydantic import BaseModel, Field

    class ConfigPayload(BaseModel):
        yaml: str

    class AdhocPayload(BaseModel):
        host: str

    class PingRunPayload(BaseModel):
        hosts: list[str] | None = None

    class LivePingPayload(BaseModel):
        hosts: list[str] = Field(..., min_length=1, max_length=3)
        interval: float = 1.0
        max_samples: int = 60

    class PortScanPayload(BaseModel):
        host: str
        profile: str = Field(..., pattern="^(standard|industrial|custom)$")
        ports: str | list[int] | None = None
        timeout_ms: int = Field(default=1500, ge=300, le=5000)

    class DnsLookupPayload(BaseModel):
        hostname: str

    class NetworkCheckPayload(BaseModel):
        hostnames: list[str] = Field(default_factory=list)
        include_gateway: bool = True

    app = FastAPI(title="NDP", version="0.9")
    discovery = DiscoveryUISession(config)
    live_pings = LivePingManager()
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
    def api_put_config(payload: ConfigPayload) -> dict[str, object]:
        try:
            save_config_text(config_path, payload.yaml)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info("Configuration updated via web UI at %s", config_path)
        return {"ok": True, "path": str(config_path)}

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
    def api_ping_run(payload: PingRunPayload | None = None) -> dict[str, object]:
        state = get_state()
        hosts = payload.hosts if payload and payload.hosts else None
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
    def api_ping_live_start(payload: LivePingPayload) -> dict[str, object]:
        try:
            session = live_pings.create(
                payload.hosts,
                interval_seconds=payload.interval,
                max_samples=payload.max_samples,
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
    def api_ping_set_adhoc(payload: AdhocPayload) -> dict[str, object]:
        from ndp.ping.service import validate_host, write_adhoc_host

        try:
            host = validate_host(payload.host)
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
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return snapshot.to_dict()

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

    @app.get("/api/scan/profiles")
    def api_scan_profiles() -> dict[str, object]:
        return profiles_catalog()

    @app.post("/api/scan/ports")
    def api_scan_ports(payload: PortScanPayload) -> dict[str, object]:
        nonlocal last_scan_result
        try:
            validate_host(payload.host)
            custom_ports = None
            if payload.profile == "custom":
                custom_ports = parse_custom_ports(payload.ports)
                if not custom_ports:
                    raise ValueError("specificare almeno una porta custom")
            result = scan_ports(
                payload.host,
                payload.profile,
                custom_ports=custom_ports,
                timeout_seconds=payload.timeout_ms / 1000.0,
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
    def api_network_check(payload: NetworkCheckPayload | None = None) -> dict[str, object]:
        nonlocal last_network_diag
        state = get_state()
        hostnames = []
        if payload and payload.hostnames:
            hostnames = [name.strip() for name in payload.hostnames if name.strip()]
        else:
            hostnames = ["gateway"]
        if payload is None or payload.include_gateway:
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
            gateway=state.ip.gateway if (payload is None or payload.include_gateway) else None,
        )
        last_network_diag = diag
        return diag.to_dict()

    @app.on_event("shutdown")
    def _shutdown_live_ping() -> None:
        live_pings.stop_all()

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
