"""
ORM-Modell für die extrahierten Rechnungsdaten.

Pro Dokument gibt es genau einen InvoiceExtraction-Datensatz (1:1-Beziehung).
Alle Felder sind nullable, da die KI nicht immer alle Daten erkennen kann.
Die Rohantwort der KI wird in raw_response gespeichert, um Extraktion-Fehler
später analysieren zu können.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.supplier import Supplier  # noqa: F401

from app.database import Base


class InvoiceExtraction(Base):
    """Extrahierte Rechnungsfelder für ein Dokument."""

    __tablename__ = "invoice_extractions"

    # Primärschlüssel
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Fremdschlüssel zum Dokument (unique = 1:1-Beziehung)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Fremdschlüssel zum Lieferanten-Stammdatensatz (optional)
    supplier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplier: Mapped["Supplier | None"] = relationship("Supplier")

    # ─── Lieferantendaten ────────────────────────────────────────────────────
    # Vollständige Bezeichnung des Lieferanten
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Vollständige Anschrift des Lieferanten (mehrzeilig möglich)
    supplier_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Handelsregister-Nummer des Lieferanten (z.B. "HRB 12345")
    hrb_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Steuernummer des Lieferanten
    tax_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Umsatzsteuer-Identifikationsnummer (USt-IdNr.) des Lieferanten
    vat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ─── Bankverbindung ──────────────────────────────────────────────────────
    # Name der kontoführenden Bank
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # IBAN-Nummer
    iban: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # BIC/SWIFT-Code
    bic: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ─── Rechnungsidentifikation ─────────────────────────────────────────────
    # Kundennummer des Bestellers beim Lieferanten
    customer_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Rechnungsnummer des Lieferanten
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Rechnungsdatum (Ausstellungsdatum)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Fälligkeitsdatum der Rechnung
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ─── Beträge ─────────────────────────────────────────────────────────────
    # Gesamtbetrag der Rechnung (brutto)
    total_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Ausgewiesener Preisnachlass (Rabatt) auf der Rechnung
    discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Skontobetrag (Nachlass bei frühzeitiger Zahlung)
    cash_discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # ─── Zahlungsbedingungen ─────────────────────────────────────────────────
    # Zahlungsbedingungen als Freitext (z.B. "30 Tage netto, 2% Skonto bei 10 Tagen")
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── KI-Rohdaten ─────────────────────────────────────────────────────────
    # Vollständige JSON-Antwort der KI für spätere Fehleranalyse
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Erstellungs- und Änderungszeitpunkt
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Beziehung zum Dokument
    document: Mapped["Document"] = relationship(  # noqa: F821
        "Document", back_populates="extraction"
    )
