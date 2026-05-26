import asyncio
import json

import websockets


async def test_ws() -> None:
    uri = "ws://localhost:8000/ws/jarvis"
    print(f"Conectando em {uri}...")

    async with websockets.connect(uri) as ws:
        print("OK Conectado")

        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg)
        print(f"OK Mensagem inicial: {data.get('status') or data.get('type')}")

        await ws.send("oi jarvis, me responda em portugues")
        print("OK Mensagem enviada")

        tokens = []
        full_response = ""
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < 15:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                data = json.loads(msg)
                msg_type = data.get("type") or data.get("status", "")

                if msg_type == "token":
                    token = data.get("content", "")
                    tokens.append(token)
                    print(f"TOKEN: {token}", end="", flush=True)
                elif msg_type == "done":
                    full_response = data.get("full_response", "".join(tokens))
                    print("\nOK DONE recebido")
                    break
                elif msg_type in ["thinking", "idle", "speaking"]:
                    print(f"\nSTATUS: {msg_type}")
                else:
                    print(f"\nMSG: {data}")
            except asyncio.TimeoutError:
                break

        summary = full_response[:200] or "".join(tokens)[:200]
        print("\n" + "=" * 50)
        print(f"OK Resposta completa: {summary}")
        print(f"OK Tokens recebidos: {len(tokens)}")


if __name__ == "__main__":
    asyncio.run(test_ws())
