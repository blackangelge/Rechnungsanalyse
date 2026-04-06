"""
ORM-Modell für Lieferanten (deduplizierte Stammdaten).

Lieferanten werden aus den extrahierten Rechnungsdaten befüllt und
dedupliziert — zuerst nach IBAN, dann nach VAT-ID, dann nach Name.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Supplier(Base):
    """Deduplizierter Lieferanten-Stammdatensatz."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Vollständige Firma / Bezeichnung
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Anschrift (mehrzeilig möglich)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Handelsregisternummer (z.B. "HRB 12345")
    hrb_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Steuernummer
    tax_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Umsatzsteuer-Identifikationsnummer (USt-IdNr.)
    vat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Bankverbindung
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
