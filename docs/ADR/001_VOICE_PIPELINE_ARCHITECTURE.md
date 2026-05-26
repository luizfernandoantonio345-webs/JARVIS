# ADR-001: Voice Pipeline Architecture

**Status**: Accepted  
**Date**: May 25, 2026  
**Participants**: JARVIS Team  

---

## Context

JARVIS v6.0 requires robust voice interaction capabilities including:
- Real-time speech recognition (Whisper)
- Natural language processing (Ollama LLM)
- Speech synthesis (Edge-TTS)
- Low-latency audio streaming via WebSocket
- Graceful degradation when components unavailable

The system must support:
- PT-BR language with Antonio Neural voice (masculine)
- Audio rate control (-12%) and pitch adjustment (-15Hz)
- Multiple concurrent voice sessions
- Wake word detection ("Jarvis")
- Headset/microphone support

---

## Decision

Implement a **three-stage asynchronous pipeline** with the following architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                      VOICE PIPELINE V3                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  STAGE 1: AUDIO CAPTURE          STAGE 2: PROCESSING           │
│  ┌──────────────────┐            ┌──────────────────┐          │
│  │ Headset Audio    │            │ Wake Detection   │          │
│  │ @ 16kHz, 16-bit  │ ──────────> │ (Optional)       │          │
│  │ PCM Format       │            └──────────────────┘          │
│  └──────────────────┘                    ↓                     │
│                                ┌──────────────────┐            │
│                                │ Whisper Model    │            │
│                                │ (STT)            │            │
│                                │ Small INT8       │            │
│                                └──────────────────┘            │
│                                         ↓                      │
│                                ┌──────────────────┐            │
│                                │ Text Processing  │            │
│                                │ (Preprocess)     │            │
│                                └──────────────────┘            │
│                                                                 │
│  STAGE 3: RESPONSE GENERATION                                  │
│  ┌────────────────────────────────────────────┐               │
│  │ LLM Processing                             │               │
│  │ (Ollama / Claude / GPT-4o-mini)            │               │
│  │ with context + memory                      │               │
│  └────────────────────────────────────────────┘               │
│           ↓                              ↓                     │
│  ┌──────────────────┐      ┌──────────────────┐               │
│  │ Edge-TTS         │      │ Streaming        │               │
│  │ (PT-BR)          │      │ Response Tokens  │               │
│  │ -12% rate        │      │ via WebSocket    │               │
│  │ -15Hz pitch      │      │                  │               │
│  └──────────────────┘      └──────────────────┘               │
│           ↓                                                    │
│  ┌──────────────────┐                                         │
│  │ Audio Output     │                                         │
│  │ to Speakers      │                                         │
│  └──────────────────┘                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions:

#### 1. **Pipeline Stages**

- **Capture**: Headset audio via sounddevice or pyaudio
- **Recognition**: Whisper model (small, INT8, CPU-only for low memory)
- **Processing**: Orchestrator coordinates agents (Planner, Executor, Critic)
- **Generation**: LLM generates response with experience context
- **Synthesis**: Edge-TTS converts text to speech (PT-BR with custom voice profile)
- **Output**: Stream audio chunks via WebSocket for real-time playback

#### 2. **State Management**

Voice states track pipeline progress:

```python
class VoiceState(Enum):
    IDLE = "idle"              # Listening for wake word
    LISTENING = "listening"    # User speaking
    RECORDING = "recording"    # Capturing audio
    PROCESSING = "processing"  # Running recognition/LLM
    SPEAKING = "speaking"      # Playing response
    WAKE_DETECTED = "wake_detected"  # Wake word recognized
```

State transitions via event bus:

```
IDLE → WAKE_DETECTED → LISTENING → RECORDING → PROCESSING → SPEAKING → IDLE
```

#### 3. **Concurrency Model**

- **Async/await**: All I/O operations non-blocking
- **Message queues**: Agent inbox/outbox pattern prevents race conditions
- **Single writer**: Memory agent prevents concurrent write conflicts
- **WebSocket streams**: Token-by-token delivery for responsiveness

#### 4. **Error Handling & Fallback**

- **Whisper unavailable**: Fallback to text-only mode (disable voice)
- **LLM timeout**: Return cached response or "I'm thinking..."
- **TTS failure**: Log error, return text response to WebSocket
- **Audio device failure**: Graceful degradation to terminal input

#### 5. **Performance Optimization**

- **Model warm-up**: Pre-load Whisper model at startup (eliminates first-request latency)
- **Streaming tokens**: Send LLM tokens immediately instead of waiting for complete response
- **Audio compression**: Optional - send PCM chunks directly over WebSocket
- **Caching**: Store common responses with voice synthesis cache

---

## Rationale

### Why This Architecture?

1. **Separation of Concerns**: Each stage handles specific responsibility (audio → text → context → speech)
2. **Scalability**: Async model allows handling multiple concurrent voice sessions
3. **Reliability**: Fallback mechanisms ensure system works even if components fail
4. **User Experience**: Real-time streaming (tokens + audio) creates responsive feel
5. **Resource Efficiency**: INT8 Whisper model + CPU-only reduces memory footprint

### Why These Technologies?

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| STT | Faster-Whisper | Local, offline-capable, fast inference |
| LLM | Ollama (qwen2:0.5b) | Local first, no API costs, offline capable |
| TTS | Edge-TTS | PT-BR native support, free, no key required |
| Audio Capture | sounddevice | Cross-platform, low latency |
| Real-time | WebSocket | Bidirectional streaming, low latency |

---

## Consequences

### Positive

✅ **Offline capability**: System works without internet (Ollama local)  
✅ **Low latency**: No network round-trips for core processing  
✅ **Privacy**: Audio processed locally, not sent to cloud APIs  
✅ **Cost**: No per-request API costs  
✅ **Scalability**: Async model handles concurrent sessions  

### Negative

❌ **Resource usage**: Requires 8GB+ RAM for Whisper + Ollama  
❌ **Setup complexity**: Multiple service dependencies (Ollama, Whisper model)  
❌ **Model limitations**: Ollama qwen2:0.5b smaller context than cloud APIs  
❌ **Response quality**: Local models less capable than GPT-4o for complex tasks  

### Mitigations

- Provide deployment guide for resource-constrained environments
- Implement fallback to cloud APIs (Claude, GPT-4o-mini) if Ollama unavailable
- Cache common responses to reduce processing overhead
- Allow model switching via configuration

---

## Alternatives Considered

### Alternative 1: Cloud-only (Azure Speech Services, Google Cloud Speech-to-Text)

**Pros**: High accuracy, native support for many languages  
**Cons**: Requires internet, incurs API costs, privacy concerns, high latency

**Decision**: ❌ Rejected - user wants offline-first, cost-effective solution

### Alternative 2: Hybrid (Local primary + Cloud fallback)

**Pros**: Best of both - local for privacy, cloud for quality  
**Cons**: Complex failover, inconsistent experiences, cost unpredictable

**Decision**: ✅ Partially Accepted - Ollama primary, Claude/GPT-4o-mini fallback for LLM only (not for STT/TTS)

### Alternative 3: Batch processing (Collect audio → Process → Respond)

**Pros**: Simpler implementation, better error handling  
**Cons**: High latency, poor user experience, no real-time streaming

**Decision**: ❌ Rejected - streaming model provides better UX

---

## Implementation Status

| Component | Status | Details |
|-----------|--------|---------|
| Audio capture | ✅ Complete | sounddevice integration |
| Whisper STT | ✅ Complete | Small INT8 model, pre-warmed |
| Ollama LLM | ✅ Complete | qwen2:0.5b with fallback chain |
| Edge-TTS | ✅ Complete | PT-BR with custom voice profile |
| WebSocket streaming | ✅ Complete | Token + audio chunk streaming |
| State management | ✅ Complete | Event bus driven state machine |
| Error handling | ✅ Complete | Graceful degradation + fallbacks |

---

## Monitoring & Metrics

Track pipeline health:

```python
# Latency metrics
voice_capture_latency      # Audio → Whisper
voice_recognition_latency  # Whisper → Text
voice_processing_latency   # Text → LLM response
voice_synthesis_latency    # Response → Audio
voice_total_latency        # End-to-end time

# Quality metrics
voice_recognition_accuracy    # Whisper correctness
voice_processing_success_rate # LLM success rate
voice_synthesis_success_rate  # TTS success rate
voice_concurrent_sessions     # Parallel voice sessions
```

---

## References

- [Whisper Architecture](https://github.com/openai/whisper)
- [Ollama Documentation](https://ollama.ai)
- [Edge-TTS GitHub](https://github.com/rany2/edge-tts)
- [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)

---

**Approved by**: JARVIS Development Team  
**Last Updated**: May 25, 2026
