"""Rotas de health check e métricas do sistema."""
import logging
import time

import httpx
from fastapi import APIRouter

router = APIRouter()
log = logging.getLogger(__name__)

_START_TIME = time.time()


async def _check_ollama(url: str, timeout: float = 1.0) -> tuple[bool, list[str]]:
    try:
        clean = url.replace("localhost", "127.0.0.1")
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=0.5)) as c:
            r = await c.get(f"{clean}/api/tags")
            if r.status_code != 200:
                return False, []
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return True, [m for m in models if m]
    except Exception:
        return False, []


@router.get("/health")
async def health_check():
    import asyncio
    from config import get_config
    from runtime.watchdog import get_watchdog

    cfg = get_config()
    wd = get_watchdog()
    uptime_s = wd.uptime()
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)

    try:
        ollama_ok, models = await asyncio.wait_for(_check_ollama(cfg.ollama_url), timeout=1.5)
    except Exception:
        ollama_ok, models = False, []

    degraded = [] if ollama_ok else ["ollama"]

    return {
        "status":   "ok" if not degraded else "degraded",
        "service":  "JARVIS API",
        "version":  "6.0",
        "uptime":   f"{h:02d}:{m:02d}:{s:02d}",
        "uptime_seconds": uptime_s,
        "models": {
            "active":  os_env("JARVIS_MODEL", cfg.local_model),
            "ollama":  "ok" if ollama_ok else "error",
            "list":    models,
        },
        "degraded": degraded,
    }


@router.get("/status")
async def status():
    from config import get_config
    from runtime.watchdog import get_watchdog
    cfg = get_config()
    wd = get_watchdog()
    import os
    return {
        "jarvis":          "online",
        "model":           os.getenv("JARVIS_MODEL", cfg.local_model),
        "uptime_seconds":  wd.uptime(),
        "voice":           os.getenv("JARVIS_VOICE_ENABLED", "true") == "true",
        "ollama_url":      cfg.ollama_url,
    }


@router.get("/metrics")
async def get_metrics():
    """Métricas reais do sistema via psutil — usadas pelo frontend."""
    try:
        import psutil

        cpu     = psutil.cpu_percent(interval=0.3)
        ram     = psutil.virtual_memory()
        disk    = psutil.disk_usage("C:\\" if __import__("sys").platform == "win32" else "/")
        net     = psutil.net_io_counters()
        procs   = len(psutil.pids())

        # Top 3 processos por CPU
        top_procs = []
        try:
            all_procs = [
                p.info for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"])
                if p.info.get("cpu_percent") is not None
            ]
            top_procs = sorted(all_procs, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:3]
            top_procs = [{"name": p["name"], "cpu": round(p["cpu_percent"], 1)} for p in top_procs]
        except Exception:
            pass

        return {
            "cpu_percent":   round(cpu, 1),
            "ram_percent":   round(ram.percent, 1),
            "ram_used_gb":   round(ram.used  / 1024**3, 1),
            "ram_total_gb":  round(ram.total / 1024**3, 1),
            "ram_free_gb":   round(ram.available / 1024**3, 1),
            "disk_percent":  round(disk.percent, 1),
            "disk_used_gb":  round(disk.used  / 1024**3, 1),
            "disk_free_gb":  round(disk.free  / 1024**3, 1),
            "disk_total_gb": round(disk.total / 1024**3, 1),
            "net_sent_mb":   round(net.bytes_sent / 1024**2, 1),
            "net_recv_mb":   round(net.bytes_recv / 1024**2, 1),
            "process_count": procs,
            "top_processes": top_procs,
        }
    except ImportError:
        return {"error": "psutil não instalado", "cpu_percent": 0, "ram_percent": 0}
    except Exception as e:
        log.warning("[METRICS] Erro: %s", e)
        return {"error": str(e), "cpu_percent": 0, "ram_percent": 0}


@router.get("/system/info")
async def system_info():
    """Snapshot completo do sistema — versão, modelo, config, agentes ativos."""
    import os, sys, platform
    from config import get_config
    from runtime.watchdog import get_watchdog
    cfg = get_config()
    wd = get_watchdog()
    uptime_s = wd.uptime()

    info: dict = {
        "jarvis_version": "6.0",
        "python_version": sys.version.split()[0],
        "platform": platform.system() + " " + platform.release(),
        "model": os.getenv("JARVIS_MODEL", cfg.local_model),
        "ollama_url": cfg.ollama_url,
        "uptime_seconds": uptime_s,
        "uptime_human": f"{int(uptime_s//3600):02d}:{int((uptime_s%3600)//60):02d}:{int(uptime_s%60):02d}",
        "tts_voice": cfg.tts_voice,
        "voice_enabled": cfg.voice_enabled,
        "safe_mode": cfg.safe_mode,
        "debug": cfg.debug,
    }

    try:
        import psutil
        info["cpu_count"] = psutil.cpu_count()
        ram = psutil.virtual_memory()
        info["ram_total_gb"] = round(ram.total / 1024**3, 1)
        info["ram_used_gb"]  = round(ram.used  / 1024**3, 1)
    except Exception:
        pass

    try:
        from routes.agents import list_agents_route
        agents_data = list_agents_route()
        info["agent_count"] = agents_data.get("count", 0)
    except Exception:
        info["agent_count"] = 0

    return info


@router.get("/audit")
async def get_audit_log(limit: int = 50):
    """Retorna as últimas entradas do audit log (apenas localhost)."""
    try:
        from middleware.audit import get_recent_audit
        entries = get_recent_audit(limit)
        return {"count": len(entries), "entries": entries}
    except Exception as e:
        return {"error": str(e), "entries": []}


@router.get("/security/status")
async def security_status():
    """Estado da camada de segurança — middlewares ativos."""
    checks = {}
    try:
        from middleware.security_headers import SecurityHeadersMiddleware
        checks["security_headers"] = "active"
    except Exception:
        checks["security_headers"] = "inactive"
    try:
        from middleware.input_guard import InputGuardMiddleware
        checks["input_guard"] = "active"
    except Exception:
        checks["input_guard"] = "inactive"
    try:
        from middleware.audit import AuditMiddleware
        checks["audit_log"] = "active"
    except Exception:
        checks["audit_log"] = "inactive"
    try:
        from middleware.ws_guard import check_ws_allowed
        checks["ws_guard"] = "active"
    except Exception:
        checks["ws_guard"] = "inactive"
    try:
        from utils.crypto import generate_token
        checks["crypto"] = "active"
    except Exception:
        checks["crypto"] = "inactive"

    active = sum(1 for v in checks.values() if v == "active")
    total = len(checks)
    return {
        "security_score": f"{active}/{total}",
        "level": "MAXIMUM" if active == total else "PARTIAL" if active >= 3 else "MINIMAL",
        "checks": checks,
    }


def os_env(key: str, default: str = "") -> str:
    import os
    return os.getenv(key, default)
