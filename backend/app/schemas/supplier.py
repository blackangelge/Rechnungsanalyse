"""
Pydantic-Schemas für Lieferanten.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    name: str
    street: str | None = None
    zip_code: str | None = None
    city: str | None = None
    address: str | None = None
    hrb_number: str | None = None
    tax_number: str | None = None
    vat_id: str | None = None
    bank_name: str | None = None
    iban: str | None = None
    bic: str | None = None


class SupplierUpdate(SupplierBase):
    pass


class SupplierRead(SupplierBase):
    id: int
    document_count: int = 0
    workflow_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DuplicateGroupRead(BaseModel):
    """Gruppe von Dublettenkandidaten mit den gefundenen Übereinstimmungen."""

    suppliers: list[SupplierRead]
    reasons: list[str]            # iban | vat_id | tax_number | name | name_similar
    reason_labels: list[str]
    confidence: str               # high | medium | low


class SupplierMergeRequest(BaseModel):
    target_id: int
    source_ids: list[int] = Field(min_length=1)
    # Ausdrücklich gewählte Endwerte einzelner Stammdatenfelder (sonst: Ziel behalten, Leeres auffüllen)
    fields: dict[str, str | None] | None = None
    update_document_names: bool = False


class SupplierMergeResult(BaseModel):
    supplier: SupplierRead
    merged_ids: list[int]
    moved_documents: int
    renamed_documents: int
