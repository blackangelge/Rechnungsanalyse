"""
Pydantic-Schemas für die Verarbeitungseinstellungen.
"""

from pydantic import BaseModel, ConfigDict, Field


class ProcessingSettingsUpdate(BaseModel):
    """Schema für das Aktualisieren der Verarbeitungseinstellungen (PUT)."""

    import_concurrency: int = Field(
        default=10,
        ge=1,
        le=32,
        description="Maximale Anzahl parallel verarbeiteter PDFs beim Import",
    )

    ai_concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximale Anzahl paralleler KI-Aufrufe bei der Analyse",
    )


class ProcessingSettingsRead(ProcessingSettingsUpdate):
    """Schema für die API-Antwort inkl. id."""

    id: int

    model_config = ConfigDict(from_attributes=True)
