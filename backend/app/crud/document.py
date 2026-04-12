"""
CRUD-Operationen für importierte Dokumente.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

from sqlalchemy import outerjoin
from sqlalchemy.orm import Session, joinedload

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
        )
        .filter(Document.id == doc_id)
        .first()
    )


def get_all_filtered(
    db: Session,
    company: str | None = None,
    year: int | None = None,
    status: str | None = None,
    total_min: float | None = None,
    total_max: float | None = None,
    page_min: int | None = None,
    page_max: int | None = None,
    batch_ids: list[int] | None = None,
    include_deleted: bool = False,
) -> list[Document]:
    """
    Gibt alle Dokumente zurück, optional gefiltert.

    Für Betragsfilter wird ein Outer Join auf invoice_extractions gemacht,
    damit Dokumente ohne Extraktion weiterhin erscheinen (außer wenn ein
    Betragsfilter aktiv ist, der eine vorhandene Extraktion voraussetzt).
    """
    query = db.query(Document).options(joinedload(Document.extraction))

    # Soft-Delete-Filter: standardmäßig nur nicht-gelöschte Dokumente anzeigen
    if not include_deleted:
        query = query.filter(Document.deleted_at.is_(None))

    # Import-Batch-Filter
    if batch_ids:
        query = query.filter(Document.batch_id.in_(batch_ids))

    # Betragsfilter benötigen den Join
    if total_min is not None or total_max is not None:
        query = query.outerjoin(
            InvoiceExtraction,
            Document.id == InvoiceExtraction.document_id,
        )
        if total_min is not None:
            query = query.filter(InvoiceExtraction.total_amount >= Decimal(str(total_min)))
        if total_max is not None:
            query = query.filter(InvoiceExtraction.total_amount <= Decimal(str(total_max)))

    if company:
        query = query.filter(Document.company.ilike(f"%{company}%"))
    if year is not None:
        query = query.filter(Document.year == year)
    if status:
        query = query.filter(Document.status == status)
    if page_min is not None:
        query = query.filter(Document.page_count >= page_min)
    if page_max is not None:
        query = query.filter(Document.page_count <= page_max)

    return query.order_by(Document.id.desc()).all()


def save_extraction(
    db: Session,
    doc_id: int,
    extracted_data: dict,
    positions: list[dict],
    raw_response: str,
    supplier_id: int | None = None,
    ki_stats: dict | None = None,
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
