"""
CRUD-Operationen für Import-Batches.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.import_batch import ImportBatch
from app.schemas.import_batch import ImportBatchCreate


def get_all(
    db: Session,
    company_name: str | None = None,
    year: int | None = None,
) -> list[ImportBatch]:
    """
    Gibt alle Import-Batches zurück.
    Optionale Filter: Firmenname (Teilstring) und/oder Jahr.
    """
    query = db.query(ImportBatch).order_by(ImportBatch.created_at.desc())

    if company_name:
        # Groß-/Kleinschreibung ignorieren
        query = query.filter(
            ImportBatch.company_name.ilike(f"%{company_name}%")
        )

    if year:
        query = query.filter(ImportBatch.year == year)

    return query.all()


def get_by_id(db: Session, batch_id: int) -> ImportBatch | None:
    """
    Gibt einen Batch mit vorgeladenen Dokumenten zurück.
    joinedload vermeidet N+1-Abfragen beim Zugriff auf batch.documents.
    """
    return (
        db.query(ImportBatch)
        .options(joinedload(ImportBatch.documents))
        .filter(ImportBatch.id == batch_id)
        .first()
    )


def create(
    db: Session,
    data: ImportBatchCreate,
    company_name: str,
    year: int,
) -> ImportBatch:
    """
    Erstellt einen neuen Import-Batch.
    company_name und year werden vom Router nach dem Parsen übergeben.
    """
    obj = ImportBatch(
        folder_path=data.folder_path,
        company_name=company_name,
        year=year,
        comment=data.comment,
        ai_config_id=data.ai_config_id,
        status="pending",
        total_docs=0,
        processed_docs=0,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, batch_id: int) -> bool:
    """Löscht einen Import-Batch (inkl. Dokumente via CASCADE)."""
    obj = db.get(ImportBatch, batch_id)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    return True


def update_status(
    db: Session,
    batch_id: int,
    status: str,
    total_docs: int | None = None,
    processed_docs: int | None = None,
) -> ImportBatch | None:
    """
    Aktualisiert Status und optionale Zählfelder eines Batches.
    Setzt started_at/finished_at automatisch anhand des neuen Status.
    """
    obj = db.get(ImportBatch, batch_id)
    if obj is None:
        return None

    obj.status = status

    if total_docs is not None:
        obj.total_docs = total_docs

    if processed_docs is not None:
        obj.processed_docs = processed_docs

    # Zeitstempel bei Statusübergängen setzen
    now = datetime.now(timezone.utc)
    if status == "running" and obj.started_at is None:
        obj.started_at = now
    elif status in ("done", "error"):
        obj.finished_at = now

    db.commit()
    db.refresh(obj)
    return obj
