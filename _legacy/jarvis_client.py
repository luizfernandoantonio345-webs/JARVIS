#!/usr/bin/env python3
"""
JARVIS Client — Interface interativa para comunicação com o backend
"""

import asyncio
import json
import websockets
import sys
from pathlib import Path

async def jarvis_chat():
    """Inicia sessão interativa com JARVIS via WebSocket"""
    
    uri = "ws://localhost:8000/ws/jarvis"
    
    print("\n" + "="*60)
    print("JARVIS v5.2 — Sistema de IA Autônoma")
    print("="*60)
    print("\nConectando ao JARVIS...\n")
    
    try:
        async with websockets.connect(uri) as websocket:
            # Recebe mensagem de boas-vindas
            welcome = await websocket.recv()
            print(f"[JARVIS]: {welcome}\n")
            
            while True:
                try:
                    user_input = input("Você: ").strip()
                    
                    if not user_input:
                        continue
                    
                    if user_input.lower() in ['sair', 'exit', 'quit']:
                        print("\n[JARVIS]: Desconectando. Até logo, senhor.\n")
                        break
                    
                    # Envia mensagem
                    await websocket.send(user_input)
                    
                    # Recebe resposta
                    response = await websocket.recv()
                    print(f"\n[JARVIS]: {response}\n")
                    
                except KeyboardInterrupt:
                    print("\n\n[JARVIS]: Interrupção detectada. Encerrando sessão.\n")
                    break
                except Exception as e:
                    print(f"\n[ERRO]: {e}\n")
                    break
                    
    except ConnectionRefusedError:
        print("\n[ERRO]: Não foi possível conectar ao JARVIS.")
        print("Certifique-se de que o servidor está rodando em http://localhost:8000")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERRO]: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(jarvis_chat())
