# Configurazione temi NDP

Guida alla personalizzazione dei colori per **Web UI** (telefono/PC) e **display TFT** del Network Diagnostic Probe.

---

## 1. Panoramica

Un **tema** definisce:

- I colori dell’interfaccia web mobile (`dashboard.html`)
- La palette del display TFT sul Raspberry Pi
- Il nome mostrato nel menu **Config → Lingua e profilo scansione → Tema colori**

NDP include **5 temi predefiniti**. Puoi aggiungere temi **custom** (es. aziendale con i colori del brand) senza modificare il codice sorgente.

| Componente | File di riferimento |
|------------|---------------------|
| Temi inclusi nel pacchetto | `ndp/locale/themes.json` |
| Temi custom (priorità) | `/etc/ndp/locale/themes.json` |
| Tema attivo in configurazione | `config.yaml` → `ui.theme: <id-tema>` |

---

## 2. Come funziona il caricamento

1. NDP legge sempre prima il catalogo **bundled** (`ndp/locale/themes.json`).
2. Se esiste `/etc/ndp/locale/themes.json`, viene **unito** al catalogo:
   - I temi con **nuovo ID** vengono aggiunti.
   - I temi con **ID esistente** vengono aggiornati campo per campo (merge).
   - Il campo `"default"` nel file custom, se presente, sostituisce il default globale.
3. Il menu Config mostra **tutti i temi** disponibili (built-in + custom), con nome tradotto.
4. In Web UI l’anteprima del tema è **immediata** al cambio select; per **salvare** serve **Salva configurazione**.
5. Per il **TFT** serve **Salva** + `sudo systemctl restart ndp`.

---

## 3. Struttura del file `themes.json`

**Schema di riferimento (campo per campo):** [`ndp/locale/themes.schema.json`](../ndp/locale/themes.schema.json) (copia anche in `docs/themes.schema.json`)  
Apri il file in un editor con supporto JSON Schema (VS Code, Cursor) per vedere descrizione e tipo di ogni voce mentre modifichi il tema.

Dopo `install.sh` una copia è in `/etc/ndp/locale/themes.schema.json`.

**Validazione rapida:**

```bash
ndp theme validate
ndp theme validate --file /etc/ndp/locale/themes.json
ndp theme validate --json
```

```json
{
  "version": 1,
  "default": "field-dark",
  "themes": {
    "<id-tema>": { ... }
  }
}
```

### Campi radice

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `version` | numero | Versione schema (attualmente `1`). Riservato per evoluzioni future. |
| `default` | stringa | ID del tema usato se `ui.theme` in config non esiste o non è valido. |
| `themes` | oggetto | Mappa `id-tema` → definizione tema. |

### Regole per l’`id-tema`

- Solo lettere minuscole, cifre e trattini: es. `aziendale`, `acme-blue`, `plant-2024`
- Deve essere **univoco** nel catalogo
- Viene salvato in `config.yaml` come `ui.theme: aziendale`

---

## 4. Definizione di un singolo tema

Ogni voce in `themes` ha questa struttura:

```json
{
  "name": { "it": "...", "en": "...", "de": "..." },
  "color_scheme": "dark",
  "web": { ... },
  "tft": { ... }
}
```

### 4.1 `name` — Nome visualizzato

Oggetto con codici lingua ISO brevi. Compare nel menu a tendina Config.

| Chiave | Esempio |
|--------|---------|
| `it` | `"Aziendale"` |
| `en` | `"Corporate"` |
| `de` | `"Unternehmen"` |

Se manca la lingua corrente, NDP usa `it`, poi `en`, poi il primo valore disponibile.

### 4.2 `color_scheme`

| Valore | Effetto |
|--------|---------|
| `"dark"` | Tema scuro (predefinito per uso campo) |
| `"light"` | Tema chiaro (es. `office-light`) |

Influisce su controlli nativi del browser (`color-scheme` CSS).

---

## 5. Sezione `web` — Interfaccia mobile / browser

Tutti i colori sono stringhe **esadecimali** con `#` e 6 cifre (`#RRGGBB`).

| Campo | Uso nell’interfaccia |
|-------|----------------------|
| `bg` | Sfondo generale pagina |
| `card` | Sfondo pannelli / card |
| `surface` | Sfondo secondario, aree inset |
| `text` | Testo principale |
| `muted` | Testo secondario, didascalie, label deboli |
| `accent` | Colore primario: tab attivi, pulsanti Salva, link, evidenziazioni |
| `accent_text` | Testo **su** sfondo accent (es. testo dentro pulsante verde/blu) |
| `danger` | Pulsante Spegni, errori, stati FAIL |
| `border` | Bordi card, separatori, input |
| `header_alpha` | Opacità barra header sticky (`"0.96"` = 96%) |
| `chart` | Array di 3 colori per grafici ping live |

### Consigli per tema aziendale

- **`accent`**: colore brand (es. blu corporate `#0066cc`)
- **`accent_text`**: bianco `#ffffff` su accent scuro, nero `#000000` su accent chiaro
- **`bg` / `card`**: toni scuri coerenti con brand (non serve copiare il sito web 1:1)
- **Contrasto**: testo `text` su `bg` e `card` deve restare leggibile all’aperto

---

## 6. Sezione `tft` — Display del probe

Colori come array **RGB** `[R, G, B]` con valori interi **0–255**.

| Campo | Uso sul display |
|-------|-----------------|
| `bg` | Sfondo schermate normali |
| `header` | Barra titolo in alto |
| `text` | Testo corpo |
| `muted` | Footer (SSID, IP, stato telefono), hint |
| `accent` | Titolo schermata, valori OK |

### Note TFT

- Il display è piccolo (320×240): pochi colori, alto contrasto.
- Lo **spegnimento** usa una palette rossa **fissa** (non dipende dal tema).
- Dopo modifica tema TFT: `sudo systemctl restart ndp`.

---

## 7. Temi predefiniti

| ID | Nome (IT) | Uso tipico |
|----|-----------|------------|
| `field-dark` | Campo scuro | Default, uso generale |
| `industrial-amber` | Industriale ambra | Ambienti OT / fabbrica |
| `high-contrast` | Alto contrasto | Leggibilità massima |
| `office-light` | Ufficio chiaro | Contesti IT / ufficio |
| `night-vision` | Visione notturna | Bassa luminosità, tonalità rosse |

---

## 8. Esempio: tema aziendale

File di esempio nel repository: `docs/examples/themes-aziendale.example.json` (include `"$schema"` verso lo schema).

Validazione manuale alternativa:

```bash
jsonschema -i /etc/ndp/locale/themes.json /etc/ndp/locale/themes.schema.json
python3 -m json.tool /etc/ndp/locale/themes.json
```

### Passo 1 — Copiare il tema custom

```bash
sudo mkdir -p /etc/ndp/locale
sudo cp docs/examples/themes-aziendale.example.json /etc/ndp/locale/themes.json
```

Il file contiene solo il tema `aziendale` e imposta `"default": "aziendale"`.  
I 5 temi built-in **restano disponibili** (merge automatico).

### Passo 2 — Selezionare il tema

1. Apri Web UI dal telefono → **Config**
2. In **Tema colori** compare **Aziendale**
3. Anteprima immediata → **Salva configurazione**

Oppure in `config.yaml`:

```yaml
ui:
  theme: aziendale
  locale: it
```

### Passo 3 — Applicare al TFT

```bash
sudo systemctl restart ndp
```

(`ndp-hotspot` non serve riavviarlo solo per il tema.)

---

## 9. Export / import (senza marketplace)

Non c’è un “theme market”. Per **condividere** un tema tra probe:

**Export**

```bash
sudo cp /etc/ndp/locale/themes.json ~/backup-tema-aziendale.json
```

**Import** su un altro NDP

```bash
sudo cp backup-tema-aziendale.json /etc/ndp/locale/themes.json
sudo systemctl restart ndp
```

Poi seleziona il tema in Config e salva.

Per **solo un tema** puoi incollare la voce dentro `"themes": { ... }` nel file custom.

---

## 10. API di riferimento

| Endpoint | Contenuto |
|----------|-----------|
| `GET /api/themes` | Catalogo completo + `themes_list` con `{id, name}` localizzati |
| `GET /api/config/schema?locale=it` | Opzioni tema nel form Config |

---

## 11. Risoluzione problemi

| Problema | Causa probabile | Soluzione |
|----------|-----------------|-----------|
| Tema custom non compare in Config | JSON invalido o file non in `/etc/ndp/locale/` | `python3 -m json.tool /etc/ndp/locale/themes.json` |
| Web OK, TFT vecchio tema | Servizio ndp non riavviato | `sudo systemctl restart ndp` |
| Anteprima OK, dopo reload perso | Non salvato in config | **Salva configurazione** |
| Colori web strani | `accent_text` sbagliato su accent | Verificare contrasto accent / accent_text |
| ID tema in config ma fallback a field-dark | Typo in `ui.theme` | ID deve esistere in catalogo merged |

---

## 12. Schema riassuntivo

```
/etc/ndp/locale/themes.json  ──┐
                                 ├── merge ──► catalogo temi ──► /api/themes
ndp/locale/themes.json       ──┘                      │
                                                      ├──► Config (select dinamico)
                                                      ├──► Web UI (applyTheme)
                                                      └──► TFT (tft_palette, restart ndp)

config.yaml: ui.theme ──► ID tema attivo
```

---

*Documento relativo a NDP v0.22+. Per installazione e accesso telefono vedi `docs/MANUALE-ACCESSO-TELEFONO.md`.*
