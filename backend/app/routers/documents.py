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
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import SessionLocal, get_db
from app.schemas.document import DocumentCommentUpdate, DocumentDetail, DocumentListRead
from app.services import ai_service, pdf_service

logger = logging.getLogger(__name__)

# Eigener Thread-Pool für KI-PDF-Rendering — verhindert, dass der shared
# uvicorn-Thread-Pool durch langläufige PDF-Operationen gesättigt wird.
_KI_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=min(16, (os.cpu_count() or 4) * 2),
    thread_name_prefix="ki_pdf",
)

router = APIRouter(prefix="/api/documents", tags=["Dokumente"])


async def _run_ki_io(func, *args):
    """Führt eine blockierende Funktion im KI-eigenen Thread-Pool aus."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_KI_IO_EXECUTOR, func, *args)


def _set_error(doc_id: int, message: str) -> None:
    """Setzt den Fehlerstatus eines Dokuments in einer eigenen Session."""
    try:
        _db = SessionLocal()
        try:
            crud.document.update_status(_db, doc_id, "error", error_message=message)
        finally:
            _db.close()
    except Exception as exc:
        logger.error("Konnte Fehlerstatus für #%d nicht setzen: %s", doc_id, exc)


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
    batch_ids: Optional[list[int]] = Query(default=None),
    include_deleted: bool = False,
    db: Session = Depends(get_db),
):
    """
    Gibt alle Dokumente zurück, optional gefiltert.
    include_deleted=true zeigt auch soft-gelöschte Dokumente an.
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
        batch_ids=batch_ids,
        include_deleted=include_deleted,
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
    from app.models.document import Document as DocModel
    valid_ids: list[int] = []
    for doc_id in payload.document_ids:
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


def _db_get_ai_concurrency() -> int:
    """Liest die KI-Parallelität aus den ProcessingSettings (sync, für to_thread)."""
    db = SessionLocal()
    try:
        s = crud.processing_settings.get_or_create(db)
        return s.ai_concurrency
    except Exception:
        return 2
    finally:
        db.close()


def _db_analyze_read(doc_id: int, ai_config_id: int) -> dict | None:
    """
    Phase 1 (sync, für asyncio.to_thread): Liest alle für die KI-Analyse
    benötigten Daten aus der DB und gibt sie als Dict zurück.
    Gibt None zurück, wenn Dokument oder KI-Konfiguration nicht gefunden.
    """
    from app.models.document import Document as DocModel
    db = SessionLocal()
    try:
        doc = db.get(DocModel, doc_id)
        if doc is None:
            logger.error("Dokument #%d nicht in DB gefunden", doc_id)
            return None

        ai_config = crud.ai_config.get_by_id(db, ai_config_id)
        if ai_config is None:
            logger.error("KI-Konfiguration #%d nicht in DB gefunden", ai_config_id)
            crud.document.update_status(db, doc_id, "error",
                                        error_message="KI-Konfiguration nicht gefunden")
            return None

        subfolder = f"{doc.company}_{doc.year}"
        pdf_path = Path(settings.storage_path) / subfolder / doc.stored_filename

        if not pdf_path.exists():
            logger.error("PDF nicht gefunden: %s", pdf_path)
            crud.document.update_status(db, doc_id, "error",
                                        error_message=f"PDF nicht gefunden: {pdf_path}")
            return None

        img_settings = crud.image_settings.get_or_create(db)

        return {
            "pdf_path": pdf_path,
            "original_filename": doc.original_filename,
            "batch_id": doc.batch_id,
            "img_dpi": img_settings.dpi,
            "img_format": img_settings.image_format,
            "img_quality": img_settings.jpeg_quality,
            "ai_api_url": ai_config.api_url,
            "ai_api_key": ai_config.api_key,
            "ai_model_name": ai_config.model_name,
            "ai_max_tokens": ai_config.max_tokens,
            "ai_temperature": ai_config.temperature,
            "ai_reasoning": getattr(ai_config, "reasoning", "off") or "off",
            "ai_endpoint_type": getattr(ai_config, "endpoint_type", "openai") or "openai",
        }
    except Exception as exc:
        logger.exception("Phase 1 DB-Fehler bei Dokument #%d: %s", doc_id, exc)
        try:
            db.rollback()
            crud.document.update_status(db, doc_id, "error",
                                        error_message=f"DB-Fehler (Phase 1): {exc}")
        except Exception:
            pass
        return None
    finally:
        db.close()


def _db_analyze_write(
    doc_id: int,
    original_filename: str,
    batch_id: int | None,
    ai_model_name: str,
    page_count: int,
    extracted_fields: dict,
    order_positions: list,
    raw_response: str,
) -> None:
    """
    Phase 4 (sync, für asyncio.to_thread): Schreibt KI-Ergebnisse in die DB.
    """
    db = SessionLocal()
    try:
        crud.system_log.add(
            db, category="ki", level="info",
            message=(f"KI-Analyse gestartet: {original_filename} — "
                     f"Modell: {ai_model_name}, {page_count} Seite(n)"),
            batch_id=batch_id, document_id=doc_id,
        )

        # Lieferant deduplizieren
        supplier_id: int | None = None
        try:
            supplier = crud.supplier.find_or_create(
                db=db,
                name=extracted_fields.get("supplier_name"),
                address=extracted_fields.get("supplier_address"),
                street=extracted_fields.get("supplier_street"),
                zip_code=extracted_fields.get("supplier_zip"),
                city=extracted_fields.get("supplier_city"),
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
            logger.warning("Supplier-Lookup für #%d fehlgeschlagen: %s", doc_id, exc)

        crud.document.save_extraction(
            db=db,
            doc_id=doc_id,
            extracted_data=extracted_fields,
            positions=order_positions,
            raw_response=raw_response,
            supplier_id=supplier_id,
        )

        is_ki_error = any(raw_response.startswith(p) for p in (
            "KI überlastet:", "KI-Fehler:", "KI-Timeout",
            "KI-Verbindungsfehler", "Unerwarteter KI-Fehler",
        ))
        if is_ki_error:
            crud.document.update_status(db, doc_id, "error", error_message=raw_response)
            crud.system_log.add(
                db, category="ki", level="error",
                message=f"KI-Fehler: {original_filename} — {raw_response[:200]}",
                batch_id=batch_id, document_id=doc_id,
            )
            logger.warning("Dokument #%d: KI-Fehler — %s", doc_id, raw_response[:100])
        else:
            filled = len([v for v in extracted_fields.values() if v is not None])
            crud.document.update_status(db, doc_id, "done")
            crud.system_log.add(
                db, category="ki", level="info",
                message=(f"KI-Analyse erfolgreich: {original_filename} — "
                         f"{filled} Felder, {len(order_positions)} Positionen"),
                batch_id=batch_id, document_id=doc_id,
            )
            logger.info("Dokument #%d erfolgreich analysiert", doc_id)

    except Exception as exc:
        logger.exception("Phase 4 DB-Fehler bei Dokument #%d: %s", doc_id, exc)
        try:
            db.rollback()
            crud.document.update_status(db, doc_id, "error",
                                        error_message=f"Speicherfehler: {exc}")
        except Exception:
            _set_error(doc_id, f"Speicherfehler (Fallback): {exc}")
    finally:
        db.close()


async def _run_analysis(
    document_ids: list[int],
    ai_config_id: int,
    system_prompt_text: str | None,
) -> None:
    """
    Hintergrund-Coroutine: Analysiert alle Dokumente parallel.
    DB-Operationen laufen via asyncio.to_thread() — blockieren den Event-Loop nicht.
    """
    ai_concurrency = await asyncio.to_thread(_db_get_ai_concurrency)
    logger.info("KI-Analyse-Parallelität: %d gleichzeitige Aufrufe", ai_concurrency)
    semaphore = asyncio.Semaphore(ai_concurrency)
    tasks = [
        _analyze_single(doc_id, ai_config_id, system_prompt_text, semaphore)
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
    """
    Analysiert ein einzelnes Dokument mit KI-Extraktion.

    ARCHITEKTUR — Event-Loop-Schutz:
      Alle DB-Operationen laufen via asyncio.to_thread() in Threads.
      Alle IO-Operationen (PDF-Rendering) laufen via _run_ki_io() im KI-Pool.
      Der Event-Loop-Thread macht KEINE blockierenden Aufrufe.

    Phase 1: DB-Daten lesen         → asyncio.to_thread(_db_analyze_read)
    Phase 2: PDF → Bilder           → _run_ki_io() (dedizierter Pool)
    Phase 3: KI-API-Aufruf          → async httpx (nativ nicht-blockierend)
    Phase 4: Ergebnisse in DB       → asyncio.to_thread(_db_analyze_write)
    """
    async with semaphore:
        # ── Phase 1: Alle Daten aus DB lesen (im Thread, nicht-blockierend) ──
        data = await asyncio.to_thread(_db_analyze_read, doc_id, ai_config_id)
        if data is None:
            return  # Fehler wurde bereits von _db_analyze_read in DB geschrieben

        pdf_path: Path = data["pdf_path"]
        original_filename: str = data["original_filename"]
        batch_id: int | None = data["batch_id"]
        img_dpi: int = data["img_dpi"]
        img_format: str = data["img_format"]
        img_quality: int = data["img_quality"]
        ai_api_url: str = data["ai_api_url"]
        ai_api_key: str | None = data["ai_api_key"]
        ai_model_name: str = data["ai_model_name"]
        ai_max_tokens: int = data["ai_max_tokens"]
        ai_temperature: float = data["ai_temperature"]
        ai_reasoning: str = data["ai_reasoning"]
        ai_endpoint_type: str = data["ai_endpoint_type"]

        # ── Phase 2: PDF → Bilder (blockierende IO, kein DB-Handle offen) ────
        logger.info("Rendere PDF für Dokument #%d: %s", doc_id, pdf_path.name)
        try:
            images_b64: list = await _run_ki_io(
                pdf_service.pdf_to_base64_images,
                pdf_path,
                img_dpi,
                img_format,
                img_quality,
            )
        except Exception as exc:
            logger.error("Fehler beim Rendern von #%d: %s", doc_id, exc)
            _set_error(doc_id, f"PDF-Rendering-Fehler: {exc}")
            return

        if not images_b64:
            _set_error(doc_id, "PDF konnte nicht gerendert werden")
            return

        # ── Phase 3: KI-API-Aufruf (async httpx, kein DB-Handle offen) ───────
        logger.info("Starte KI-Extraktion für Dokument #%d (%d Seite(n))", doc_id, len(images_b64))

        # Minimales Config-Proxy-Objekt für ai_service (nur benötigte Felder)
        class _ConfigProxy:
            def __init__(self):
                self.api_url = ai_api_url
                self.api_key = ai_api_key
                self.model_name = ai_model_name
                self.max_tokens = ai_max_tokens
                self.temperature = ai_temperature
                self.reasoning = ai_reasoning
                self.endpoint_type = ai_endpoint_type

        extracted_fields, order_positions, raw_response = await ai_service.extract_invoice_data(
            images_b64=images_b64,
            config=_ConfigProxy(),
            system_prompt_text=system_prompt_text,
        )

        # ── Phase 4: Ergebnisse in DB schreiben (im Thread, nicht-blockierend) ─
        await asyncio.to_thread(
            _db_analyze_write,
            doc_id,
            original_filename,
            batch_id,
            ai_model_name,
            len(images_b64),
            extracted_fields,
            order_positions,
            raw_response,
        )


# ─── DELETE /api/documents/{id} — Soft-Delete ───────────────────────────────

@router.delete("/{doc_id}", response_model=DocumentDetail)
def soft_delete_document(doc_id: int, db: Session = Depends(get_db)):
    """
    Markiert ein Dokument als gelöscht (Soft-Delete).
    Die PDF-Datei und alle Extraktionsdaten bleiben erhalten.
    Das Dokument kann über POST /{id}/restore wiederhergestellt werden.
    """
    doc = crud.document.soft_delete(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return crud.document.get_by_id_with_details(db, doc_id)


# ─── POST /api/documents/{id}/restore — Wiederherstellen ────────────────────

@router.post("/{doc_id}/restore", response_model=DocumentDetail)
def restore_document(doc_id: int, db: Session = Depends(get_db)):
    """Stellt ein soft-gelöschtes Dokument wieder her."""
    doc = crud.document.restore(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return crud.document.get_by_id_with_details(db, doc_id)


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
