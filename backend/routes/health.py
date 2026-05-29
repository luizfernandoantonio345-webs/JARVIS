import shutil
import time
import logging
import asyncio

import httpx
from fastapi import APIRouter

router = APIRouter()
log = logging.getLogger(__name__)

_START_TIME = time.time()


async def _get_ollama_models_fast(url: str, timeout: float = 0.8) -> tuple[bool, list[str]]:
    """Check rápido com timeout curto — não trava o health"""
    try:
        clean_url = url.replace("localhost", "127.0.0.1")
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=0.3, read=timeout, write=0.5, pool=0.3)
        ) as c:
            r = await c.get(f"{clean_url}/api/tags")
            if r.status_code != 200:
                return False, []
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return True, [m for m in models if m]
    except Exception:
        return False, []


@router.get("/health")
async def health_check():
    log.info("[HEALTH] Check started")
    from backend.config import get_config
    from backend.runtime.watchdog import get_watchdog

    cfg = get_config()
    log.info("[HEALTH] Config loaded")
    wd = get_watchdog()
    log.info("[HEALTH] Watchdog retrieved")
    uptime_s = wd.uptime()
    log.info("[HEALTH] Uptime calculated: %s", uptime_s)
    hours, rem = divmod(uptime_s, 3600)
    mins, secs = divmod(rem, 60)

    ollama_ok = False
    installed_models: list[str] = []
    try:
        ollama_ok, installed_models = await asyncio.wait_for(
            _get_ollama_models_fast(cfg.ollama_url),
            timeout=1.2,
        )
    except Exception:
        ollama_ok = False

    model_info = {
        "provider": "ollama",
        "local_model": cfg.local_model,
        "model": cfg.local_model,
        "url": cfg.ollama_url,
        "status": "ok" if ollama_ok else "error",
        "models": installed_models,
        "openai_available": bool(getattr(cfg, "openai_api_key", None)),
        "claude_model": None,
        "openai_model": None,
        "complex_threshold": getattr(cfg, "complex_threshold", 0.45),
    }

    cache_info = {}
    try:
        from services.cache_service import cache_stats
        cache_info = cache_stats()
    except Exception:
        pass

    components = {
        "api": True,
        "ollama": ollama_ok,
        "voice_guard": True,
        "domain_detector": True,
        "semantic_memory": True,
    }
    degraded = [k for k, v in components.items() if not v]

    return {
        "status": "ok" if not degraded else "degraded",
        "service": "JARVIS API",
        "version": "6.0",
        "uptime": f"{hours:02d}:{mins:02d}:{secs:02d}",
        "uptime_seconds": uptime_s,
        "docker_available": shutil.which("docker") is not None,
        "models": model_info,
        "cache": cache_info,
        "components": components,
        "degraded": degraded,
    }
