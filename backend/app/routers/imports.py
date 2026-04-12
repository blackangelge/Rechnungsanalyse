"""
Router für Import-Batches.

Endpunkte:
  GET  /api/imports/      — alle Batches (optional gefiltert)
  POST /api/imports/      — neuen Import starten
  GET  /api/imports/{id}  — Batch-Details mit Dokumentliste
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.database import SessionLocal, get_db
from app.schemas.import_batch import ImportBatchCreate, ImportBatchRead, ImportBatchWithDocuments
from app.services.import_service import (
    _run_import_io,
    list_pdf_files,
    run_import,
    validate_import_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["Imports"])


# ─── Sync DB-Hilfsfunktionen (laufen via asyncio.to_thread) ─────────────────

def _db_get_source_filenames(batch_id: int) -> list[str]:
    """Gibt die original_filename aller erfolgreich kopierten Dokumente zurück."""
    db = SessionLocal()
    try:
        batch = crud.import_batch.get_by_id(db, batch_id)
        return [
            d.original_filename
            for d in (batch.documents if batch else [])
            if d.stored_filename and d.original_filename
        ]
    finally:
        db.close()


def _db_get_analyze_setup(
    batch_id: int,
    ai_config_id: int | None,
    system_prompt_id: int | None,
) -> dict | None:
    """
    Löst KI-Config, Systemprompt und Dokument-IDs für die KI-Analyse auf.
    Gibt None zurück, wenn keine KI-Konfiguration gefunden wurde.
    """
    db = SessionLocal()
    try:
        if ai_config_id:
            resolved_config = crud.ai_config.get_by_id(db, ai_config_id)
        else:
            resolved_config = crud.ai_config.get_default(db)

        if resolved_config is None:
            logger.warning(
                "Batch #%d: Keine KI-Konfiguration gefunden — KI-Analyse übersprungen",
                batch_id,
            )
            return None

        if system_prompt_id:
            sp = crud.system_prompt.get_by_id(db, system_prompt_id)
            system_prompt_text = sp.content if sp else None
        else:
            default_sp = crud.system_prompt.get_default(db)
            system_prompt_text = default_sp.content if default_sp else None

        batch = crud.import_batch.get_by_id(db, batch_id)
        doc_ids = [d.id for d in (batch.documents if batch else []) if d.stored_filename]

        return {
            "ai_config_id": resolved_config.id,
            "system_prompt_text": system_prompt_text,
            "doc_ids": doc_ids,
        }
    finally:
        db.close()


def _db_set_processing(doc_ids: list[int]) -> None:
    """Setzt alle angegebenen Dokumente auf Status 'processing'."""
    db = SessionLocal()
    try:
        for doc_id in doc_ids:
            crud.document.update_status(db, doc_id, "processing")
    finally:
        db.close()


def _sync_delete_source_files(import_folder: str, original_names: list[str]) -> tuple[int, int]:
    """
    Sync: Löscht Quelldateien aus dem Import-Ordner.
    Gibt (deleted, failed) zurück. Läuft via _run_import_io().
    """
    folder = Path(import_folder)
    deleted, failed = 0, 0
    for name in original_names:
        src = folder / name
        try:
            if src.exists():
                src.unlink()
                deleted += 1
                logger.info("Quelldatei gelöscht: %s", src)
            else:
                logger.debug("Quelldatei bereits weg: %s", src)
        except Exception as exc:
            failed += 1
            logger.warning("Konnte Quelldatei nicht löschen %s: %s", src, exc)
    return deleted, failed


async def _delete_source_files(batch_id: int, import_folder: str) -> None:
    """
    Löscht die Original-PDFs aus dem Import-Ordner, die erfolgreich kopiert wurden.
    Es werden nur Dateien gelöscht, für die ein DB-Eintrag mit stored_filename existiert.
    DB-Abfrage und Filesystem-Operationen laufen in Thread-Pools (nicht-blockierend).
    """
    # DB-Abfrage im Thread
    original_names = await asyncio.to_thread(_db_get_source_filenames, batch_id)

    if not original_names:
        logger.debug("Batch #%d: Keine Quelldateien zum Löschen", batch_id)
        return

    # Filesystem-Operationen im Import-IO-Pool
    deleted, failed = await _run_import_io(_sync_delete_source_files, import_folder, original_names)

    logger.info(
        "Batch #%d: Quelldateien gelöscht=%d, fehlgeschlagen=%d", batch_id, deleted, failed
    )


async def _import_and_delete(batch_id: int, import_folder: str) -> None:
    """Import durchführen und danach Quelldateien löschen (ohne KI-Analyse)."""
    await run_import(batch_id)
    await _delete_source_files(batch_id, import_folder)


async def _import_then_analyze(
    batch_id: int,
    import_folder: str,
    ai_config_id: int | None = None,
    system_prompt_id: int | None = None,
    delete_source_files: bool = False,
) -> None:
    """
    Führt zuerst den Import durch, danach startet automatisch die KI-Analyse
    für alle erfolgreich importierten Dokumente.
    Alle DB- und Filesystem-Operationen laufen in Thread-Pools (nicht-blockierend).
    """
    from app.routers.documents import _run_analysis

    # 1. Import abwarten
    await run_import(batch_id)

    # 2. Quelldateien löschen (falls gewünscht), bevor KI läuft
    if delete_source_files:
        await _delete_source_files(batch_id, import_folder)

    # 3. KI-Konfiguration + Systemprompt + Dokument-IDs auflösen (im Thread)
    setup = await asyncio.to_thread(_db_get_analyze_setup, batch_id, ai_config_id, system_prompt_id)
    if setup is None:
        return

    doc_ids: list[int] = setup["doc_ids"]
    if not doc_ids:
        logger.info("Batch #%d: Keine Dokumente für KI-Analyse", batch_id)
        return

    # 4. Dokumente auf "processing" setzen (im Thread)
    await asyncio.to_thread(_db_set_processing, doc_ids)

    logger.info("Batch #%d: KI-Analyse für %d Dokument(e) gestartet", batch_id, len(doc_ids))
    await _run_analysis(doc_ids, setup["ai_config_id"], setup["system_prompt_text"])


@router.get("", response_model=list[ImportBatchRead])
def list_imports(
    company_name: str | None = Query(None, description="Firmenname (Teilstring-Suche)"),
    year: int | None = Query(None, description="Importjahr (exakt)"),
    db: Session = Depends(get_db),
):
    """
    Gibt alle Import-Batches zurück.
    Optional nach Firmenname (Teilstring) und/oder Jahr filtern.
    """
    return crud.import_batch.get_all(db, company_name=company_name, year=year)


@router.post("", response_model=ImportBatchRead, status_code=status.HTTP_201_CREATED)
async def start_import(payload: ImportBatchCreate, db: Session = Depends(get_db)):
    """
    Startet einen neuen Import-Vorgang.

    Der Ordnerpfad wird aus Firma + Jahr konstruiert: IMPORT_BASE_PATH/Firma_Jahr
    Falls der Ordner noch nicht existiert, wird er angelegt.
    Keine KI-Extraktion beim Import – nur Kopieren und Metadaten erfassen.
    """
    # ── Firma + Jahr bestimmen ─────────────────────────────────────────────
    if not payload.company_name or not payload.year:
        raise HTTPException(status_code=400, detail="Firmenname und Jahr sind erforderlich.")
    company_name = payload.company_name
    year = payload.year

    # ── Import-Pfad: immer IMPORT_BASE_PATH (fest, kein Unterordner) ───────
    from app.config import settings as _settings
    folder_path = _settings.import_base_path
    payload = payload.model_copy(update={"folder_path": folder_path})

    try:
        validated_path = validate_import_path(folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── PDF-Prüfung ────────────────────────────────────────────────────────
    pdf_files = list_pdf_files(validated_path)
    if not pdf_files:
        raise HTTPException(
            status_code=400,
            detail=f"Keine PDF-Dateien im Import-Ordner gefunden.",
        )

    # ── Batch in DB anlegen ────────────────────────────────────────────────
    batch = crud.import_batch.create(
        db=db,
        data=payload,
        company_name=company_name,
        year=year,
    )
    logger.info("Import-Batch #%d erstellt: %s_%d (%d PDFs)", batch.id, company_name, year, len(pdf_files))

    if payload.analyze_after_import:
        asyncio.create_task(_import_then_analyze(
            batch_id=batch.id,
            import_folder=folder_path,
            ai_config_id=payload.ai_config_id,
            system_prompt_id=payload.system_prompt_id,
            delete_source_files=payload.delete_source_files,
        ))
    elif payload.delete_source_files:
        asyncio.create_task(_import_and_delete(batch.id, folder_path))
    else:
        asyncio.create_task(run_import(batch.id))
    return batch


@router.get("/{batch_id}/status", response_model=ImportBatchRead)
def get_import_status(batch_id: int, db: Session = Depends(get_db)):
    """
    Gibt nur den Status eines Import-Batches zurück — OHNE Dokumentliste.
    Für leichtgewichtiges Polling während eines laufenden Imports.
    """
    from app.models.import_batch import ImportBatch as ImportBatchModel
    obj = db.get(ImportBatchModel, batch_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Import-Batch nicht gefunden")
    return obj


@router.get("/{batch_id}", response_model=ImportBatchWithDocuments)
def get_import(batch_id: int, db: Session = Depends(get_db)):
    """Gibt einen Import-Batch mit vollständiger Dokumentliste zurück."""
    batch = crud.import_batch.get_by_id(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import-Batch nicht gefunden")
    return batch


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_import(batch_id: int, db: Session = Depends(get_db)):
    """Löscht einen Import-Batch, alle zugehörigen Dokumente und die PDF-Dateien vom Filesystem."""
    import shutil
    from pathlib import Path

    from app.config import settings as _settings

    # Batch mit Dokumenten laden
    batch = crud.import_batch.get_by_id(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import-Batch nicht gefunden")

    # PDF-Dateien vom Filesystem löschen
    deleted_files = 0
    failed_files = 0
    deleted_folders: set[Path] = set()

    for doc in batch.documents:
        if doc.stored_filename:
            subfolder = f"{doc.company}_{doc.year}"
            pdf_path = Path(_settings.storage_path) / subfolder / doc.stored_filename
            if pdf_path.exists():
                try:
                    pdf_path.unlink()
                    deleted_files += 1
                    deleted_folders.add(pdf_path.parent)
                    logger.info("Datei gelöscht: %s", pdf_path)
                except Exception as exc:
                    failed_files += 1
                    logger.warning("Fehler beim Löschen von %s: %s", pdf_path, exc)

    # Leere Unterordner ebenfalls löschen
    for folder in deleted_folders:
        try:
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
                logger.info("Leerer Ordner gelöscht: %s", folder)
        except Exception as exc:
            logger.warning("Fehler beim Löschen des Ordners %s: %s", folder, exc)

    if deleted_files or failed_files:
        logger.info(
            "Batch #%d: %d Datei(en) gelöscht, %d Fehler",
            batch_id, deleted_files, failed_files,
        )

    # DB-Eintrag löschen (CASCADE zu Dokumenten, Extraktionen, Positionen)
    crud.import_batch.delete(db, batch_id)
