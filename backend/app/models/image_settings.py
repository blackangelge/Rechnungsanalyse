"""
ORM-Modell für die Bildkonvertierungseinstellungen.

Singleton-Tabelle: immer genau eine Zeile mit id=1.
Die Einstellungen steuern, wie PDF-Seiten vor der KI-Extraktion
in Bilder umgewandelt werden.

Höhere DPI = bessere Texterkennung, aber größere Bilder (mehr Tokens, langsamer).
JPEG spart Speicher und Tokens, PNG ist verlustfrei.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImageSettings(Base):
    """Globale Einstellungen für die PDF-zu-Bild-Konvertierung (Singleton)."""

    __tablename__ = "image_settings"

    # Immer 1 — diese Tabelle hat nur eine einzige Konfigurationszeile
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Auflösung beim Rendern der PDF-Seiten in Pixel pro Zoll.
    # Empfohlene Werte: 72 (schnell/klein), 150 (Standard), 300 (hohe Qualität)
    dpi: Mapped[int] = mapped_column(Integer, default=150, nullable=False)

    # Bildformat für die gerenderten Seiten.
    # "PNG" = verlustfrei, größere Dateien
    # "JPEG" = komprimiert, kleinere Dateien, marginal schlechtere Texterkennung
    image_format: Mapped[str] = mapped_column(String(10), default="PNG", nullable=False)

    # JPEG-Kompressionsqualität (1–100).
    # Nur relevant wenn image_format == "JPEG".
    # 85 = gutes Gleichgewicht zwischen Qualität und Dateigröße.
    jpeg_quality: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
