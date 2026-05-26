from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.security_guard import get_guard

router = APIRouter(tags=["security-compat"])


class FileReadRequest(BaseModel):
    path: str = Field(..., min_length=1)


class ShellExecuteRequest(BaseModel):
    command: str = Field(..., min_length=1)


class SearchRequest(BaseModel):
    query: str = Field("", max_length=500)


@router.post("/files/read")
async def read_file_alias(request: FileReadRequest) -> dict:
    guard_result = get_guard().check("fs", request.path)
    if not guard_result.allowed:
        raise HTTPException(status_code=403, detail=guard_result.reason)

    path = Path(request.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")

    return {
        "success": True,
        "path": str(path),
        "content": path.read_text(encoding="utf-8", errors="replace"),
    }


@router.post("/shell/execute")
async def execute_shell_alias(request: ShellExecuteRequest) -> dict:
    guard_result = get_guard().check("shell", request.command)
    if not guard_result.allowed:
        raise HTTPException(status_code=403, detail=guard_result.reason)

    return {
        "success": False,
        "message": "Execucao direta de shell desabilitada neste endpoint de compatibilidade",
    }


@router.post("/search")
async def search_alias(request: SearchRequest) -> dict:
    # Accept hostile input as inert data; never pass it to SQL or executable code.
    normalized = re.sub(r"\s+", " ", request.query).strip()
    return {"success": True, "query": normalized, "results": []}
