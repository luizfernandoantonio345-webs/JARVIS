#!/usr/bin/env python3
"""
JARVIS Chat Client via HTTP API
"""

import httpx
import sys
import json

def chat_with_jarvis():
    """Interface simples para conversar com JARVIS via HTTP"""
    
    base_url = "http://localhost:8000"
    
    print("\n" + "="*70)
    print("JARVIS v5.2 — Sistema de IA Autônoma")
    print("="*70)
    print("\nSistemas online. Digite suas instruções (ou 'sair' para encerrar).\n")
    
    try:
        while True:
            try:
                user_input = input("Você: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['sair', 'exit', 'quit', 'sai']:
                    print("\n[JARVIS]: Desconectando. Até logo, senhor.\n")
                    break
                
                # Envia comando para o endpoint /process
                print("\n[JARVIS]: Processando...\n")
                
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        f"{base_url}/process",
                        params={"cmd": user_input}
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Extrai resposta
                        if isinstance(result, dict):
                            if "response" in result:
                                print(f"[JARVIS]: {result['response']}\n")
                            elif "error" in result:
                                print(f"[ERRO]: {result['error']}\n")
                            else:
                                print(f"[RESPOSTA]: {json.dumps(result, indent=2, ensure_ascii=False)}\n")
                        else:
                            print(f"[JARVIS]: {result}\n")
                    else:
                        print(f"[ERRO]: Status {response.status_code} — {response.text}\n")
                        
            except KeyboardInterrupt:
                print("\n\n[JARVIS]: Interrupção detectada. Encerrando sessão.\n")
                break
            except Exception as e:
                print(f"[ERRO]: {type(e).__name__}: {e}\n")
                
    except Exception as e:
        print(f"\n[ERRO CRÍTICO]: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    try:
        chat_with_jarvis()
    except KeyboardInterrupt:
        print("\n\nDesconectando...\n")
        sys.exit(0)
