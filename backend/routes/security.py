"""
JARVIS Security Routes — Dashboard e controle de segurança.

Endpoints:
  GET  /security/status          — visão geral: tokens, IPs bloqueados, ameaças
  POST /security/token/generate  — gera token para um dispositivo
  POST /security/token/revoke    — revoga token de um dispositivo
  POST /security/token/revoke_all— revoga TODOS os tokens (emergência)
  POST /security/ip/block        — bloqueia IP manualmente
  POST /security/ip/unblock      — desbloqueia IP
  GET  /security/threats         — histórico de ameaças
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger("jarvis.routes.security")

router = APIRouter(prefix="/security", tags=["security"])


# ── Models ────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    device_name: str
    ip_hint: Optional[str] = ""


class RevokeRequest(BaseModel):
    device_name: str


class BlockIPRequest(BaseModel):
    ip: str
    reason: str
    duration_minutes: int = 60


class UnblockIPRequest(BaseModel):
    ip: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_guardian():
    try:
        from security.guardian import get_guardian
        return get_guardian()
    except ImportError:
        from backend.security.guardian import get_guardian
        return get_guardian()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def security_status():
    """Dashboard completo de segurança."""
    guardian = _get_guardian()
    return guardian.security_status()


@router.post("/token/generate")
async def generate_token(req: TokenRequest):
    """Gera token HMAC-SHA256 para um dispositivo."""
    guardian = _get_guardian()
    token = guardian.auth.generate_token(req.device_name, req.ip_hint or "")
    return {
        "device": req.device_name,
        "token": token,
        "auth_url": f"/?auth={token}",
        "note": "Salve este token — ele não aparecerá novamente se for revogado",
    }


@router.post("/token/revoke")
async def revoke_token(req: RevokeRequest):
    """Revoga token de um dispositivo específico."""
    guardian = _get_guardian()
    ok = guardian.auth.revoke_token(req.device_name)
    if not ok:
        raise HTTPException(404, f"Dispositivo '{req.device_name}' não encontrado")
    return {"revoked": True, "device": req.device_name}


@router.post("/token/revoke_all")
async def revoke_all_tokens():
    """Revoga TODOS os tokens — use em emergência."""
    guardian = _get_guardian()
    count = guardian.auth.revoke_all()
    return {"revoked_count": count, "message": "Todos os tokens foram invalidados"}


@router.post("/ip/block")
async def block_ip(req: BlockIPRequest):
    """Bloqueia um IP manualmente."""
    guardian = _get_guardian()
    guardian.auth.block_ip(req.ip, req.reason, req.duration_minutes)
    return {"blocked": True, "ip": req.ip, "duration_minutes": req.duration_minutes}


@router.post("/ip/unblock")
async def unblock_ip(req: UnblockIPRequest):
    """Remove bloqueio de um IP."""
    guardian = _get_guardian()
    ok = guardian.auth.unblock_ip(req.ip)
    if not ok:
        raise HTTPException(404, f"IP '{req.ip}' não estava bloqueado")
    return {"unblocked": True, "ip": req.ip}


@router.get("/threats")
async def get_threats(limit: int = 50):
    """Histórico dos últimos eventos de segurança."""
    guardian = _get_guardian()
    return {
        "events": guardian.detector.recent_events(limit),
        "stats": guardian.detector.stats(),
    }
