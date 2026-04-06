"""
Pydantic-Schemas für importierte Dokumente (PDF-Rechnungen).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    """Basisanzeige eines Dokuments (in Listen und Batch-Detail)."""

    id: int
    batch_id: int
    original_filename: str
    stored_filename: str | None
    file_size_bytes: int
    page_count: int
    company: str
    year: int
    comment: str | None
    status: str
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListRead(DocumentRead):
    """
    Dokument in der Beleg-Listenansicht — enthält zusätzlich
    Kurzfelder aus der verknüpften Extraktion (falls vorhanden).
    """

    total_amount: float | None = None
    invoice_number: str | None = None
    supplier_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentCommentUpdate(BaseModel):
    """Schema für das Aktualisieren des Dokument-Kommentars (PATCH)."""

    comment: str | None = None


class DocumentDetail(DocumentRead):
    """
    Detailansicht eines Dokuments inkl. extrahierter Rechnungsdaten
    und aller Bestellpositionen.
    """

    # Extrahierte Rechnungsfelder (None, wenn noch nicht extrahiert)
    extraction: "InvoiceExtractionRead | None" = None

    # Liste aller Bestellpositionen
    order_positions: list["OrderPositionRead"] = []

    model_config = ConfigDict(from_attributes=True)


# Zirkuläre Imports auflösen
from app.schemas.invoice_extraction import InvoiceExtractionRead, OrderPositionRead  # noqa: E402
DocumentDetail.model_rebuild()
