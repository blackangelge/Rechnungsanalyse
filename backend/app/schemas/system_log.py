"""Pydantic-Schemas für Systemlogs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SystemLogRead(BaseModel):
    id: int
    category: str
    level: str
    message: str
    batch_id: int | None
    document_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
