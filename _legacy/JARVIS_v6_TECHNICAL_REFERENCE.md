# JARVIS v6.0 — TECHNICAL REFERENCE

## 📁 Estrutura de Arquivos

### Voice Pipeline v3 (Novo)
```
backend/
  voice_v2/
    headset_listener.py       [NOVO] Captura contínua de áudio
    voice_pipeline_v3.py      [NOVO] STT→Process→TTS pipeline
    output.py                 [ATUALIZADO] speak() com en-GB-RyanNeural
    __init__.py
```

### Configuração
```
.env                          [ATUALIZADO] JARVIS_TTS_VOICE, etc
backend/core/jarvis_persona.py  [ATUALIZADO] IDENTITY_PROMPT britânico
backend/main.py               [ATUALIZADO] Init voice_pipeline_v3
```

### Executáveis
```
start_jarvis_final.bat        [NOVO] Launcher definitivo
validate_jarvis_final.py      [NOVO] Smoke tests
test_tts_british.py           [NOVO] TTS test
test_audio_devices.py         [NOVO] Audio diagnostic
test_headset_recording.py     [NOVO] Recording test
```

---

## 🔌 API Endpoints (Voice)

### WebSocket
```
ws://localhost:8000/ws/jarvis
```

**Eventos broadcast:**
```json
{
  "event": "voice_state",
  "state": "IDLE|PROCESSING|SPEAKING",
  "text": "transcription or response"
}
```

### REST (Existing)
```
GET  /health                    → system status
GET  /tts-iron?text=...         → generate audio
POST /chat                      → process message
```

---

## 🎯 Fluxo de Voz (Voice Pipeline v3)

### 1. HeadsetListener
```python
from voice_v2.headset_listener import HeadsetListener

# Auto-detects device, triggers on speech
listener = HeadsetListener(
    device_index=1,           # Microfone Intel [1]
    on_audio=callback,        # async callback
    loop=asyncio.get_event_loop()
)
listener.start()
```

### 2. Audio Processing
```
Raw audio (int16, 16000 Hz)
    ↓
numpy array (float32)
    ↓
silence detection (SILENCE_DB=0.015)
    ↓
on_audio() callback triggered
```

### 3. Transcription
```python
from faster_whisper import WhisperModel

model = WhisperModel('small', device='cpu', compute_type='int8')
segments, info = model.transcribe(audio_buffer, language='pt')
text = " ".join(s.text for s in segments)
```

### 4. Response Generation
```python
response = await orchestrator.execute(text, 'voice')
# or
response = chat_service.process_message(text)
```

### 5. Text-to-Speech
```python
from voice.output import speak

await speak(
    response,
    voice='en-GB-RyanNeural'  # default from .env
)
```

---

## ⚙️ Configuration (Environment Variables)

### Voice Settings
```bash
JARVIS_VOICE_ENABLED=true                    # Enable voice
JARVIS_TTS_VOICE=en-GB-RyanNeural            # Default voice
JARVIS_TTS_RATE=-5%                          # Speed adjustment
JARVIS_TTS_PITCH=-8Hz                        # Pitch adjustment
JARVIS_STT_MODEL=small                       # Whisper model size
JARVIS_LANG=en-GB                            # Language code
JARVIS_USER_TITLE=Sir                        # User address

# Optional: Access control
JARVIS_ACCESS_KEY=your_password_here         # Basic auth
```

### Backend Settings
```bash
JARVIS_HOST=0.0.0.0                          # Listen all interfaces
JARVIS_PORT=8000                             # HTTP port
JARVIS_DEBUG=false                           # Debug mode
JARVIS_OLLAMA_URL=http://192.168.0.106:11434
JARVIS_MODEL=phi:latest
```

---

## 🧪 Testing Commands

### Quick Tests
```bash
# Audio devices
python test_audio_devices.py

# Recording (3 seconds)
python test_headset_recording.py

# TTS British voice
python test_tts_british.py

# Full validation (with backend running)
python validate_jarvis_final.py
```

### Manual Testing
```bash
# Start backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# In another terminal:
# Open http://localhost:8000
# Speak in microphone
# Wait 2 seconds silence
# JARVIS responds in British voice
```

---

## 📊 Logging

### Important Log Keywords
```
[HEADSET]     Audio device detection
[HEADSET]     Capturing audio
[VOICE_V3]    Transcription results
[VOICE_V3]    Orchestrator processing
[TTS]         Text-to-speech generation
[VOZ]         Voice system startup
```

### Log Levels
```
INFO    Normal operation events
DEBUG   Detailed debugging info
WARNING Warnings (non-fatal)
ERROR   Errors (needs attention)
```

---

## 🚀 Performance Notes

### CPU Usage
- **Whisper small model:** ~1-2GB RAM, 500ms/audio
- **edge-tts:** Network call, ~100ms
- **pyttsx3 fallback:** CPU fallback, instant

### Latency
- Audio capture to transcription: ~500ms
- Orchestrator processing: ~1-2s (depends on Ollama)
- TTS generation: ~200-500ms
- **Total:** ~2-3 seconds from speech to response

### Optimization
- Whisper model pre-warmed on startup
- pyttsx3 engine singleton (reused)
- Edge-tts streams to memory (no disk)

---

## 🔐 Security

### Tailscale VPN
```
VPN ensures: Only your devices can access JARVIS
No port forwarding needed
Automatic WireGuard encryption
```

### Optional Basic Auth
```
In .env: JARVIS_ACCESS_KEY=your_password
Browser will prompt for password on first visit
```

### Best Practices
- Change Tailscale password regularly
- Keep Tailscale app updated
- Monitor access logs on backend
- Use strong JARVIS_ACCESS_KEY if enabled

---

## 🔧 Troubleshooting Code

### Check Audio Device
```python
import sounddevice as sd
devices = sd.query_devices()
for i, d in enumerate(devices):
    print(f"[{i}] {d['name']}")
```

### Test Transcription
```python
from faster_whisper import WhisperModel
model = WhisperModel('small', device='cpu', compute_type='int8')
segments, info = model.transcribe('test_mic.wav', language='pt')
print("\n".join(s.text for s in segments))
```

### Test TTS
```python
import asyncio
from voice.output import speak
asyncio.run(speak("Test voice"))
```

### Check Ollama Connection
```bash
curl http://192.168.0.106:11434/api/tags
```

---

## 📈 Monitoring

### Backend Health
```bash
curl http://localhost:8000/health
```

### Voice Pipeline Status
```python
from voice_v2.voice_pipeline_v3 import get_voice_pipeline
pipeline = get_voice_pipeline()
print(pipeline.status())
# Output:
# {
#   "active": true,
#   "processing": false,
#   "stt_loaded": true,
#   "listener_ok": true,
# }
```

---

## 📞 Support

### Common Issues

**"No audio captured"**
- Check device index: `python test_audio_devices.py`
- Check audio level: `python test_headset_recording.py`
- Verify device is connected and not muted

**"TTS not playing"**
- Check speakers are connected
- Fallback to pyttsx3 (check logs)
- Test with: `python test_tts_british.py`

**"Backend not responsive"**
- Kill old process: `netstat -ano | findstr :8000`
- Check Ollama on PC2: `curl http://192.168.0.106:11434/api/tags`
- Increase startup wait time in batch file

**"Transcription empty"**
- Check microphone audio level (need >0.01)
- Try again with clearer speech
- Check Whisper logs for errors

---

**Version:** 6.0 Final  
**Last Updated:** 19/05/2026  
**Status:** Production Ready ✓
