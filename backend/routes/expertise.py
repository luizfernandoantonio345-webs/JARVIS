from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from expertise.domain_detector import DomainDetector
from expertise.domain_memory import DomainMemory
from expertise.task_handler import ExpertResponse, handle_expert_request

router = APIRouter()


class ExpertiseRequest(BaseModel):
    input: str
    attachments: list = []


@router.post("/analyze", response_model=ExpertResponse)
async def analyze(body: ExpertiseRequest):
    return await handle_expert_request(body.input, body.attachments)


@router.post("/detect")
async def detect(body: ExpertiseRequest):
    return await DomainDetector().detect(body.input)


@router.get("/domains")
async def domains():
    memory = DomainMemory()
    return {"domains": await memory.list_known_domains(), "stats": await memory.get_stats()}


@router.delete("/domain/{domain}")
async def delete_domain(domain: str):
    deleted = await DomainMemory().delete(domain)
    if not deleted:
        raise HTTPException(404, "domain not found")
    return {"status": "ok", "deleted": domain}

