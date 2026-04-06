"""
Router für Import-Batches.

Endpunkte:
  GET  /api/imports/      — alle Batches (optional gefiltert)
  POST /api/imports/      — neuen Import starten
  GET  /api/imports/{id}  — Batch-Details mit Dokumentliste
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.import_batch import ImportBatchCreate, ImportBatchRead, ImportBatchWithDocuments
from app.services.import_service import (
    list_pdf_files,
    parse_folder_name,
    run_import,
    validate_import_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["Imports"])


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
