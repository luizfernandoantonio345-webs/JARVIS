#!/usr/bin/env python
"""
Practical chat test for JARVIS v6.0
Tests WebSocket chat endpoint without voice input
"""
import asyncio
import json
import sys
import time

async def send_chat_message(message, timeout=15):
    """Send a chat message and get response via WebSocket"""
    try:
        import websockets
    except ImportError:
        print("Error: websockets package not installed")
        return False
    
    try:
        print(f"\n📤 Connecting to WebSocket (timeout={timeout}s)...")
        async with websockets.connect("ws://localhost:8000/ws/jarvis") as ws:
            print("✓ Connected!")
            
            # Send message
            payload = {"type": "text", "content": message}
            print(f"📝 Sending: {message}")
            await ws.send(json.dumps(payload))
            
            # Collect response
            response_text = ""
            start_time = time.time()
            
            try:
                while True:
                    # Check timeout
                    if time.time() - start_time > timeout:
                        print(f"⏱️  Response timeout after {timeout}s")
                        break
                    
                    # Receive with per-message timeout
                    data = await asyncio.wait_for(ws.recv(), timeout=2)
                    msg = json.loads(data)
                    
                    if msg.get("type") == "token":
                        response_text += msg.get("content", "")
                        print(msg.get("content", ""), end="", flush=True)
                    elif msg.get("type") == "done":
                        print("\n✓ Response complete")
                        break
                    elif msg.get("type") == "error":
                        print(f"\n✗ Error: {msg.get('content')}")
                        break
                        
            except asyncio.TimeoutError:
                pass
            
            if response_text:
                print(f"\n✓ Got response ({len(response_text)} chars)")
                return True
            else:
                print("✗ No response received")
                return False
                
    except Exception as e:
        print(f"✗ WebSocket error: {e}")
        return False

async def main():
    print("\n" + "="*60)
    print("JARVIS v6.0 - Chat Test")
    print("="*60)
    
    # Test 1: Simple greeting
    print("\n[Test 1] Simple greeting...")
    success1 = await send_chat_message("Olá JARVIS, você está funcionando?")
    
    # Test 2: Question
    print("\n[Test 2] Question...")
    success2 = await send_chat_message("Qual é a data de hoje?", timeout=20)
    
    # Test 3: Command
    print("\n[Test 3] Command...")
    success3 = await send_chat_message("Qual é o seu objetivo principal?", timeout=20)
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary:")
    print(f"  Greeting: {'✓' if success1 else '✗'}")
    print(f"  Question: {'✓' if success2 else '✗'}")
    print(f"  Command:  {'✓' if success3 else '✗'}")
    print("="*60)
    
    return success1 or success2 or success3

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
