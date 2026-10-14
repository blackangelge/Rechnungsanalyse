"""
CRUD-Operationen für importierte Dokumente.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

from sqlalchemy import func, outerjoin
from sqlalchemy.orm import Session, defer, joinedload

from app.models.document import Document
from app.models.invoice_extraction import InvoiceExtraction
from app.models.order_position import OrderPosition


def create(
    db: Session,
    batch_id: int,
    original_filename: str,
    file_size_bytes: int,
    company: str,
    year: int,
) -> Document:
    """
    Erstellt einen neuen Dokument-Datensatz (ohne stored_filename — wird
    erst nach dem Kopiervorgang gesetzt, da die ID als Dateiname dient).
    """
    obj = Document(
        batch_id=batch_id,
        original_filename=original_filename,
        file_size_bytes=file_size_bytes,
        company=company,
        year=year,
        status="pending",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_after_copy(
    db: Session,
    doc_id: int,
    stored_filename: str,
    page_count: int,
) -> Document | None:
    """
    Setzt stored_filename und page_count nach dem erfolgreichen Kopieren.
    Dies ist Schritt 2 des Zwei-Schritt-Prozesses (Insert → Copy → Update).
    """
    obj = db.get(Document, doc_id)
    if obj is None:
        return None
    obj.stored_filename = stored_filename
    obj.page_count = page_count
    obj.status = "processing"
    db.commit()
    db.refresh(obj)
    return obj


def update_status(
    db: Session,
    doc_id: int,
    status: str,
    error_message: str | None = None,
) -> Document | None:
    """Aktualisiert den Verarbeitungsstatus eines Dokuments."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return None
    obj.status = status
    if error_message is not None:
        obj.error_message = error_message
    db.commit()
    db.refresh(obj)
    return obj


def soft_delete(db: Session, doc_id: int) -> Document | None:
    """Markiert ein Dokument als gelöscht (Soft-Delete). PDF bleibt erhalten."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return None
    obj.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def restore(db: Session, doc_id: int) -> Document | None:
    """Stellt ein soft-gelöschtes Dokument wieder her."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return None
    obj.deleted_at = None
    db.commit()
    db.refresh(obj)
    return obj


def update_comment(db: Session, doc_id: int, comment: str | None) -> Document | None:
    """Setzt oder entfernt den Kommentar eines Dokuments."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return None
    obj.comment = comment
    db.commit()
    db.refresh(obj)
    return obj


def update_document_type(db: Session, doc_id: int, type_id: int | None) -> Document | None:
    """Setzt den erkannten Dokumententyp eines Dokuments."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return None
    obj.document_type_id = type_id
    db.commit()
    db.refresh(obj)
    return obj


def get_by_id_with_details(db: Session, doc_id: int) -> Document | None:
    """
    Gibt ein Dokument inkl. Extraktion und Bestellpositionen zurück.
    Nutzt joinedload um N+1-Abfragen zu vermeiden.
    """
    return (
        db.query(Document)
        .options(
            joinedload(Document.extraction),
            joinedload(Document.order_positions),
            joinedload(Document.document_type),
        )
        .filter(Document.id == doc_id)
        .first()
    )


# Filter, die von get_all_filtered / count_filtered / get_ids_filtered gleichermaßen verstanden werden
_FILTER_KEYS = (
    "company", "year", "status", "total_min", "total_max", "page_min", "page_max", "batch_ids",
    "include_deleted", "has_extraction", "supplier_name_filter", "doc_id", "document_type_ids",
    "validation_statuses",
)


def _filtered_query(db: Session, **f):
    """
    Basisabfrage mit allen Filtern (ohne Eager-Loading, Sortierung und Paginierung).

    Für Betrags-, KI-, Lieferanten- und Prüfstatus-Filter wird ein Outer Join auf
    invoice_extractions gemacht (1:1 → keine Zeilenvervielfachung).
    """
    unknown = set(f) - set(_FILTER_KEYS)
    if unknown:
        raise TypeError(f"Unbekannte Filter: {sorted(unknown)}")
    g = f.get
    query = db.query(Document)

    # Soft-Delete-Filter: standardmäßig nur nicht-gelöschte Dokumente anzeigen
    if not g("include_deleted"):
        query = query.filter(Document.deleted_at.is_(None))

    if g("batch_ids"):
        query = query.filter(Document.batch_id.in_(g("batch_ids")))

    needs_join = (
        g("total_min") is not None
        or g("total_max") is not None
        or g("has_extraction") is not None
        or g("supplier_name_filter") is not None
        or bool(g("validation_statuses"))
    )
    if needs_join:
        query = query.outerjoin(InvoiceExtraction, Document.id == InvoiceExtraction.document_id)

    if g("total_min") is not None:
        query = query.filter(InvoiceExtraction.total_amount >= Decimal(str(g("total_min"))))
    if g("total_max") is not None:
        query = query.filter(InvoiceExtraction.total_amount <= Decimal(str(g("total_max"))))
    if g("has_extraction") is True:
        query = query.filter(InvoiceExtraction.id.isnot(None))
    elif g("has_extraction") is False:
        query = query.filter(InvoiceExtraction.id.is_(None))
    if g("validation_statuses"):
        query = query.filter(InvoiceExtraction.validation_status.in_(g("validation_statuses")))
    if g("supplier_name_filter"):
        query = query.filter(InvoiceExtraction.supplier_name.ilike(f"%{g('supplier_name_filter')}%"))

    if g("company"):
        query = query.filter(Document.company.ilike(f"%{g('company')}%"))
    if g("year") is not None:
        query = query.filter(Document.year == g("year"))
    if g("status"):
        query = query.filter(Document.status == g("status"))
    if g("page_min") is not None:
        query = query.filter(Document.page_count >= g("page_min"))
    if g("page_max") is not None:
        query = query.filter(Document.page_count <= g("page_max"))
    if g("doc_id") is not None:
        query = query.filter(Document.id == g("doc_id"))
    if g("document_type_ids"):
        query = query.filter(Document.document_type_id.in_(g("document_type_ids")))
    return query


def get_all_filtered(
    db: Session,
    limit: int | None = None,
    offset: int = 0,
    **filters,
) -> list[Document]:
    """
    Gibt Dokumente (neueste zuerst) zurück, optional gefiltert und paginiert.

    Für die Listenansicht werden die schweren Textspalten NICHT geladen (KI-Rohantwort,
    Prüfdetails, Prompt-/Workflow-Snapshots) — bei tausenden Belegen machen sie sonst
    hunderte MB aus, obwohl die Liste sie nie anzeigt.
    """
    query = _filtered_query(db, **filters).options(
        joinedload(Document.extraction)
        .defer(InvoiceExtraction.raw_response)
        .defer(InvoiceExtraction.validation_details),
        joinedload(Document.document_type),
        defer(Document.used_system_prompt),
        defer(Document.used_doc_type_prompt),
        defer(Document.used_recheck_prompt),
        defer(Document.used_workflow_graph),
        defer(Document.workflow_trace),
    ).order_by(Document.id.desc())
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    return query.all()


def count_filtered(db: Session, **filters) -> int:
    """Anzahl der Treffer (ohne Eager-Loading → schnell)."""
    return _filtered_query(db, **filters).with_entities(func.count(Document.id)).scalar() or 0


def get_ids_filtered(db: Session, **filters) -> list[int]:
    """Alle Treffer-IDs (neueste zuerst) — z.B. für „alle Treffer auswählen"."""
    rows = _filtered_query(db, **filters).with_entities(Document.id).order_by(Document.id.desc()).all()
    return [r[0] for r in rows]


def get_filter_options(db: Session) -> dict:
    """Werte für die Filter-Dropdowns: Jahre und Firmen aller (nicht gelöschten) Belege."""
    years = [r[0] for r in db.query(Document.year).filter(Document.deleted_at.is_(None))
             .distinct().order_by(Document.year.desc()).all()]
    companies = [r[0] for r in db.query(Document.company).filter(Document.deleted_at.is_(None))
                 .distinct().order_by(Document.company).all()]
    return {"years": years, "companies": companies}


def save_extraction(
    db: Session,
    doc_id: int,
    extracted_data: dict,
    positions: list[dict],
    raw_response: str,
    supplier_id: int | None = None,
    ki_stats: dict | None = None,
    validation: dict | None = None,
) -> InvoiceExtraction:
    """
    Speichert extrahierte Rechnungsdaten und Bestellpositionen.
    Falls bereits eine Extraktion existiert, wird sie überschrieben.

    Args:
        doc_id: ID des Dokuments
        extracted_data: Dict mit den Rechnungsfeldern (supplier_name, iban, ...)
        positions: Liste von Dicts für die Bestellpositionen
        raw_response: vollständige KI-Antwort als String (für Debugging)
        supplier_id: optionale ID des verknüpften Lieferanten-Stammdatensatzes
        ki_stats: optionale KI-Statistiken (Token-Counts, Geschwindigkeit)
        validation: optionales Ergebnis der Plausibilitätsprüfung
                    (ValidationResult.to_dict() + Zusatzinfos)
    """
    # Vorhandene Extraktion löschen (falls Wiederholung)
    db.query(InvoiceExtraction).filter(
        InvoiceExtraction.document_id == doc_id
    ).delete()
    db.query(OrderPosition).filter(
        OrderPosition.document_id == doc_id
    ).delete()

    # KI-Statistiken auspacken
    stats = ki_stats or {}
    validation_cols = (
        {
            "validation_status": validation.get("status"),
            "validation_details": json.dumps(validation, ensure_ascii=False),
        }
        if validation else {}
    )

    # Neue Extraktion speichern — erst mit KI-Stats, bei DB-Fehler ohne Retry
    extraction = InvoiceExtraction(
        document_id=doc_id,
        raw_response=raw_response,
        supplier_id=supplier_id,
        ki_input_tokens=stats.get("input_tokens"),
        ki_output_tokens=stats.get("output_tokens"),
        ki_reasoning_tokens=stats.get("reasoning_tokens"),
        ki_tokens_per_second=stats.get("tokens_per_second"),
        ki_time_to_first_token=stats.get("time_to_first_token"),
        ki_total_duration=stats.get("total_duration"),
        **validation_cols,
        **extracted_data,
    )
    db.add(extraction)

    # Bestellpositionen speichern
    for idx, pos in enumerate(positions):
        order_pos = OrderPosition(
            document_id=doc_id,
            position_index=idx,
            **pos,
        )
        db.add(order_pos)

    try:
        db.commit()
    except Exception as commit_exc:
        # Fallback: ohne KI-Stats speichern (z.B. wenn Migration noch nicht gelaufen)
        logger.warning(
            "Commit mit KI-Stats fehlgeschlagen (Migration ausstehend?), "
            "Retry ohne Stats: %s", commit_exc
        )
        db.rollback()
        # Nochmal löschen, da der rollback die deletes rückgängig macht
        db.query(InvoiceExtraction).filter(
            InvoiceExtraction.document_id == doc_id
        ).delete()
        db.query(OrderPosition).filter(
            OrderPosition.document_id == doc_id
        ).delete()
        extraction = InvoiceExtraction(
            document_id=doc_id,
            raw_response=raw_response,
            supplier_id=supplier_id,
            **extracted_data,
        )
        db.add(extraction)
        for idx, pos in enumerate(positions):
            order_pos = OrderPosition(
                document_id=doc_id,
                position_index=idx,
                **pos,
            )
            db.add(order_pos)
        db.commit()

    db.refresh(extraction)
    return extraction


def save_used_prompts(
    db: Session,
    doc_id: int,
    system_prompt: str | None = None,
    doc_type_prompt: str | None = None,
) -> None:
    """
    Speichert den Wortlaut der bei der Analyse verwendeten Systemprompts am
    Dokument. Wird zu Beginn jeder (Neu-)Analyse aufgerufen und überschreibt
    die vorherigen Prompts; der Nachprüfungs-Prompt wird dabei zurückgesetzt.
    """
    obj = db.get(Document, doc_id)
    if obj is None:
        return
    obj.used_system_prompt = system_prompt
    obj.used_doc_type_prompt = doc_type_prompt
    obj.used_recheck_prompt = None
    # Workflow-Angaben der vorherigen Analyse zurücksetzen (neue Analyse = neuer Stand)
    obj.used_workflow_id = None
    obj.used_workflow_name = None
    obj.used_workflow_graph = None
    obj.workflow_trace = None
    db.commit()


def set_used_prompt(
    db: Session,
    doc_id: int,
    system_prompt: str | None = None,
    doc_type_prompt: str | None = None,
) -> None:
    """Setzt nur die übergebenen Prompts (None = unverändert) — für Workflow-Knoten."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return
    if system_prompt is not None:
        obj.used_system_prompt = system_prompt
    if doc_type_prompt is not None:
        obj.used_doc_type_prompt = doc_type_prompt
    db.commit()


def save_workflow_run(
    db: Session,
    doc_id: int,
    workflow_id: int | None,
    workflow_name: str,
    graph: dict,
    trace: list[dict],
) -> None:
    """Speichert Workflow-Snapshot und Ablaufprotokoll der Analyse am Dokument."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return
    obj.used_workflow_id = workflow_id
    obj.used_workflow_name = workflow_name
    obj.used_workflow_graph = json.dumps(graph, ensure_ascii=False)
    obj.workflow_trace = json.dumps(trace, ensure_ascii=False)
    db.commit()


def save_recheck_prompt(db: Session, doc_id: int, recheck_prompt: str | None) -> None:
    """Speichert den Prompt der zweiten KI-Abfrage (Plausibilitäts-Nachprüfung)."""
    obj = db.get(Document, doc_id)
    if obj is None:
        return
    obj.used_recheck_prompt = recheck_prompt
    db.commit()


def update_validation(
    db: Session,
    doc_id: int,
    validation: dict,
    corrected_positions: list[dict] | None = None,
) -> InvoiceExtraction | None:
    """
    Schreibt ein (neues) Prüfergebnis in die Extraktion. Optional werden
    korrigierte `total_price`-Werte in die Positionen übernommen
    (`corrected_positions` = [{"position": idx, "to": wert}, ...]).
    """
    extraction = (
        db.query(InvoiceExtraction).filter(InvoiceExtraction.document_id == doc_id).first()
    )
    if extraction is None:
        return None
    for corr in corrected_positions or []:
        pos = (
            db.query(OrderPosition)
            .filter(
                OrderPosition.document_id == doc_id,
                OrderPosition.position_index == corr["position"],
            )
            .first()
        )
        if pos is not None:
            pos.total_price = Decimal(str(corr["to"]))
    extraction.validation_status = validation.get("status")
    extraction.validation_details = json.dumps(validation, ensure_ascii=False)
    db.commit()
    db.refresh(extraction)
    return extraction
