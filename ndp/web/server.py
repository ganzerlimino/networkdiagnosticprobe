"""FastAPI server for remote configuration and probe status."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from ndp.core.config import DEFAULT_CONFIG_PATH, NdpConfig
from ndp.core.config_io import load_config_text, save_config_text
from ndp.core.ping_state import PingSuiteState
from ndp.core.state import ProbeState

logger = logging.getLogger(__name__)

_INDEX_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0c1220">
  <title>NDP</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0c1220;
      --card: #18243f;
      --text: #e8f0ff;
      --muted: #9eb0d0;
      --accent: #50c878;
      --danger: #ff8080;
      --border: #2a3a5c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 0 0 5rem;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 2;
      background: rgba(12, 18, 32, 0.95);
      border-bottom: 1px solid var(--border);
      padding: 0.9rem 1rem 0.7rem;
    }
    h1 { margin: 0; font-size: 1.15rem; }
    .sub { color: var(--muted); font-size: 0.85rem; margin-top: 0.2rem; }
    nav {
      display: flex;
      gap: 0.4rem;
      padding: 0.6rem 1rem;
      overflow-x: auto;
      border-bottom: 1px solid var(--border);
      background: var(--bg);
      position: sticky;
      top: 3.6rem;
      z-index: 2;
    }
    nav button {
      flex: 1;
      min-width: 5.5rem;
      border: 1px solid var(--border);
      background: var(--card);
      color: var(--text);
      border-radius: 999px;
      padding: 0.55rem 0.8rem;
      font-size: 0.9rem;
    }
    nav button.active {
      border-color: var(--accent);
      color: var(--accent);
    }
    main { padding: 1rem; }
    .panel { display: none; }
    .panel.active { display: block; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.9rem 1rem;
      margin-bottom: 0.8rem;
    }
    .card h2 {
      margin: 0 0 0.6rem;
      font-size: 0.95rem;
      color: var(--accent);
    }
    .row {
      display: flex;
      justify-content: space-between;
      gap: 0.8rem;
      padding: 0.35rem 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 0.92rem;
    }
    .row:last-child { border-bottom: 0; }
    .label { color: var(--muted); }
    .ok { color: var(--accent); }
    .bad { color: var(--danger); }
    .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.8rem; }
    button.primary, button.secondary {
      border: 0;
      border-radius: 10px;
      padding: 0.75rem 1rem;
      font-size: 0.95rem;
      font-weight: 600;
    }
    button.primary { background: var(--accent); color: #062010; flex: 1; }
    button.secondary {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
    }
    input, textarea {
      width: 100%;
      background: #0f1728;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.7rem 0.8rem;
      font-size: 1rem;
    }
    textarea {
      min-height: 18rem;
      font-family: ui-monospace, monospace;
      font-size: 0.85rem;
    }
    #msg { min-height: 1.2rem; font-size: 0.9rem; margin-top: 0.5rem; }
    .hosts { font-size: 0.88rem; }
    .hosts div { padding: 0.25rem 0; }
  </style>
</head>
<body>
  <header>
    <h1>Network Diagnostic Probe</h1>
    <div class="sub" id="version">Caricamento...</div>
  </header>
  <nav>
    <button class="active" data-panel="status">Stato</button>
    <button data-panel="ping">Ping</button>
    <button data-panel="discover">Discover</button>
    <button data-panel="config">Config</button>
  </nav>
  <main>
    <section class="panel active" id="panel-status">
      <div class="card">
        <h2>Link</h2>
        <div id="status-link"></div>
      </div>
      <div class="card">
        <h2>Rete</h2>
        <div id="status-network"></div>
      </div>
      <div class="card">
        <h2>Switch / LLDP</h2>
        <div id="status-switch"></div>
      </div>
      <div class="card">
        <h2>Sistema</h2>
        <div id="status-system"></div>
      </div>
    </section>

    <section class="panel" id="panel-ping">
      <div class="card">
        <h2>Ping suite</h2>
        <div id="ping-results" class="hosts">Caricamento...</div>
        <div class="actions">
          <button class="primary" id="ping-run">Esegui ping</button>
        </div>
      </div>
      <div class="card">
        <h2>Host ad-hoc</h2>
        <p class="sub">Un host temporaneo oltre a 8.8.8.8, 1.1.1.1 e i target in config.</p>
        <input id="adhoc-host" placeholder="es. 192.168.1.1">
        <div class="actions">
          <button class="secondary" id="adhoc-save">Salva host</button>
          <button class="secondary" id="adhoc-clear">Rimuovi</button>
        </div>
        <p id="ping-msg"></p>
      </div>
    </section>

    <section class="panel" id="panel-discover">
      <div class="card">
        <h2>Scansione ARP</h2>
        <p class="sub">Trova i dispositivi sulla subnet. Per il wizard Up/Down completo usa <code>ndp discover updown</code> da SSH.</p>
        <div class="actions">
          <button class="primary" id="discover-scan">Scansiona rete</button>
        </div>
        <div id="discover-results" class="hosts"></div>
      </div>
    </section>

    <section class="panel" id="panel-config">
      <div class="card">
        <h2>config.yaml</h2>
        <p class="sub">Dopo il salvataggio riavvia: <code>sudo systemctl restart ndp</code></p>
        <textarea id="yaml"></textarea>
        <div class="actions">
          <button class="primary" id="save">Salva</button>
          <button class="secondary" id="reload">Ricarica</button>
        </div>
        <p id="msg"></p>
      </div>
    </section>
  </main>
  <script>
    const panels = document.querySelectorAll('.panel');
    const navButtons = document.querySelectorAll('nav button');
    navButtons.forEach(btn => btn.onclick = () => {
      navButtons.forEach(b => b.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('panel-' + btn.dataset.panel).classList.add('active');
    });

    function row(label, value, cls='') {
      return `<div class="row"><span class="label">${label}</span><span class="${cls}">${value}</span></div>`;
    }

    async function loadVersion() {
      const r = await fetch('/api/version');
      const j = await r.json();
      document.getElementById('version').textContent =
        `v${j.version} · ${j.interface} · aggiornamento ogni 5s`;
    }

    function renderStatus(data) {
      const link = data.link || {};
      const ip = data.ip || {};
      const neighbor = data.neighbor || {};
      const system = data.system || {};
      document.getElementById('status-link').innerHTML = [
        row('Stato', link.carrier ? 'UP' : 'DOWN', link.carrier ? 'ok' : 'bad'),
        row('MAC', link.mac_address || 'n/a'),
        row('Velocità', link.speed_mbps ? link.speed_mbps + ' Mbps' : 'n/a'),
      ].join('');
      const addresses = (ip.addresses || []).map(a => `${a.address}/${a.prefixlen}`).join(', ') || 'n/a';
      document.getElementById('status-network').innerHTML = [
        row('IP', addresses),
        row('Gateway', ip.gateway || 'n/a'),
        row('DNS', (ip.dns_servers || []).join(', ') || 'n/a'),
      ].join('');
      document.getElementById('status-switch').innerHTML = neighbor.available ? [
        row('Protocollo', neighbor.protocol || 'n/a'),
        row('Switch', neighbor.switch_name || 'n/a'),
        row('Porta', neighbor.port_id || 'n/a'),
        row('VLAN', neighbor.vlan_id || 'n/a'),
      ].join('') : row('Stato', neighbor.message || 'In attesa', 'bad');
      document.getElementById('status-system').innerHTML = [
        row('Hostname', system.hostname || 'n/a'),
        row('Uptime', system.uptime_seconds != null ? Math.round(system.uptime_seconds) + ' s' : 'n/a'),
        row('Temp', system.cpu_temperature_c != null ? system.cpu_temperature_c.toFixed(1) + ' °C' : 'n/a'),
      ].join('');
    }

    function renderPing(ping) {
      const el = document.getElementById('ping-results');
      if (ping.running) {
        el.innerHTML = row('Stato', ping.message || 'In corso...');
        return;
      }
      const results = ping.results || [];
      if (!results.length) {
        el.innerHTML = '<div class="sub">Nessun risultato. Premi Esegui ping.</div>';
        return;
      }
      el.innerHTML = results.map(item => {
        const ok = item.result && item.result.reachable;
        const rtt = item.result && item.result.rtt_ms != null ? item.result.rtt_ms.toFixed(0) + ' ms' : 'FAIL';
        return row(item.label, `${item.host} · ${rtt}`, ok ? 'ok' : 'bad');
      }).join('');
      if (ping.adhoc_host) {
        el.innerHTML += row('Ad-hoc', ping.adhoc_host, 'ok');
      }
    }

    async function loadStatus() {
      const r = await fetch('/api/status');
      const data = await r.json();
      renderStatus(data);
      renderPing(data.ping || {});
    }

    async function loadConfig() {
      const r = await fetch('/api/config');
      const j = await r.json();
      document.getElementById('yaml').value = j.yaml || '';
    }

    document.getElementById('reload').onclick = () => { loadConfig(); loadStatus(); };
    document.getElementById('save').onclick = async () => {
      const msgEl = document.getElementById('msg');
      msgEl.textContent = '';
      const r = await fetch('/api/config', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({yaml: document.getElementById('yaml').value})
      });
      const j = await r.json();
      msgEl.textContent = r.ok ? 'Salvato.' : (j.detail || 'Errore');
      msgEl.className = r.ok ? 'ok' : 'bad';
    };

    document.getElementById('ping-run').onclick = async () => {
      const msgEl = document.getElementById('ping-msg');
      msgEl.textContent = 'Ping in corso...';
      const r = await fetch('/api/ping/run', {method: 'POST'});
      const j = await r.json();
      msgEl.textContent = r.ok ? 'Completato.' : (j.detail || 'Errore');
      renderPing(j);
      loadStatus();
    };

    document.getElementById('adhoc-save').onclick = async () => {
      const host = document.getElementById('adhoc-host').value.trim();
      const msgEl = document.getElementById('ping-msg');
      const r = await fetch('/api/ping/adhoc', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host})
      });
      const j = await r.json();
      msgEl.textContent = r.ok ? `Host salvato: ${j.host}` : (j.detail || 'Errore');
      loadStatus();
    };

    document.getElementById('adhoc-clear').onclick = async () => {
      const msgEl = document.getElementById('ping-msg');
      await fetch('/api/ping/adhoc', {method: 'DELETE'});
      document.getElementById('adhoc-host').value = '';
      msgEl.textContent = 'Host ad-hoc rimosso.';
      loadStatus();
    };

    document.getElementById('discover-scan').onclick = async () => {
      const el = document.getElementById('discover-results');
      el.textContent = 'Scansione in corso...';
      const r = await fetch('/api/discover/scan');
      const j = await r.json();
      if (!r.ok) {
        el.textContent = j.detail || 'Errore scansione';
        return;
      }
      const hosts = j.hosts || [];
      if (!hosts.length) {
        el.innerHTML = '<div class="sub">Nessun host trovato.</div>';
        return;
      }
      el.innerHTML = hosts.slice(0, 40).map(h =>
        `<div>${h.ip} · ${h.mac}${h.vendor ? ' · ' + h.vendor : ''}</div>`
      ).join('');
      if (hosts.length > 40) {
        el.innerHTML += `<div class="sub">... e altri ${hosts.length - 40}</div>`;
      }
    };

    loadVersion();
    loadConfig();
    loadStatus();
    setInterval(loadStatus, 5000);
  </script>
</body>
</html>
"""


def create_app(
    config: NdpConfig,
    config_path: Path,
    get_state: Callable[[], ProbeState],
    *,
    on_ping_complete: Callable[[PingSuiteState], None] | None = None,
    on_adhoc_changed: Callable[[], None] | None = None,
) -> object:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel

    class ConfigPayload(BaseModel):
        yaml: str

    class AdhocPayload(BaseModel):
        host: str

    app = FastAPI(title="NDP", version="0.7")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

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

    @app.get("/api/ping")
    def api_ping_status() -> dict[str, object]:
        return get_state().ping.to_dict()

    @app.post("/api/ping/run")
    def api_ping_run() -> dict[str, object]:
        from ndp.ping.service import run_ping_suite

        state = get_state()
        suite = run_ping_suite(
            config,
            gateway=state.ip.gateway,
            adhoc_path=Path(config.ping_adhoc_path),
        )
        if on_ping_complete is not None:
            on_ping_complete(suite)
        return suite.to_dict()

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
