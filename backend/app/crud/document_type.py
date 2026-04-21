"""CRUD-Operationen für Dokumententypen."""

from sqlalchemy.orm import Session

from app.models.document_type import DocumentType


def get_all(db: Session) -> list[DocumentType]:
    """Gibt alle Dokumententypen sortiert nach ID zurück."""
    return db.query(DocumentType).order_by(DocumentType.id).all()


def get_by_id(db: Session, type_id: int) -> DocumentType | None:
    return db.get(DocumentType, type_id)
