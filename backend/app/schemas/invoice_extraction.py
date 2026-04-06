"""
Pydantic-Schemas für extrahierte Rechnungsdaten und Bestellpositionen.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OrderPositionRead(BaseModel):
    """Eine einzelne Bestellposition innerhalb einer Rechnung."""

    id: int
    document_id: int
    position_index: int
    product_description: str | None
    article_number: str | None
    unit_price: Decimal | None
    total_price: Decimal | None
    quantity: Decimal | None
    unit: str | None
    discount: str | None

    model_config = ConfigDict(from_attributes=True)


class InvoiceExtractionRead(BaseModel):
    """Alle extrahierten Rechnungsfelder eines Dokuments."""

    id: int
    document_id: int

    # Lieferantendaten
    supplier_name: str | None
    supplier_address: str | None
    hrb_number: str | None
    tax_number: str | None
    vat_id: str | None

    # Bankverbindung
    bank_name: str | None
    iban: str | None
    bic: str | None

    # Rechnungsidentifikation
    customer_number: str | None
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None

    # Beträge
    total_amount: Decimal | None
    discount_amount: Decimal | None
    cash_discount_amount: Decimal | None

    # Zahlungsbedingungen
    payment_terms: str | None

    # Rohantwort der KI (für Debugging)
    raw_response: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
