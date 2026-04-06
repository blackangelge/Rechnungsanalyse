"""
Router für importierte Dokumente.

Endpunkte:
  GET   /api/documents/             — Liste aller Dokumente mit optionalen Filtern
  POST  /api/documents/analyze      — KI-Analyse für ausgewählte Dokumente starten
  GET   /api/documents/{id}         — Dokument mit Extraktion und Positionen
  GET   /api/documents/{id}/preview — PDF-Datei streamen (für Browser-Vorschau)
  PATCH /api/documents/{id}/comment — Kommentar aktualisieren
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import SessionLocal, get_db
from app.schemas.document import DocumentCommentUpdate, DocumentDetail, DocumentListRead, DocumentRead
from app.services import ai_service, pdf_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Dokumente"])


# ─── Schemas für neue Endpunkte ──────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Request-Body für den Analyse-Endpunkt."""
    document_ids: list[int]
    ai_config_id: Optional[int] = None
    system_prompt_id: Optional[int] = None


class AnalyzeResponse(BaseModel):
    """Response des Analyse-Endpunkts."""
    started: int
    message: str


# ─── GET /api/documents/ ────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentListRead])
def list_documents(
    company: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    total_min: Optional[float] = None,
    total_max: Optional[float] = None,
    page_min: Optional[int] = None,
    page_max: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Gibt alle Dokumente zurück, optional gefiltert nach Firma, Jahr, Status und Betrag.
    """
    return crud.document.get_all_filtered(
        db,
        company=company,
        year=year,
        status=status,
        total_min=total_min,
        total_max=total_max,
        page_min=page_min,
        page_max=page_max,
    )


# ─── POST /api/documents/analyze ────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_documents(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
):
    """
    Startet eine KI-Analyse für die angegebenen Dokumente im Hintergrund.

    - Setzt alle Dokumente sofort auf status="processing"
    - Startet einen asyncio-Task für die parallele Verarbeitung (max. 4 gleichzeitig)
    - Gibt sofort zurück — Ergebnisse werden asynchron in die DB geschrieben
    """
    if not payload.document_ids:
        raise HTTPException(status_code=400, detail="Keine Dokument-IDs angegeben")

    # KI-Konfiguration auflösen
    ai_config = None
    if payload.ai_config_id:
        ai_config = crud.ai_config.get_by_id(db, payload.ai_config_id)
        if ai_config is None:
            raise HTTPException(
                status_code=404,
                detail=f"KI-Konfiguration #{payload.ai_config_id} nicht gefunden",
            )
    else:
        ai_config = crud.ai_config.get_default(db)
        if ai_config is None:
            raise HTTPException(
                status_code=400,
                detail="Keine Standard-KI-Konfiguration vorhanden. Bitte eine auswählen.",
            )

    # System-Prompt auflösen
    system_prompt_text: str | None = None
    if payload.system_prompt_id:
        sp = crud.system_prompt.get_by_id(db, payload.system_prompt_id)
        if sp:
            system_prompt_text = sp.content
    else:
        default_sp = crud.system_prompt.get_default(db)
        if default_sp:
            system_prompt_text = default_sp.content

    # Validierte Dokumente laden und sofort auf "processing" setzen
    valid_ids: list[int] = []
    for doc_id in payload.document_ids:
        doc = db.get(crud.document.Document if hasattr(crud.document, "Document") else __import__(
            "app.models.document", fromlist=["Document"]
        ).Document, doc_id)

        # Importiere Document direkt
        from app.models.document import Document as DocModel
        doc = db.get(DocModel, doc_id)
        if doc is None:
            logger.warning("Dokument #%d nicht gefunden — übersprungen", doc_id)
            continue
        if not doc.stored_filename:
            logger.warning("Dokument #%d hat keine gespeicherte Datei — übersprungen", doc_id)
            continue

        valid_ids.append(doc_id)
        crud.document.update_status(db, doc_id, "processing")

    if not valid_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine gültigen Dokumente gefunden (bereits verarbeitet oder nicht importiert)",
        )

    # KI-Config-ID für den Hintergrund-Task merken (nicht ORM-Objekt übergeben)
    ai_config_id = ai_config.id

    # Hintergrund-Task starten
    asyncio.create_task(
        _run_analysis(
            document_ids=valid_ids,
            ai_config_id=ai_config_id,
            system_prompt_text=system_prompt_text,
        )
    )

    return AnalyzeResponse(
        started=len(valid_ids),
        message=f"KI-Analyse für {len(valid_ids)} Dokument(e) gestartet",
    )


async def _run_analysis(
    document_ids: list[int],
    ai_config_id: int,
    system_prompt_text: str | None,
) -> None:
    """
    Hintergrund-Coroutine: Analysiert alle Dokumente parallel (max. 4 gleichzeitig).
    Öffnet eigene DB-Session (läuft unabhängig vom Request-Lifecycle).
    """
    semaphore = asyncio.Semaphore(4)
    tasks = [
        _analyze_single(
            doc_id=doc_id,
            ai_config_id=ai_config_id,
            system_prompt_text=system_prompt_text,
            semaphore=semaphore,
        )
        for doc_id in document_ids
    ]
    await asyncio.gather(*tasks)
    logger.info("KI-Analyse-Batch abgeschlossen (%d Dokumente)", len(document_ids))


async def _analyze_single(
    doc_id: int,
    ai_config_id: int,
    system_prompt_text: str | None,
    semaphore: asyncio.Semaphore,
) -> None:
    """Analysiert ein einzelnes Dokument mit KI-Extraktion."""
    async with semaphore:
        db: Session = SessionLocal()
        try:
            from app.models.document import Document as DocModel

            doc = db.get(DocModel, doc_id)
            if doc is None:
                logger.error("Dokument #%d nicht in DB gefunden", doc_id)
                return

            ai_config = crud.ai_config.get_by_id(db, ai_config_id)
            if ai_config is None:
                logger.error("KI-Konfiguration #%d nicht in DB gefunden", ai_config_id)
                crud.document.update_status(
                    db, doc_id, "error", error_message="KI-Konfiguration nicht gefunden"
                )
                return

            # PDF-Pfad zusammenbauen
            subfolder = f"{doc.company}_{doc.year}"
            pdf_path = Path(settings.storage_path) / subfolder / doc.stored_filename

            if not pdf_path.exists():
                logger.error("PDF nicht gefunden: %s", pdf_path)
                crud.document.update_status(
                    db, doc_id, "error", error_message=f"PDF nicht gefunden: {pdf_path}"
                )
                return

            # Bildeinstellungen laden
            img_settings = crud.image_settings.get_or_create(db)

            # PDF → Bilder
            logger.info("Rendere PDF für Dokument #%d: %s", doc_id, pdf_path.name)
            try:
                images_b64 = await asyncio.to_thread(
                    pdf_service.pdf_to_base64_images,
                    pdf_path,
                    img_settings.dpi,
                    img_settings.image_format,
                    img_settings.jpeg_quality,
                )
            except Exception as exc:
                logger.error("Fehler beim Rendern von #%d: %s", doc_id, exc)
                crud.document.update_status(
                    db, doc_id, "error", error_message=f"PDF-Rendering-Fehler: {exc}"
                )
                return

            if not images_b64:
                crud.document.update_status(
                    db, doc_id, "error", error_message="PDF konnte nicht gerendert werden"
                )
                return

            # KI-Extraktion
            logger.info("Starte KI-Extraktion für Dokument #%d", doc_id)
            extracted_fields, order_positions, raw_response = await ai_service.extract_invoice_data(
                images_b64=images_b64,
                config=ai_config,
                system_prompt_text=system_prompt_text,
            )

            # Lieferant deduplizieren
            supplier_id: int | None = None
            try:
                supplier = crud.supplier.find_or_create(
                    db=db,
                    name=extracted_fields.get("supplier_name"),
                    address=extracted_fields.get("supplier_address"),
                    hrb_number=extracted_fields.get("hrb_number"),
                    tax_number=extracted_fields.get("tax_number"),
                    vat_id=extracted_fields.get("vat_id"),
                    bank_name=extracted_fields.get("bank_name"),
                    iban=extracted_fields.get("iban"),
                    bic=extracted_fields.get("bic"),
                )
                if supplier is not None:
                    supplier_id = supplier.id
            except Exception as exc:
                logger.warning("Fehler beim Supplier-Lookup für #%d: %s", doc_id, exc)

            # Extraktion speichern
            crud.document.save_extraction(
                db=db,
                doc_id=doc_id,
                extracted_data=extracted_fields,
                positions=order_positions,
                raw_response=raw_response,
                supplier_id=supplier_id,
            )

            # Status setzen
            if raw_response.startswith("KI überlastet:") or raw_response.startswith("KI-Fehler:"):
                crud.document.update_status(
                    db, doc_id, "error", error_message=raw_response
                )
                logger.warning("Dokument #%d: KI-Fehler — %s", doc_id, raw_response)
            else:
                crud.document.update_status(db, doc_id, "done")
                logger.info("Dokument #%d erfolgreich analysiert", doc_id)

        except Exception as exc:
            logger.exception("Unerwarteter Fehler bei Analyse von #%d: %s", doc_id, exc)
            try:
                crud.document.update_status(
                    db, doc_id, "error", error_message=f"Unerwarteter Fehler: {exc}"
                )
            except Exception:
                pass
        finally:
            db.close()


# ─── GET /api/documents/{id} ─────────────────────────────────────────────────

@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    """
    Gibt ein Dokument mit allen extrahierten Rechnungsdaten und
    Bestellpositionen zurück.
    """
    doc = crud.document.get_by_id_with_details(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return doc


# ─── GET /api/documents/{id}/preview ────────────────────────────────────────

@router.get("/{doc_id}/preview")
def preview_document(doc_id: int, db: Session = Depends(get_db)):
    """
    Streamt die gespeicherte PDF-Datei direkt im Browser.

    Der Browser (oder ein <iframe>) kann diese URL direkt aufrufen und zeigt
    die PDF-Vorschau ohne zusätzliche Libraries an.

    Content-Type: application/pdf wird automatisch durch FileResponse gesetzt.
    """
    doc = crud.document.get_by_id_with_details(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if not doc.stored_filename:
        raise HTTPException(
            status_code=404,
            detail="PDF-Datei noch nicht verfügbar (Import läuft noch?).",
        )

    subfolder = f"{doc.company}_{doc.year}"
    pdf_path = Path(settings.storage_path) / subfolder / doc.stored_filename

    if not pdf_path.exists():
        logger.error(
            "PDF-Datei nicht gefunden auf Disk: %s (Dokument #%d)", pdf_path, doc_id
        )
        raise HTTPException(
            status_code=404,
            detail="PDF-Datei nicht auf dem Server gefunden.",
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=doc.original_filename,
        content_disposition_type="inline",
    )


# ─── PATCH /api/documents/{id}/comment ──────────────────────────────────────

@router.patch("/{doc_id}/comment", response_model=DocumentDetail)
def update_document_comment(
    doc_id: int,
    payload: DocumentCommentUpdate,
    db: Session = Depends(get_db),
):
    """
    Aktualisiert oder entfernt den Kommentar eines Dokuments.
    Gibt das aktualisierte Dokument mit allen Details zurück.
    """
    doc = crud.document.update_comment(db, doc_id, payload.comment)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    return crud.document.get_by_id_with_details(db, doc_id)
