"""
ORM-Modell für die Verarbeitungseinstellungen.

Singleton-Tabelle: immer genau eine Zeile mit id=1.
Steuert die Parallelität beim PDF-Import und bei der KI-Analyse.
"""

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProcessingSettings(Base):
    """Globale Einstellungen für die parallele Verarbeitung (Singleton)."""

    __tablename__ = "processing_settings"

    # Immer 1 — Singleton-Tabelle
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Anzahl der parallel verarbeiteten PDFs beim Import.
    # Höhere Werte = schnellerer Import, aber mehr CPU/IO-Last auf dem NAS.
    import_concurrency: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # Anzahl der parallel ausgeführten KI-Anfragen bei der KI-Analyse.
    # Höhere Werte = schnellere Analyse, aber mehr Last auf der KI-API.
    # Vorsicht bei lokalen Modellen (LM Studio / Ollama): 1–2 empfohlen.
    ai_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
