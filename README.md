# Network Diagnostic Probe (NDP)

Dispositivo portatile di diagnostica di rete basato su **Raspberry Pi 3**, pensato per rispondere rapidamente alla domanda: *cosa c'è dall'altra parte del cavo?*

Collegando il probe a una porta switch, NDP mostra informazioni L2 (LLDP/CDP) e L3 (IP, gateway, DNS) senza bisogno di laptop o console.

## Stato del progetto

**v0.7 — Display read-only + telefono come controllo**

- TFT a **rotazione automatica** delle schermate (nessun tasto/encoder necessario)
- **Web UI mobile** come strumento principale: stato, ping, scan ARP, config
- `ui.input: none` — nessun GPIO input sul dispositivo
- Il touchscreen del display Joy-it **non è usato** (solo framebuffer)

**v0.5 — Ping diagnostico**

- ICMP verso **8.8.8.8**, **1.1.1.1**, fino a **4 host in config**, più **1 adhoc** al volo
- Schermata **Ping** sul TFT; CLI `ndp test ping`
- API web `/api/ping/*`

**v0.4 — UI discovery + web config**

- Splash screen e warmup all'avvio (tasti attivi solo quando pronto)
- Schermata **Discover** con wizard Up/Down sul display TFT
- Server HTTP per stato probe e modifica `config.yaml` (`web.enabled: true`)
- Parametri UI documentati in `ndp/config/default.yaml`

**v0.3 — UI Pygame (Joy-it RB-TFT3.2)**

- 5 schermate: Home, Switch, Network, System, Discover
- Output framebuffer raw su `/dev/fb1` (Pi OS Lite)
- Legenda tasti laterale, font e spaziatura configurabili

**v0.2 — Discovery Up/Down (CLI)**

- Wizard guidato per trovare un dispositivo scollegandolo e confrontando due scansioni
- ARP scan attivo (`arp-scan`) con fallback su tabella kernel
- Pulizia cache ARP prima della seconda scansione
- Verifica al ricollegamento (passo 5)

**v0.1 — Core engine**

- Collector per link Ethernet, IP stack, LLDP/CDP e metriche di sistema
- Motore di polling con cache neighbor
- Output console e JSON (`ndp --once --json`)
- Script di installazione per Raspberry Pi OS Lite
- Unit file systemd per avvio automatico

Prossime milestone: immagine SD pronta al flash, hotspot Wi-Fi per accesso remoto.

## Hardware di riferimento

| Componente | Modello |
|------------|---------|
| SBC | Raspberry Pi 3 Model B/B+ |
| Display | Joy-it RB-TFT3.2 (solo output, no touch) |
| Controllo | Smartphone via browser (`http://<ip-pi>:8080`) |
| Rete | Ethernet RJ45 integrata |
| Alimentazione | Powerbank USB 5V |

Il Pi 3 è scelto per il **basso costo**. Un boot di 60–90 secondi è accettabile per uno strumento da campo, non per un dispositivo consumer.

## Architettura software

```
                    ┌─────────────────┐
  Smartphone  ─────►│  Web UI :8080   │  ping, discover, config
                    └────────┬────────┘
                             │
ndp-core (polling) ◄─────────┤
    ├── collectors/          │
    └── engine               ▼
                    ┌─────────────────┐
                    │  TFT /dev/fb1   │  mirror read-only, auto-cycle
                    └─────────────────┘
```

Il display mostra i risultati in rotazione (Home → Switch → Network → Ping → System).  
Tutta l'interazione (ping, scan rete, configurazione) avviene dal **telefono** sulla stessa rete.

```
ndp-core (polling)
    ├── collectors/link.py    → operstate, speed, duplex, MAC
    ├── collectors/ip.py      → iproute2 JSON
    ├── collectors/lldp.py    → lldpctl JSON
    └── collectors/system.py  → hostname, uptime, temperatura

ndp-discovery
    ├── arp.py                → arp-scan, flush ARP cache
    ├── diff.py               → confronto snapshot
    └── wizard.py             → flusso Up/Down guidato (5 passi)

ndp.service (systemd) → avvio automatico all'accensione
```

La UI locale (Pygame) è un **pannello informativo**; la Web UI (FastAPI) è il **piano di controllo**.

### Profilo consigliato (Pi con display)

```yaml
ui:
  enabled: true
  input: none
  auto_cycle_seconds: 8
  hint_edge: none
  content_margin_side: 0

web:
  enabled: true
  port: 8080
```

Apri `http://<ip-della-pi>:8080/` dal telefono (stessa rete Ethernet/Wi-Fi della Pi).

> Il touchscreen resistivo del Joy-it non è utilizzato da NDP. Non serve calibrarlo né abilitare driver touch.

## Installazione rapida su Raspberry Pi

Su Raspberry Pi OS Lite (64-bit), con rete disponibile:

```bash
git clone https://github.com/networkdiagnosticprobe/networkdiagnosticprobe.git
cd networkdiagnosticprobe
sudo ./scripts/install.sh
```

Lo script:

1. Installa `lldpd`, `iproute2`, `ethtool`, `arp-scan`
2. Crea un virtualenv in `/opt/ndp`
3. Copia la configurazione in `/etc/ndp/config.yaml`
4. Abilita e avvia `lldpd` e `ndp`

### Verifica

```bash
sudo systemctl status ndp
ndp --once
ndp --once --json
sudo ndp discover scan
sudo ndp discover updown
```

> `arp-scan` e il wizard discovery richiedono privilegi root (raw socket / flush ARP).

## Discovery Up/Down

Workflow guidato per identificare un dispositivo quando non conosci il suo IP/MAC:

1. **Baseline** — scansione ARP della subnet
2. **Stacca** — l'utente scollega il device cercato
3. **Flush ARP + attesa** — svuota la cache kernel e attende che la rete si stabilizzi
4. **Seconda scansione** — confronto e lista device andati offline
5. **Ricollega e verifica** — conferma che il MAC scomparso ricompare

```bash
sudo ndp discover updown
sudo ndp discover updown --json
sudo ndp discover updown --skip-verify
```

Comandi utili:

```bash
sudo ndp discover scan --save /tmp/baseline.json
sudo ndp discover flush-arp
sudo ndp discover diff /tmp/baseline.json /tmp/after.json
```

### Perché il flush ARP al passo 3?

Senza pulizia, il kernel può conservare voci **stale** nella neighbor table anche dopo lo scollegamento fisico. La seconda scansione potrebbe quindi “vedere” ancora il device come presente. `ip neigh flush dev eth0` azzera la cache prima del countdown e della nuova scansione attiva, rendendo il diff molto più affidabile.

## Sviluppo locale (PC o Pi)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ndp --once
```

Su un PC senza `lldpd` o senza interfaccia `eth0`, i collector gestiscono l'assenza dei dati senza crash.

## Configurazione

File predefinito: `/etc/ndp/config.yaml` — ogni chiave è commentata nel template `ndp/config/default.yaml`.

```yaml
ui:
  enabled: true
  input: none
  auto_cycle_seconds: 8
  hint_edge: none
  content_margin_side: 0

web:
  enabled: true
  port: 8080

discovery:
  disconnect_wait_seconds: 8
```

## Web UI (controllo da telefono)

Con `web.enabled: true` apri `http://<ip-della-pi>:8080/` da browser sulla stessa rete:

- **Stato** — link, IP, LLDP, sistema (aggiornamento automatico)
- **Ping** — esegui suite ICMP, host ad-hoc temporaneo
- **Discover** — scansione ARP della subnet (wizard Up/Down completo via CLI/SSH)
- **Config** — modifica e salva `/etc/ndp/config.yaml`

Dopo modifiche al config: `sudo systemctl restart ndp`

Il Wi-Fi hotspot è previsto in una fase successiva; per ora usa Ethernet o la rete Wi-Fi già configurata sulla Pi.

### Input opzionale sul dispositivo

Per prototipi con tasti TFT o encoder KY-040, imposta `ui.input: buttons` o `ui.input: encoder` in config. Il profilo di prodotto consigliato resta `none` (solo telefono).

## Immagine SD pronta al flash

Obiettivo release: scaricare un'immagine, flasharla con [Raspberry Pi Imager](https://www.raspberrypi.com/software/), inserire la SD e usare il probe.

Per ora:

1. Flash di Raspberry Pi OS Lite (64-bit)
2. Esecuzione di `scripts/install.sh` al primo avvio

La fase successiva automatizzerà questi passi con una stage **pi-gen** dedicata (`image/pi-gen/`). Vedi `scripts/build-sd-image.sh` per il piano di build.

## Roadmap

| Fase | Contenuto | Stato |
|------|-----------|-------|
| 0 | PoC hardware (display + lldpd) | Da validare su Pi reale |
| 1 | Core engine Python | ✅ v0.1 |
| 1b | Discovery Up/Down wizard | ✅ v0.2 |
| 2 | UI Pygame su framebuffer | ✅ v0.3 |
| 2b | Splash + schermate TFT | ✅ v0.4 |
| 2c | Display read-only + web mobile | ✅ v0.7 |
| 3 | Immagine SD custom (pi-gen) | Prossima |
| 4 | Web config HTTP | ✅ v0.4 (senza hotspot) |
| 4b | Hotspot Wi-Fi | Ultima — dopo funzioni core |
| 5 | Case 3D | Pianificata |

## Licenza

MIT — vedi [LICENSE](LICENSE).
