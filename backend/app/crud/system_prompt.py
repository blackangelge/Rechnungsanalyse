"""CRUD-Operationen für Systemprompts."""

from sqlalchemy.orm import Session
from app.models.system_prompt import SystemPrompt
from app.schemas.system_prompt import SystemPromptCreate, SystemPromptUpdate


def get_all(db: Session) -> list[SystemPrompt]:
    return db.query(SystemPrompt).order_by(SystemPrompt.id).all()


def get_by_id(db: Session, prompt_id: int) -> SystemPrompt | None:
    return db.get(SystemPrompt, prompt_id)


def get_default(db: Session) -> SystemPrompt | None:
    return db.query(SystemPrompt).filter(SystemPrompt.is_default == True).first()  # noqa: E712


def get_doc_type_prompt(db: Session) -> SystemPrompt | None:
    """Gibt den als Dokumententyp-Prompt markierten Systemprompt zurück."""
    return (
        db.query(SystemPrompt)
        .filter(SystemPrompt.is_document_type_prompt == True)  # noqa: E712
        .order_by(SystemPrompt.id)
        .first()
    )


def create(db: Session, data: SystemPromptCreate) -> SystemPrompt:
    if data.is_default:
        _clear_default(db)
    if data.is_document_type_prompt:
        _clear_doc_type_prompt(db)
    obj = SystemPrompt(
        name=data.name,
        content=data.content,
        is_default=data.is_default,
        is_document_type_prompt=data.is_document_type_prompt,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, prompt_id: int, data: SystemPromptUpdate) -> SystemPrompt | None:
    obj = db.get(SystemPrompt, prompt_id)
    if obj is None:
        return None
    if data.is_default:
        _clear_default(db)
    if data.is_document_type_prompt:
        _clear_doc_type_prompt(db)
    obj.name = data.name
    obj.content = data.content
    obj.is_default = data.is_default
    obj.is_document_type_prompt = data.is_document_type_prompt
    db.commit()
    db.refresh(obj)
    return obj


def set_default(db: Session, prompt_id: int) -> SystemPrompt | None:
    _clear_default(db)
    obj = db.get(SystemPrompt, prompt_id)
    if obj is None:
        return None
    obj.is_default = True
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, prompt_id: int) -> bool:
    obj = db.get(SystemPrompt, prompt_id)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    return True


def _clear_default(db: Session) -> None:
    db.query(SystemPrompt).filter(SystemPrompt.is_default == True).update(  # noqa: E712
        {"is_default": False}
    )
    db.commit()


def _clear_doc_type_prompt(db: Session) -> None:
    db.query(SystemPrompt).filter(
        SystemPrompt.is_document_type_prompt == True  # noqa: E712
    ).update({"is_document_type_prompt": False})
    db.commit()
