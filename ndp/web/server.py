"""FastAPI server for remote configuration and probe status."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from ndp.core.config import DEFAULT_CONFIG_PATH, NdpConfig
from ndp.core.config_io import load_config_text, save_config_text
from ndp.core.state import ProbeState

logger = logging.getLogger(__name__)

_INDEX_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NDP Config</title>
  <style>
    body { font-family: sans-serif; margin: 1rem; background: #0c1220; color: #e8f0ff; }
    textarea { width: 100%; min-height: 28rem; font-family: monospace; font-size: 14px; }
    button { margin-top: 0.5rem; padding: 0.5rem 1rem; }
    .ok { color: #50c878; }
    .err { color: #ff8080; }
    pre { background: #18243f; padding: 0.75rem; overflow: auto; }
  </style>
</head>
<body>
  <h1>Network Diagnostic Probe</h1>
  <p>Modifica <code>/etc/ndp/config.yaml</code> e salva. Riavvia il servizio per applicare.<br>
  Per non perdere i commenti, usa <code>/etc/ndp/config.yaml.example</code> come riferimento.</p>
  <textarea id="yaml"></textarea><br>
  <button id="save">Salva configurazione</button>
  <button id="reload">Ricarica</button>
  <p id="msg"></p>
  <h2>Stato probe</h2>
  <pre id="status">Caricamento...</pre>
  <script>
    const yamlEl = document.getElementById('yaml');
    const msgEl = document.getElementById('msg');
    const statusEl = document.getElementById('status');
    async function loadConfig() {
      const r = await fetch('/api/config');
      const j = await r.json();
      yamlEl.value = j.yaml || '';
    }
    async function loadStatus() {
      const r = await fetch('/api/status');
      statusEl.textContent = JSON.stringify(await r.json(), null, 2);
    }
    document.getElementById('reload').onclick = () => { loadConfig(); loadStatus(); };
    document.getElementById('save').onclick = async () => {
      msgEl.textContent = '';
      const r = await fetch('/api/config', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({yaml: yamlEl.value})
      });
      const j = await r.json();
      msgEl.textContent = r.ok ? 'Salvato.' : (j.detail || 'Errore');
      msgEl.className = r.ok ? 'ok' : 'err';
    };
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
) -> object:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel

    class ConfigPayload(BaseModel):
        yaml: str

    app = FastAPI(title="NDP", version="0.4")

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

    return app


def start_web_server(
    config: NdpConfig,
    config_path: Path,
    get_state: Callable[[], ProbeState],
) -> threading.Thread:
    import uvicorn

    app = create_app(config, config_path, get_state)
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
