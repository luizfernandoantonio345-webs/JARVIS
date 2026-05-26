#!/usr/bin/env python3
import asyncio
import websockets
import json

async def test_ws():
    try:
        print("Connecting to ws://localhost:8000/ws/jarvis...")
        async with websockets.connect("ws://localhost:8000/ws/jarvis", ping_timeout=10) as ws:
            print("✓ Connected! Sending message...")
            await ws.send("oi")
            
            print("Waiting for responses...")
            for i in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    print(f"  [{i}] Received: {msg[:100]}")
                    m = json.loads(msg)
                    print(f"       → Type: {m.get('type')}, Status: {m.get('status')}")
                except asyncio.TimeoutError:
                    print(f"  [{i}] Timeout waiting for response")
                    break
            
            print("✓ WebSocket test complete")
            
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ws())
