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


# ── Backup / Restore ──────────────────────────────────────────────────────────

from fastapi import UploadFile, File
from fastapi.responses import JSONResponse
import json as _json
from datetime import datetime as _dt


@router.get("/backup")
def download_backup(db: Session = Depends(get_db)):
    """
    Exportiert alle Einstellungen als JSON-Datei:
    KI-Konfigurationen, Systemprompts, Bildeinstellungen, Verarbeitungseinstellungen.
    """
    ai_configs = crud.ai_config.get_all(db)
    prompts = crud.system_prompt.get_all(db)
    img = crud.image_settings.get_or_create(db)
    processing = crud.processing_settings.get_or_create(db)

    def _obj(o):
        return {c.name: getattr(o, c.name) for c in o.__table__.columns}

    backup = {
        "version": 1,
        "exported_at": _dt.utcnow().isoformat(),
        "ai_configs": [_obj(c) for c in ai_configs],
        "system_prompts": [_obj(p) for p in prompts],
        "image_settings": _obj(img),
        "processing_settings": _obj(processing),
    }

    from fastapi.responses import Response
    content = _json.dumps(backup, ensure_ascii=False, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=rechnungsanalyse-backup.json"},
    )


@router.post("/restore")
async def upload_restore(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Importiert Einstellungen aus einer zuvor exportierten Backup-JSON-Datei.
    Bestehende Daten werden GELÖSCHT und durch die Backup-Daten ersetzt.
    """
    try:
        content = await file.read()
        backup = _json.loads(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ungültige JSON-Datei: {exc}")

    if backup.get("version") != 1:
        raise HTTPException(status_code=400, detail="Unbekanntes Backup-Format (version != 1)")

    restored = {"ai_configs": 0, "system_prompts": 0}

    # KI-Konfigurationen wiederherstellen
    from app.models.ai_config import AIConfig
    db.query(AIConfig).delete()
    for c in (backup.get("ai_configs") or []):
        c.pop("id", None)
        c.pop("created_at", None)
        c.pop("updated_at", None)
        db.add(AIConfig(**c))
        restored["ai_configs"] += 1

    # Systemprompts wiederherstellen
    from app.models.system_prompt import SystemPrompt
    db.query(SystemPrompt).delete()
    for p in (backup.get("system_prompts") or []):
        p.pop("id", None)
        p.pop("created_at", None)
        p.pop("updated_at", None)
        db.add(SystemPrompt(**p))
        restored["system_prompts"] += 1

    # Bildeinstellungen wiederherstellen
    img_data = backup.get("image_settings")
    if img_data:
        from app.models.image_settings import ImageSettings
        img_data.pop("id", None)
        img_data.pop("created_at", None)
        img_data.pop("updated_at", None)
        db.query(ImageSettings).delete()
        db.add(ImageSettings(**img_data))

    # Verarbeitungseinstellungen wiederherstellen
    proc_data = backup.get("processing_settings")
    if proc_data:
        from app.models.processing_settings import ProcessingSettings
        proc_data.pop("id", None)
        proc_data.pop("created_at", None)
        proc_data.pop("updated_at", None)
        db.query(ProcessingSettings).delete()
        db.add(ProcessingSettings(**proc_data))

    db.commit()
    return {"restored": restored, "message": "Backup erfolgreich wiederhergestellt"}
