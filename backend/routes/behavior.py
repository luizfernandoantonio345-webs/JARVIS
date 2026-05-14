"""
routes/behavior — FASE 11B

GET  /behavior/profile
PUT  /behavior/profile
POST /behavior/profile/reset
GET  /behavior/profile/history
POST /behavior/profile/feedback   — update from natural language feedback
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from behavior.behavior_manager import get_behavior_manager
from behavior.schemas import BehaviorEvent

router = APIRouter()


def _mgr():
    from behavior.profile_manager import get_profile_manager
    return get_profile_manager()


# ── Read ──────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile():
    """Return the current Behavior Profile."""
    return _mgr().get().model_dump()


@router.get("/profile/history")
async def get_profile_history(limit: int = 20):
    """Return last N profile versions (chronological, most recent first)."""
    return {"history": _mgr().history(limit=min(limit, 100))}


# ── Write ─────────────────────────────────────────────────────────────────────

class ProfilePatch(BaseModel):
    """Partial profile update — only supplied fields are changed."""
    llm_routing:                      dict[str, str]  | None = None
    verbosity:                        str              | None = None
    code_style:                       dict[str, Any]  | None = None
    test_preference:                  str              | None = None
    risk_tolerance:                   str              | None = None
    escalation_threshold:             float            | None = None
    max_autonomous_actions_per_hour:  int              | None = None


@router.put("/profile")
async def update_profile(patch: ProfilePatch):
    """
    Partially update the Behavior Profile.
    Only provided fields are changed; rest remains unchanged.
    """
    mgr = _mgr()
    current = mgr.get().model_dump()
    patch_dict = {k: v for k, v in patch.model_dump().items() if v is not None}

    if not patch_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    current.update(patch_dict)
    current["update_count"] = mgr.get().update_count + 1

    from behavior.profile import BehaviorProfile
    try:
        new_profile = BehaviorProfile.model_validate(current)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    mgr.save(new_profile)
    return {"ok": True, "profile": new_profile.model_dump()}


@router.post("/profile/reset")
async def reset_profile():
    """Reset Behavior Profile to factory defaults."""
    profile = _mgr().reset()
    return {"ok": True, "profile": profile.model_dump()}


# ── Feedback endpoint ─────────────────────────────────────────────────────────

class FeedbackBody(BaseModel):
    feedback: str
    context:  dict[str, Any] | None = None


@router.post("/profile/feedback")
async def profile_feedback(body: FeedbackBody):
    """
    Update the Behavior Profile from natural language user feedback.

    Example body: {"feedback": "você está sendo muito verboso"}
    """
    if len(body.feedback.strip()) < 5:
        raise HTTPException(status_code=400, detail="Feedback too short")
    profile = _mgr().update_from_feedback(body.feedback, body.context or {})
    return {"ok": True, "profile": profile.model_dump()}


class BehaviorFeedbackBody(BaseModel):
    event_type: str = "feedback"
    action: str = "user_feedback"
    metadata: dict[str, Any] = {}


class RoutineApprovalBody(BaseModel):
    routine_id: str
    approved: bool = True


@router.get("/suggestions")
async def behavior_suggestions():
    return {"suggestions": [s.model_dump() for s in get_behavior_manager().suggestions()]}


@router.post("/feedback")
async def behavior_feedback(body: BehaviorFeedbackBody):
    event = BehaviorEvent(type=body.event_type, action=body.action, metadata=body.metadata)
    get_behavior_manager().record_event(event)
    return {"ok": True, "event": event.model_dump()}


@router.get("/routines")
async def behavior_routines():
    return {"routines": [r.model_dump() for r in get_behavior_manager().get_routines()]}


@router.post("/routines/approve")
async def behavior_routine_approve(body: RoutineApprovalBody):
    ok = get_behavior_manager().approve_routine(body.routine_id, body.approved)
    if not ok:
        raise HTTPException(status_code=404, detail="Routine not found")
    return {"ok": True}
