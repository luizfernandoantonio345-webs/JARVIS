"""
Advanced JARVIS control endpoints
B16: Memory management
B17: History access
B18: Capabilities listing
B19: Session management
B20: Performance diagnostics
"""

from fastapi import APIRouter, HTTPException
import json

router = APIRouter()

@router.get("/jarvis/memory/profile")
async def get_user_profile():
    """Get learned user profile"""
    try:
        from memory.persistent_memory import get_persistent_memory
        mem = get_persistent_memory()
        profile = mem.get_profile()
        return {"profile": profile or {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jarvis/history")
async def get_command_history(session_id: str, limit: int = 20):
    """Get command history for a session"""
    try:
        from memory.persistent_memory import get_persistent_memory
        mem = get_persistent_memory()
        recent = mem.get_recent(session_id, limit)
        return {"history": recent or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jarvis/capabilities")
async def get_capabilities():
    """List all JARVIS capabilities"""
    capabilities = {
        "chat": "Conversational AI with context memory",
        "code": "Code generation, analysis, debugging",
        "voice": "Voice input and output (TTS/STT)",
        "memory": "Persistent memory across sessions",
        "research": "Information synthesis and research",
        "automation": "Computer control and task execution",
        "agents": "Specialized task agents",
        "streaming": "Real-time token streaming",
        "websocket": "Real-time bidirectional communication",
    }
    return {"capabilities": capabilities}

@router.post("/jarvis/wake")
async def wake_jarvis():
    """Wake JARVIS (set listening state)"""
    from main import manager
    await manager.broadcast({
        "event": "voice_state",
        "state": "LISTENING"
    })
    return {"status": "listening"}

@router.post("/jarvis/sleep")
async def sleep_jarvis():
    """Put JARVIS to sleep (set idle state)"""
    from main import manager
    await manager.broadcast({
        "event": "voice_state", 
        "state": "IDLE"
    })
    return {"status": "idle"}

@router.get("/jarvis/diagnostics")
async def system_diagnostics():
    """Get detailed system diagnostics"""
    try:
        from observability.enhanced_metrics import get_metrics
        from ai.client import get_ai_client
        import os
        
        metrics = get_metrics().snapshot()
        
        ollama_ok = False
        ollama_version = None
        try:
            client = get_ai_client()
            h = client.health_check()
            ollama_ok = h.get("ok", False)
            ollama_version = h.get("version")
        except:
            pass
        
        return {
            "metrics": metrics,
            "ollama": {
                "connected": ollama_ok,
                "version": ollama_version,
                "model": os.getenv("JARVIS_MODEL", "unknown"),
            },
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
