#!/usr/bin/env python3
"""
Test script to validate voice integration end-to-end.
Tests: Frontend audio capture → Backend voice/command → TTS playback
"""
import os
import sys
import asyncio
import json
import tempfile
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

os.environ["PYTHONPATH"] = str(Path(__file__).parent)

async def test_voice_route():
    """Test if /voice/command route is accessible and working."""
    try:
        import requests
        
        # Test 1: Check if backend is running
        print("[TEST 1] Verificando se backend está rodando...")
        r = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"[OK] Backend respondendo: {data['status']}")
            print(f"   - Ollama: {data['components']['ollama']}")
            print(f"   - Voice Guard: {data['components']['voice_guard']}")
        else:
            print(f"[ERR] Backend retornou: {r.status_code}")
            return False
        
        # Test 2: Create a simple WAV file for testing
        print("\n[TEST 2] Criando arquivo WAV de teste...")
        import wave
        import struct
        
        wav_path = str(Path(tempfile.gettempdir()) / "test_voice.wav")
        sample_rate = 16000
        duration = 1  # 1 segundo de silêncio
        
        # Create simple WAV with silence
        with wave.open(wav_path, 'w') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            samples = struct.pack('<' + ('h' * (sample_rate * duration)), *[0] * (sample_rate * duration))
            wav.writeframes(samples)
        
        print(f"[OK] WAV criado em: {wav_path}")
        
        # Test 3: Test /voice/command endpoint
        print("\n[TEST 3] Testando rota /voice/command...")
        with open(wav_path, 'rb') as f:
            files = {'audio': ('test.wav', f, 'audio/wav')}
            data = {'session_id': 'test_voice_v2'}
            
            r = requests.post(
                "http://127.0.0.1:8000/voice/command",
                files=files,
                data=data,
                timeout=30
            )
        
        if r.status_code == 200:
            result = r.json()
            print("[OK] /voice/command respondeu com sucesso!")
            print(f"   - Status: {result.get('status')}")
            print(f"   - Response: {result.get('response', 'N/A')[:100]}")
            if 'audio_path' in result:
                print(f"   - Audio Path: {result['audio_path']}")
            return True
        else:
            print(f"[ERR] /voice/command retornou {r.status_code}")
            print(f"   Erro: {r.text[:200]}")
            return False
            
    except Exception as e:
        print(f"[ERR] Erro no teste: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_voice_route())
    sys.exit(0 if success else 1)
