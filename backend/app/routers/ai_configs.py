"""
Router für KI-Konfigurationen.

Endpunkte:
  GET    /api/ai-configs/           — alle Konfigurationen auflisten
  POST   /api/ai-configs/           — neue Konfiguration erstellen
  GET    /api/ai-configs/{id}       — einzelne Konfiguration abrufen
  PUT    /api/ai-configs/{id}       — Konfiguration aktualisieren
  DELETE /api/ai-configs/{id}       — Konfiguration löschen
  POST   /api/ai-configs/{id}/set-default — als Standard setzen
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.ai_config import AIConfigCreate, AIConfigRead, AIConfigUpdate

# Alle Endpunkte dieses Routers beginnen mit /api/ai-configs
router = APIRouter(prefix="/api/ai-configs", tags=["KI-Konfigurationen"])


@router.get("", response_model=list[AIConfigRead])
def list_ai_configs(db: Session = Depends(get_db)):
    """Gibt alle konfigurierten KI-APIs zurück."""
    return crud.ai_config.get_all(db)


@router.post("", response_model=AIConfigRead, status_code=status.HTTP_201_CREATED)
def create_ai_config(payload: AIConfigCreate, db: Session = Depends(get_db)):
    """
    Erstellt eine neue KI-Konfiguration.
    Falls is_default=True, wird der Standard von allen anderen entfernt.
    """
    return crud.ai_config.create(db, payload)


@router.get("/{config_id}", response_model=AIConfigRead)
def get_ai_config(config_id: int, db: Session = Depends(get_db)):
    """Gibt eine einzelne KI-Konfiguration anhand ihrer ID zurück."""
    obj = crud.ai_config.get_by_id(db, config_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="KI-Konfiguration nicht gefunden")
    return obj


@router.put("/{config_id}", response_model=AIConfigRead)
def update_ai_config(
    config_id: int, payload: AIConfigUpdate, db: Session = Depends(get_db)
):
    """Aktualisiert eine KI-Konfiguration vollständig."""
    obj = crud.ai_config.update(db, config_id, payload)
    if obj is None:
        raise HTTPException(status_code=404, detail="KI-Konfiguration nicht gefunden")
    return obj


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_config(config_id: int, db: Session = Depends(get_db)):
    """Löscht eine KI-Konfiguration."""
    if not crud.ai_config.delete(db, config_id):
        raise HTTPException(status_code=404, detail="KI-Konfiguration nicht gefunden")


@router.post("/{config_id}/set-default", response_model=AIConfigRead)
def set_default_ai_config(config_id: int, db: Session = Depends(get_db)):
    """
    Setzt eine KI-Konfiguration als Standard für neue Imports.
    Entfernt automatisch den Standard von der bisherigen Konfiguration.
    """
    obj = crud.ai_config.set_default(db, config_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="KI-Konfiguration nicht gefunden")
    return obj
