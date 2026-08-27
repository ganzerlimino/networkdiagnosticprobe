# NDP — Accesso dal telefono

Guida rapida per controllare il probe dal browser del cellulare (Stato, Ping, Discover, Scan, Config).

---

## Cosa ti serve

| Requisito | Note |
|-----------|------|
| NDP installato e attivo | `sudo systemctl status ndp` → `active (running)` |
| Hotspot abilitato (consigliato) | `wifi_hotspot.enabled: true` in config (default da v0.10) |
| Web abilitato | `web.enabled: true` (default) |
| Browser sul telefono | Chrome, Safari, Firefox — nessuna app da installare |

**Indirizzo consigliato (hotspot):**

```
http://192.168.50.1:8080/
```

**Alternativa (stessa LAN del cliente):**

```
http://<IP-ETH0-DELLA-PI>:8080/
```

---

## Modo consigliato: hotspot NDP (v0.10+)

```
[Telefono] ──Wi-Fi NDP-XXXX── [wlan0 Pi]     ← pannello di controllo
                    │
[NDP Probe] ──eth0── [Rete cliente]          ← diagnostica sul cavo
```

1. Accendi il probe e attendi ~1–2 minuti (hotspot parte con `ndp-hotspot.service`).
2. Sul telefono, apri **Impostazioni Wi‑Fi** e cerca una rete tipo **NDP-3456**  
   (prefisso `NDP` + ultime 4 cifre del MAC Wi‑Fi della Pi).
3. Password predefinita: **`ndp-probe`** (modificabile in config).
4. Apri il browser su:

   ```
   http://192.168.50.1:8080/
   ```

5. Nella tab **Stato** compare la scheda **Hotspot telefono** con SSID, URL e stato.

### Verifica hotspot dalla Pi (SSH)

```bash
sudo systemctl status ndp-hotspot
ndp hotspot status
ndp hotspot status --json
```

Per riavviare manualmente:

```bash
sudo systemctl restart ndp-hotspot
```

---

## Wi‑Fi e hotspot — riepilogo

| Funzione | Stato |
|----------|--------|
| Web UI su porta **8080** | ✅ Disponibile |
| **Hotspot Wi‑Fi integrato** (`wifi_hotspot`) | ✅ v0.10 |
| Probe su **Ethernet** (`eth0`) | ✅ Uso normale in campo |
| Telefono sulla **stessa LAN** del probe | ✅ Alternativa se hai Wi‑Fi cliente |

---

## Scenari alternativi

### 1. Rete del cliente (senza hotspot)

```
[Switch/LAN cliente] ──eth0── [NDP Probe]
        │
     [Wi‑Fi cliente] ── [Telefono tecnico]
```

1. Colleghi il probe con il cavo Ethernet alla rete da diagnosticare.
2. Il telefono si collega al **Wi‑Fi della stessa rete**.
3. Trovi l'IP Ethernet del probe (schermata HOME del TFT).
4. Apri `http://<IP>:8080/`.

Funziona se Wi‑Fi e porta Ethernet del probe sono sulla **stessa subnet**.

### 2. Solo Ethernet, nessun Wi‑Fi cliente

Usa l'**hotspot NDP** (modo consigliato): non serve la rete del sito per controllare il probe dal telefono.

Se l'hotspot è disabilitato (`wifi_hotspot.enabled: false`), serve comunque una rete condivisa (Wi‑Fi cliente o router di servizio).

---

## Come trovare l'IP della Pi

| Metodo | Dove |
|--------|------|
| **Hotspot** | URL fisso `192.168.50.1` (non serve cercare l'IP) |
| **Display TFT** | Schermata **HOME** → riga `IP` (indirizzo `eth0`) |
| **SSH** | `hostname -I` o `ip -4 addr show eth0` |
| **CLI** | `ndp --once` |
| **Web UI** | Tab **Stato** → scheda Hotspot |

---

## Primo accesso — passo passo

1. Accendi il probe e attendi lo splash (~1–2 minuti al primo avvio).
2. Collega il cavo Ethernet alla rete da diagnosticare (link UP sulla HOME).
3. Sul telefono, connetti il Wi‑Fi **NDP-XXXX** (password `ndp-probe` se non cambiata).
4. Apri `http://192.168.50.1:8080/`.
5. Dovresti vedere **Network Diagnostic Probe** con le tab:
   - **Stato** — link, IP, LLDP, hotspot
   - **Ping** — grafico live e suite
   - **Discover** — wizard Up/Down
   - **Scan** — porte e DNS/gateway
   - **Config** — file YAML

---

## Verifica rapida dalla Pi (se hai SSH)

```bash
sudo systemctl status ndp ndp-hotspot
curl -s http://127.0.0.1:8080/api/version
curl -s http://127.0.0.1:8080/api/hotspot/status
```

Risposta attesa (esempio):

```json
{"version":"0.10.0","interface":"eth0"}
```

Se funziona in locale ma non dal telefono, controlla che il telefono sia sulla rete **NDP-XXXX** (o sulla stessa LAN del probe).

---

## Problemi frequenti

### Il telefono non vede la rete NDP-XXXX

| Causa probabile | Cosa fare |
|-----------------|-----------|
| Hotspot disabilitato | `wifi_hotspot.enabled: true` in config, poi `sudo systemctl restart ndp-hotspot` |
| Servizio fermo | `sudo systemctl restart ndp-hotspot` |
| `wlan0` assente | Verifica modulo Wi‑Fi sulla Pi 3 |
| `hostapd`/`dnsmasq` non installati | `sudo ./scripts/install.sh` |
| Conflitto con `wpa_supplicant` | L'install script disabilita il client Wi‑Fi su `wlan0`; riavvia `ndp-hotspot` |

### “Impossibile aprire la pagina” / timeout

| Causa probabile | Cosa fare |
|-----------------|-----------|
| Telefono non sull'hotspot NDP | Ricollega il Wi‑Fi **NDP-XXXX** |
| URL sbagliato | Usa `http://192.168.50.1:8080/` (non l'IP eth0) |
| `web.enabled: false` | Metti `web.enabled: true`, poi `sudo systemctl restart ndp` |
| Servizio fermo | `sudo systemctl restart ndp` |

### Discover / Scan non funzionano

- Richiedono privilegi di rete sulla Pi (il servizio `ndp` gira già come root).
- La diagnostica usa **eth0** verso la rete cliente; l'hotspot serve solo per il telefono.

---

## Configurazione consigliata (`/etc/ndp/config.yaml`)

```yaml
ui:
  enabled: true
  input: none
  auto_cycle_seconds: 8

web:
  enabled: true
  host: "0.0.0.0"
  port: 8080

wifi_hotspot:
  enabled: true
  ssid_prefix: "NDP"
  password: "ndp-probe"
  interface: wlan0
  ip: "192.168.50.1"
  country: "IT"
```

Dopo ogni modifica al config:

```bash
sudo systemctl restart ndp-hotspot ndp
```

Per disabilitare l'hotspot (solo LAN cliente):

```yaml
wifi_hotspot:
  enabled: false
```

---

## Segnalibro sul telefono

- **Nome:** NDP probe
- **URL (hotspot):** `http://192.168.50.1:8080/`

L'IP `eth0` può cambiare tra un sito e l'altro; l'hotspot mantiene sempre lo stesso URL per il telefono.

---

## Riepilogo in una riga

> Accendi il probe, collega il cavo Ethernet, connetti il telefono al Wi‑Fi **NDP-XXXX**, apri `http://192.168.50.1:8080/`.
