"""
live_docs route — REST endpoints for the Live Documentation system  (FASE 13B)

GET  /live-docs/wiki/search?q=...   — semantic wiki search
GET  /live-docs/wiki/stats          — wiki statistics
GET  /live-docs/changelog           — read the global CHANGELOG
POST /live-docs/wiki                — manually add a wiki entry
POST /live-docs/readme/{job_id}     — regenerate README for a job
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import get_config

log = logging.getLogger(__name__)
router = APIRouter()


class WikiEntryIn(BaseModel):
    type: str = "general"
    title: str
    description: str = ""
    tags: list[str] = []
    job_id: str = ""
    agent: str = "user"


@router.get("/wiki/search")
async def wiki_search(q: str = Query(..., min_length=2), max_results: int = 5) -> dict:
    from services.live_docs import search_wiki
    results = search_wiki(q, max_results=max_results)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/wiki/stats")
async def wiki_stats() -> dict:
    from services.live_docs import get_wiki_stats
    return get_wiki_stats()


@router.get("/changelog")
async def get_changelog(lines: int = 200) -> dict:
    from services.live_docs import _CHANGELOG_FILE
    if not _CHANGELOG_FILE.exists():
        return {"content": "_No changelog yet._"}
    content = _CHANGELOG_FILE.read_text(encoding="utf-8")
    # Return last N lines to keep response small
    all_lines = content.splitlines()
    return {"content": "\n".join(all_lines[:lines]), "total_lines": len(all_lines)}


@router.post("/wiki")
async def add_wiki_entry(entry: WikiEntryIn) -> dict:
    from services.live_docs import log_to_wiki
    log_to_wiki(entry.model_dump())
    return {"status": "logged", "title": entry.title}


@router.post("/readme/{job_id}")
async def regenerate_readme(job_id: str) -> dict:
    from services.live_docs import generate_project_readme
    cfg = get_config()
    job_dir = cfg.jarvis_jobs_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job directory not found: {job_id}")
    readme = await generate_project_readme(job_dir)
    if not readme:
        raise HTTPException(status_code=422, detail="Could not generate README (missing state.json?)")
    return {"status": "generated", "job_id": job_id, "length": len(readme)}
