"""
ORM-Modell für KI-Konfigurationen.

Jede Zeile repräsentiert eine konfigurierte Vision-LLM-API
(z.B. lokales LM Studio, Ollama, gehostete OpenAI-kompatible API).
Genau eine Konfiguration kann als Standard (is_default=True) markiert sein,
die beim Import automatisch verwendet wird.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIConfig(Base):
    """KI-Konfiguration für die Rechnungsextraktion."""

    __tablename__ = "ai_configs"

    # Primärschlüssel
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Anzeigename der Konfiguration (z.B. "LM Studio - LLaVA 1.5")
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Basis-URL der OpenAI-kompatiblen API (ohne /chat/completions)
    # Beispiel: http://localhost:1234/v1
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # API-Schlüssel (optional; für lokale APIs meist nicht benötigt)
    api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Modell-ID, wie sie die API erwartet (z.B. "llava-1.5-7b-hf")
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Ist diese Konfiguration der Standard beim Import?
    # Nur eine Zeile sollte gleichzeitig True sein.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Maximale Anzahl an Token in der LLM-Antwort
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)

    # Temperatur für die Textgenerierung (0 = deterministisch, 1 = kreativ)
    temperature: Mapped[float] = mapped_column(Float, default=0.1, nullable=False)

    # Reasoning-Modus: "off" | "low" | "medium" | "high" | "on"
    # Wird als reasoning_effort an OpenAI-kompatible APIs übergeben (sofern != "off")
    reasoning: Mapped[str] = mapped_column(String(20), default="off", server_default="off", nullable=False)

    # API-Endpunkt-Typ: "openai" = POST /chat/completions, "lmstudio" = POST /api/v1/chat
    endpoint_type: Mapped[str] = mapped_column(String(20), default="openai", server_default="openai", nullable=False)

    # Erstellungs- und Änderungszeitpunkt
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
