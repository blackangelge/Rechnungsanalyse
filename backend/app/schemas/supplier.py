"""
Pydantic-Schema für Lieferanten-Stammdaten.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SupplierRead(BaseModel):
    """Lieferanten-Stammdaten (Lese-Schema)."""

    id: int
    name: str
    address: str | None
    hrb_number: str | None
    tax_number: str | None
    vat_id: str | None
    bank_name: str | None
    iban: str | None
    bic: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
