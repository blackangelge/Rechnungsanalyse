"""
ORM-Modell für ein importiertes Dokument (PDF-Rechnung).

Jedes Dokument gehört zu einem ImportBatch.
Nach dem Kopieren wird die Originaldatei unter {id}.pdf im Storage gespeichert.
"""

import json
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.document_type import DocumentType  # noqa: F401

from app.database import Base


class Document(Base):
    """Eine einzelne PDF-Datei innerhalb eines Import-Batches."""

    __tablename__ = "documents"

    # Primärschlüssel — wird auch als Dateiname verwendet: {id}.pdf
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Fremdschlüssel zum Import-Batch (CASCADE: Dokument wird mit Batch gelöscht)
    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
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
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Optionaler, dokument-spezifischer Kommentar des Nutzers
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Verarbeitungsstatus
    # pending     = noch nicht begonnen
    # processing  = KI-Extraktion läuft
    # done        = erfolgreich extrahiert
    # error       = Fehler bei Kopieren oder Extraktion
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)

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

    # Erkannter Dokumententyp (durch KI-Klassifikation, optional)
    document_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_types.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # KI-Stats direkt auf dem Dokument — befüllt für Nicht-Eingangsrechnungen,
    # bei denen keine InvoiceExtraction angelegt wird.
    doc_ki_input_tokens:  Mapped[int | None]   = mapped_column(Integer, nullable=True)
    doc_ki_output_tokens: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    doc_ki_total_duration: Mapped[float | None] = mapped_column(nullable=True)

    # Aktuelle PDF-Version (1 = Original) und die Version, auf der die letzte
    # KI-Analyse lief — zeigt, ob nach einer PDF-Bearbeitung neu analysiert werden sollte.
    pdf_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    analyzed_pdf_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Beim Analysieren tatsächlich verwendete Systemprompts (Wortlaut-Snapshot)
    used_system_prompt:   Mapped[str | None] = mapped_column(Text, nullable=True)
    used_doc_type_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_recheck_prompt:  Mapped[str | None] = mapped_column(Text, nullable=True)

    # Verwendeter Workflow: Snapshot des Graphen (bleibt auch nach Änderung/Löschen des
    # Workflows erhalten) und Ablaufprotokoll der einzelnen Knoten.
    used_workflow_id:    Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_workflow_name:  Mapped[str | None] = mapped_column(String(255), nullable=True)
    used_workflow_graph: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_trace:      Mapped[str | None] = mapped_column(Text, nullable=True)

    # Beziehung zum übergeordneten Batch
    batch: Mapped["ImportBatch"] = relationship(  # noqa: F821
        "ImportBatch", back_populates="documents"
    )

    # Beziehung zum Dokumententyp (n:1, optional)
    document_type: Mapped["DocumentType | None"] = relationship(
        "DocumentType", foreign_keys=[document_type_id]
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

    @property
    def has_extraction(self) -> bool:
        return self.extraction is not None

    @property
    def ki_input_tokens(self) -> int | None:
        # Extraktion hat Vorrang; Fallback auf die direkt gespeicherten Stats
        # (befüllt für Nicht-Eingangsrechnungen ohne InvoiceExtraction)
        if self.extraction and self.extraction.ki_input_tokens is not None:
            return self.extraction.ki_input_tokens
        return self.doc_ki_input_tokens

    @property
    def ki_output_tokens(self) -> int | None:
        if self.extraction and self.extraction.ki_output_tokens is not None:
            return self.extraction.ki_output_tokens
        return self.doc_ki_output_tokens

    @property
    def ki_total_duration(self) -> float | None:
        if self.extraction and self.extraction.ki_total_duration is not None:
            return self.extraction.ki_total_duration
        return self.doc_ki_total_duration

    @staticmethod
    def _json_or_none(raw: str | None):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    @property
    def used_workflow(self) -> dict | None:
        """Graph des bei der letzten Analyse verwendeten Workflows (Snapshot)."""
        return self._json_or_none(self.used_workflow_graph)

    @property
    def workflow_run(self) -> list | None:
        """Ablaufprotokoll der Knoten der letzten Analyse."""
        return self._json_or_none(self.workflow_trace)

    @property
    def validation_status(self) -> str | None:
        return self.extraction.validation_status if self.extraction else None

    @property
    def validation(self) -> dict | None:
        """Geparste Prüfdetails (issues, corrections …) oder None."""
        raw = self.extraction.validation_details if self.extraction else None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    @property
    def document_type_name(self) -> str | None:
        return self.document_type.name if self.document_type else None
