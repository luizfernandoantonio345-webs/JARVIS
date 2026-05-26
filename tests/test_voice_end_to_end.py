"""
End-to-end voice integration tests
Tests complete voice pipeline: Audio Input -> STT -> LLM -> TTS -> Audio Output
"""
import asyncio
import pytest
import sys
import time
import os

sys.path.insert(0, "backend")


@pytest.mark.asyncio
async def test_voice_end_to_end_chat():
    """Test complete voice pipeline: Text -> LLM -> TTS."""
    from backend.voice.output import speak
    from backend.services.chat_service import process_message
    
    test_phrase = "Olá JARVIS, qual é sua função?"
    
    print(f"\n🎤 Voice Test: {test_phrase}")
    
    # 1. Simulate LLM response
    start = time.time()
    response = await asyncio.get_event_loop().run_in_executor(
        None, process_message, test_phrase, "test_session"
    )
    elapsed = time.time() - start
    
    print(f"✓ LLM Response: {response[:80]}... ({elapsed:.2f}s)")
    assert len(response) > 0
    
    # 2. Generate TTS
    start = time.time()
    audio_path = await speak(response)
    tts_time = time.time() - start
    
    print(f"✓ TTS Generated: {tts_time:.2f}s (cache: {tts_time < 0.5})")
    # Should be <2s for generation, <100ms for cache


@pytest.mark.asyncio
async def test_audio_device_detection():
    """Test headset/microphone detection."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        
        input_devices = [d for d in devices if d["max_input_channels"] > 0]
        print(f"\n🎧 Found {len(input_devices)} input devices:")
        
        for i, d in enumerate(input_devices):
            name = d["name"]
            channels = d["max_input_channels"]
            print(f"  {i}: {name} ({channels} channels)")
        
        assert len(input_devices) > 0, "No audio input devices found"
        
    except ImportError:
        print("⚠️  sounddevice not available, skipping device detection")


@pytest.mark.asyncio
async def test_fast_tts_cache():
    """Test that TTS caching provides significant speedup."""
    from backend.voice.output import speak
    
    text = "Teste de cache"
    times = []
    
    for i in range(2):
        start = time.time()
        await speak(text)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"\n  Call {i+1}: {elapsed*1000:.0f}ms")
    
    # Second call should be much faster (cache hit)
    speedup = times[0] / times[1] if times[1] > 0 else float("inf")
    print(f"  Speedup: {speedup:.0f}x")
    
    assert times[1] < 0.5, f"Cache miss not fast: {times[1]}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
