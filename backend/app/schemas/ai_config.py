"""
Pydantic-Schemas für KI-Konfigurationen.

Trennt die API-Datenstruktur vom ORM-Modell:
- AIConfigCreate / AIConfigUpdate: eingehende Requests (ohne ID, Timestamps)
- AIConfigRead: ausgehende Response (mit ID, Timestamps)
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class AIConfigBase(BaseModel):
    """Gemeinsame Felder für Create und Update."""

    # Anzeigename der Konfiguration
    name: str
    # Basis-URL der OpenAI-kompatiblen API
    api_url: str
    # API-Schlüssel (optional bei lokalen APIs)
    api_key: str | None = None
    # Modell-ID, die die API erwartet
    model_name: str
    # Soll diese Konfiguration als Standard verwendet werden?
    is_default: bool = False
    # Maximale Token-Anzahl in der KI-Antwort
    max_tokens: int = 2048
    # Temperatur (0 = deterministisch, 1 = kreativ)
    temperature: float = 0.1


class AIConfigCreate(AIConfigBase):
    """Schema für das Erstellen einer neuen KI-Konfiguration (POST)."""
    pass


class AIConfigUpdate(AIConfigBase):
    """Schema für das Aktualisieren einer KI-Konfiguration (PUT).
    Alle Felder bleiben erforderlich (vollständiges Update)."""
    pass


class AIConfigRead(AIConfigBase):
    """Schema für die API-Antwort inkl. Datenbankfelder."""

    id: int
    created_at: datetime
    updated_at: datetime

    # ORM-Modus: Pydantic liest Attribute direkt vom SQLAlchemy-Objekt
    model_config = ConfigDict(from_attributes=True)
