#!/usr/bin/env python
"""
Quick validation of JARVIS server and voice system
"""
import asyncio
import json
import sys

async def test_websocket_chat():
    """Test WebSocket chat endpoint"""
    try:
        import websockets
    except ImportError:
        print("⚠️  websockets not installed, skipping WebSocket test")
        return False
    
    try:
        print("\n🔌 Testing WebSocket connection to localhost:8000/ws/jarvis...")
        
        async with websockets.connect("ws://localhost:8000/ws/jarvis") as websocket:
            print("   ✓ Connected!")
            
            # Send a test message
            test_msg = {"type": "text", "content": "Oi JARVIS, você está aí?"}
            await websocket.send(json.dumps(test_msg))
            print(f"   ✓ Sent message: {test_msg['content']}")
            
            # Receive response (with timeout)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                data = json.loads(response)
                print(f"   ✓ Received: {data.get('type', 'unknown')} - {data.get('content', '')[:50]}...")
                return True
            except asyncio.TimeoutError:
                print("   ⚠️  Response timeout (LLM might be busy)")
                return False
                
    except Exception as e:
        print(f"   ✗ WebSocket test failed: {e}")
        return False

async def test_voice_modules():
    """Test voice module imports"""
    print("\n🎤 Testing voice modules...")
    try:
        from backend.voice.output import speak
        print("   ✓ TTS (voice.output) imported")
        
        from backend.voice.voice_loop import capture_audio_realtime
        print("   ✓ Audio capture (voice.voice_loop) imported")
        
        import sounddevice
        devices = sounddevice.query_devices()
        input_count = sum(1 for d in devices if d["max_input_channels"] > 0)
        print(f"   ✓ Audio devices detected: {input_count}")
        
        return True
    except Exception as e:
        print(f"   ✗ Voice module test failed: {e}")
        return False

async def test_cache():
    """Test TTS cache functionality"""
    print("\n💾 Testing TTS cache...")
    try:
        from backend.voice.output import speak
        
        test_text = "Teste de cache"
        
        # First call (generation)
        import time
        start = time.time()
        result1 = await speak(test_text)
        time1 = time.time() - start
        
        # Second call (should be cached)
        start = time.time()
        result2 = await speak(test_text)
        time2 = time.time() - start
        
        speedup = time1 / time2 if time2 > 0 else float("inf")
        print(f"   ✓ Call 1: {time1*1000:.0f}ms (generation)")
        print(f"   ✓ Call 2: {time2*1000:.0f}ms (cache)")
        print(f"   ✓ Speedup: {speedup:.1f}x")
        
        return True
    except Exception as e:
        print(f"   ⚠️  Cache test warning: {e}")
        return False

async def main():
    print("\n" + "="*60)
    print("JARVIS v6.0 - System Validation")
    print("="*60)
    
    results = []
    
    # Test voice modules
    results.append(("Voice Modules", await test_voice_modules()))
    
    # Test cache
    results.append(("TTS Cache", await test_cache()))
    
    # Test WebSocket
    results.append(("WebSocket", await test_websocket_chat()))
    
    # Summary
    print("\n" + "="*60)
    print("Validation Results:")
    print("="*60)
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    total = len(results)
    passed = sum(1 for _, r in results if r)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
