"""
Pydantic-Schemas für die Bildkonvertierungseinstellungen.
"""

from pydantic import BaseModel, ConfigDict, Field


class ImageSettingsUpdate(BaseModel):
    """Schema für das Aktualisieren der Bildeinstellungen (PUT)."""

    # DPI: 72–300 sind sinnvolle Werte
    dpi: int = Field(default=150, ge=72, le=600, description="Renderauflösung in DPI")

    # Bildformat: nur PNG und JPEG unterstützt
    image_format: str = Field(default="PNG", pattern="^(PNG|JPEG)$")

    # JPEG-Qualität: 1–100 (nur bei JPEG relevant)
    jpeg_quality: int = Field(default=85, ge=1, le=100)


class ImageSettingsRead(ImageSettingsUpdate):
    """Schema für die API-Antwort inkl. id."""

    id: int

    model_config = ConfigDict(from_attributes=True)
