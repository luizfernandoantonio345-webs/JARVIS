"""
JARVIS Security Routes — Dashboard e controle de segurança.

Endpoints:
  GET  /security/status          — status do health middleware (coexiste)
  GET  /security/guardian        — status completo do guardian (tokens, IPs, ameaças)
  POST /security/token/generate
  POST /security/token/revoke
  POST /security/token/revoke_all
  POST /security/ip/block
  POST /security/ip/unblock
  GET  /security/threats
  POST /security/allowlist/add
  DELETE /security/allowlist/remove
  GET  /security/allowlist
  POST /security/lockdown
  DELETE /security/lockdown
  GET  /security/metrics
  GET  /security/audit
  POST /security/device/ban
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger("jarvis.routes.security")

router = APIRouter(tags=["security"])


# ── Models ────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    device_name: str
    ip_hint: Optional[str] = ""
    ttl_days: int = 0


class RevokeRequest(BaseModel):
    device_name: str
    reason: Optional[str] = "manual"


class BlockIPRequest(BaseModel):
    ip: str
    reason: str
    duration_minutes: int = 60


class UnblockIPRequest(BaseModel):
    ip: str


class AllowlistRequest(BaseModel):
    ip: str
    reason: Optional[str] = ""


class DeviceBanRequest(BaseModel):
    device_name: str
    reason: Optional[str] = "manual"


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
    """Dashboard completo de segurança (alias de /guardian)."""
    guardian = _get_guardian()
    return guardian.security_status()


@router.get("/guardian")
async def guardian_status():
    """Status completo do Guardian — tokens, IPs bloqueados, ameaças."""
    guardian = _get_guardian()
    return guardian.security_status()


@router.post("/token/generate")
async def generate_token(req: TokenRequest):
    guardian = _get_guardian()
    token = guardian.auth.generate_token(req.device_name, req.ip_hint or "", req.ttl_days)
    return {
        "device": req.device_name,
        "token": token,
        "auth_url": f"/?auth={token}",
        "ttl_days": req.ttl_days or "sem expiração",
        "note": "Salve este token — ele não aparecerá novamente se for revogado",
    }


@router.post("/token/revoke")
async def revoke_token(req: RevokeRequest):
    guardian = _get_guardian()
    ok = guardian.auth.revoke_token(req.device_name, req.reason or "manual")
    if not ok:
        raise HTTPException(404, f"Dispositivo '{req.device_name}' não encontrado")
    return {"revoked": True, "device": req.device_name, "reason": req.reason}


@router.post("/token/revoke_all")
async def revoke_all_tokens():
    guardian = _get_guardian()
    count = guardian.auth.revoke_all()
    return {"revoked_count": count, "message": "Todos os tokens foram invalidados"}


@router.post("/ip/block")
async def block_ip(req: BlockIPRequest):
    guardian = _get_guardian()
    guardian.auth.block_ip(req.ip, req.reason, req.duration_minutes)
    return {"blocked": True, "ip": req.ip, "duration_minutes": req.duration_minutes}


@router.post("/ip/unblock")
async def unblock_ip(req: UnblockIPRequest):
    guardian = _get_guardian()
    ok = guardian.auth.unblock_ip(req.ip)
    if not ok:
        raise HTTPException(404, f"IP '{req.ip}' não estava bloqueado")
    return {"unblocked": True, "ip": req.ip}


@router.get("/threats")
async def get_threats(limit: int = 50):
    guardian = _get_guardian()
    return {
        "events": guardian.detector.recent_events(limit),
        "stats": guardian.detector.stats(),
    }


@router.post("/allowlist/add")
async def allowlist_add(req: AllowlistRequest):
    guardian = _get_guardian()
    guardian.auth.add_to_allowlist(req.ip, req.reason or "")
    return {"added": True, "ip": req.ip, "reason": req.reason}


@router.delete("/allowlist/remove")
async def allowlist_remove(ip: str):
    guardian = _get_guardian()
    ok = guardian.auth.remove_from_allowlist(ip)
    if not ok:
        raise HTTPException(404, f"IP '{ip}' não estava na allowlist")
    return {"removed": True, "ip": ip}


@router.get("/allowlist")
async def get_allowlist():
    guardian = _get_guardian()
    return {"allowlist": guardian.auth.list_allowlisted_ips()}


@router.post("/lockdown")
async def enable_lockdown():
    guardian = _get_guardian()
    guardian.enable_lockdown()
    return {"lockdown": True, "message": "Modo lockdown ativado — apenas /health permitido"}


@router.delete("/lockdown")
async def disable_lockdown():
    guardian = _get_guardian()
    guardian.disable_lockdown()
    return {"lockdown": False, "message": "Lockdown desativado"}


@router.get("/metrics")
async def security_metrics():
    guardian = _get_guardian()
    stats = guardian.detector.stats()
    return {
        "security_score": guardian.security_score(),
        "lockdown_active": guardian.is_lockdown,
        "uptime_seconds": int(time.time() - guardian._started_at),
        "threat_summary": stats,
        "tokens_active": sum(1 for t in guardian.auth.list_tokens() if not t.get("revoked")),
        "tokens_revoked": sum(1 for t in guardian.auth.list_tokens() if t.get("revoked")),
        "ips_blocked": len(guardian.auth.list_blocked_ips()),
        "ips_allowlisted": len(guardian.auth.list_allowlisted_ips()),
    }


@router.get("/audit")
async def get_audit_log(limit: int = 100):
    guardian = _get_guardian()
    return {"audit": guardian.auth.get_audit_log(limit), "total": limit}


@router.post("/device/ban")
async def ban_device(req: DeviceBanRequest):
    guardian = _get_guardian()
    ok = guardian.ban_device(req.device_name, req.reason or "manual")
    if not ok:
        raise HTTPException(404, f"Dispositivo '{req.device_name}' não encontrado")
    return {"banned": True, "device": req.device_name, "reason": req.reason}
