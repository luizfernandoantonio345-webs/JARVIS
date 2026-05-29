# J.A.R.V.I.S. v6.0 — GUIA DE USO FINAL

**Implementação Completa:** Voz britânica + Acesso remoto  
**Data:** 19 de maio de 2026  
**Status:** PRONTO PARA PRODUÇÃO ✓

---

## 🚀 INICIAR JARVIS EM 1 CLIQUE

### Windows
```bash
start_jarvis_final.bat
```

Isso faz automaticamente:
- ✓ Verifica PC2 Ollama (192.168.0.106:11434)
- ✓ Mata instâncias antigas
- ✓ Inicia backend (localhost:8000)
- ✓ Abre interface no navegador

**Tempo de boot:** ~30 segundos

---

## 🎤 USAR A VOZ

### Como Usar
1. Backend rodando em http://localhost:8000
2. Fale claramente no microfone
3. Aguarde 2 segundos de silêncio
4. JARVIS responde em voz britânica refinada

### Personagem
- **Nome:** J.A.R.V.I.S. (Just A Rather Very Intelligent System)
- **Voz:** en-GB-RyanNeural (britânica, masculina, refinada)
- **Tratamento:** "Sir" (inglês) ou "Senhor" (português)
- **Estilo:** Preciso, direto, sem emoção

### Exemplo de Diálogo
**Você:** "What time is it?"  
**JARVIS:** "It is currently 14:37, Sir. Is there anything else you require?"

---

## 🌍 ACESSO REMOTO COM TAILSCALE

### Instalação (1 vez)
1. Baixar: https://tailscale.com/download/windows
2. Instalar no PC1, celular e outros dispositivos
3. Login com a mesma conta em todos

### Usar de Qualquer Lugar
```
http://100.X.X.X:8000  ← IP Tailscale do PC1
```

**Exemplo:**
- PC1 (local): http://localhost:8000
- Celular (remoto): http://100.X.X.X:8000
- Notebook (remoto): http://100.X.X.X:8000

### Segurança
- VPN Tailscale só permite acesso da sua conta
- Ninguém da internet consegue acessar
- Senha opcional em .env: `JARVIS_ACCESS_KEY=...`

---

## ✅ VALIDAR TUDO ESTÁ FUNCIONANDO

Com backend rodando:
```bash
python validate_jarvis_final.py
```

**Resultado esperado:**
```
==================================================
  13/13 PASS (100%)
==================================================
  ✓ J.A.R.V.I.S. 100% OPERATIONAL
  ✓ Ready for production use
```

---

## 🔍 DIAGNÓSTICO DE ÁUDIO

Se o microfone não capturar:
```bash
python test_audio_devices.py
```

Buscar na lista por "Headset" ou "Microfone":
- Se encontrou o seu: dispositivo está OK
- Se não encontrou: desconectar/reconectar headset

### Testar Captura
```bash
python test_headset_recording.py
```

**Resultado:** Arquivo `test_mic.wav` com sua gravação

---

## 🔊 TESTAR TTS BRITÂNICO

```bash
python test_tts_british.py
```

Escuta a voz britânica JARVIS dizendo:
> "Good evening, Sir. All systems are operational."

---

## 📊 ARQUITETURA

```
┌─────────────────────────────────────────┐
│         FRONTEND (http://localhost:8000)│
│         - Orbe visual                   │
│         - Chat em tempo real            │
│         - Controle de voz               │
└──────────────┬──────────────────────────┘
               │ WebSocket
┌──────────────▼──────────────────────────┐
│        BACKEND (FastAPI, port 8000)     │
│        - Orchestrator                   │
│        - Chat service                   │
│        - Voice pipeline v3              │
│        - TTS/STT handlers               │
└──────┬─────────────┬─────────────────┬──┘
       │             │                 │
   ┌───▼─┐       ┌───▼──┐         ┌───▼──┐
   │ TTS │◄──────┤ STT  │         │Chat  │
   └─────┘  Edge-├──────┤         └──────┘
            TTS  │Whisper│        Local
            PyTTS│Small  │        Ollama
                 └───────┘        PC2

VoicePipeline v3 Flow:
Headset → HeadsetListener → NumPy array
      → Whisper.transcribe() → text
      → orchestrator.execute() → response
      → speak(response) → PowerShell MediaPlayer
```

---

## 🛠️ CONFIGURAÇÃO

### .env Voz
```bash
JARVIS_VOICE_ENABLED=true
JARVIS_TTS_VOICE=en-GB-RyanNeural
JARVIS_TTS_RATE=-5%
JARVIS_TTS_PITCH=-8Hz
JARVIS_LANG=en-GB
JARVIS_USER_TITLE=Sir
```

### Mudar para Português (opcional)
```bash
JARVIS_TTS_VOICE=pt-BR-AntonioNeural
JARVIS_USER_TITLE=Senhor
```

---

## 📝 LOGS

Logs ao vivo no terminal do backend:
```
[VOZ_V3] Transcrição: hello JARVIS
[VOZ_V3] Resposta: Good evening, Sir...
[TTS] edge_tts (en-GB-RyanNeural) OK
```

---

## ⚠️ TROUBLESHOOTING

| Problema | Solução |
|----------|---------|
| Sem áudio capturado | `python test_headset_recording.py` → check nível |
| TTS não fala | Verificar speakers; edge-tts fallback para pyttsx3 |
| Backend não inicia | `netstat -ano \| findstr :8000` → kill processo |
| WebSocket desconecta | Verificar firewall; Tailscale requer conexão |
| Ollama não conecta | PC2 offline: `set OLLAMA_HOST=0.0.0.0 && ollama serve` |

---

## 📋 CHECKLIST DE USO

- [ ] Backend rodando: `start_jarvis_final.bat`
- [ ] Frontend carrega em http://localhost:8000
- [ ] Orbe visual funciona
- [ ] Chat em texto funciona
- [ ] Microfone captura (teste 3s)
- [ ] TTS responde em voz britânica
- [ ] Validação passa: `python validate_jarvis_final.py`
- [ ] Tailscale conectado (opcional, para remoto)

---

## 🎯 PRÓXIMOS PASSOS

1. **Hoje:** Ligar PC1 e rodar `start_jarvis_final.bat`
2. **Hoje:** Testar conversa por voz (falar claro)
3. **Hoje:** Instalar Tailscale para acesso remoto
4. **Hoje:** Criar bookmark JARVIS no celular
5. **Amanhã:** Treinar mais modelos se necessário

---

**Engenheiro:** Senior AI Assistant  
**Versão:** 6.0 Final Production  
**Build:** 19/05/2026  
**Status:** ✓ Pronto para entrega
