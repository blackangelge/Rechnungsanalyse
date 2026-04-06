"""
Router für Systemlogs.

Endpunkte:
  GET    /api/logs  — Log-Einträge laden (gefiltert nach Kategorie und Level)
  DELETE /api/logs  — Alle (oder gefilterte) Logs löschen
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.system_log import SystemLogRead

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("", response_model=list[SystemLogRead])
def list_logs(
    category: Optional[str] = Query(None, description="'import' oder 'ki'"),
    level: Optional[str] = Query(None, description="'info', 'warning' oder 'error'"),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """
    Gibt Log-Einträge zurück (neueste zuerst).
    Optional gefiltert nach Kategorie und/oder Level.
    """
    return crud.system_log.get_all(db, category=category, level=level, limit=limit)


@router.delete("", status_code=200)
def clear_logs(
    category: Optional[str] = Query(None, description="Nur diese Kategorie löschen"),
    db: Session = Depends(get_db),
):
    """Löscht alle oder kategoriegefilterte Log-Einträge."""
    count = crud.system_log.clear(db, category=category)
    return {"deleted": count}
