# Network Diagnostic Probe (NDP) — Documentazione completa

**Versione software:** 0.19.1  
**Repository:** [networkdiagnosticprobe](https://github.com/ganzerlimino/networkdiagnosticprobe.git)  
**Scopo del documento:** recap tecnico, manuale operativo e riferimento per manutenzione futura.

---

## Indice

1. [Cos'è NDP e a cosa serve](#1-cosè-ndp-e-a-cosa-serve)
2. [Hardware](#2-hardware)
3. [Software e architettura](#3-software-e-architettura)
4. [Installazione e deploy](#4-installazione-e-deploy)
5. [Casi d'uso operativi](#5-casi-duso-operativi)
6. [Identificazione hardware individuale](#6-identificazione-hardware-individuale)
7. [Interfaccia web — layout e scelte di design](#7-interfaccia-web--layout-e-scelte-di-design)
8. [Protocolli e discovery](#8-protocolli-e-discovery)
9. [Esportazione dati e report](#9-esportazione-dati-e-report)
10. [Configurazione del device](#10-configurazione-del-device)
11. [Hotspot Wi‑Fi e accesso telefono](#11-hotspot-wi-fi-e-accesso-telefono)
12. [Spegnimento controllato](#12-spegnimento-controllato)
13. [Display TFT (UI locale)](#13-display-tft-ui-locale)
14. [Manutenzione e aggiornamenti](#14-manutenzione-e-aggiornamenti)
15. [Risoluzione problemi](#15-risoluzione-problemi)
16. [Riferimenti rapidi](#16-riferimenti-rapidi)

---

## 1. Cos'è NDP e a cosa serve

NDP è un **dispositivo portatile di diagnostica di rete** basato su Raspberry Pi, pensato per rispondere rapidamente alla domanda:

> *Cosa c'è dall'altra parte del cavo?*

Collegando il probe alla porta Ethernet di uno switch o di un dispositivo, NDP raccoglie informazioni **L2** (LLDP/CDP, neighbor discovery, protocolli passivi) e **L3** (IP, gateway, DNS, ping, scan porte) **senza laptop né console**.

### Principio architetturale

NDP separa due piani:

| Piano | Interfaccia | Ruolo |
|-------|-------------|-------|
| **Diagnostica** | `eth0` (Ethernet) | Cavo verso la rete cliente |
| **Controllo** | `wlan0` (hotspot) + Web UI :8080 | Telefono del tecnico |

Il display TFT è un **mirror read-only** in rotazione automatica. Tutta l'interazione (ping, scan, config, spegnimento) avviene dal **browser del telefono**.

```
[Telefono] ──Wi‑Fi NDP-XXXX──► [wlan0] Web UI :8080
                                    │
[NDP Probe] ──eth0──────────────────┼──► [Rete cliente / switch]
                                    │
[TFT /dev/fb1] ◄── mirror automatico (Home → Switch → Network → Ping → System)
```

### Profilo d'uso tipico

1. Accendi il probe (powerbank o alimentatore USB 5V).
2. Collega il cavo RJ45 alla rete da analizzare.
3. Connetti il telefono all'hotspot **NDP-XXXX**.
4. Apri `http://192.168.50.1:8080/`.
5. Consulta **Monitor → Stato**, poi esegui ping, discover o scan secondo il caso.
6. Esporta JSON/CSV o invia report via email.
7. A fine intervento: **Sistema → Spegnimento**.

---

## 2. Hardware

### 2.1 Componenti di riferimento

| Componente | Modello / specifica | Note |
|------------|---------------------|------|
| **SBC** | Raspberry Pi 3 Model B / B+ | Scelta per basso costo; boot 60–90 s accettabile |
| **Display** | Joy-it **RB-TFT3.2** (320×240) | Framebuffer `/dev/fb1`; **solo output** |
| **Touchscreen** | Resistivo (presente sul TFT) | **Non utilizzato** da NDP — non serve calibrazione |
| **Rete cablata** | RJ45 integrato (`eth0`) | Interfaccia diagnostica principale |
| **Wi‑Fi** | `wlan0` onboard | Hotspot dedicato per il telefono |
| **Alimentazione** | USB 5V (powerbank consigliata) | Per uso portatile in campo |
| **Controllo** | Smartphone (browser) | Nessuna app da installare |

> **Pi 4/5:** compatibili in linea di principio, ma il profilo di prodotto e i test sono orientati al Pi 3.

### 2.2 Display Joy-it RB-TFT3.2

| Parametro | Valore |
|-----------|--------|
| Risoluzione | 320 × 240 px |
| Framebuffer | `/dev/fb1` (Pi OS Lite / Bookworm) |
| Retroilluminazione | GPIO **18** (BCM) |
| Driver | LCD-show (`goodtft/LCD-show`, script `LCD32-show`) |
| Backend NDP | `raw` su framebuffer RGB565 (auto su Lite) |

Installazione driver display (riavvia la Pi):

```bash
sudo ./scripts/install.sh --with-display
# oppure
sudo NDP_INSTALL_DISPLAY=1 ./scripts/install.sh
```

Test display:

```bash
ndp test display --color cycle
```

### 2.3 Input opzionale (prototipi)

Per versioni con tasti fisici o encoder, NDP supporta GPIO opzionali. Il **profilo di prodotto consigliato** resta `ui.input: none`.

| Modalità | GPIO | Uso |
|----------|------|-----|
| `buttons` | BCM 23, 24, 25 | ◀ precedente · ○ select · ▶ successivo |
| `encoder` | CLK=5, DT=6, SW=19 | KY-040 rotativo + click |
| `none` | — | Solo telefono (consigliato) |

Con `input: none` la schermata **Discover** non compare nel ciclo TFT (il wizard Up/Down resta disponibile solo da Web UI).

### 2.4 Cablaggio in campo

```
[Switch / dispositivo cliente]
         │
    Cavo Ethernet
         │
    [eth0 NDP Probe]
         │
    [Powerbank USB 5V]
```

Per il telefono **non serve** la rete Wi‑Fi del cliente: l'hotspot integrato del probe è sufficiente.

---

## 3. Software e architettura

### 3.1 Stack tecnologico

| Layer | Tecnologia |
|-------|------------|
| Linguaggio | Python ≥ 3.9 |
| Dipendenze core | PyYAML |
| Web | FastAPI + Uvicorn (`[web]` extra) |
| UI TFT | Pygame su framebuffer raw (`[ui]` extra) |
| Sistema | Raspberry Pi OS Lite 64-bit |
| Servizi systemd | `lldpd`, `ndp-hotspot`, `ndp` |

### 3.2 Pacchetti di sistema (install.sh)

`lldpd`, `hostapd`, `dnsmasq`, `iproute2`, `ethtool`, `arp-scan`, `iputils-ping`, `python3-lgpio`, `python3-pygame`, `iw`, `wireless-tools`, `rfkill`

### 3.3 Percorsi installazione

| Percorso | Contenuto |
|----------|-----------|
| `/opt/ndp/` | Codice applicazione + venv Python |
| `/etc/ndp/config.yaml` | Configurazione attiva |
| `/etc/ndp/config.yaml.example` | Template commentato |
| `/etc/ndp/hotspot/` | `hostapd.conf`, `dnsmasq.conf` generati |
| `/var/lib/ndp/` | Stato runtime (es. host ping adhoc) |
| `/run/ndp/` | PID e stato hotspot |
| `/usr/local/bin/ndp` | Symlink CLI |

### 3.4 Servizi systemd

| Unit | Tipo | Funzione |
|------|------|----------|
| `lldpd.service` | daemon | Ricezione LLDP/CDP su eth0 |
| `ndp-hotspot.service` | oneshot + maintain | Avvia `hostapd` + `dnsmasq` su wlan0 |
| `ndp.service` | daemon | Motore probe + TFT + Web UI |

Ordine di avvio: `ndp-hotspot` → `ndp` (dopo `network-online`).

### 3.5 Moduli applicativi

```
ndp/
├── core/           Motore polling, collectors (link, IP, LLDP, system, neighbors, MNDP)
├── discovery/      ARP, wizard Up/Down, mDNS, SSDP, passive sniff, OT, camere, NAS, stampanti
├── scan/           Profili porte TCP, DNS/gateway
├── ping/           Suite ICMP, ping live SSE
├── mtu/            Path MTU discovery
├── network/        Gestione hotspot Wi‑Fi
├── web/            FastAPI server + dashboard.html (PWA)
├── ui/             Pygame TFT (schermate, splash, spegnimento)
├── system/         Spegnimento controllato
└── cli/            Comandi discover, hotspot, test
```

---

## 4. Installazione e deploy

### 4.1 Prima installazione

```bash
git clone https://github.com/ganzerlimino/networkdiagnosticprobe.git
cd networkdiagnosticprobe
sudo ./scripts/install.sh
```

Con display Joy-it:

```bash
sudo ./scripts/install.sh --with-display   # riavvia automaticamente
```

### 4.2 Verifica post-install

```bash
sudo systemctl status ndp ndp-hotspot lldpd
ndp --once
ndp --once --json
ndp hotspot status
curl -s http://127.0.0.1:8080/api/version
```

### 4.3 Aggiornamento software

```bash
cd ~/networkdiagnosticprobe
git pull origin <branch>
sudo ./scripts/install.sh
sudo systemctl restart ndp-hotspot ndp
```

Lo script `install.sh`:
- sincronizza `/opt/ndp`
- reinstalla dipendenze Python
- **merge** nuove chiavi config da `default.yaml` senza sovrascrivere valori esistenti
- riavvia i servizi

### 4.4 Immagine SD (roadmap)

Obiettivo futuro: immagine pronta al flash via **pi-gen**. Oggi: Pi OS Lite + `install.sh` manuale.

---

## 5. Casi d'uso operativi

### 5.1 «Cosa c'è sullo switch?» — Stato immediato

**Quando:** appena collegato il cavo.

**Come:**
1. Attendi link UP (TFT Home o **Monitor → Stato**).
2. Apri **Monitor → Stato**.
3. Leggi le card:
   - **Link** — velocità, duplex, MAC eth0
   - **Rete** — IP, mask, gateway, DNS
   - **Switch** — neighbor LLDP/CDP/MNDP (nome switch, porta, VLAN se presente)
   - **Sistema** — hostname, uptime, temperatura CPU

**Output:** comprensione immediata di *dove sei connesso* senza configurare nulla.

---

### 5.2 «Questo cavo ha internet / raggiunge il gateway?» — Ping

**Quando:** verifica connettività verso internet, gateway o host specifici.

**Come:**
1. **Monitor → Ping**.
2. **Ping live:** inserisci fino a 3 host → **Avvia live** → grafico RTT in tempo reale.
3. **Suite completa:** ping verso 8.8.8.8, 1.1.1.1, target custom da config + eventuale adhoc.

**Nota tecnica:** i ping partono da **eth0** (`-I interface`), non dall'hotspot. Funziona anche con wlan0 attivo.

**Report:** pulsante 📧 Report ping.

---

### 5.3 «Qual è il MTU del percorso?» — MTU discovery

**Quando:** VPN site-to-site, tunnel, link con MTU ridotto.

**Come:**
1. **Monitor → MTU**.
2. Inserisci host destinazione (es. IP remoto VPN).
3. **Avvia discovery** — test decrementale da 1500 con DF (Don't Fragment).
4. Leggi MTU path rilevato nel log/stream.

---

### 5.4 «Chi è in questa subnet?» — Discover ARP

**Quando:** inventario rapido dispositivi sulla LAN.

**Come:**
1. **LAN → Discover**.
2. **Scansione rapida ARP** → elenco host con IP, MAC, vendor OUI.
3. Opzionale: **Servizi LAN** (mDNS, SSDP, probe L2 FDP/EDP/LLTD).
4. Tabella **Vendor MAC (OUI)** — cerca per prefisso o nome vendor.

**Export:** JSON / CSV dalla toolbar del pannello.

---

### 5.5 «Quale dispositivo è questo cavo?» — Wizard Up/Down

**Quando:** un solo device su una porta e non conosci IP/MAC.

**Come:**
1. **LAN → Discover** → card **Discover Up/Down**.
2. Segui i passi guidati:
   1. **Baseline** — scansione ARP
   2. **Stacca** il cavo dal device target
   3. **Attesa** + flush ARP (configurabile)
   4. **Seconda scansione** — diff: chi è sparito
   5. **Ricollega** — verifica che il MAC ricompaia

**Perché flush ARP:** senza pulizia cache kernel, il device scollegato può apparire ancora «presente».

**CLI equivalente:**

```bash
sudo ndp discover updown
sudo ndp discover updown --json
```

---

### 5.6 «Cosa trasmette questa rete?» — Sniff passivo

**Quando:** capire protocolli L2/L3 attivi senza inviare traffico invasivo.

**Come:**
1. **LAN → Sniff**.
2. Imposta durata (secondi) e opzionale host SNMP.
3. **Avvia passive check**.
4. Leggi sezioni: STP/LACP/VLAN/IGMP, FDP/EDP/LLTD, mDNS/SSDP, DHCP Option 82, SNMP probe.

---

### 5.7 «Quali porte sono aperte su questo IP?» — Scan

**Quando:** audit servizi IT su un host noto.

**Come:**
1. **LAN → Scan**.
2. Inserisci IP target (o **Usa gateway**).
3. **Porte standard** — SSH, HTTP/S, SMB, RDP, SNMP…
4. **Porte custom** — es. `80,443,8080`
5. **DNS e gateway** — risoluzione hostname + verifica gateway

> Per protocolli **OT** (Modbus, OPC UA, Weintek, eWON) usa **OT → Impianto**, non LAN → Scan.

---

### 5.8 «Cosa c'è in un impianto OT?» — Impianto

**Quando:** HMI, gateway VPN industriali, PLC su LAN di bordo macchina.

**Come:**
1. **OT → Impianto**.
2. **Senza IP:** **Scansiona impianto** → discovery broadcast Weintek + eWON.
3. **Con IP target** (PLC/gateway): imposta IP o **Usa gateway** → scan include profilo porte industriali (502, 4840, 102, …).
4. Leggi sezioni separate: Weintek HMI, eWON, Porte OT sul target.

**Export:** JSON / CSV.

---

### 5.9 «C'è un MikroTik nello switch?» — MikroTik MNDP

**Quando:** router/switch MikroTik, identificazione porta switch collegata.

**Come:**
1. **OT → MikroTik**.
2. Imposta durata ascolto (default 6 s).
3. **Scansiona MikroTik** — probe UDP/5678 + ascolto risposte MNDP.

**Nota:** la card **Switch** in Stato mostra il neighbor che matcha il gateway (dispositivo «sopra» il probe).

---

### 5.10 «Ci sono telecamere / NAS / stampanti?»

| Tab | Protocolli principali |
|-----|----------------------|
| **OT → Camere** | ONVIF WS-Discovery :3702, Hikvision SADP :37020, Dahua :37810, mDNS, SSDP |
| **OT → NAS** | Synology :9997, QNAP :7777, ASUSTOR :8888-8889, Netgear RAIDar :22081, WS-Discovery, mDNS |
| **OT → Stampanti** | Epson ENPC UDP :3289 (retail/fiscali), Zebra Link-OS UDP :4201 (etichette) |

Ogni tab ha pulsante scan dedicato + export JSON/CSV.

---

### 5.11 «Devo documentare l'intervento» — Report email

**Quando:** invio risultati al cliente o archiviazione.

**Come:** pulsanti 📧 nelle varie tab → apre l'app mail del telefono con oggetto e corpo precompilati (`mailto:` + testo da `/api/report`).

Sezioni disponibili: `status`, `ping`, `discover`, `scan`, `network`, `all`.

---

## 6. Identificazione hardware individuale

NDP identifica i dispositivi combinando più fonti. La tabella seguente riassume **come** viene riconosciuto ogni tipo e **dove** vederlo in UI.

### 6.1 Switch e infrastruttura L2

| Dispositivo | Metodo | Dati estratti | Dove in UI |
|-------------|--------|---------------|------------|
| Switch generico | LLDP (lldpd) | Nome, porta, chassis ID, VLAN, PoE/MED | Monitor → Stato → Switch |
| Switch Cisco | CDP via lldpd | ID device, porta, piattaforma | Monitor → Stato → Switch |
| MikroTik | MNDP UDP/5678 | Identity, versione, MAC, interfacce | Stato (neighbor) + OT → MikroTik |
| Bridge STP | Sniff BPDU | Root bridge, priorità | LAN → Sniff |

### 6.2 Host generici LAN

| Dispositivo | Metodo | Dati estratti | Dove in UI |
|-------------|--------|---------------|------------|
| Qualsiasi IP/MAC | ARP scan | IP, MAC, vendor OUI | LAN → Discover |
| Server/servizio | mDNS | Nome, tipo servizio, porta | LAN → Discover → Servizi |
| UPnP device | SSDP | UUID, server, location | LAN → Discover → Servizi |
| Host con porte aperte | TCP connect scan | Porta, servizio, stato | LAN → Scan |

**Vendor MAC:** lookup OUI (database IEEE + bundle OT + voci apprese) — tabella in LAN → Discover.

### 6.3 OT / Industriale

| Dispositivo | Metodo | Porte / protocollo | Dove in UI |
|-------------|--------|-------------------|------------|
| Weintek HMI | UDP broadcast HMI Search | 59999→60000, 10275, 20249 | OT → Impianto |
| eWON Cosy/Flexy | UDP IPCONF + OUI HMS | 1507/1506, 1234, 4242 | OT → Impianto |
| PLC / SCADA | TCP port scan profilo industrial | 502 Modbus, 4840 OPC UA, 102 S7, … | OT → Impianto (con IP target) |
| Gateway OT | Porte gestione | 80, 443, 21, 5900, 8000 | Incluso in discovery device |

### 6.4 Video sorveglianza

| Vendor | Metodo | Porta |
|--------|--------|-------|
| ONVIF (generico) | WS-Discovery | UDP 3702 |
| Hikvision | SADP | UDP 37020 |
| Dahua | DHDiscover | UDP 37810 |
| Vari | mDNS `_onvif._tcp`, `_rtsp._tcp` | 5353 |
| Vari | SSDP/UPnP | 1900 |

### 6.5 Storage NAS

| Vendor | Metodo | Porta |
|--------|--------|-------|
| Synology | Discovery protocol | UDP 9997 |
| QNAP | Qfinder | UDP 7777 |
| ASUSTOR | ADM search | UDP 8888–8889 |
| Netgear ReadyNAS | RAIDar | UDP 22081 |
| Generico | WS-Discovery, mDNS, SSDP | 3702, 5353, 1900 |

### 6.6 Stampanti

| Tipo | Vendor | Metodo | Porta |
|------|--------|--------|-------|
| Scontrini / fiscali | Epson | ENPC | UDP 3289 |
| Etichette industriali | Zebra | Link-OS discovery | UDP 4201 |

### 6.7 Flusso logico di identificazione

```
Cavo collegato
    │
    ├─► LLDP/CDP/MNDP (passivo/attivo) ──► «Chi è lo switch e su quale porta sono?»
    │
    ├─► ARP scan ──► «Quali IP/MAC ci sono?» + OUI vendor
    │
    ├─► Wizard Up/Down ──► «Quale MAC è questo cavo specifico?»
    │
    └─► Discovery specializzata (OT / camere / NAS / stampanti)
            └─► Probe UDP/TCP vendor-specifici
```

---

## 7. Interfaccia web — layout e scelte di design

### 7.1 Filosofia UX

| Scelta | Motivazione |
|--------|-------------|
| **Mobile-first** | Il tecnico usa il telefono, non il TFT |
| **PWA** (`manifest.webmanifest`) | Aggiungibile a home screen; tema scuro |
| **Nessuna app nativa** | Zero installazione; solo browser |
| **Navigazione a due livelli** | 4 macro-aree + sotto-tab scrollabili |
| **Dark theme** | Leggibilità in ambiente industriale / cabine |
| **Italiano** | UI e messaggi per operatori italiani |
| **Azioni con feedback** | Pulsanti Ferma, messaggi di stato, disable durante scan |
| **Export sempre vicino** | JSON/CSV accanto a ogni scan |

### 7.2 Struttura navigazione (v0.19)

**Barra primaria (4 gruppi):**

| Gruppo | Sotto-pannelli | Default |
|--------|----------------|---------|
| **Monitor** | Stato, Ping, MTU | Stato |
| **LAN** | Discover, Sniff, Scan | Discover |
| **OT** | Impianto, MikroTik, Camere, NAS, Stampanti | Impianto |
| **Sistema** | Hotspot, Config, Spegnimento | Hotspot |

URL diretto a un pannello: `http://192.168.50.1:8080/?panel=plant`

### 7.3 Dettaglio pannelli

#### Monitor → Stato
- Card: Hotspot telefono, Link, Rete, Switch, Sistema
- Aggiornamento automatico periodico
- Report email stato / completo

#### Monitor → Ping
- Fino a 3 host in parallelo con grafico canvas RTT (SSE)
- Suite ICMP completa
- Host adhoc temporaneo

#### Monitor → MTU
- Path MTU discovery con stream eventi

#### LAN → Discover
- Wizard Up/Down guidato
- Scansione ARP rapida
- Servizi mDNS/SSDP/L2
- Tabella OUI searchable

#### LAN → Sniff
- Passive check multi-protocollo
- Durata e host SNMP configurabili

#### LAN → Scan
- Porte standard e custom
- DNS + gateway
- Hint verso OT → Impianto per protocolli industriali

#### OT → Impianto
- IP target opzionale
- Discovery Weintek + eWON
- Profilo porte industriali su target
- Chip anteprima porte OT

#### OT → MikroTik / Camere / NAS / Stampanti
- Scan dedicato per categoria
- Export JSON/CSV

#### Sistema → Hotspot
- Stato SSID, URL, password
- Modifica parametri Wi‑Fi + riavvio hotspot

#### Sistema → Config
- Form guidato con spiegazioni per campo
- YAML avanzato (textarea)
- Export / import file
- Salvataggio con restart asincrono servizio

#### Sistema → Spegnimento
- Arresto controllato con conferma
- Feedback su TFT

### 7.4 Pattern UI ricorrenti

- **Primary button** — azione principale (verde `#50c878`)
- **Danger button** — stop scan / spegnimento
- **Export group** — JSON + CSV affiancati
- **Chip list** — anteprima porte profilo scan
- **Device block** — scheda per ogni device trovato (titolo, IP, MAC, porte)
- **Log scrollabile** — output testuale compatto

---

## 8. Protocolli e discovery

### 8.1 Protocolli L2 / neighbor

| Protocollo | Modalità | Dettaglio |
|------------|----------|-----------|
| LLDP | Passivo (lldpd) | TLV base + LLDP-MED/PoE |
| CDP | Passivo (lldpd) | Da switch Cisco |
| MNDP | Attivo | UDP 5678 refresh + listen |
| STP/RSTP/MSTP | Sniff | BPDU |
| LACP | Sniff | Multicast 01:80:c2:00:00:02 |
| VLAN/ISL/VTP | Sniff | 802.1Q, ISL, VTP Cisco |
| IGMP | Sniff | Multicast IPv4 |
| FDP | Probe | Ethertype 0x2000 (rilevamento, no parser TLV) |
| EDP | Probe | Ethertype 0xEEEE |
| LLTD | Probe | Ethertype 0x88D9 |

### 8.2 Protocolli L3 / servizi

| Protocollo | Porta | Modalità |
|------------|-------|----------|
| mDNS | UDP 5353 | Attivo |
| SSDP/UPnP | UDP 1900 | Attivo (239.255.255.250) |
| SNMP | UDP 161 (GET), 162 (check) | Attivo |
| DHCP Opt 82 | UDP 67/68 | Sniff |
| ARP | L2 | Attivo (arp-scan) |

### 8.3 OT / Industriale

| Protocollo | Porta/trasporto |
|------------|-----------------|
| Modbus TCP | TCP 502 |
| OPC UA | TCP 4840 |
| S7comm | TCP 102 |
| MQTT | TCP 1883 / 8883 |
| EtherNet/IP | TCP 44818 |
| PROFINET | TCP 34962–34964 |
| BACnet/IP | UDP/TCP 47808 |
| DNP3 | TCP 20000 |
| IEC 60870-5-104 | TCP 2404 |
| CODESYS | TCP 11740, 2455 |
| Weintek HMI Search | UDP 59999→60000, 10275, 20249 |
| eWON IPCONF | UDP 1507 / 1506 |

### 8.4 Video / NAS / Stampanti

Vedi sezioni casi d'uso 5.9–5.10.

### 8.5 Catalogo API

Elenco completo protocolli con note: `GET /api/discover/protocols`

---

## 9. Esportazione dati e report

### 9.1 Export file (browser)

Disponibile sui pannelli con scan attivo. Generazione **client-side** (JavaScript).

| Formato | Contenuto | Nome file |
|---------|-----------|-----------|
| **JSON** | Risposta API completa + metadati | `ndp-<pannello>-<timestamp>.json` |
| **CSV** | Righe tabellari device/host | `ndp-<pannello>-<timestamp>.csv` |

Pannelli con export: discover-scan, discover-services, passive, mikrotik, plant, cameras, nas, printers.

### 9.2 Report email (`mailto:`)

| Sezione | API | Pulsante |
|---------|-----|----------|
| Stato | `?section=status` | Report stato |
| Completo | `?section=all` | Report completo |
| Ping | `?section=ping` | Report ping |
| Discover | `?section=discover` | Report discover |
| Porte | `?section=scan` | Report porte |
| DNS | `?section=network` | Report DNS |

Il telefono apre l'app mail precompilata — **nessun server SMTP** sul probe.

### 9.3 Export configurazione

| Azione | Dove |
|--------|------|
| Download YAML | Sistema → Config → Esporta YAML |
| Import YAML | Sistema → Config → Importa file |
| Backup email | 📧 Invia backup mail |

### 9.4 CLI / JSON

```bash
ndp --once --json
sudo ndp discover scan --json --save /tmp/scan.json
sudo ndp discover updown --json
ndp hotspot status --json
```

---

## 10. Configurazione del device

### 10.1 File di configurazione

| File | Ruolo |
|------|-------|
| `/etc/ndp/config.yaml` | Config attiva |
| `/etc/ndp/config.yaml.example` | Template con tutti i commenti |
| `ndp/config/default.yaml` | Sorgente nel repo |

### 10.2 Sezioni principali

| Sezione | Contenuto |
|---------|-----------|
| `interface` | Interfaccia monitorata (eth0) |
| `poll_interval_*` | Frequenza polling motore |
| `lldp` | Cache TTL neighbor |
| `ui` | Display TFT, GPIO, splash, rotazione |
| `web` | Server HTTP (host, porta) |
| `wifi_hotspot` | SSID, password, IP, DHCP, canale, paese |
| `discovery` | Wizard Up/Down, MNDP, passive listen |
| `ping` | Count, timeout, packet size, target custom |
| `logging` | Livello log |
| `console` | Output journal periodico |

### 10.3 Modifica da Web UI

**Sistema → Config:**
1. Form guidato — ogni campo con spiegazione
2. **Salva configurazione** — scrive YAML + restart asincrono `ndp` (non blocca UI)
3. YAML avanzato — modifica diretta per utenti esperti

**Nota:** salvataggio da form può rimuovere commenti YAML; per backup commentato usare export.

### 10.4 Profilo consigliato (produzione)

```yaml
interface: eth0

ui:
  enabled: true
  input: none
  auto_cycle_seconds: 8
  hint_edge: none
  content_margin_side: 0

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

discovery:
  disconnect_wait_seconds: 8
  flush_arp_before_second_scan: true
  verify_replug: true
  mndp_listen_seconds: 6
  passive_listen_seconds: 3

ping:
  count: 2
  timeout_seconds: 3
  packet_size: 56
```

### 10.5 Restart dopo modifiche

```bash
sudo systemctl restart ndp-hotspot ndp
```

Oppure attendere il restart automatico dopo salvataggio da Web UI.

---

## 11. Hotspot Wi‑Fi e accesso telefono

### 11.1 Parametri default

| Parametro | Valore |
|-----------|--------|
| SSID | `NDP-XXXX` (prefisso + ultime 4 cifre MAC wlan0) |
| Password | `ndp-probe` (WPA2, min 8 caratteri) |
| IP probe | `192.168.50.1` |
| DHCP | `192.168.50.10` – `192.168.50.50` |
| Canale | 6 (2.4 GHz) |
| Paese | IT |
| URL telefono | `http://192.168.50.1:8080/` |

### 11.2 Stack rete

- **hostapd** — access point su wlan0
- **dnsmasq** — DHCP per client Wi‑Fi
- **Non** NetworkManager AP mode
- `wpa_supplicant@wlan0` disabilitato dall'install script

### 11.3 Modifica da Web UI

**Sistema → Hotspot:**
- Visualizza stato corrente (SSID, URL, client)
- Modifica password, canale, paese
- **Salva e riavvia hotspot**

### 11.4 CLI hotspot

```bash
ndp hotspot status
ndp hotspot status --json
sudo ndp hotspot restart
sudo systemctl restart ndp-hotspot
```

### 11.5 Scenari alternativi

| Scenario | Quando | URL |
|----------|--------|-----|
| Hotspot NDP (consigliato) | Sempre in campo | `http://192.168.50.1:8080/` |
| Wi‑Fi cliente | Telefono e probe sulla stessa LAN | `http://<IP-eth0>:8080/` |
| Solo Ethernet | Hotspot disabilitato | IP eth0 su TFT Home |

Guida dettagliata: [MANUALE-ACCESSO-TELEFONO.md](MANUALE-ACCESSO-TELEFONO.md)

---

## 12. Spegnimento controllato

### 12.1 Da Web UI

1. **Sistema → Spegnimento**
2. Leggi avviso
3. **Spegni NDP** → conferma

### 12.2 Sequenza interna

```
idle → in_progress (3 s) → stopping_services → powering_off → systemctl poweroff
```

| Fase | Azione |
|------|--------|
| `in_progress` | Countdown 3 secondi |
| `stopping_services` | Stop hotspot (`hostapd`/`dnsmasq`) |
| `powering_off` | `systemctl poweroff` |

### 12.3 Feedback

- **Web UI:** messaggio di stato aggiornato
- **TFT:** schermata «SPEGNIMENTO — Non scollegare l'alimentazione»

### 12.4 API

```bash
curl -s http://127.0.0.1:8080/api/system/shutdown
curl -X POST http://127.0.0.1:8080/api/system/shutdown \
  -H 'Content-Type: application/json' \
  -d '{"confirm": true}'
```

---

## 13. Display TFT (UI locale)

### 13.1 Schermate in rotazione (`ui.input: none`)

| # | Schermata | Contenuto |
|---|-----------|-----------|
| 1 | **Home** | Link, IP eth0, hint hotspot/Web |
| 2 | **Switch** | Neighbor LLDP/CDP/MNDP, porta, VLAN |
| 3 | **Network** | Gateway, DNS, dettagli IP |
| 4 | **Ping** | Risultati suite ICMP |
| 5 | **System** | Hostname, uptime, temperatura, versione |

Intervallo rotazione: `ui.auto_cycle_seconds` (default 8 s).

### 13.2 Splash e warmup

All'avvio: splash «Network Diagnostic Probe» finché font, framebuffer e prima scansione probe non sono pronti (`splash_enabled`, `warmup_on_start`).

### 13.3 Spegnimento

Overlay dedicato con messaggio di stato durante la sequenza poweroff.

---

## 14. Manutenzione e aggiornamenti

### 14.1 Checklist periodica

- [ ] `systemctl status ndp ndp-hotspot lldpd` — tutti active
- [ ] `ndp hotspot status` — SSID raggiungibile
- [ ] `curl http://127.0.0.1:8080/api/version` — versione attesa
- [ ] Test display: `ndp test display --color cycle`
- [ ] Test ping: `ndp test ping`
- [ ] Verifica spazio SD: `df -h`
- [ ] Log recenti: `journalctl -u ndp -n 50 --no-pager`

### 14.2 Backup configurazione

```bash
sudo cp /etc/ndp/config.yaml /etc/ndp/config.yaml.bak.$(date +%Y%m%d)
```

Oppure export da Web UI → Config.

### 14.3 Reset configurazione

```bash
sudo cp /etc/ndp/config.yaml.example /etc/ndp/config.yaml
sudo systemctl restart ndp-hotspot ndp
```

### 14.4 Log utili

```bash
journalctl -u ndp -f
journalctl -u ndp-hotspot -f
journalctl -u lldpd -f
```

### 14.5 Test automatici (sviluppo)

```bash
cd /opt/ndp   # o repo clone
source venv/bin/activate
pytest -q
```

### 14.6 Palestra di test (progetto separato)

Per test OT/IT senza hardware reale: progetto **`ndp-lab`** (Raspberry dedicato che emula Weintek, eWON, Modbus, stampanti, ecc.). Repo separato dal prodotto NDP.

---

## 15. Risoluzione problemi

### 15.1 Telefono non vede NDP-XXXX

| Causa | Soluzione |
|-------|-----------|
| Hotspot disabilitato | `wifi_hotspot.enabled: true`, restart `ndp-hotspot` |
| Servizio fermo | `sudo systemctl restart ndp-hotspot` |
| wlan0 assente | Verificare modulo Wi‑Fi Pi 3 |
| Conflitto wpa_supplicant | Re-run `install.sh` o disable manuale |

### 15.2 Web UI non risponde

| Causa | Soluzione |
|-------|-----------|
| URL errato con hotspot | Usare `192.168.50.1`, non IP eth0 |
| `web.enabled: false` | Abilitare in config |
| Servizio ndp fermo | `sudo systemctl restart ndp` |
| Porta occupata | Cambiare `web.port` o liberare :8080 |

### 15.3 LLDP / Switch vuoto

| Causa | Soluzione |
|-------|-----------|
| LLDP disabilitato sullo switch | Abilitare LLDP sulla porta |
| lldpd fermo | `sudo systemctl restart lldpd` |
| Cavo down | Verificare link in Stato |
| Attesa | LLDP può richiedere 30–60 s |

### 15.4 Discover / Scan falliscono

- Il servizio `ndp` gira come **root** — privilegi OK
- Diagnostica usa **eth0** — verificare cavo sulla rete giusta
- ARP scan richiede subnet raggiungibile via eth0

### 15.5 Salvataggio config bloccato

Da v0.18.4: restart servizio è **asincrono** — il pulsante non resta su «Salvataggio...». Se persiste: `journalctl -u ndp -n 30`.

### 15.6 Display nero o colori errati

```bash
ndp test display --color cycle
```

Verificare `ui.framebuffer`, `rgb565_bgr`, `rgb565_swap_bytes` in config. Reinstallare driver: `--with-display`.

---

## 16. Riferimenti rapidi

### Comandi CLI

```bash
ndp --once                          # Stato probe
ndp --once --json                   # JSON completo
sudo ndp discover scan               # ARP scan
sudo ndp discover updown             # Wizard Up/Down
ndp hotspot status                   # Stato hotspot
ndp test ping                        # Test suite ping
ndp test display --color cycle       # Test TFT
```

### URL

| Contesto | URL |
|----------|-----|
| Hotspot (default) | `http://192.168.50.1:8080/` |
| LAN cliente | `http://<IP-eth0>:8080/` |
| API versione | `http://192.168.50.1:8080/api/version` |

### File chiave

| File | Descrizione |
|------|-------------|
| `/etc/ndp/config.yaml` | Configurazione |
| `/opt/ndp/` | Installazione software |
| `docs/MANUALE-ACCESSO-TELEFONO.md` | Guida telefono |
| `docs/DOCUMENTAZIONE.md` | Questo documento |
| `ndp/config/default.yaml` | Template commentato |

### Versioni recenti (changelog sintetico)

| Versione | Contenuto principale |
|----------|---------------------|
| 0.19.1 | OT → Impianto (refactor UI industriale) |
| 0.19.0 | Discovery stampanti Epson/Zebra |
| 0.18.4 | Spegnimento controllato + fix save config |
| 0.18.3 | Port/VLAN neighbor + config discovery MNDP/passive |
| 0.12 | MTU discovery |
| 0.10 | Hotspot Wi‑Fi integrato |
| 0.7 | Display read-only + web mobile |

---

*Documento generato per NDP v0.19.1 — aggiornare ad ogni release significativa.*
