# Network Diagnostic Probe (NDP)

**Versione corrente: v0.23.1**

Dispositivo portatile di diagnostica di rete basato su **Raspberry Pi 3**, pensato per rispondere rapidamente alla domanda: *cosa c'è dall'altra parte del cavo?*

Collegando il probe a una porta switch, NDP mostra informazioni **L2** (LLDP/CDP, MNDP, sniff passivo) e **L3** (IP, gateway, DNS, ping, scan porte) senza laptop né console. Il **telefono** (via hotspot integrato) è il pannello di controllo; il **display TFT** è un mirror read-only in rotazione automatica.

---

## Documentazione

| Documento | Descrizione |
|-----------|-------------|
| **[docs/NDP-MANUALE-COMPLETO.docx](docs/NDP-MANUALE-COMPLETO.docx)** | **Manuale completo impaginato** (hardware, software, Web UI, OT, config, temi, i18n, troubleshooting) |
| **[docs/DOCUMENTAZIONE.md](docs/DOCUMENTAZIONE.md)** | Stessa guida in Markdown (aggiornabile in repo) |
| **[docs/MANUALE-ACCESSO-TELEFONO.md](docs/MANUALE-ACCESSO-TELEFONO.md)** | Hotspot, URL, accesso da telefono |
| **[docs/CONFIGURAZIONE-TEMI.md](docs/CONFIGURAZIONE-TEMI.md)** | Temi colori custom (Web UI + TFT) |

---

## Stato del progetto (v0.23.1)

Release di riferimento per uso sul campo. Funzionalità principali:

| Area | Contenuto |
|------|-----------|
| **Core** | Link, IP, LLDP/CDP, sistema, polling, JSON/console |
| **Hotspot** | Rete **NDP-XXXX** su `wlan0`, boot automatico, `ndp hotspot ensure` |
| **Web UI mobile** | Monitor, LAN, OT, Sistema — PWA dark, export JSON/CSV, report email |
| **Discover** | Wizard Up/Down, ARP, mDNS/SSDP, OUI, passive sniff, MNDP |
| **OT** | Impianto (Weintek, eWON, Modbus), MikroTik, camere, NAS, stampanti Epson/Zebra |
| **Scan** | Porte standard/custom, DNS, gateway, MTU path discovery |
| **Config** | Form guidato, YAML, backup mail, profili scenario (impianto/retail/ufficio) |
| **TFT** | Pygame su `/dev/fb1`, splash, spegnimento rosso ad alto contrasto |
| **i18n** | Italiano, English, Deutsch (UI web, TFT, report email) |
| **Temi** | 5 temi bundled + overlay `/etc/ndp/locale/themes.json`, `ndp theme validate` |
| **Spegnimento** | Sequenza sicura da telefono con messaggio su TFT |
| **Diagnostica** | `scripts/ndp-doctor.sh` per verifiche rapide sul Pi |

### Changelog recente

| Versione | Novità principali |
|----------|-------------------|
| **0.23.1** | Fix menu lingue (esclusi file temi da select locale) |
| **0.23.0** | i18n completo IT/EN/DE, report mail multilingua, stringhe Web UI |
| **0.22.x** | Validatore temi (`ndp theme validate`), fix crash catalogo temi, fix hotspot NM |
| **0.20–0.21** | Temi custom, scenari discovery, footer TFT client Wi‑Fi |
| **0.19** | Tab OT (Impianto, camere, NAS, stampanti), navigazione Monitor/LAN/OT/Sistema |
| **0.18** | Spegnimento controllato, MNDP in status, passive check |
| **0.12** | MTU discovery |
| **0.10** | Hotspot Wi‑Fi integrato |
| **0.7** | Display read-only + Web UI come controllo principale |

Prossima milestone opzionale: **immagine SD pronta al flash** (pi-gen).

---

## Hardware di riferimento

| Componente | Modello |
|------------|---------|
| SBC | Raspberry Pi 3 Model B/B+ |
| Display | Joy-it RB-TFT3.2 (320×240, solo output) |
| Controllo | Smartphone via browser (`http://192.168.50.1:8080/`) |
| Rete diagnostica | Ethernet RJ45 (`eth0`) |
| Alimentazione | Powerbank USB 5V |

Il touchscreen del TFT **non è usato**. Boot 60–90 s è accettabile per uno strumento da campo.

---

## Architettura

```
  Smartphone ── Wi‑Fi NDP-XXXX ──► Web UI :8080   (ping, discover, config, spegnimento)
  eth0 ─────────────────────────► rete cliente   (diagnostica L2/L3)
  TFT /dev/fb1 ◄────────────────── mirror read-only, auto-cycle
```

```
ndp (servizio systemd)
 ├── collectors/     link, IP, LLDP, sistema
 ├── discovery/      ARP, wizard Up/Down, vendor probes
 ├── scan/           porte TCP, DNS, MTU
 ├── network/        hotspot hostapd + dnsmasq
 ├── web/            FastAPI + dashboard.html (PWA)
 ├── ui/             Pygame framebuffer TFT
 └── locale/         it, en, de + themes.json
```

---

## Installazione su Raspberry Pi

Su **Raspberry Pi OS Lite (64-bit)**:

```bash
git clone https://github.com/ganzerlimino/networkdiagnosticprobe.git ~/networkdiagnosticprobe
cd ~/networkdiagnosticprobe
git pull   # assicurati di essere su main aggiornato
sudo ./scripts/install.sh
```

Con display Joy-it RB-TFT3.2 (installa driver e **riavvia**):

```bash
sudo ./scripts/install.sh --with-display
```

Lo script installa dipendenze di sistema, crea `/opt/ndp`, config in `/etc/ndp/`, abilita `ndp-hotspot`, `lldpd` e `ndp`.

### Aggiornamento

```bash
cd ~/networkdiagnosticprobe
git pull
sudo ./scripts/install.sh
sudo systemctl restart ndp-hotspot ndp
```

### Verifica

```bash
sudo ./scripts/ndp-doctor.sh    # diagnostica rapida
sudo systemctl status ndp ndp-hotspot
ndp --once
ndp --once --json
ndp hotspot status
ndp theme validate              # valida temi custom
```

---

## Uso rapido

1. Accendi il probe, collega **eth0** alla rete da analizzare.
2. Connetti il telefono all'hotspot **NDP-XXXX** (password in config).
3. Apri **`http://192.168.50.1:8080/`**.
4. **Monitor → Stato** per link, IP, switch LLDP.
5. Usa **Discover**, **Ping**, **OT → Impianto** secondo il caso.
6. **Sistema → Config** per lingua (IT/EN/DE), scenario, tema colori.
7. **Sistema → Spegnimento** a fine intervento.

URL alternativo sulla LAN cliente: `http://<IP-eth0>:8080/`.

### Profilo config consigliato

```yaml
ui:
  enabled: true
  input: none
  locale: it          # it | en | de
  theme: field-dark
  auto_cycle_seconds: 8

web:
  enabled: true
  port: 8080

wifi_hotspot:
  enabled: true
  ssid_prefix: "NDP"
  password: "ndp-probe"   # min 8 caratteri

discovery:
  scenario: impianto      # impianto | retail | ufficio
```

---

## Comandi CLI

```bash
ndp --once [--json]                 # stato probe
sudo ndp discover scan              # ARP scan
sudo ndp discover updown            # wizard Up/Down
ndp hotspot start|stop|status|ensure
ndp theme validate [--file PATH] [--json]
ndp test ping [--adhoc HOST]
ndp test display --color cycle
```

---

## Temi e personalizzazione

- Temi bundled: `ndp/locale/themes.json`
- Overlay custom: `/etc/ndp/locale/themes.json` (merge a runtime)
- Schema: `/etc/ndp/locale/themes.schema.json`
- Validazione: `ndp theme validate`
- Guida: [docs/CONFIGURAZIONE-TEMI.md](docs/CONFIGURAZIONE-TEMI.md)

---

## Sviluppo e test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web,ui]"
pytest
```

Rigenerare il manuale Word dopo modifiche a `docs/DOCUMENTAZIONE.md`:

```bash
python3 scripts/generate-manuale-docx.py
```

---

## Roadmap

| Fase | Stato |
|------|-------|
| Core + discovery + UI TFT + Web | ✅ |
| Hotspot + OT + i18n + temi | ✅ |
| Immagine SD custom (pi-gen) | Pianificata |
| Case 3D | Pianificata |

---

## Licenza

MIT — vedi [LICENSE](LICENSE).
