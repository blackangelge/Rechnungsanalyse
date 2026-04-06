"""
Router für globale Anwendungseinstellungen.

Endpunkte:
  GET /api/settings/image-conversion — aktuelle Bildkonvertierungseinstellungen
  PUT /api/settings/image-conversion — Einstellungen aktualisieren
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db
from app.schemas.image_settings import ImageSettingsRead, ImageSettingsUpdate
from app.schemas.processing_settings import ProcessingSettingsRead, ProcessingSettingsUpdate
from app.schemas.system_prompt import SystemPromptCreate, SystemPromptRead, SystemPromptUpdate

router = APIRouter(prefix="/api/settings", tags=["Einstellungen"])


@router.get("/paths")
def get_paths():
    """Gibt die konfigurierten Pfade zurück."""
    return {
        "import_base_path": settings.import_base_path,
        "storage_path": settings.storage_path,
    }


@router.get("/image-conversion", response_model=ImageSettingsRead)
def get_image_settings(db: Session = Depends(get_db)):
    return crud.image_settings.get_or_create(db)


@router.put("/image-conversion", response_model=ImageSettingsRead)
def update_image_settings(payload: ImageSettingsUpdate, db: Session = Depends(get_db)):
    return crud.image_settings.update(db, payload)


# ── Verarbeitungseinstellungen ────────────────────────────────────────────────

@router.get("/processing", response_model=ProcessingSettingsRead)
def get_processing_settings(db: Session = Depends(get_db)):
    """Gibt die aktuellen Parallelitäts-Einstellungen zurück."""
    return crud.processing_settings.get_or_create(db)


@router.put("/processing", response_model=ProcessingSettingsRead)
def update_processing_settings(payload: ProcessingSettingsUpdate, db: Session = Depends(get_db)):
    """Aktualisiert die Parallelitäts-Einstellungen."""
    return crud.processing_settings.update(db, payload)


# ── Systemprompts ─────────────────────────────────────────────────────────────

@router.get("/system-prompts", response_model=list[SystemPromptRead])
def list_system_prompts(db: Session = Depends(get_db)):
    return crud.system_prompt.get_all(db)


@router.post("/system-prompts", response_model=SystemPromptRead, status_code=201)
def create_system_prompt(payload: SystemPromptCreate, db: Session = Depends(get_db)):
    return crud.system_prompt.create(db, payload)


@router.put("/system-prompts/{prompt_id}", response_model=SystemPromptRead)
def update_system_prompt(prompt_id: int, payload: SystemPromptUpdate, db: Session = Depends(get_db)):
    obj = crud.system_prompt.update(db, prompt_id, payload)
    if obj is None:
        raise HTTPException(status_code=404, detail="Systemprompt nicht gefunden")
    return obj


@router.post("/system-prompts/{prompt_id}/set-default", response_model=SystemPromptRead)
def set_default_system_prompt(prompt_id: int, db: Session = Depends(get_db)):
    obj = crud.system_prompt.set_default(db, prompt_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Systemprompt nicht gefunden")
    return obj


@router.delete("/system-prompts/{prompt_id}", status_code=204)
def delete_system_prompt(prompt_id: int, db: Session = Depends(get_db)):
    if not crud.system_prompt.delete(db, prompt_id):
        raise HTTPException(status_code=404, detail="Systemprompt nicht gefunden")
