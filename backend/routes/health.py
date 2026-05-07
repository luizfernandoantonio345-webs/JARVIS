import shutil
import time
import logging

from fastapi import APIRouter

from services.llm_service import get_model_info
from services.cache_service import cache_stats

router = APIRouter()
log = logging.getLogger(__name__)

_START_TIME = time.time()


@router.get("/health")
def health_check():
    uptime_s = int(time.time() - _START_TIME)
    hours, rem = divmod(uptime_s, 3600)
    mins, secs = divmod(rem, 60)

    model_info = {}
    try:
        model_info = get_model_info()
    except Exception as exc:
        log.debug("[routes.health] suppressed exception", exc_info=exc)
        pass

    cache_info = {}
    try:
        cache_info = cache_stats()
    except Exception as exc:
        log.debug("[routes.health] suppressed exception", exc_info=exc)
        pass

    return {
        "status": "ok",
        "service": "JARVIS API",
        "version": "3.0.0",
        "uptime": f"{hours:02d}:{mins:02d}:{secs:02d}",
        "docker_available": shutil.which("docker") is not None,
        "models": model_info,
        "cache": cache_info,
        "components": {
            "voice_guard": True,
            "domain_detector": True,
            "semantic_memory": True,
            "document_processor": True,
            "expert_system": True,
        },
    }
