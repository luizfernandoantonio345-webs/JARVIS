#!/usr/bin/env python
"""
JARVIS Minimal Debug Server — testa apenas /health sem outros routers
"""
import sys
import os
import logging

# Setup path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, os.path.join(BACKEND_DIR, "backend"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("MINIMAL")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time

app = FastAPI(title="JARVIS Minimal")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple health check (no watchdog, no expensive checks)
@app.get("/health")
async def health_minimal():
    """Minimal health check without expensive initialization"""
    import httpx
    
    log.info("Health check requested...")
    
    # Just check if Ollama responds
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            ollama_ok = r.status_code == 200
            log.info(f"Ollama check: {ollama_ok}")
    except Exception as e:
        log.warning(f"Ollama check failed: {e}")
    
    return {
        "status": "ok" if ollama_ok else "degraded",
        "service": "JARVIS API",
        "version": "6.0",
        "components": {
            "api": True,
            "ollama": ollama_ok,
        }
    }

if __name__ == "__main__":
    log.info("Starting JARVIS Minimal Server on port 8000...")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
