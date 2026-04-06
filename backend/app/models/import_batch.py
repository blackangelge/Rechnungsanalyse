"""
ORM-Modell für einen Import-Batch.

Ein Import-Batch repräsentiert einen einzelnen Import-Vorgang:
der Nutzer gibt einen Ordnerpfad an (z.B. /imports/LieferantGmbH_2025),
und alle darin enthaltenen PDF-Dateien werden als Dokumente diesem Batch zugeordnet.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ImportBatch(Base):
    """Ein Import-Job, der einen Ordner mit PDF-Rechnungen verarbeitet."""

    __tablename__ = "import_batches"

    # Primärschlüssel
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Vom Nutzer angegebener Pfad zum Import-Ordner auf dem Host
    # Beispiel: /imports/Lieferant_GmbH_2025
    folder_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Aus dem Ordnernamen geparster Firmenname (alles vor dem letzten _YYYY)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Aus dem Ordnernamen geparsts Jahr (letzte 4 Ziffern nach _)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optionaler Kommentar des Nutzers zum Import
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status des Import-Vorgangs
    # pending  = angelegt, noch nicht gestartet
    # running  = läuft gerade
    # done     = erfolgreich abgeschlossen
    # error    = fehlgeschlagen
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    # Gesamtanzahl der gefundenen PDF-Dokumente im Ordner
    total_docs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Anzahl der bereits verarbeiteten Dokumente (wird während des Imports hochgezählt)
    processed_docs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Welche KI-Konfiguration wurde für diesen Import verwendet?
    # Nullable, falls die Konfiguration später gelöscht wird.
    ai_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_configs.id", ondelete="SET NULL"), nullable=True
    )

    # Zeitstempel: wann der Import gestartet/beendet wurde
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Erstellungszeitpunkt des Datensatzes
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Beziehung zu den Dokumenten dieses Batches (1:n)
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        "Document", back_populates="batch", cascade="all, delete-orphan"
    )

    # Beziehung zur verwendeten KI-Konfiguration
    ai_config: Mapped["AIConfig"] = relationship("AIConfig")  # noqa: F821
