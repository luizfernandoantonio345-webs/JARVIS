from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from memory.training_collector import get_training_collector

router = APIRouter()


class TrainingFeedbackRequest(BaseModel):
    session_id: str = "default"
    rating: str


@router.get("/export")
async def export_training_dataset():
    data = get_training_collector().export_jsonl()
    return Response(
        content=data,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=jarvis-training.jsonl"},
    )


@router.get("/stats")
async def training_stats():
    return get_training_collector().stats()


@router.post("/feedback")
async def training_feedback(request: TrainingFeedbackRequest):
    rating = request.rating.strip().lower()
    if rating not in {"positive", "negative"}:
        return {"ok": False, "error": "rating must be positive or negative"}
    ok = get_training_collector().mark_last_for_session(request.session_id, rating)
    return {"ok": ok}
