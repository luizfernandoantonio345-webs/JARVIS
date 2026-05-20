from fastapi import APIRouter, Body
from backend.experience.engine import get_experience

router = APIRouter()

@router.get("/stats")
def exp_stats():
    return get_experience().stats()

@router.get("/search")
def exp_search(q: str = "", category: str = None, limit: int = 5):
    return {"results": get_experience().find(q, category, limit)}

@router.post("/save")
async def exp_save(
    category: str = Body(...),
    title: str = Body(...),
    problem: str = Body(""),
    solution: str = Body(""),
    tags: list = Body([])
):
    from backend.core.event_bus import get_event_bus
    id_ = get_experience().save(category, title, problem, solution, tags=tags)
    await get_event_bus().emit("experience.saved", {"id": id_, "title": title})
    return {"id": id_, "saved": True}

@router.get("/recent")
def exp_recent(limit: int = 10):
    return get_experience().find("", limit=limit)
