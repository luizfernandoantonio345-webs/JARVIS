"""
Prewarming the LLM model on startup for faster first response
"""

import asyncio
import logging

log = logging.getLogger(__name__)

async def prewarm_ollama_model():
    """Warm up the model by sending a dummy prompt"""
    await asyncio.sleep(5)  # Wait for server to fully start
    try:
        from ai.client import get_ai_client
        client = get_ai_client()
        
        # Send a simple prompt to load the model
        result = client.call([
            {"role": "user", "content": "respond with only: model ready"}
        ])
        
        log.info("[PREWARM] Ollama model warmed up successfully")
        return True
    except Exception as e:
        log.warning("[PREWARM] Model warmup failed (non-critical): %s", e)
        return False
