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
│   └── document.py         # DocumentRead, DocumentListRead (+Extraktion-Summary),
│                           #   DocumentDetail, DocumentCommentUpdate
├── crud/                   # Datenbankoperationen (je Modell eine Datei)
│   ├── document.py         # get_all_filtered mit joinedload(extraction)
│   ├── import_batch.py
│   ├── supplier.py         # find_or_create (IBAN → VAT-ID → Name)
│   └── system_prompt.py
├── routers/                # API-Endpunkte
│   ├── imports.py          # GET/POST /api/imports, DELETE löscht auch Dateien
│   ├── documents.py        # GET /api/documents, POST /analyze, GET/{id}, preview, comment
│   ├── ai_configs.py       # CRUD /api/ai-configs, POST set-default
│   ├── settings.py         # GET/PUT /api/settings/image-conversion
│   │                       # GET /api/settings/paths
│   │                       # CRUD /api/settings/system-prompts
│   ├── sse.py              # GET /api/imports/{id}/progress (Server-Sent Events)
│   └── items.py            # CRUD /api/items (Platzhalter)
└── services/
    ├── import_service.py   # Import-Orchestrierung, parallel (Semaphore 4), kein KI
    ├── ai_service.py       # KI-Extraktion via OpenAI-kompatibler Vision-API
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
6. **Kein KI beim Import** — KI-Analyse wird separat über die Belege-Seite gestartet
7. Fortschritt wird via SSE an das Frontend gestreamt

### Import löschen

`DELETE /api/imports/{id}` löscht:
- PDF-Dateien aus `STORAGE_PATH/{Firma}_{Jahr}/`
- Leere Unterordner werden ebenfalls entfernt
- DB-Einträge (Batch → Dokumente → Extraktionen → Positionen via CASCADE)

### KI-Extraktion

- Unterstützt jede OpenAI-kompatible Vision-API (LM Studio, Ollama, OpenAI, etc.)
- Endpunkt: `{api_url}/chat/completions`
- Alle PDF-Seiten werden in **einer** Anfrage gesendet (als `image_url`-Parts)
- System-Prompt: aus DB (Standard-Prompt) oder explizit per `system_prompt_id`
- Antwort: JSON mit Rechnungsfeldern + `order_positions`-Array
- JSON-Parse-Fallbacks: direkt → Markdown-Codeblock → `{...}`-Suche
- **Niemals `raise_for_status()`** — alle HTTP-Fehler (429/503/500/Timeout/Netzwerk)
  werden als `({}, [], "KI-Fehler: ...")` zurückgegeben, nie als Exception

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
