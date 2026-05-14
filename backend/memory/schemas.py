from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SemanticMemory(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list)


class RetrievedMemory(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    distance: float | None = None

