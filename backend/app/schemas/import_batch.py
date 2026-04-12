"""
Pydantic-Schemas für Import-Batches.

ImportBatchCreate: wird vom Frontend gesendet, wenn ein Import gestartet wird.
ImportBatchRead: vollständige Antwort inkl. Status und Dokumente.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportBatchCreate(BaseModel):
    """
    Eingabe beim Starten eines neuen Imports.
    Firma und Jahr werden serverseitig aus dem Ordnernamen geparst,
    können aber vom Nutzer überschrieben werden.
    """

    # Absoluter Pfad zum Import-Ordner auf dem Host
    # Beispiel: /imports/Lieferant_GmbH_2025
    folder_path: str

    # Optionaler Kommentar zum Import
    comment: str | None = None

    # Optionale Überschreibung des geparsten Firmennamens
    company_name: str | None = None

    # Optionale Überschreibung des geparsten Jahres
    year: int | None = None

    # ID der KI-Konfiguration (None = Standard-Konfiguration verwenden)
    ai_config_id: int | None = None

    # ID des Systemprompts für die KI-Analyse (None = Standard-Prompt verwenden)
    system_prompt_id: int | None = None

    # Nach Abschluss des Imports direkt KI-Analyse starten
    analyze_after_import: bool = False

    # Quelldateien aus dem Import-Ordner löschen, nachdem sie erfolgreich kopiert wurden
    delete_source_files: bool = False


class ImportBatchRead(BaseModel):
    """Vollständige Antwort eines Import-Batches."""

    id: int
    folder_path: str
    company_name: str
    year: int
    comment: str | None
    status: str
    total_docs: int
    processed_docs: int
    ai_config_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportBatchWithDocuments(ImportBatchRead):
    """Erweitertes Schema mit eingebetteter Dokumentenliste."""

    # Wird dynamisch aus der documents-Beziehung befüllt
    documents: list["DocumentRead"] = []  # noqa: F821

    model_config = ConfigDict(from_attributes=True)


# Zirkulärer Import vermeiden: DocumentRead wird nach dem Import definiert
from app.schemas.document import DocumentRead  # noqa: E402
ImportBatchWithDocuments.model_rebuild()
