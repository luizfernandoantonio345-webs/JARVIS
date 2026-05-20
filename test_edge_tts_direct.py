#!/usr/bin/env python3
import asyncio
import tempfile
import os
from backend.config import get_config

async def test_tts():
    cfg = get_config()
    print(f"TTS Voice: {cfg.tts_voice}")
    print(f"TTS Rate: {cfg.tts_rate}")
    print(f"TTS Pitch: {cfg.tts_pitch}")
    
    try:
        import edge_tts
        print("edge_tts imported OK")
        
        text = "Olá, eu sou o JARVIS"
        print(f"Text: {text}")
        
        comm = edge_tts.Communicate(text, cfg.tts_voice, rate=cfg.tts_rate, pitch=cfg.tts_pitch)
        print("Communicate object created")
        
        path = os.path.join(tempfile.gettempdir(), "test_tts.mp3")
        print(f"Saving to: {path}")
        
        await comm.save(path)
        print(f"Saved! Size: {os.path.getsize(path)} bytes")
        os.unlink(path)
        print("Success!")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tts())
