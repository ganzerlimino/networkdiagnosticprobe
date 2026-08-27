# NDP — Accesso dal telefono

Guida rapida per controllare il probe dal browser del cellulare (Stato, Ping, Discover, Scan, Config).

---

## Cosa ti serve

| Requisito | Note |
|-----------|------|
| NDP installato e attivo | `sudo systemctl status ndp` → `active (running)` |
| Web abilitato | In `/etc/ndp/config.yaml`: `web.enabled: true` (default da v0.7) |
| **Stessa rete IP** del probe | Telefono e Raspberry Pi devono raggiungersi a livello LAN |
| Browser sul telefono | Chrome, Safari, Firefox — nessuna app da installare |

**Indirizzo da aprire:**

```
http://<IP-DELLA-PI>:8080/
```

Esempio: `http://192.168.1.42:8080/`

> Sul display TFT, in basso, compare spesso `Telefono :8080` come promemoria della porta.

---

## Wi‑Fi e hotspot — cosa c’è oggi e cosa no

| Funzione | Stato |
|----------|--------|
| Web UI su porta **8080** | ✅ Disponibile |
| Probe su **Ethernet** (`eth0`) | ✅ Uso normale in campo |
| Telefono sulla **stessa LAN** del probe | ✅ Modo consigliato oggi |
| **Hotspot Wi‑Fi integrato** sulla Pi (`wifi_hotspot`) | ❌ **Non ancora implementato** (previsto in roadmap) |

Non esiste ancora una rete `NDP-XXXX` generata dal probe. Per ora il telefono deve collegarsi a una rete esistente che vede anche la Pi.

---

## Scenari pratici (come collegarsi)

### 1. Rete del cliente (il più comune)

```
[Switch/LAN cliente] ──eth0── [NDP Probe]
        │
     [Wi‑Fi cliente] ── [Telefono tecnico]
```

1. Colleghi il probe con il cavo Ethernet alla rete da diagnosticare.
2. Il telefono si collega al **Wi‑Fi della stessa rete** (ufficio, impianto, guest Wi‑Fi se presente).
3. Trovi l’IP del probe (vedi sotto).
4. Apri `http://<IP>:8080/` sul telefono.

Funziona se Wi‑Fi e porta Ethernet del probe sono sulla **stessa subnet** (es. entrambi `192.168.10.0/24`).

---

### 2. Pi con Wi‑Fi già configurato (Raspberry Pi OS)

Se sulla SD hai configurato anche `wlan0` (stesso Wi‑Fi del telefono), puoi usare l’IP Wi‑Fi della Pi invece di quello Ethernet:

```bash
ip -4 addr show wlan0
```

Poi apri quell’IP sulla porta 8080.

---

### 3. Solo Ethernet sul probe, telefono senza Wi‑Fi del cliente

In questo caso **non puoi** usare il telefono finché non condividi una rete con la Pi. Opzioni:

- Chiedere accesso al Wi‑Fi LAN del sito.
- Collegare temporaneamente un **router/AP di servizio** (telefono + probe sulla stessa rete di test).
- Attendere la funzione **hotspot NDP** (futura): la Pi creerà una rete Wi‑Fi dedicata a cui ti colleghi col telefono.

---

## Come trovare l’IP della Pi

| Metodo | Dove |
|--------|------|
| **Display TFT** | Schermata **HOME** → riga `IP` |
| **SSH** (se abilitato) | `hostname -I` sulla Pi |
| **CLI** | `ndp --once` (mostra riepilogo rete) |
| **Router/DHCP** | Lista lease del gateway (se hai accesso) |

Annota l’indirizzo IPv4 (es. `192.168.10.50`), non l’IPv6 se non sei sicuro.

---

## Primo accesso — passo passo

1. Accendi il probe e attendi lo splash (~1–2 minuti al primo avvio).
2. Verifica che il link Ethernet sia **UP** (schermata HOME o Stato).
3. Sul telefono, connetti il **Wi‑Fi della stessa rete**.
4. Apri il browser e digita:

   ```
   http://IP_VISTO_SUL_DISPLAY:8080/
   ```

5. Dovresti vedere **Network Diagnostic Probe** con le tab:
   - **Stato** — link, IP, LLDP
   - **Ping** — grafico live e suite
   - **Discover** — wizard Up/Down
   - **Scan** — porte e DNS/gateway
   - **Config** — file YAML

---

## Verifica rapida dalla Pi (se hai SSH)

```bash
sudo systemctl status ndp
curl -s http://127.0.0.1:8080/api/version
```

Risposta attesa (esempio):

```json
{"version":"0.9.0","interface":"eth0"}
```

Se funziona in locale ma non dal telefono, il problema è quasi sempre **rete diversa** o **firewall**.

---

## Problemi frequenti

### “Impossibile aprire la pagina” / timeout

| Causa probabile | Cosa fare |
|-----------------|-----------|
| Telefono su rete diversa | Stesso Wi‑Fi/VLAN del probe; controlla IP e subnet |
| IP sbagliato | Rileggi IP dalla schermata HOME del TFT |
| `web.enabled: false` | In `/etc/ndp/config.yaml` metti `web.enabled: true`, poi `sudo systemctl restart ndp` |
| Servizio fermo | `sudo systemctl restart ndp` |
| Firewall sulla Pi | Su Lite di solito non c’è; se hai `ufw`: `sudo ufw allow 8080/tcp` |

### La pagina si apre ma i dati non si aggiornano

- Attendi qualche secondo (aggiornamento automatico ogni 5 s sulla tab Stato).
- Controlla che il cavo Ethernet sia collegato (link UP).

### Discover / Scan non funzionano

- Richiedono privilegi di rete sulla Pi (il servizio `ndp` gira già come root).
- Su alcune reti guest, **ARP scan** o **ping** possono essere filtrati dal firewall del cliente.

---

## Configurazione consigliata (`/etc/ndp/config.yaml`)

```yaml
ui:
  enabled: true
  input: none
  auto_cycle_seconds: 8

web:
  enabled: true
  host: "0.0.0.0"    # ascolta su tutte le interfacce
  port: 8080

wifi_hotspot:
  enabled: false     # non ancora attivo — lasciare false
```

Dopo ogni modifica al config:

```bash
sudo systemctl restart ndp
```

---

## Segnalibro sul telefono

Quando hai trovato l’IP, salva nei preferiti:

- **Nome:** NDP probe
- **URL:** `http://192.168.x.x:8080/`

Se il probe riceve IP via DHCP e cambia tra un sito e l’altro, conviene controllare l’IP sul display HOME ogni volta.

---

## Prossimo passo: hotspot Wi‑Fi NDP

In roadmap è previsto `wifi_hotspot.enabled: true`: la Pi creerà una rete tipo **NDP-XXXX** e potrai collegare il telefono **direttamente** al probe **senza** Wi‑Fi del cliente.

Fino ad allora: **Ethernet sul probe + telefono sulla stessa LAN**.

---

## Riepilogo in una riga

> Collega il probe al cavo, metti il telefono sul Wi‑Fi della stessa rete, leggi l’IP sul display HOME, apri `http://quell-IP:8080/`.
