"""
Import-Service: Orchestriert den gesamten Import-Prozess.

Ablauf für einen Import-Batch:
1. Ordnerpfad validieren
2. Alle PDF-Dateien im Ordner auflisten
3. Für jede PDF (parallel, max. import_concurrency gleichzeitig):
   Phase 1 — DB:  Dokument anlegen      (Session öffnen → commit → sofort schließen)
   Phase 2 — IO:  Datei kopieren         (KEINE DB-Verbindung!)
   Phase 3 — IO:  Seitenanzahl lesen     (KEINE DB-Verbindung!)
   Phase 4 — DB:  Status aktualisieren  (Session öffnen → commit → sofort schließen)
4. Batch-Status abschließen

VERBINDUNGSMANAGEMENT:
  Jede DB-Phase öffnet eine eigene SessionLocal() und schließt sie unmittelbar
  nach dem Commit. Während der IO-Phasen (Kopieren, Seitenanzahl) wird KEINE
  Verbindung gehalten. Das bedeutet: Selbst mit 32 parallelen Tasks belegt das
  System nur wenige gleichzeitige DB-Verbindungen (die DB-Phasen sind Millisekunden,
  das Kopieren dauert Sekunden bis Minuten).

  Pool-Bedarf: ~5 gleichzeitige Verbindungen, unabhängig von der Parallelität.
"""

import asyncio
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import crud
from app.config import settings
from app.database import SessionLocal
from app.services import pdf_service

logger = logging.getLogger(__name__)

# Fallback, falls DB-Einstellung nicht lesbar
CONCURRENCY_DEFAULT = 10

# ── Dedizierter Thread-Pool für Import-IO ─────────────────────────────────────
# GETRENNT vom Standard-Thread-Pool (den uvicorn für HTTP-Requests nutzt).
# Wenn asyncio.to_thread() den Standard-Pool saturiert (32 Datei-Kopier-Threads),
# kann uvicorn keine neuen Requests mehr bearbeiten → ECONNRESET.
# Mit einem eigenen Pool konkurriert der Import NICHT mit dem HTTP-Server.
_IMPORT_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=min(64, (os.cpu_count() or 4) * 8),
    thread_name_prefix="import_io",
)


async def _run_import_io(func, *args):
    """Führt eine blockierende IO-Funktion im dedizierten Import-Thread-Pool aus."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_IMPORT_IO_EXECUTOR, func, *args)


# ─── Pfad-Hilfsfunktionen ────────────────────────────────────────────────────

def validate_import_path(folder_path: str) -> Path:
    """
    Prüft, ob der Pfad unter IMPORT_BASE_PATH liegt und erstellt ihn bei Bedarf.
    Raises ValueError wenn der Pfad außerhalb liegt.
    """
    from pathlib import Path as _Path
    base = _Path(settings.import_base_path).resolve()
    target = _Path(folder_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Ungültiger Pfad: '{folder_path}' liegt nicht unter '{settings.import_base_path}'."
        )
    target.mkdir(parents=True, exist_ok=True)
    return target


def parse_folder_name(folder_name: str) -> tuple[str, int]:
    """Parst 'FirmaName_YYYY' → (firma, jahr)."""
    import re
    match = re.match(r"^(.+)_(\d{4})$", folder_name)
    if not match:
        raise ValueError(f"Ordnername '{folder_name}' muss dem Format 'FirmaName_YYYY' entsprechen.")
    return match.group(1), int(match.group(2))


def list_pdf_files(folder_path: Path) -> list[Path]:
    """Gibt alle .pdf/.PDF-Dateien im Ordner zurück (sortiert, nicht rekursiv)."""
    all_files = sorted(
        set(folder_path.glob("*.pdf")) | set(folder_path.glob("*.PDF")),
        key=lambda p: p.name.lower(),
    )
    logger.info("Gefundene PDFs in '%s': %d", folder_path.name, len(all_files))
    return all_files


# ─── Haupt-Import-Funktion ────────────────────────────────────────────────────

async def run_import(batch_id: int) -> None:
    """
    Orchestriert den gesamten Import eines Batches.
    Die Haupt-Session wird NUR für Batch-Status-Updates verwendet.
    Dokument-Verarbeitung läuft in _process_single_document mit eigenen Sessions.
    """
    logger.info("Import-Task gestartet für Batch #%d", batch_id)
    db = SessionLocal()
    try:
        batch = crud.import_batch.update_status(db, batch_id, "running")
        if batch is None:
            logger.error("Batch #%d nicht gefunden", batch_id)
            return

        crud.system_log.add(
            db, category="import", level="info",
            message=f"Import gestartet: {batch.company_name} {batch.year}",
            batch_id=batch_id,
        )

        # Pfad validieren
        try:
            folder_path = validate_import_path(batch.folder_path)
        except (ValueError, FileNotFoundError) as exc:
            crud.system_log.add(db, category="import", level="error",
                                message=f"Ungültiger Ordnerpfad: {exc}", batch_id=batch_id)
            crud.import_batch.update_status(db, batch_id, "error")
            return

        # PDFs auflisten
        pdf_files = list_pdf_files(folder_path)
        if not pdf_files:
            crud.system_log.add(db, category="import", level="warning",
                                message="Keine PDF-Dateien im Import-Ordner gefunden",
                                batch_id=batch_id)
            crud.import_batch.update_status(db, batch_id, "done", total_docs=0, processed_docs=0)
            return

        crud.system_log.add(
            db, category="import", level="info",
            message=f"{len(pdf_files)} PDF-Datei(en) gefunden — starte Verarbeitung",
            batch_id=batch_id,
        )
        crud.import_batch.update_status(db, batch_id, "running", total_docs=len(pdf_files))

        # Zielordner
        storage_dir = Path(settings.storage_path) / f"{batch.company_name}_{batch.year}"
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Parallelität aus DB lesen
        try:
            proc_settings = crud.processing_settings.get_or_create(db)
            concurrency = proc_settings.import_concurrency
        except Exception:
            concurrency = CONCURRENCY_DEFAULT
        logger.info("Import-Parallelität: %d", concurrency)

        semaphore = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        processed_count = 0
        error_count = 0

        # Batch-Status nicht bei JEDEM Dokument updaten (=1000 DB-Commits bei 1000 Dateien).
        # Stattdessen: alle 10 Dokumente oder wenn fertig.
        # Das reduziert DB-Commits von 1000 auf ~100 und entlastet den Event-Loop.
        UPDATE_EVERY = max(1, min(10, len(pdf_files) // 20))  # ~5% der Gesamtzahl, min 1, max 10

        async def process_with_semaphore(pdf_path: Path) -> None:
            nonlocal processed_count, error_count
            async with semaphore:
                success = await _process_single_document(
                    batch_id=batch_id,
                    batch_company=batch.company_name,
                    batch_year=batch.year,
                    pdf_path=pdf_path,
                    storage_dir=storage_dir,
                )
                async with lock:
                    processed_count += 1
                    if not success:
                        error_count += 1
                    # Nur bei jedem N-ten Dokument oder am Ende updaten
                    if processed_count % UPDATE_EVERY == 0 or processed_count == len(pdf_files):
                        try:
                            crud.import_batch.update_status(
                                db, batch_id, "running", processed_docs=processed_count
                            )
                        except Exception as upd_exc:
                            logger.warning("Batch-Status-Update fehlgeschlagen: %s", upd_exc)
                            try:
                                db.rollback()
                            except Exception:
                                pass

        await asyncio.gather(*[process_with_semaphore(p) for p in pdf_files])

        # Abschluss
        ok_count = processed_count - error_count
        level = "warning" if error_count > 0 else "info"
        msg = f"Import abgeschlossen: {ok_count} erfolgreich" + \
              (f", {error_count} fehlerhaft" if error_count else "") + \
              f" (von {len(pdf_files)} gesamt)"
        crud.system_log.add(db, category="import", level=level, message=msg, batch_id=batch_id)
        crud.import_batch.update_status(db, batch_id, "done", processed_docs=processed_count)
        logger.info("Batch #%d fertig: %d ok, %d Fehler", batch_id, ok_count, error_count)

    except Exception as exc:
        logger.exception("Unerwarteter Fehler in Import-Task #%d: %s", batch_id, exc)
        try:
            crud.system_log.add(db, category="import", level="error",
                                message=f"Unerwarteter Fehler: {exc}", batch_id=batch_id)
            crud.import_batch.update_status(db, batch_id, "error")
        except Exception:
            pass
    finally:
        db.close()


# ─── Einzel-Dokument-Verarbeitung ─────────────────────────────────────────────

async def _process_single_document(
    batch_id: int,
    batch_company: str,
    batch_year: int,
    pdf_path: Path,
    storage_dir: Path,
) -> bool:
    """
    Verarbeitet ein einzelnes PDF in vier Phasen.

    Jede DB-Phase öffnet eine eigene, kurzlebige Session und schließt sie
    unmittelbar nach dem Commit. Während der IO-Phasen (Kopieren, Seitenanzahl)
    wird keine Datenbankverbindung gehalten — das ist der Schlüssel zur
    Skalierbarkeit: 32 parallele Tasks ≠ 32 gleichzeitige DB-Verbindungen.

    Returns: True = Erfolg, False = Fehler
    """
    doc_id: int | None = None

    # ── Phase 1: Dokument-Datensatz anlegen ───────────────────────────────────
    # Verbindungszeit: < 50 ms
    try:
        db = SessionLocal()
        try:
            file_size = pdf_path.stat().st_size
            doc = crud.document.create(
                db=db,
                batch_id=batch_id,
                original_filename=pdf_path.name,
                file_size_bytes=file_size,
                company=batch_company,
                year=batch_year,
            )
            doc_id = doc.id
        finally:
            db.close()  # ← Verbindung frei, BEVOR der IO startet
    except Exception as exc:
        logger.error("DB-Fehler beim Anlegen von '%s': %s", pdf_path.name, exc)
        return False

    stored_filename = f"{doc_id}.pdf"
    dest_path = storage_dir / stored_filename

    # ── Phase 2: Datei kopieren ───────────────────────────────────────────────
    # Verbindungszeit: 0 — keine DB-Verbindung während des Kopierens!
    try:
        await _run_import_io(shutil.copy2, str(pdf_path), str(dest_path))
    except OSError as exc:
        logger.error("Kopierfehler für '%s': %s", pdf_path.name, exc)
        _write_error(doc_id, batch_id, f"Kopierfehler: {exc}", pdf_path.name)
        return False

    # ── Phase 3: Seitenanzahl auslesen ────────────────────────────────────────
    # Verbindungszeit: 0 — keine DB-Verbindung während des PDF-Parsens!
    try:
        page_count = await _run_import_io(pdf_service.get_page_count, dest_path)
    except Exception as exc:
        logger.warning("Seitenanzahl für '%s' nicht lesbar: %s", pdf_path.name, exc)
        page_count = 0

    # ── Phase 4: Status auf "done" setzen ─────────────────────────────────────
    # Verbindungszeit: < 50 ms
    try:
        db = SessionLocal()
        try:
            crud.document.update_after_copy(db, doc_id, stored_filename, page_count)
            crud.document.update_status(db, doc_id, "done")
        finally:
            db.close()  # ← sofort freigeben
    except Exception as exc:
        logger.error("DB-Fehler beim Abschließen von #%d: %s", doc_id, exc)
        _write_error(doc_id, batch_id, f"DB-Update-Fehler: {exc}", pdf_path.name)
        return False

    logger.debug("Dokument #%d importiert: %s (%d Seiten)", doc_id, pdf_path.name, page_count)
    return True


def _write_error(doc_id: int, batch_id: int, error_msg: str, filename: str) -> None:
    """
    Schreibt Fehler-Status und Log-Eintrag synchron in eigener Session.
    Wird aus dem Import-IO-Thread-Pool heraus aufgerufen (nicht vom Event-Loop).
    Wirft nie eine Exception.
    """
    try:
        db = SessionLocal()
        try:
            crud.document.update_status(db, doc_id, "error", error_message=error_msg)
            crud.system_log.add(
                db, category="import", level="error",
                message=f"{filename}: {error_msg}",
                batch_id=batch_id, document_id=doc_id,
            )
        finally:
            db.close()
    except Exception as exc:
        logger.error("Fehler beim Schreiben des Error-Status für #%d: %s", doc_id, exc)
