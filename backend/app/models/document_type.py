"""ORM-Modell für Dokumententypen."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
