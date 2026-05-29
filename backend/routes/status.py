"""
New endpoint: GET /status
Returns comprehensive system status for dashboards
"""

from fastapi import APIRouter
from datetime import datetime
import os
import time

router = APIRouter()

start_time = time.time()

@router.get("/status")
async def system_status():
    """
    Get comprehensive system status
    
    Response includes:
    - System: online/degraded/offline
    - Ollama: connected/disconnected
    - Uptime: seconds
    """
    ai_ok = False
    try:
        from ai.client import get_ai_client
        client = get_ai_client()
        h = client.health_check()
        ai_ok = h.get("ok", False)
    except Exception as e:
        pass
    
    uptime = time.time() - start_time
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "jarvis": "online",
        "model": os.getenv("JARVIS_MODEL", "qwen2:0.5b"),
        "ollama_connected": ai_ok,
        "uptime_seconds": int(uptime),
        "uptime_formatted": f"{int(uptime//3600)}h {int((uptime%3600)//60)}m",
        "voice_enabled": os.getenv("JARVIS_VOICE_ENABLED", "true") == "true",
        "health_score": 100 if ai_ok else 60,
    }
