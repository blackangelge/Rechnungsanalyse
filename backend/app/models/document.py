"""
ORM-Modell für ein importiertes Dokument (PDF-Rechnung).

Jedes Dokument gehört zu einem ImportBatch.
Nach dem Kopieren wird die Originaldatei unter {id}.pdf im Storage gespeichert.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    """Eine einzelne PDF-Datei innerhalb eines Import-Batches."""

    __tablename__ = "documents"

    # Primärschlüssel — wird auch als Dateiname verwendet: {id}.pdf
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Fremdschlüssel zum Import-Batch (CASCADE: Dokument wird mit Batch gelöscht)
    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )

    # Ursprünglicher Dateiname (vor dem Umbenennen)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)

    # Gespeicherter Dateiname nach dem Umbenennen: "{id}.pdf"
    # Wird erst nach dem Kopiervorgang gesetzt (Zwei-Schritt-Prozess)
    stored_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Dateigröße in Bytes
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Anzahl der Seiten im PDF
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Denormalisiert aus dem Batch für einfachere Abfragen / Filterung
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optionaler, dokument-spezifischer Kommentar des Nutzers
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Verarbeitungsstatus
    # pending     = noch nicht begonnen
    # processing  = KI-Extraktion läuft
    # done        = erfolgreich extrahiert
    # error       = Fehler bei Kopieren oder Extraktion
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    # Fehlerbeschreibung, falls status == "error"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Erstellungszeitpunkt
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Soft-Delete: gesetzt wenn das Dokument als gelöscht markiert wurde
    # (NULL = aktiv, Timestamp = gelöscht)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Beziehung zum übergeordneten Batch
    batch: Mapped["ImportBatch"] = relationship(  # noqa: F821
        "ImportBatch", back_populates="documents"
    )

    # Beziehung zur extrahierten Rechnungsdaten (1:1, optional)
    extraction: Mapped["InvoiceExtraction | None"] = relationship(  # noqa: F821
        "InvoiceExtraction", back_populates="document", uselist=False,
        cascade="all, delete-orphan"
    )

    # Beziehung zu den Bestellpositionen (1:n)
    order_positions: Mapped[list["OrderPosition"]] = relationship(  # noqa: F821
        "OrderPosition", back_populates="document", cascade="all, delete-orphan",
        order_by="OrderPosition.position_index"
    )

    # ─── Kurzfelder aus der Extraktion ──────────────────────────────────────
    # Werden als Properties angeboten, damit DocumentListRead sie direkt
    # serialisieren kann (from_attributes=True + joinedload in der Abfrage).

    @property
    def total_amount(self) -> float | None:
        return self.extraction.total_amount if self.extraction else None

    @property
    def invoice_number(self) -> str | None:
        return self.extraction.invoice_number if self.extraction else None

    @property
    def supplier_name(self) -> str | None:
        return self.extraction.supplier_name if self.extraction else None
