from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.audit_log import list_audit_events, update_audit_decision

router = APIRouter()


class AuditDecisionRequest(BaseModel):
    decision: str


@router.get("/log")
async def get_audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    risk: str | None = None,
):
    return {"events": list_audit_events(limit=limit, risk=risk)}


@router.post("/log/{audit_id}/decision")
async def decide_audit_event(audit_id: str, request: AuditDecisionRequest):
    decision = request.decision.strip().lower()
    if decision not in {"approved", "blocked"}:
        raise HTTPException(400, "decision must be approved or blocked")
    result = update_audit_decision(
        audit_id,
        decision=decision,
        confirmed_by="user",
        result=decision,
    )
    if result is None:
        raise HTTPException(404, "audit event not found")
    return {"event": result}
