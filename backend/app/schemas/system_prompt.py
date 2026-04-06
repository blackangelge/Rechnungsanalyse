"""Pydantic-Schemas für Systemprompts."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SystemPromptCreate(BaseModel):
    name: str
    content: str
    is_default: bool = False


class SystemPromptUpdate(BaseModel):
    name: str
    content: str
    is_default: bool = False


class SystemPromptRead(BaseModel):
    id: int
    name: str
    content: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
