from fastapi import APIRouter, Body
from backend.research_runtime.researcher import get_researcher

router = APIRouter()

@router.post("/start")
async def start_research(
    query: str = Body(...),
    session_id: str = Body("research")
):
    researcher = get_researcher()
    result = await researcher.research(query, session_id)
    return {"result": result, "steps": researcher.steps}

@router.get("/status")
def research_status():
    return get_researcher().status()
