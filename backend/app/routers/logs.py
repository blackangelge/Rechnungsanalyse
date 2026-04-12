"""
Router für Systemlogs.

Endpunkte:
  GET    /api/logs            — Log-Einträge laden (gefiltert nach Kategorie und Level)
  GET    /api/logs/ki-stats   — Aggregierte KI-Statistiken (Token-Summen, Durchschnitte)
  DELETE /api/logs            — Alle (oder gefilterte) Logs löschen
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models.invoice_extraction import InvoiceExtraction
from app.schemas.system_log import SystemLogRead

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("/ki-stats")
def get_ki_stats(db: Session = Depends(get_db)):
    """
    Gibt aggregierte KI-Statistiken über alle gespeicherten Extraktionen zurück.

    Enthält:
    - Anzahl der KI-Anfragen (Extraktionen mit mindestens einem Token-Wert)
    - Summe Input-Tokens, Output-Tokens, Reasoning-Tokens
    - Durchschnitt Tokens/Sekunde, Time-to-First-Token
    """
    row = db.query(
        func.count(InvoiceExtraction.id).label("total_extractions"),
        func.count(InvoiceExtraction.ki_input_tokens).label("ki_requests"),
        func.sum(InvoiceExtraction.ki_input_tokens).label("sum_input_tokens"),
        func.sum(InvoiceExtraction.ki_output_tokens).label("sum_output_tokens"),
        func.sum(InvoiceExtraction.ki_reasoning_tokens).label("sum_reasoning_tokens"),
        func.avg(InvoiceExtraction.ki_tokens_per_second).label("avg_tokens_per_second"),
        func.avg(InvoiceExtraction.ki_time_to_first_token).label("avg_time_to_first_token"),
        func.avg(InvoiceExtraction.ki_input_tokens).label("avg_input_tokens"),
        func.avg(InvoiceExtraction.ki_output_tokens).label("avg_output_tokens"),
    ).one()

    def _int(v) -> int | None:
        return int(v) if v is not None else None

    def _float(v) -> float | None:
        return round(float(v), 2) if v is not None else None

    return {
        "total_extractions": _int(row.total_extractions),
        "ki_requests": _int(row.ki_requests),
        "sum_input_tokens": _int(row.sum_input_tokens),
        "sum_output_tokens": _int(row.sum_output_tokens),
        "sum_reasoning_tokens": _int(row.sum_reasoning_tokens),
        "avg_tokens_per_second": _float(row.avg_tokens_per_second),
        "avg_time_to_first_token": _float(row.avg_time_to_first_token),
        "avg_input_tokens": _float(row.avg_input_tokens),
        "avg_output_tokens": _float(row.avg_output_tokens),
    }


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
