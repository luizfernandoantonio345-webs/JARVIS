from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BehaviorEvent(BaseModel):
    type: str
    action: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Pattern(BaseModel):
    name: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class Routine(BaseModel):
    id: str
    name: str
    actions: list[str]
    approved: bool = False
    risk_level: Literal["low", "medium", "high"] = "low"


class Suggestion(BaseModel):
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    action: str | None = None

