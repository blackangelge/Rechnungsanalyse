"""
ORM-Modell für Systemlog-Einträge.

Kategorien:
  import  — Import-Prozess (Kopieren, Seitenanzahl, Fehler)
  ki      — KI-Abfragen (Modell, Ergebnis, Fehler, Tokens)

Level:
  info     — normaler Ablauf
  warning  — Problem, aber weitergemacht
  error    — Fehler mit Auswirkung auf das Ergebnis
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # "import" | "ki"
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # "info" | "warning" | "error"
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info")

    # Freitext-Nachricht
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Optionaler Bezug zum Import-Batch
    batch_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("import_batches.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Optionaler Bezug zum Dokument
    document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
