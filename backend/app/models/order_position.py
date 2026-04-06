"""
ORM-Modell für Bestellpositionen einer Rechnung.

Eine Rechnung kann mehrere Positionen enthalten (z.B. verschiedene Artikel).
Jede Position gehört zu einem Dokument und wird mit einem Index geordnet.
"""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderPosition(Base):
    """Eine einzelne Bestellposition innerhalb einer Rechnung."""

    __tablename__ = "order_positions"

    # Primärschlüssel
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Fremdschlüssel zum Dokument (CASCADE: Position wird mit Dokument gelöscht)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    # Reihenfolge der Position innerhalb des Dokuments (0-basiert)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Vollständige Produktbezeichnung / Artikelbezeichnung
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Artikelnummer des Lieferanten
    article_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Einzelpreis pro Einheit (z.B. 12,50 €)
    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )

    # Gesamtpreis für diese Position (Einzelpreis × Menge, nach Nachlass)
    total_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Bestellmenge (kann Dezimalzahlen haben, z.B. 2,5 kg)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    # Mengeneinheit / Losgröße (z.B. "Stück", "kg", "m²", "Palette")
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Ausgewiesener Preisnachlass pro Position (absolut oder prozentual als Text)
    discount: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Beziehung zum Dokument
    document: Mapped["Document"] = relationship(  # noqa: F821
        "Document", back_populates="order_positions"
    )
