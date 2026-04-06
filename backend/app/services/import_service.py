"""
Import-Service: Orchestriert den gesamten Import-Prozess.

Ablauf für einen Import-Batch:
1. Ordnerpfad validieren (Sicherheitscheck: muss unter IMPORT_BASE_PATH liegen)
2. Alle PDF-Dateien im Ordner auflisten
3. Für jede PDF (parallel, max. CONCURRENCY gleichzeitig):
   a. Dokument-Datensatz in DB anlegen (→ erhält ID)
   b. Datei in STORAGE_PATH/{id}.pdf kopieren
   c. Seitenanzahl auslesen und DB aktualisieren
   d. Status auf "done" setzen
4. Batch-Status auf "done" oder "error" setzen

KI-Extraktion ist NICHT Teil des Imports – sie wird separat ausgelöst.
"""

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import SessionLocal
from app.services import pdf_service

logger = logging.getLogger(__name__)

# Maximale Anzahl gleichzeitig verarbeiteter Dokumente
CONCURRENCY = 4


def validate_import_path(folder_path: str) -> Path:
    """
    Prüft, ob der angegebene Pfad unter IMPORT_BASE_PATH liegt.
    Erstellt den Ordner, falls er noch nicht existiert.

    Raises:
        ValueError: Wenn der Pfad außerhalb von IMPORT_BASE_PATH liegt.
    """
    base = Path(settings.import_base_path).resolve()
    target = Path(folder_path).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Ungültiger Pfad: '{folder_path}' liegt nicht unter dem "
            f"konfigurierten Import-Basisordner '{settings.import_base_path}'."
        )

    # Ordner anlegen, falls er noch nicht existiert
    target.mkdir(parents=True, exist_ok=True)

    return target


def parse_folder_name(folder_name: str) -> tuple[str, int]:
    """
    Parst Firmenname und Jahr aus einem Ordnernamen.
    Format: {Firmenname}_{YYYY}
    """
    import re
    match = re.match(r"^(.+)_(\d{4})$", folder_name)
    if not match:
        raise ValueError(
            f"Ordnername '{folder_name}' entspricht nicht dem Format 'FirmaName_YYYY'."
        )
    return match.group(1), int(match.group(2))


def list_pdf_files(folder_path: Path) -> list[Path]:
    """Gibt alle PDF-Dateien im Ordner zurück (nicht rekursiv, sortiert)."""
    pdf_files = sorted(folder_path.glob("*.pdf"))
    pdf_files_upper = sorted(folder_path.glob("*.PDF"))
    all_files = sorted(set(pdf_files + pdf_files_upper), key=lambda p: p.name.lower())
    logger.info("Gefundene PDFs in '%s': %d", folder_path.name, len(all_files))
    return all_files


async def run_import(batch_id: int) -> None:
    """
    Hauptfunktion des Import-Hintergrundtasks.
    Verarbeitet alle PDFs eines Import-Batches parallel (max. CONCURRENCY gleichzeitig).
    """
    logger.info("Import-Task gestartet für Batch #%d", batch_id)
    db: Session = SessionLocal()

    try:
        batch = crud.import_batch.update_status(db, batch_id, "running")
        if batch is None:
            logger.error("Batch #%d nicht gefunden", batch_id)
            return

        try:
            folder_path = validate_import_path(batch.folder_path)
        except (ValueError, FileNotFoundError) as exc:
            logger.error("Ungültiger Ordnerpfad für Batch #%d: %s", batch_id, exc)
            crud.import_batch.update_status(db, batch_id, "error")
            return

        pdf_files = list_pdf_files(folder_path)

        if not pdf_files:
            logger.warning("Keine PDF-Dateien in '%s' gefunden", batch.folder_path)
            crud.import_batch.update_status(db, batch_id, "done", total_docs=0, processed_docs=0)
            return

        crud.import_batch.update_status(db, batch_id, "running", total_docs=len(pdf_files))

        # Zielordner: STORAGE_PATH/Firma_Jahr/
        storage_dir = Path(settings.storage_path) / f"{batch.company_name}_{batch.year}"
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Semaphore: maximal CONCURRENCY Dokumente gleichzeitig
        semaphore = asyncio.Semaphore(CONCURRENCY)
        processed_count = 0
        lock = asyncio.Lock()

        async def process_with_semaphore(pdf_path: Path) -> None:
            nonlocal processed_count
            async with semaphore:
                await _process_single_document(
                    db=db,
                    batch_id=batch_id,
                    batch_company=batch.company_name,
                    batch_year=batch.year,
                    pdf_path=pdf_path,
                    storage_dir=storage_dir,
                )
                async with lock:
                    processed_count += 1
                    crud.import_batch.update_status(
                        db, batch_id, "running", processed_docs=processed_count
                    )

        await asyncio.gather(*[process_with_semaphore(p) for p in pdf_files])

        crud.import_batch.update_status(db, batch_id, "done", processed_docs=processed_count)
        logger.info("Batch #%d abgeschlossen (%d Dokumente)", batch_id, processed_count)

    except Exception as exc:
        logger.exception("Unerwarteter Fehler in Import-Task #%d: %s", batch_id, exc)
        try:
            crud.import_batch.update_status(db, batch_id, "error")
        except Exception:
            pass
    finally:
        db.close()


async def _process_single_document(
    db: Session,
    batch_id: int,
    batch_company: str,
    batch_year: int,
    pdf_path: Path,
    storage_dir: Path,
) -> None:
    """
    Verarbeitet ein einzelnes PDF: kopieren + Seitenanzahl auslesen.
    Keine KI-Extraktion – diese erfolgt separat.
    """
    logger.info("Verarbeite Dokument: %s", pdf_path.name)

    file_size = pdf_path.stat().st_size
    doc = crud.document.create(
        db=db,
        batch_id=batch_id,
        original_filename=pdf_path.name,
        file_size_bytes=file_size,
        company=batch_company,
        year=batch_year,
    )

    stored_filename = f"{doc.id}.pdf"
    dest_path = storage_dir / stored_filename

    try:
        await asyncio.to_thread(shutil.copy2, str(pdf_path), str(dest_path))
    except OSError as exc:
        logger.error("Kopierfehler für '%s': %s", pdf_path.name, exc)
        crud.document.update_status(db, doc.id, "error", error_message=f"Kopierfehler: {exc}")
        return

    try:
        page_count = await asyncio.to_thread(pdf_service.get_page_count, dest_path)
    except Exception as exc:
        logger.error("Fehler beim Auslesen der Seitenanzahl für #%d: %s", doc.id, exc)
        page_count = 0

    crud.document.update_after_copy(db, doc.id, stored_filename, page_count)
    crud.document.update_status(db, doc.id, "done")
    logger.info("Dokument #%d importiert (%d Seiten)", doc.id, page_count)
