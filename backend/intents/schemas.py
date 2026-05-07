from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

RiskLevel = Literal["low", "medium", "high"]


class Intent(BaseModel):
    action: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    requires_confirmation: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "llm"
    raw_text: str | None = None

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("steps")
    @classmethod
    def clean_steps(cls, value: list[str]) -> list[str]:
        return [step.strip() for step in value if step and step.strip()]


class IntentResult(BaseModel):
    success: bool
    action: str
    risk_level: RiskLevel
    requires_confirmation: bool
    executed: bool = False
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


class ConfirmationRequest(BaseModel):
    confirmation_id: str
    intent: Intent
    prompt: str
    expires_at: datetime
