"""
Router für importierte Dokumente.

Endpunkte:
  GET   /api/documents/             — Liste aller Dokumente mit optionalen Filtern
  POST  /api/documents/analyze      — KI-Analyse für ausgewählte Dokumente starten
  GET   /api/documents/{id}         — Dokument mit Extraktion und Positionen
  GET   /api/documents/{id}/preview — PDF-Datei streamen (für Browser-Vorschau)
  PATCH /api/documents/{id}/comment — Kommentar aktualisieren
  POST  /api/documents/{id}/validate — Plausibilitätsprüfung erneut ausführen
  POST  /api/documents/{id}/validation/confirm — Prüfung manuell als "geprüft" bestätigen
"""

import asyncio
import json
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
from app.models.document import Document as DocModel
from app.schemas.document import DocumentCommentUpdate, DocumentDetail, DocumentListRead
from app.services import ai_service, pdf_edit_service, pdf_service, plausibility_service

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
    # Workflow (Analyse-Ablauf). None = automatisch: Workflow des Lieferanten, sonst Standard-Workflow,
    # sonst der klassische Ablauf.
    workflow_id: Optional[int] = None


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
    has_extraction: Optional[bool] = None,
    supplier_name: Optional[str] = None,
    doc_id: Optional[int] = None,
    document_type_ids: Optional[list[int]] = Query(default=None),
    validation_status: Optional[list[str]] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Gibt alle Dokumente zurück, optional gefiltert.
    validation_status filtert nach Ergebnis der Plausibilitätsprüfung
    (ok, corrected, ai_corrected, needs_review, manual_ok, unchecked).
    include_deleted=true zeigt auch soft-gelöschte Dokumente an.
    has_extraction=true/false filtert nach KI-analysierten Dokumenten.
    supplier_name filtert nach Lieferantenname (case-insensitive LIKE).
    document_type_ids filtert nach Dokumententypen (mehrere möglich).
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
        has_extraction=has_extraction,
        supplier_name_filter=supplier_name,
        doc_id=doc_id,
        document_type_ids=document_type_ids,
        validation_statuses=validation_status,
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

    if payload.workflow_id is not None and crud.workflow.get_by_id(db, payload.workflow_id) is None:
        raise HTTPException(status_code=404, detail=f"Workflow #{payload.workflow_id} nicht gefunden")

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
            workflow_id=payload.workflow_id,
        )
    )

    return AnalyzeResponse(
        started=len(valid_ids),
        message=f"KI-Analyse für {len(valid_ids)} Dokument(e) gestartet",
    )


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

        # Dokumententyp-Prompt und Typliste laden
        doc_type_prompt = crud.system_prompt.get_doc_type_prompt(db)
        doc_types = crud.document_type.get_all(db)

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
            # Zweistufige Analyse
            "doc_type_prompt_text": doc_type_prompt.content if doc_type_prompt else None,
            "document_types": [{"id": dt.id, "name": dt.name} for dt in doc_types],
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


def _db_prepare_pdf(
    doc_id: int, original_filename: str, batch_id: int | None, allow_auto_trim: bool = True
) -> None:
    """
    Vor dem Rendern (sync, für asyncio.to_thread): optional automatisch kürzen
    (neue PDF-Version) und die analysierte PDF-Version am Dokument festhalten.
    Fehler beim Kürzen brechen die Analyse nie ab — es wird dann das volle PDF analysiert.
    """
    db = SessionLocal()
    try:
        doc = db.get(DocModel, doc_id)
        if doc is None:
            return
        pdf_settings = crud.pdf_settings.get_or_create(db)
        if allow_auto_trim and pdf_settings.auto_trim_enabled:
            try:
                version = pdf_edit_service.auto_trim(db, doc, pdf_settings.auto_trim_max_pages)
                if version is not None:
                    crud.system_log.add(
                        db, category="pdf", level="info",
                        message=f"PDF automatisch gekürzt: {original_filename} — {version.description}",
                        batch_id=batch_id, document_id=doc_id,
                    )
            except Exception as exc:
                db.rollback()
                logger.warning("Auto-Kürzen für #%d fehlgeschlagen: %s", doc_id, exc)
                crud.system_log.add(
                    db, category="pdf", level="warning",
                    message=f"Automatisches Kürzen fehlgeschlagen: {original_filename} — {exc}",
                    batch_id=batch_id, document_id=doc_id,
                )
        doc = db.get(DocModel, doc_id)
        doc.analyzed_pdf_version = doc.pdf_version
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("PDF-Vorbereitung für #%d fehlgeschlagen: %s", doc_id, exc)
    finally:
        db.close()


def _db_save_used_prompts(
    doc_id: int, system_prompt: str | None, doc_type_prompt: str | None
) -> None:
    """Speichert den Wortlaut der verwendeten Systemprompts (eigene Session)."""
    db = SessionLocal()
    try:
        crud.document.save_used_prompts(db, doc_id, system_prompt, doc_type_prompt)
    except Exception as exc:
        # Prompt-Snapshot ist Zusatzinformation — ein Fehler hier darf die Analyse nicht abbrechen
        db.rollback()
        logger.warning("Systemprompts für #%d nicht gespeichert: %s", doc_id, exc)
    finally:
        db.close()


def _db_save_recheck_prompt(doc_id: int, prompt: str) -> None:
    db = SessionLocal()
    try:
        crud.document.save_recheck_prompt(db, doc_id, prompt)
    except Exception as exc:
        db.rollback()
        logger.warning("Nachprüfungs-Prompt für #%d nicht gespeichert: %s", doc_id, exc)
    finally:
        db.close()


_KI_ERROR_PREFIXES = (
    "KI überlastet:", "KI-Fehler:", "KI-Timeout",
    "KI-Verbindungsfehler", "Unerwarteter KI-Fehler",
)


def _parse_raw(raw_response: str | None) -> dict | None:
    """Parst die gespeicherte KI-Antwort sicher (None bei leerem/ungültigem JSON)."""
    if not raw_response:
        return None
    try:
        data = json.loads(raw_response)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def _plausibility_pass(
    doc_id: int,
    images_b64: list,
    config_proxy,
    base_prompt: str | None,
    extracted_fields: dict,
    order_positions: list,
    raw_response: str,
    ki_stats: dict,
    auto_correct: bool = True,
    ai_recheck: bool = True,
) -> tuple[dict, list, str, dict, dict | None]:
    """
    Plausibilitätsprüfung in drei Stufen (Stufe 1 und 2 lassen sich im Workflow abschalten):
      1. rechnerische Prüfung inkl. automatischer Einheiten-Korrektur
      2. bei Auffälligkeiten: zweite KI-Abfrage mit Prüfhinweisen
      3. besteht auch diese nicht: Status "needs_review" (manuelle Bearbeitung)

    Gibt (fields, positions, raw_response, ki_stats, validation_dict) zurück.
    validation_dict ist None, wenn nichts zu prüfen war (KI-Fehler / leeres Ergebnis).
    """
    if raw_response.startswith(_KI_ERROR_PREFIXES) or not (extracted_fields or order_positions):
        return extracted_fields, order_positions, raw_response, ki_stats, None

    ps = plausibility_service
    result = await asyncio.to_thread(
        ps.validate_invoice, extracted_fields, order_positions, _parse_raw(raw_response), auto_correct
    )
    validation = result.to_dict()
    validation["method"] = "rules"
    if result.status != ps.STATUS_NEEDS_REVIEW or not ai_recheck:
        return extracted_fields, order_positions, raw_response, ki_stats, validation

    # ── Stufe 2: zweite KI-Abfrage ───────────────────────────────────────────
    issue_texts = [i.message for i in result.blocking_issues]
    logger.info("Plausibilität #%d: %d Auffälligkeit(en) → zweite KI-Abfrage",
                doc_id, len(issue_texts))
    f2, p2, raw2, stats2, recheck_prompt = await asyncio.to_thread(
        ai_service.recheck_invoice_data,
        images_b64, config_proxy, base_prompt, issue_texts, raw_response,
    )
    await asyncio.to_thread(_db_save_recheck_prompt, doc_id, recheck_prompt)
    merged_stats = _merge_ki_stats(ki_stats or {}, stats2 or {})
    validation["recheck"] = {"performed": True, "issues_before": [i.to_dict() for i in result.issues]}

    if raw2.startswith(_KI_ERROR_PREFIXES) or not (f2 or p2):
        validation["recheck"]["outcome"] = "failed"
        validation["recheck"]["error"] = raw2[:300]
        return extracted_fields, order_positions, raw_response, merged_stats, validation

    result2 = await asyncio.to_thread(ps.validate_invoice, f2, p2, _parse_raw(raw2))
    if result2.status in (ps.STATUS_OK, ps.STATUS_CORRECTED):
        validation2 = result2.to_dict()
        validation2["status"] = ps.STATUS_AI_CORRECTED
        validation2["method"] = "ai_recheck"
        validation2["recheck"] = {
            "performed": True, "outcome": "corrected",
            "issues_before": [i.to_dict() for i in result.issues],
        }
        return f2, p2, raw2, merged_stats, validation2

    # Auch die zweite Auslesung ist nicht plausibel → Original behalten, markieren
    validation["recheck"]["outcome"] = "still_inconsistent"
    validation["recheck"]["issues_after"] = [i.to_dict() for i in result2.issues]
    return extracted_fields, order_positions, raw_response, merged_stats, validation


def _db_save_document_type(doc_id: int, type_id: int | None) -> None:
    """Speichert den erkannten Dokumententyp in der DB (eigene Session)."""
    db = SessionLocal()
    try:
        crud.document.update_document_type(db, doc_id, type_id)
    except Exception as exc:
        logger.error("Fehler beim Speichern des Dokumententyps für #%d: %s", doc_id, exc)
    finally:
        db.close()


def _db_type_only_finish(
    doc_id: int,
    type_id: int | None,
    type_name: str | None,
    page_count: int,
    batch_id: int | None,
    original_filename: str,
    ki_stats: dict | None = None,
) -> None:
    """
    Schließt die Analyse ab ohne Rechnungsdaten-Extraktion.
    Wird verwendet wenn der Dokumententyp KEINE Eingangsrechnung ist.
    Ki-Stats (Token-Verbrauch der Typ-Erkennung) werden direkt am Dokument gespeichert.
    """
    db = SessionLocal()
    try:
        from app.models.document import Document as _DocModel
        doc = db.get(_DocModel, doc_id)
        if doc is not None:
            doc.document_type_id = type_id
            if page_count > 0:
                doc.page_count = page_count
            doc.status = "done"
            # KI-Stats der Typ-Erkennung direkt auf dem Dokument speichern
            if ki_stats:
                doc.doc_ki_input_tokens  = ki_stats.get("input_tokens")
                doc.doc_ki_output_tokens = ki_stats.get("output_tokens")
                doc.doc_ki_total_duration = ki_stats.get("total_duration")
            db.commit()

        crud.system_log.add(
            db, category="ki", level="info",
            message=(f"Dokumententyp erkannt (keine Extraktion): "
                     f"{original_filename} → {type_name or 'Unbekannt'}"),
            batch_id=batch_id, document_id=doc_id,
        )
        logger.info(
            "Dokument #%d: Typ erkannt als '%s' — keine Rechnungsextraktion", doc_id, type_name
        )
    except Exception as exc:
        logger.error("Fehler beim Abschluss ohne Extraktion für #%d: %s", doc_id, exc)
        try:
            db.rollback()
            _set_error(doc_id, f"Abschlussfehler: {exc}")
        except Exception:
            pass
    finally:
        db.close()


def _merge_ki_stats(stats1: dict, stats2: dict) -> dict:
    """Summiert die KI-Statistiken zweier API-Aufrufe."""
    def _add(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    return {
        "input_tokens":        _add(stats1.get("input_tokens"),  stats2.get("input_tokens")),
        "output_tokens":       _add(stats1.get("output_tokens"), stats2.get("output_tokens")),
        "reasoning_tokens":    _add(stats1.get("reasoning_tokens"), stats2.get("reasoning_tokens")),
        # tokens_per_second aus Stufe 2 (Extraktion) bevorzugen, Fallback Stufe 1
        "tokens_per_second":   stats2.get("tokens_per_second") or stats1.get("tokens_per_second"),
        # time_to_first_token aus Stufe 1 (erster Aufruf)
        "time_to_first_token": stats1.get("time_to_first_token"),
        "total_duration":      _add(stats1.get("total_duration"), stats2.get("total_duration")),
    }


def _db_analyze_write(
    doc_id: int,
    original_filename: str,
    batch_id: int | None,
    ai_model_name: str,
    page_count: int,
    extracted_fields: dict,
    order_positions: list,
    raw_response: str,
    ki_stats: dict | None = None,
    document_type_id: int | None = None,
    validation: dict | None = None,
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

        # Felder entfernen, die nur für den Supplier-Lookup genutzt werden
        # und KEINE Spalten in invoice_extractions sind
        _SUPPLIER_ONLY_KEYS = {"supplier_street", "supplier_zip", "supplier_city"}
        extraction_data = {k: v for k, v in extracted_fields.items()
                           if k not in _SUPPLIER_ONLY_KEYS}

        crud.document.save_extraction(
            db=db,
            doc_id=doc_id,
            extracted_data=extraction_data,
            positions=order_positions,
            raw_response=raw_response,
            supplier_id=supplier_id,
            ki_stats=ki_stats,
            validation=validation,
        )

        # Seitenanzahl und optional Dokumententyp setzen
        if page_count > 0 or document_type_id is not None:
            from app.models.document import Document as _DocModel
            _doc = db.get(_DocModel, doc_id)
            if _doc is not None:
                if page_count > 0:
                    _doc.page_count = page_count
                if document_type_id is not None:
                    _doc.document_type_id = document_type_id
                db.commit()

        is_ki_error = raw_response.startswith(_KI_ERROR_PREFIXES)
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
                         f"{filled} Felder, {len(order_positions)} Positionen, {page_count} Seite(n)"),
                batch_id=batch_id, document_id=doc_id,
            )
            logger.info("Dokument #%d erfolgreich analysiert (%d Seiten)", doc_id, page_count)
            if validation:
                v_issues = [i for i in validation.get("issues", [])
                            if i.get("severity") in ("warning", "error")]
                crud.system_log.add(
                    db, category="ki",
                    level="warning" if validation.get("status") == "needs_review" else "info",
                    message=(f"Plausibilitätsprüfung: {original_filename} — "
                             f"Status {validation.get('status')}"
                             + (f", {len(v_issues)} Auffälligkeit(en)" if v_issues else "")
                             + (f", {len(validation.get('corrections', []))} Korrektur(en)"
                                if validation.get("corrections") else "")),
                    batch_id=batch_id, document_id=doc_id,
                )

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
    workflow_id: int | None = None,
) -> None:
    """
    Hintergrund-Coroutine: Analysiert alle Dokumente nacheinander (sequenziell).

    Warum sequenziell statt parallel?
    - Lokale Modelle (LM Studio, Ollama) verarbeiten ohnehin nur eine Anfrage gleichzeitig.
    - Parallele PDF-Renderungen + JSON-Serialisierungen erschöpfen den Thread-Pool und
      den Arbeitsspeicher des NAS.
    - Sequenziell ist auf einem NAS mit lokalem Modell genauso schnell, aber stabil.
    """
    logger.info("KI-Analyse gestartet: %d Dokument(e) werden nacheinander verarbeitet", len(document_ids))

    for doc_id in document_ids:
        try:
            await _analyze_single(doc_id, ai_config_id, system_prompt_text, workflow_id)
        except Exception as exc:
            logger.exception("Unbehandelter Fehler bei Dokument #%d: %s", doc_id, exc)
            await asyncio.to_thread(_set_error, doc_id, f"Unerwarteter Fehler: {exc}")

    logger.info("KI-Analyse abgeschlossen (%d Dokumente)", len(document_ids))


def _db_resolve_workflow(doc_id: int, explicit_id: int | None) -> dict | None:
    """
    Wählt den Workflow für ein Dokument (sync, für asyncio.to_thread):
      1. explizit gewählter Workflow
      2. Workflow des (bereits bekannten) Lieferanten — greift bei erneuter Analyse
      3. Standard-Workflow
    Gibt None zurück, wenn keiner existiert → klassischer Ablauf.
    """
    import json as _json
    db = SessionLocal()
    try:
        wf = crud.workflow.get_by_id(db, explicit_id) if explicit_id else None
        source = "gewählt"
        if wf is None:
            doc = db.get(DocModel, doc_id)
            supplier = doc.extraction.supplier if doc and doc.extraction else None
            if supplier is not None and supplier.workflow_id:
                wf = crud.workflow.get_by_id(db, supplier.workflow_id)
                source = f"Lieferant {supplier.name}"
        if wf is None:
            wf = crud.workflow.get_default(db)
            source = "Standard"
        if wf is None:
            return None
        return {"id": wf.id, "name": wf.name, "graph": _json.loads(wf.graph), "source": source}
    finally:
        db.close()


async def _analyze_single(
    doc_id: int,
    ai_config_id: int,
    system_prompt_text: str | None,
    workflow_id: int | None = None,
) -> None:
    """
    Analysiert ein einzelnes Dokument — optional zweistufig.

    ARCHITEKTUR — Event-Loop-Schutz:
      Alle DB-Operationen laufen via asyncio.to_thread() in Threads.
      Alle IO-Operationen (PDF-Rendering) laufen via _run_ki_io() im KI-Pool.
      Der Event-Loop-Thread macht KEINE blockierenden Aufrufe.

    Wenn ein Dokumententyp-Systemprompt konfiguriert ist:
      Phase 3a: Dokumententyp erkennen
        → Nicht Eingangsrechnung (ID 1): Typ speichern + fertig
        → Eingangsrechnung: weiter mit Phase 3b
      Phase 3b: Vollständige Rechnungsextraktion (nur für Eingangsrechnung)

    Ohne Dokumententyp-Systemprompt: direkt zur Rechnungsextraktion (alter Modus).
    """
    # ── Workflow-Modus: Ablauf und Prompts kommen aus einem Workflow-Graphen ──
    workflow = await asyncio.to_thread(_db_resolve_workflow, doc_id, workflow_id)
    if workflow is not None:
        from app.services import workflow_runner
        await workflow_runner.analyze_with_workflow(doc_id, ai_config_id, system_prompt_text, workflow)
        return

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
    doc_type_prompt_text: str | None = data["doc_type_prompt_text"]
    document_types: list[dict] = data["document_types"]

    # Wortlaut der verwendeten Prompts am Beleg festhalten (Nachvollziehbarkeit /
    # spätere Neuverarbeitung). Bei Dokumententyp-Prompt nur, wenn er auch genutzt wird.
    await asyncio.to_thread(
        _db_save_used_prompts,
        doc_id,
        system_prompt_text or ai_service.DEFAULT_SYSTEM_PROMPT,
        doc_type_prompt_text if (doc_type_prompt_text and document_types) else None,
    )

    # ── Phase 1b: optional automatisch kürzen, analysierte PDF-Version merken ──
    await asyncio.to_thread(_db_prepare_pdf, doc_id, original_filename, batch_id)

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

    # Seitenanzahl merken (images_b64 wird später freigegeben)
    page_count = len(images_b64)

    # Minimales Config-Proxy-Objekt für ai_service
    class _ConfigProxy:
        def __init__(self):
            self.api_url = ai_api_url
            self.api_key = ai_api_key
            self.model_name = ai_model_name
            self.max_tokens = ai_max_tokens
            self.temperature = ai_temperature
            self.reasoning = ai_reasoning
            self.endpoint_type = ai_endpoint_type

    config_proxy = _ConfigProxy()

    # ── Phase 3: KI-API-Aufruf(e) ─────────────────────────────────────────────
    document_type_id: int | None = None

    if doc_type_prompt_text and document_types:
        # ── Phase 3a: Dokumententyp erkennen ─────────────────────────────────
        logger.info(
            "Starte Dokumententyp-Erkennung für #%d (%d Seite(n))", doc_id, page_count
        )
        type_id, type_name, _type_raw, type_stats = await asyncio.to_thread(
            ai_service.detect_document_type,
            images_b64,
            config_proxy,
            document_types,
            doc_type_prompt_text,
        )
        document_type_id = type_id

        # Dokumententyp sofort in DB speichern (für Fortschrittsanzeige)
        await asyncio.to_thread(_db_save_document_type, doc_id, type_id)

        # Eingangsrechnung (ID 1) → vollständige Extraktion
        # Alle anderen Typen (oder None) → fertig ohne Extraktion
        if type_id != 1:
            del images_b64
            await asyncio.to_thread(
                _db_type_only_finish,
                doc_id, type_id, type_name, page_count, batch_id, original_filename,
                type_stats,
            )
            return

        logger.info(
            "Dokumententyp='%s' → starte Rechnungsextraktion für #%d", type_name, doc_id
        )

        # ── Phase 3b: Rechnungsextraktion (nur Eingangsrechnung) ─────────────
        extracted_fields, order_positions, raw_response, inv_stats = await asyncio.to_thread(
            ai_service.extract_invoice_data,
            images_b64,
            config_proxy,
            system_prompt_text,
        )

        # KI-Statistiken beider Aufrufe summieren
        ki_stats = _merge_ki_stats(type_stats, inv_stats)

    else:
        # Kein Dokumententyp-Prompt → alter Modus: direkte Rechnungsextraktion
        logger.info(
            "Starte KI-Extraktion für Dokument #%d (%d Seite(n))", doc_id, page_count
        )
        extracted_fields, order_positions, raw_response, ki_stats = await asyncio.to_thread(
            ai_service.extract_invoice_data,
            images_b64,
            config_proxy,
            system_prompt_text,
        )

    # ── Phase 3c: Plausibilitätsprüfung (Regeln → zweite KI-Abfrage → Markierung) ──
    (extracted_fields, order_positions, raw_response,
     ki_stats, validation) = await _plausibility_pass(
        doc_id, images_b64, config_proxy, system_prompt_text,
        extracted_fields, order_positions, raw_response, ki_stats,
    )
    del images_b64

    # ── Phase 4: Ergebnisse in DB schreiben (im Thread, nicht-blockierend) ─
    await asyncio.to_thread(
        _db_analyze_write,
        doc_id,
        original_filename,
        batch_id,
        ai_model_name,
        page_count,
        extracted_fields,
        order_positions,
        raw_response,
        ki_stats,
        document_type_id,
        validation,
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


# ─── POST /api/documents/{id}/validate — Prüfung erneut ausführen ───────────

@router.post("/{doc_id}/validate", response_model=DocumentDetail)
def revalidate_document(doc_id: int, db: Session = Depends(get_db)):
    """
    Führt die rechnerische Plausibilitätsprüfung auf den gespeicherten Daten
    erneut aus (ohne KI). Eindeutige Einheitenfehler werden dabei – wie bei der
    Analyse – automatisch korrigiert. Frühere Korrekturen bleiben dokumentiert.
    """
    doc = crud.document.get_by_id_with_details(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    if doc.extraction is None:
        raise HTTPException(status_code=400, detail="Keine Rechnungsdaten zum Prüfen vorhanden")

    ps = plausibility_service
    positions = [
        {
            "quantity": p.quantity, "unit": p.unit, "unit_price": p.unit_price,
            "total_price": p.total_price, "discount": p.discount,
        }
        for p in doc.order_positions
    ]
    fields = {"total_amount": doc.extraction.total_amount}
    result = ps.validate_invoice(fields, positions, _parse_raw(doc.extraction.raw_response))
    validation = result.to_dict()
    validation["method"] = "rules"

    previous = doc.validation or {}
    previous_corrections = previous.get("corrections") or []
    if previous_corrections:
        validation["corrections"] = previous_corrections + validation["corrections"]
        if result.status in (ps.STATUS_OK, ps.STATUS_CORRECTED):
            validation["status"] = previous.get("status") if previous.get("status") in (
                ps.STATUS_CORRECTED, ps.STATUS_AI_CORRECTED
            ) else ps.STATUS_CORRECTED
    if previous.get("recheck"):
        validation["recheck"] = previous["recheck"]

    crud.document.update_validation(
        db, doc_id, validation, corrected_positions=result.corrections
    )
    return crud.document.get_by_id_with_details(db, doc_id)


# ─── POST /api/documents/{id}/validation/confirm — manuell bestätigt ────────

@router.post("/{doc_id}/validation/confirm", response_model=DocumentDetail)
def confirm_validation(doc_id: int, db: Session = Depends(get_db)):
    """Markiert die Extraktion nach manueller Kontrolle als geprüft (Status manual_ok)."""
    doc = crud.document.get_by_id_with_details(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    if doc.extraction is None:
        raise HTTPException(status_code=400, detail="Keine Rechnungsdaten vorhanden")

    validation = dict(doc.validation or {"issues": [], "corrections": [], "checks_run": 0})
    validation["status"] = plausibility_service.STATUS_MANUAL_OK
    validation["confirmed_manually"] = True
    crud.document.update_validation(db, doc_id, validation)
    return crud.document.get_by_id_with_details(db, doc_id)
