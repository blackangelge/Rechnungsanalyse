# Rechnungsanalyse — CLAUDE.md

Selbst gehostetes System zur automatischen KI-Extraktion von Rechnungsdaten.
Läuft auf einem Synology NAS via Docker Compose (Container Manager GUI — kein SSH).

## Architektur

```
Frontend  (Next.js 15, React 19, TypeScript, Tailwind 4)  → Port 3100
Backend   (FastAPI, Python 3.12, SQLAlchemy 2, Alembic)   → Port 8100
Datenbank (PostgreSQL 16)                                  → intern
```

### Datenpfade (auf dem NAS-Host)

| Pfad | Inhalt |
|---|---|
| `/volume1/docker/_rechnungsanalyse/db/` | PostgreSQL-Datenbankdateien |
| `/volume1/docker/_rechnungsanalyse/storage/` | Kopierte Rechnungs-PDFs (`{Firma_Jahr}/{id}.pdf`) |
| `/volume1/docker/_rechnungsanalyse/import/` | Quell-PDFs zum Import (`IMPORT_BASE_PATH`) |
| `/volume1/docker/_rechnungsanalyse/python_env/` | Python venv (persistent) |
| `/volume1/docker/_rechnungsanalyse/node_modules/` | npm-Pakete (persistent) |

### Wichtige Konventionen

- **`redirect_slashes=False`** in `main.py` → alle Router-Routen **ohne** abschließenden `/` registrieren (`@router.get("")` statt `@router.get("/")`), sonst 404
- **Kein Docker CLI** — der Nutzer verwendet ausschließlich den Synology Container Manager (GUI)

---

## Backend (`backend/`)

### Struktur

```
app/
├── main.py                 # FastAPI-Instanz, Router-Registrierung, CORS
│                           # redirect_slashes=False!
├── config.py               # Settings via pydantic-settings (aus .env)
├── database.py             # SQLAlchemy Session-Factory
├── models/                 # SQLAlchemy-ORM-Modelle
│   ├── document.py         # + Properties: total_amount, invoice_number, supplier_name
│   ├── import_batch.py
│   ├── ai_config.py
│   ├── image_settings.py
│   ├── invoice_extraction.py  # + supplier_id FK → suppliers
│   ├── order_position.py
│   ├── supplier.py         # Lieferanten-Stammdaten (Deduplication)
│   └── system_prompt.py    # Systemprompts für KI-Extraktion
├── schemas/                # Pydantic-Schemas (Request/Response)
│   ├── document.py         # DocumentRead, DocumentListRead (+Extraktion-Summary),
│   │                       #   DocumentDetail, DocumentCommentUpdate
│   └── import_batch.py     # ImportBatchCreate (inkl. analyze_after_import,
│                           #   system_prompt_id, delete_source_files)
├── crud/                   # Datenbankoperationen (je Modell eine Datei)
│   ├── document.py         # get_all_filtered mit joinedload(extraction)
│   ├── import_batch.py
│   ├── supplier.py         # find_or_create (IBAN → VAT-ID → Name)
│   └── system_prompt.py
├── routers/                # API-Endpunkte
│   ├── imports.py          # GET/POST /api/imports, DELETE löscht auch Dateien
│   │                       # _import_then_analyze, _delete_source_files
│   ├── documents.py        # GET /api/documents, POST /analyze, GET/{id}, preview, comment
│   │                       # _KI_IO_EXECUTOR, _analyze_single (phasenbasiert)
│   ├── ai_configs.py       # CRUD /api/ai-configs, POST set-default
│   ├── settings.py         # GET/PUT /api/settings/image-conversion
│   │                       # GET /api/settings/paths
│   │                       # CRUD /api/settings/system-prompts
│   ├── sse.py              # GET /api/imports/{id}/progress (Server-Sent Events)
│   └── items.py            # CRUD /api/items (Platzhalter)
└── services/
    ├── import_service.py   # Import-Orchestrierung, parallel (Semaphore 4), kein KI
    ├── ai_service.py       # KI-Extraktion via OpenAI-kompatibler Vision-API
    │                       # Neues verschachteltes JSON-Format + Normalisierung
    └── pdf_service.py      # PDF → Bilder (pypdfium2), Seitenanzahl (pypdf)
alembic/
└── versions/
    ├── 0001_initial.py     # Alle Basistabellen
    ├── 0002_system_prompts.py
    └── 0003_supplier.py    # suppliers-Tabelle + supplier_id FK auf invoice_extractions
```

### Import-Ablauf

1. User gibt Firmenname + Jahr an (kein Ordnerpfad — wird aus `IMPORT_BASE_PATH` genommen)
2. Sicherheitscheck: Pfad muss unter `IMPORT_BASE_PATH` liegen
3. Alle `.pdf`/`.PDF` im Import-Ordner werden gefunden
4. Speicherziel: `STORAGE_PATH/{Firma}_{Jahr}/{id}.pdf`
5. Pro PDF parallel (max. 4): DB-Datensatz anlegen → kopieren → Seitenanzahl erfassen
6. Fortschritt wird via SSE an das Frontend gestreamt
7. Optional nach Import: Quelldateien löschen und/oder KI-Analyse starten

### Import-Optionen (`ImportBatchCreate`)

| Feld | Typ | Beschreibung |
|---|---|---|
| `analyze_after_import` | `bool` | KI-Analyse direkt nach Import starten |
| `ai_config_id` | `int\|None` | Spezifische KI-Konfiguration (None = Standard) |
| `system_prompt_id` | `int\|None` | Spezifischer Systemprompt (None = Standard) |
| `delete_source_files` | `bool` | Original-PDFs aus Import-Ordner löschen nach erfolgreichem Kopieren |

**Task-Pfade in `imports.py`:**
- `analyze_after_import=True` → `_import_then_analyze(batch_id, import_folder, ai_config_id, system_prompt_id, delete_source_files)`
- `analyze_after_import=False, delete_source_files=True` → `_import_and_delete(batch_id, import_folder)`
- Sonst → `run_import(batch_id)`

`_delete_source_files()` löscht nur Dateien, für die ein DB-Eintrag mit `stored_filename` existiert (kein Blind-Delete).

### Import löschen

`DELETE /api/imports/{id}` löscht:
- PDF-Dateien aus `STORAGE_PATH/{Firma}_{Jahr}/`
- Leere Unterordner werden ebenfalls entfernt
- DB-Einträge (Batch → Dokumente → Extraktionen → Positionen via CASCADE)

### KI-Extraktion (`services/ai_service.py`)

- Unterstützt jede OpenAI-kompatible Vision-API (LM Studio, Ollama, OpenAI, etc.)
- Endpunkt: `{api_url}/chat/completions`
- Alle PDF-Seiten werden in **einer** Anfrage gesendet (als `image_url`-Parts)
- **Kein `"detail": "high"`** in image_url → LM-Studio-Kompatibilität
- **`"stream": False`** explizit gesetzt → verhindert channelId-Warnungen in LM Studio
- System-Prompt: aus DB (Standard-Prompt) oder explizit per `system_prompt_id`
- **Niemals `raise_for_status()`** — alle HTTP-Fehler (429/503/500/Timeout/Netzwerk)
  werden als `({}, [], "KI-Fehler: ...")` zurückgegeben, nie als Exception

#### Verschachteltes KI-JSON-Format (neu)

Die KI soll Daten in diesem verschachtelten Format zurückgeben:

```json
{
  "lieferant": {
    "name": "...",
    "adresse": "...",
    "steuernummer": "...",
    "ustid": "...",
    "hrb": "...",
    "bankverbindung": { "bank": "...", "iban": "...", "bic": "..." }
  },
  "rechnungsdaten": {
    "rechnungsnummer": "...",
    "rechnungsdatum": "...",
    "lieferdatum": "..."
  },
  "positionen": [
    { "bezeichnung": "...", "menge": 1, "einheit": "...", "einzelpreis": 0.0, "gesamtpreis": 0.0, "steuersatz": 19.0 }
  ],
  "zahlungsinformationen": {
    "nettobetrag": 0.0,
    "steuerbetrag": 0.0,
    "gesamtbetrag_brutto": 0.0,
    "waehrung": "EUR",
    "faelligkeitsdatum": "...",
    "zahlungsziel_tage": 0,
    "skonto_prozent": 0.0
  }
}
```

**Auto-Detection:** Enthält das geparste JSON `lieferant`, `rechnungsdaten` oder `zahlungsinformationen` → neues Format (`_map_new_format()`). Sonst → altes flaches Format (`_clean_flat_fields()`).

#### Normalisierung-Hilfsfunktionen

| Funktion | Beschreibung |
|---|---|
| `_normalize_decimal_commas(obj)` | Rekursiv: `"1.234,56 €"` → `1234.56`, `"719,99"` → `719.99` — strips `€$£¥` vorher |
| `_date(val)` | `"25.03.2025"` / `"2025-03-25"` / `"03/25/2025"` → `"2025-03-25"` (ISO); unbekanntes Format → `None` (verhindert DB-Fehler) |
| `_num(val)` | String oder Zahl → `float\|None` |
| `_str(val)` | Beliebig → `str\|None` |

### KI-Analyse: Phasenbasierter Ansatz (`routers/documents.py`)

**Problem:** Wenn `_analyze_single` die DB-Session während PDF-Rendering + KI-API-Aufruf (Minuten) offen hält, sättigt das den gemeinsamen uvicorn-Thread-Pool → GET-Endpunkte (Dokumente, Imports) timeoutten.

**Lösung:** Dedizierter `_KI_IO_EXECUTOR` (ThreadPoolExecutor, Prefix `ki_pdf`) + phasenbasierter Ablauf:

| Phase | Inhalt | DB-Session |
|---|---|---|
| 1 | Alle Daten aus DB lesen, in lokale Variablen kopieren | offen → sofort schließen |
| 2 | PDF → Bilder via `_run_ki_io()` (blockierendes IO) | geschlossen |
| 3 | KI-API-Aufruf via async httpx | geschlossen |
| 4 | Ergebnisse in DB schreiben (neue Session) | offen → schließen |

`_set_error(doc_id, message)` — Hilfsfunktion, öffnet eigene Session nur zum Setzen des Fehlerstatus.

**Fehlerbehandlung:** Bei fehlgeschlagenem DB-Commit (z.B. ungültiges Datum) → `db.rollback()` + erneuter Versuch; bei erneutem Fehler → `_set_error()` mit frischer Session.

### Lieferanten-Deduplication (`crud/supplier.py`)

`find_or_create()` sucht in dieser Priorität:
1. IBAN (stärkster Identifier)
2. VAT-ID (USt-IdNr.)
3. Name (Fallback)

Vorhandene Felder werden nur überschrieben, wenn der neue Wert besser (nicht leer) ist.
`supplier_id` wird in `invoice_extractions` gespeichert.

### Umgebungsvariablen (`.env`)

```
POSTGRES_USER=appuser
POSTGRES_PASSWORD=...
POSTGRES_DB=rechnungsanalyse
DATABASE_URL=postgresql://appuser:...@db:5432/rechnungsanalyse
IMPORT_BASE_PATH=/volume1/docker/_rechnungsanalyse/import
STORAGE_PATH=/volume1/docker/_rechnungsanalyse/storage
```

### Wichtige Abhängigkeiten

```
fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary
httpx          # KI-API-Aufrufe
pypdfium2      # PDF → Bilder (kein Poppler nötig)
pypdf          # Seitenanzahl auslesen
Pillow         # Bildbearbeitung / Base64
sse-starlette  # Server-Sent Events
pydantic-settings
```

---

## Frontend (`frontend/`)

### Struktur

```
src/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                        # Redirect zu /dashboard
│   ├── dashboard/page.tsx              # Übersicht aller Import-Batches
│   ├── belege/page.tsx                 # Alle Dokumente, Filter, KI-Analyse starten
│   │                                   # KI-Rohdaten-Ansicht + Infos-Ansicht (50/50)
│   ├── imports/
│   │   ├── new/page.tsx                # Neuen Import starten
│   │   └── [id]/page.tsx               # Import-Detail mit Dokumentenliste + PDF-Vorschau
│   └── settings/
│       ├── ai/page.tsx                 # KI-Konfigurationen verwalten
│       ├── prompts/page.tsx            # Systemprompts verwalten
│       └── image/page.tsx             # Bildkonvertierungseinstellungen
├── components/
│   ├── Nav.tsx                         # Links: Dashboard, Belege, Neuer Import,
│   │                                   #   KI-Einstellungen, Systemprompts, Bildeinstellungen
│   ├── dashboard/BatchTable.tsx
│   ├── dashboard/FilterBar.tsx
│   ├── imports/ImportForm.tsx          # Firma + Jahr + Pfad-Vorschau (aus API)
│   │                                   # Optionen: Quelldateien löschen,
│   │                                   #   KI-Analyse nach Import (mit KI-Config + Prompt)
│   ├── imports/DocumentsTable.tsx
│   ├── imports/ProgressPanel.tsx       # SSE + initialTotal/initialProcessed Fallback
│   ├── imports/DebugWindow.tsx
│   └── settings/AIConfigForm.tsx
└── lib/
    ├── api.ts      # axios-Client, alle API-Typen und -Funktionen
    └── sse.ts      # SSE-Client für Fortschritts-Updates
```

### Navigation (`Nav.tsx`)

```
/dashboard        Dashboard
/belege           Belege
/imports/new      Neuer Import
/settings/ai      KI-Einstellungen
/settings/prompts Systemprompts
/settings/image   Bildeinstellungen
```

### API-Client (`src/lib/api.ts`)

- Server-seitig: vollständige URL via `NEXT_PUBLIC_API_URL`
- Client-seitig: leere Basis → Next.js Rewrite-Proxy
- Wichtig: Axios-Calls **mit** trailing Slash (`/api/documents/`) — Next.js Rewrite
  entfernt den Slash, Backend empfängt ohne Slash → passt zu `redirect_slashes=False`

Exports:
- `itemsApi` — Platzhalter
- `aiConfigsApi` — KI-Konfigurationen CRUD
- `importsApi` — Import-Batches CRUD
- `documentsApi` — Dokumente, Analyse, Vorschau, Kommentar
- `imageSettingsApi` — Bildkonvertierungseinstellungen
- `systemPromptsApi` — Systemprompts CRUD
- `importSettingsApi` — Pfade abrufen (`/api/settings/paths`)

### Belege-Seite (`belege/page.tsx`)

- Filter: Firma, Jahr, Status, Betrag von/bis, Seiten von/bis
- Tabelle: Checkbox, ID, Firma, Jahr, Dateiname, Seiten, Betrag, Status, Rechnungsnr., Lieferant, PDF-Link
- Betrag/Rechnungsnr./Lieferant kommen direkt aus `DocumentItem` (Backend liefert Extraktion-Summary mit)
- Aktionsleiste bei Auswahl: KI-Konfiguration + Systemprompt wählen → „KI-Analyse starten"
- Auto-Refresh alle 5 s solange Dokumente mit Status `processing` vorhanden

#### Aktions-Buttons pro Dokument

| Button | Bedingung | Funktion |
|---|---|---|
| **KI** (violett) | Status `done` oder `error` | Zeigt KI-Rohantwort als JSON im Modal-Overlay |
| **Infos** (smaragd) | Status `done` | Wechselt in Infos-Ansicht (50/50 Split) |

#### Infos-Ansicht

- Tabelle verschwindet, wird durch 50/50-Split ersetzt: **Infos links, PDF-iframe rechts**
- Navigationsleiste oben: `← Zur Liste` | `Beleg N / M` | `← Vorherige` | `Nächste →`
- Navigation scrollt automatisch zum Inhalt
- Abschnitte: Lieferant, Bankverbindung, Rechnungsdaten, Zahlungsinformationen, USt-Zusammenfassung, Positionen
- Liest verschachteltes KI-JSON aus `raw_response`; fällt auf flache Extraktionsfelder zurück

#### `fmt()` Währungsformatierung

Behandelt sowohl `number` als auch Strings wie `"719,99 €"`:
- Strips `€$£¥` und Leerzeichen
- Normalisiert `"1.234,56"` → `1234.56`
- Gibt `null` zurück für leere Werte, Original-String bei Parse-Fehler

### Neuer Import (`components/imports/ImportForm.tsx`)

**Import-Optionen:**

| Option | Typ | Beschreibung |
|---|---|---|
| Quelldateien löschen | Checkbox (orange) | Original-PDFs aus Import-Ordner löschen nach erfolgreichem Kopieren |
| Dokumente an KI senden | Checkbox (blau) | KI-Analyse nach Import automatisch starten |
| ↳ KI-Konfiguration | Dropdown | Nur sichtbar wenn KI aktiv; Standard vorgewählt |
| ↳ Systemprompt | Dropdown | Nur sichtbar wenn KI aktiv; Standard-Prompt vorgewählt |

### Bekannte Fallstricke

- **Infinite render loop in `useCallback`**: Nie State-Variablen in Dependency-Array aufnehmen, die innerhalb des Callbacks gesetzt werden. Stattdessen `useRef` verwenden (z.B. `batchLoadedRef` in `/imports/[id]/page.tsx`).
- **LM Studio `channelId`-Warnung**: Entsteht durch `"detail": "high"` in image_url oder fehlendes `"stream": false`. Beides in `ai_service.py` korrekt gesetzt.
- **Dokument bleibt auf „Wird verarbeitet"**: Kann durch fehlgeschlagenen DB-Commit entstehen (z.B. Datum im falschen Format von KI). `_date()` in `ai_service.py` normalisiert alle bekannten Formate → `None` bei unbekanntem Format, verhindert Commit-Fehler.

### Wichtige Abhängigkeiten

```
next 15, react 19, typescript 5, tailwindcss 4, axios
```

---

## Entwicklungs-Workflow

### Code-Änderungen übernehmen

```
Backend  (Python): uvicorn --reload aktiv → Dateiänderung genügt
Frontend (Next.js): next dev aktiv → Dateiänderung genügt

Container-Neustart nur nötig bei:
  - neuen Python-Paketen (requirements.txt)
  - neuen npm-Paketen (package.json)
```

### DB-Migration erstellen

Nur über Container Manager → Backend-Container → Terminal:
```bash
/venv/bin/alembic revision --autogenerate -m "beschreibung"
/venv/bin/alembic upgrade head
```

### Logs einsehen

Container Manager → jeweiliger Container → Protokoll

### Swagger UI

`http://NAS-IP:8100/docs`

---

## Datenmodell (Überblick)

```
ImportBatch  1──n  Document  1──1  InvoiceExtraction  n──1  Supplier
                              1──n  OrderPosition
AIConfig        (referenziert von ImportBatch.ai_config_id)
ImageSettings   (Singleton, globale Bildkonvertierungseinstellungen)
SystemPrompt    (Standard-Prompt für KI-Extraktion)
```

### Migrationen

| Datei | Inhalt |
|---|---|
| `0001_initial.py` | Alle Basistabellen (ai_configs, image_settings, import_batches, documents, invoice_extractions, order_positions) |
| `0002_system_prompts.py` | `system_prompts`-Tabelle |
| `0003_supplier.py` | `suppliers`-Tabelle + `supplier_id` FK auf `invoice_extractions` |

### Import-Status-Flow

```
pending → running → done
                 → error
```

### Dokument-Status-Flow

```
pending → processing → done
                    → error
```
