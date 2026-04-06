"""
CRUD-Operationen für KI-Konfigurationen.

Folgt dem gleichen Muster wie crud/item.py: alle Funktionen erhalten
eine SQLAlchemy-Session und geben ORM-Objekte zurück.
"""

from sqlalchemy.orm import Session

from app.models.ai_config import AIConfig
from app.schemas.ai_config import AIConfigCreate, AIConfigUpdate


def get_all(db: Session) -> list[AIConfig]:
    """Gibt alle KI-Konfigurationen zurück, sortiert nach ID."""
    return db.query(AIConfig).order_by(AIConfig.id).all()


def get_by_id(db: Session, config_id: int) -> AIConfig | None:
    """Gibt eine KI-Konfiguration anhand ihrer ID zurück oder None."""
    return db.get(AIConfig, config_id)


def get_default(db: Session) -> AIConfig | None:
    """Gibt die als Standard markierte KI-Konfiguration zurück oder None."""
    return db.query(AIConfig).filter(AIConfig.is_default == True).first()  # noqa: E712


def create(db: Session, data: AIConfigCreate) -> AIConfig:
    """
    Erstellt eine neue KI-Konfiguration.
    Falls is_default=True, werden alle anderen zuerst auf False gesetzt.
    """
    if data.is_default:
        # Sicherstellen, dass nur eine Konfiguration Standard ist
        _clear_default(db)

    obj = AIConfig(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, config_id: int, data: AIConfigUpdate) -> AIConfig | None:
    """
    Aktualisiert eine vorhandene KI-Konfiguration vollständig.
    Gibt None zurück, wenn die ID nicht existiert.
    """
    obj = db.get(AIConfig, config_id)
    if obj is None:
        return None

    if data.is_default:
        # Anderen Standard entfernen, bevor dieser gesetzt wird
        _clear_default(db)

    for field, value in data.model_dump().items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, config_id: int) -> bool:
    """
    Löscht eine KI-Konfiguration.
    Gibt True zurück bei Erfolg, False wenn ID nicht gefunden.
    """
    obj = db.get(AIConfig, config_id)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    return True


def set_default(db: Session, config_id: int) -> AIConfig | None:
    """
    Setzt eine KI-Konfiguration als Standard und entfernt den Standard
    von allen anderen Konfigurationen.
    """
    obj = db.get(AIConfig, config_id)
    if obj is None:
        return None

    _clear_default(db)
    obj.is_default = True
    db.commit()
    db.refresh(obj)
    return obj


def _clear_default(db: Session) -> None:
    """Hilfsfunktion: Setzt is_default auf False für alle Konfigurationen."""
    db.query(AIConfig).filter(AIConfig.is_default == True).update(  # noqa: E712
        {"is_default": False}
    )
