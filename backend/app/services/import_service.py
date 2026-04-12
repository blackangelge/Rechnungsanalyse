"""
Import-Service: Orchestriert den gesamten Import-Prozess.

ARCHITEKTUR — Event-Loop-Schutz:
  Alle blockierenden Operationen (DB-Zugriffe, Filesystem) laufen in
  Thread-Pools, NICHT im Event-Loop-Thread. Dadurch bleibt der Event-Loop
  jederzeit reaktionsfähig — auch während langer Import-Vorgänge.

  Drei Thread-Pools:
  - _IMPORT_IO_EXECUTOR : Datei-Kopieren, Seitenanzahl lesen
  - asyncio.to_thread() : DB-Operationen (verwendet den Standard-Pool)
  - (Event-Loop-Thread) : NUR async/await-Koordination, KEIN blockierender Code
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

# ── Dedizierter Thread-Pool für Import-IO ────────────────────────────────────
_IMPORT_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=min(32, (os.cpu_count() or 4) * 4),
    thread_name_prefix="import_io",
)


async def _run_import_io(func, *args):
    """Führt eine blockierende IO-Funktion im dedizierten Import-Thread-Pool aus."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_IMPORT_IO_EXECUTOR, func, *args)


# ─── Pfad-Hilfsfunktionen ────────────────────────────────────────────────────

def validate_import_path(folder_path: str) -> Path:
    """Prüft ob Pfad unter IMPORT_BASE_PATH liegt und erstellt ihn bei Bedarf."""
    base = Path(settings.import_base_path).resolve()
    target = Path(folder_path).resolve()
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


# ─── Sync DB-Hilfsfunktionen ─────────────────────────────────────────────────
# Diese Funktionen laufen via asyncio.to_thread() — NICHT im Event-Loop-Thread.
# So wird der Event-Loop NICHT blockiert, auch wenn DB-Operationen länger dauern.

def _db_batch_start(batch_id: int) -> dict | None:
    """Setzt Batch auf 'running'. Gibt Batch-Info als Dict zurück (kein ORM-Objekt)."""
    db = SessionLocal()
    try:
        batch = crud.import_batch.update_status(db, batch_id, "running")
        if batch is None:
            return None
        crud.system_log.add(
            db, category="import", level="info",
            message=f"Import gestartet: {batch.company_name} {batch.year}",
            batch_id=batch_id,
        )
        return {
            "company_name": batch.company_name,
            "year": batch.year,
            "folder_path": batch.folder_path,
        }
    finally:
        db.close()


def _db_batch_pdf_count(batch_id: int, count: int) -> None:
    """Aktualisiert Gesamtanzahl der PDFs im Batch."""
    db = SessionLocal()
    try:
        crud.import_batch.update_status(db, batch_id, "running", total_docs=count)
    finally:
        db.close()


def _db_batch_progress(batch_id: int, processed: int) -> None:
    """Aktualisiert den Fortschritts-Zähler eines laufenden Batches."""
    db = SessionLocal()
    try:
        crud.import_batch.update_status(db, batch_id, "running", processed_docs=processed)
    except Exception as exc:
        logger.warning("Batch-Fortschritt-Update fehlgeschlagen: %s", exc)
    finally:
        db.close()


def _db_batch_finish(batch_id: int, processed: int, error_count: int, total: int) -> None:
    """Schließt den Import-Batch ab."""
    db = SessionLocal()
    try:
        ok = processed - error_count
        level = "warning" if error_count > 0 else "info"
        msg = (f"Import abgeschlossen: {ok} erfolgreich"
               + (f", {error_count} fehlerhaft" if error_count else "")
               + f" (von {total} gesamt)")
        crud.system_log.add(db, category="import", level=level, message=msg, batch_id=batch_id)
        crud.import_batch.update_status(db, batch_id, "done", processed_docs=processed)
    finally:
        db.close()


def _db_batch_error(batch_id: int, message: str) -> None:
    """Markiert den Batch als fehlerhaft."""
    db = SessionLocal()
    try:
        crud.system_log.add(db, category="import", level="error",
                            message=message, batch_id=batch_id)
        crud.import_batch.update_status(db, batch_id, "error")
    except Exception as exc:
        logger.error("Konnte Batch-Fehler nicht schreiben: %s", exc)
    finally:
        db.close()


def _db_doc_create(batch_id: int, filename: str, file_size: int,
                   company: str, year: int) -> int | None:
    """Legt einen Dokument-Datensatz an. Gibt die neue ID zurück."""
    db = SessionLocal()
    try:
        doc = crud.document.create(
            db=db,
            batch_id=batch_id,
            original_filename=filename,
            file_size_bytes=file_size,
            company=company,
            year=year,
        )
        return doc.id
    except Exception as exc:
        logger.error("DB-Fehler beim Anlegen von '%s': %s", filename, exc)
        return None
    finally:
        db.close()


def _db_doc_finish(doc_id: int, stored_filename: str, page_count: int) -> None:
    """Setzt stored_filename, Seitenanzahl und Status 'done'."""
    db = SessionLocal()
    try:
        crud.document.update_after_copy(db, doc_id, stored_filename, page_count)
        crud.document.update_status(db, doc_id, "done")
    except Exception as exc:
        logger.error("DB-Fehler beim Abschließen von #%d: %s", doc_id, exc)
        try:
            db.rollback()
            crud.document.update_status(db, doc_id, "error",
                                        error_message=f"DB-Update-Fehler: {exc}")
        except Exception:
            pass
    finally:
        db.close()


def _db_doc_error(doc_id: int, batch_id: int, error_msg: str, filename: str) -> None:
    """Schreibt Fehler-Status für ein Dokument."""
    db = SessionLocal()
    try:
        crud.document.update_status(db, doc_id, "error", error_message=error_msg)
        crud.system_log.add(
            db, category="import", level="error",
            message=f"{filename}: {error_msg}",
            batch_id=batch_id, document_id=doc_id,
        )
    except Exception as exc:
        logger.error("Fehler beim Schreiben des Error-Status für #%d: %s", doc_id, exc)
    finally:
        db.close()


def _db_get_concurrency() -> int:
    """Liest die Import-Parallelität aus den ProcessingSettings."""
    db = SessionLocal()
    try:
        s = crud.processing_settings.get_or_create(db)
        return s.import_concurrency
    except Exception:
        return 4
    finally:
        db.close()


# ─── Haupt-Import-Funktion ────────────────────────────────────────────────────

async def run_import(batch_id: int) -> None:
    """
    Orchestriert den gesamten Import eines Batches.

    Alle DB-Operationen laufen via asyncio.to_thread() in Threads —
    der Event-Loop wird NIEMALS durch synchrone DB-Aufrufe blockiert.
    """
    logger.info("Import-Task gestartet für Batch #%d", batch_id)

    # ── Setup: Batch-Info + Parallelität aus DB laden (im Thread) ────────────
    batch_info = await asyncio.to_thread(_db_batch_start, batch_id)
    if batch_info is None:
        logger.error("Batch #%d nicht gefunden", batch_id)
        return

    company_name: str = batch_info["company_name"]
    year: int = batch_info["year"]
    folder_path_str: str = batch_info["folder_path"]

    # Parallelität laden (im Thread, da sync DB-Aufruf)
    concurrency = await asyncio.to_thread(_db_get_concurrency)
    logger.info("Import-Parallelität: %d", concurrency)

    # ── Pfad validieren + PDFs auflisten (im IO-Thread) ──────────────────────
    try:
        folder_path = await _run_import_io(validate_import_path, folder_path_str)
    except (ValueError, Exception) as exc:
        await asyncio.to_thread(_db_batch_error, batch_id, f"Ungültiger Ordnerpfad: {exc}")
        return

    pdf_files: list[Path] = await _run_import_io(list_pdf_files, folder_path)

    if not pdf_files:
        db_msg = "Keine PDF-Dateien im Import-Ordner gefunden"
        await asyncio.to_thread(_db_batch_error, batch_id, db_msg)
        return

    # Zielordner erstellen (im IO-Thread)
    storage_dir = Path(settings.storage_path) / f"{company_name}_{year}"
    await _run_import_io(storage_dir.mkdir, True, True)  # parents=True, exist_ok=True

    await asyncio.to_thread(_db_batch_pdf_count, batch_id, len(pdf_files))
    logger.info("Batch #%d: %d PDFs gefunden", batch_id, len(pdf_files))

    # ── Dokumente parallel verarbeiten ────────────────────────────────────────
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    processed_count = 0
    error_count = 0
    UPDATE_EVERY = max(1, min(10, len(pdf_files) // 10))

    async def process_with_semaphore(pdf_path: Path) -> None:
        nonlocal processed_count, error_count
        async with semaphore:
            success = await _process_single_document(
                batch_id=batch_id,
                batch_company=company_name,
                batch_year=year,
                pdf_path=pdf_path,
                storage_dir=storage_dir,
            )
            async with lock:
                processed_count += 1
                if not success:
                    error_count += 1
                if processed_count % UPDATE_EVERY == 0 or processed_count == len(pdf_files):
                    # DB-Update im Thread — blockiert Event-Loop nicht
                    await asyncio.to_thread(_db_batch_progress, batch_id, processed_count)

    await asyncio.gather(*[process_with_semaphore(p) for p in pdf_files])

    # ── Abschluss ─────────────────────────────────────────────────────────────
    await asyncio.to_thread(_db_batch_finish, batch_id, processed_count, error_count, len(pdf_files))
    logger.info("Batch #%d fertig: %d ok, %d Fehler", batch_id,
                processed_count - error_count, error_count)


# ─── Einzel-Dokument-Verarbeitung ────────────────────────────────────────────

async def _process_single_document(
    batch_id: int,
    batch_company: str,
    batch_year: int,
    pdf_path: Path,
    storage_dir: Path,
) -> bool:
    """
    Verarbeitet ein einzelnes PDF in vier Phasen.

    Alle DB-Operationen laufen via asyncio.to_thread() im Thread-Pool.
    Alle IO-Operationen laufen via _run_import_io() im Import-IO-Pool.
    Der Event-Loop wird NIEMALS blockiert.
    """
    # ── Phase 1: Dokument-Datensatz anlegen (DB im Thread) ───────────────────
    try:
        file_size = await _run_import_io(lambda: pdf_path.stat().st_size)
    except OSError:
        file_size = 0

    doc_id = await asyncio.to_thread(
        _db_doc_create, batch_id, pdf_path.name, file_size, batch_company, batch_year
    )
    if doc_id is None:
        return False

    stored_filename = f"{doc_id}.pdf"
    dest_path = storage_dir / stored_filename

    # ── Phase 2: Datei kopieren (IO im Import-Pool) ───────────────────────────
    try:
        await _run_import_io(shutil.copy2, str(pdf_path), str(dest_path))
    except OSError as exc:
        logger.error("Kopierfehler für '%s': %s", pdf_path.name, exc)
        await asyncio.to_thread(_db_doc_error, doc_id, batch_id,
                                f"Kopierfehler: {exc}", pdf_path.name)
        return False

    # ── Phase 3: Seitenanzahl lesen (IO im Import-Pool) ──────────────────────
    try:
        page_count = await _run_import_io(pdf_service.get_page_count, dest_path)
    except Exception as exc:
        logger.warning("Seitenanzahl für '%s' nicht lesbar: %s", pdf_path.name, exc)
        page_count = 0

    # ── Phase 4: Status auf 'done' setzen (DB im Thread) ─────────────────────
    await asyncio.to_thread(_db_doc_finish, doc_id, stored_filename, page_count)

    logger.debug("Dokument #%d importiert: %s (%d Seiten)", doc_id, pdf_path.name, page_count)
    return True
