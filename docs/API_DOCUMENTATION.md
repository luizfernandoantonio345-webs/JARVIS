# JARVIS v6.0 — API Documentation

Complete REST & WebSocket API reference for JARVIS v6.0.

**Base URL**: `http://localhost:8000`  
**WebSocket URL**: `ws://localhost:8000/ws/jarvis`

---

## Table of Contents

1. [Health & Status](#health--status)
2. [Chat Endpoints](#chat-endpoints)
3. [Voice Endpoints](#voice-endpoints)
4. [Memory Endpoints](#memory-endpoints)
5. [Agent Endpoints](#agent-endpoints)
6. [WebSocket API](#websocket-api)
7. [Error Responses](#error-responses)

---

## Health & Status

### GET /health

Get system health status.

**Request**:
```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "ok",
  "version": "6.0",
  "timestamp": "2026-05-26T10:30:00Z",
  "components": {
    "backend": {"ok": true},
    "llm": {"ok": true},
    "memory": {"ok": true},
    "voice": {"ok": true}
  }
}
```

**Status Codes**:
- `200 OK` - System healthy
- `503 Service Unavailable` - Components failing

---

### GET /metrics

Get system metrics and performance data.

**Request**:
```bash
curl http://localhost:8000/metrics
```

**Response**:
```json
{
  "requests_total": 1250,
  "requests_per_second": 12.5,
  "average_response_time_ms": 145,
  "active_connections": 3,
  "memory_usage_mb": 512,
  "cpu_percent": 25
}
```

---

## Chat Endpoints

### POST /chat

Send a message to JARVIS and get a response.

**Request**:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the weather today?",
    "session_id": "user-session-123"
  }'
```

**Request Body**:
```json
{
  "message": "string (required)",
  "session_id": "string (optional)",
  "context": "string (optional)",
  "temperature": 0.7,
  "max_tokens": 500
}
```

**Response**:
```json
{
  "response": "The weather today is...",
  "intent": "weather_query",
  "confidence": 0.92,
  "processing_time_ms": 245,
  "session_id": "user-session-123"
}
```

**Parameters**:
- `message` (string, required): User input message
- `session_id` (string, optional): Unique session identifier for continuity
- `context` (string, optional): Additional context for better responses
- `temperature` (float, optional): LLM creativity (0.0-1.0), default 0.7
- `max_tokens` (int, optional): Maximum response length, default 500

**Status Codes**:
- `200 OK` - Response generated successfully
- `400 Bad Request` - Invalid parameters
- `429 Too Many Requests` - Rate limit exceeded (10 req/min per IP)
- `503 Service Unavailable` - LLM unavailable (fallback attempted)

---

### POST /chat/stream

Stream responses token-by-token (Server-Sent Events).

**Request**:
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me a story", "session_id": "user-1"}'
```

**Response** (Server-Sent Events):
```
data: {"token":"Once","type":"content"}
data: {"token":" upon","type":"content"}
data: {"token":" a","type":"content"}
data: {"token":" time","type":"content"}
data: {"metadata":{"intent":"story","confidence":0.95},"type":"complete"}
```

**Status Codes**:
- `200 OK` - Streaming started
- `400 Bad Request` - Invalid parameters
- `429 Too Many Requests` - Rate limit exceeded

---

## Voice Endpoints

### POST /tts

Convert text to speech (PT-BR).

**Request**:
```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Olá, bem-vindo ao JARVIS"}' \
  --output audio.mp3
```

**Request Body**:
```json
{
  "text": "string (required)",
  "voice": "pt-BR-AntonioNeural",
  "rate": "-12%",
  "pitch": "-15Hz"
}
```

**Response**:
```
[Binary audio data - MP3 format]
```

**Headers**:
```
Content-Type: audio/mpeg
Content-Length: 45234
```

**Parameters**:
- `text` (string, required): Text to synthesize
- `voice` (string, optional): Voice identifier, default "pt-BR-AntonioNeural"
- `rate` (string, optional): Speed adjustment, default "-12%"
- `pitch` (string, optional): Pitch adjustment, default "-15Hz"

**Status Codes**:
- `200 OK` - Audio generated
- `400 Bad Request` - Invalid text
- `503 Service Unavailable` - TTS service unavailable

---

### POST /tts-iron/tts

Synthesize speech with "Iron Man" voice profile (faster, lower pitch).

**Request**:
```bash
curl -X POST http://localhost:8000/tts-iron/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "I am JARVIS"}'
```

**Response**: Same as `/tts` endpoint (MP3 audio)

---

### GET /voice/config

Get current voice configuration.

**Request**:
```bash
curl http://localhost:8000/voice/config
```

**Response**:
```json
{
  "tts_voice": "pt-BR-AntonioNeural",
  "tts_rate": "-12%",
  "tts_pitch": "-15Hz",
  "stt_model": "small",
  "wake_word": "jarvis",
  "language": "pt-BR"
}
```

---

### PUT /voice/config

Update voice configuration.

**Request**:
```bash
curl -X PUT http://localhost:8000/voice/config \
  -H "Content-Type: application/json" \
  -d '{
    "tts_rate": "-5%",
    "tts_pitch": "0Hz",
    "wake_word": "alexa"
  }'
```

**Response**:
```json
{
  "status": "updated",
  "config": {...}
}
```

---

## Memory Endpoints

### GET /memory/health

Check memory service health.

**Request**:
```bash
curl http://localhost:8000/memory/health
```

**Response**:
```json
{
  "status": "healthy",
  "database_size_mb": 125.5,
  "experience_count": 2340,
  "last_backup": "2026-05-26T09:00:00Z"
}
```

---

### GET /memory/experiences

Query past experiences for context.

**Request**:
```bash
curl "http://localhost:8000/memory/experiences?limit=10&days=7"
```

**Query Parameters**:
- `limit` (int): Maximum results to return (default: 10)
- `days` (int): Look back N days (default: 7)
- `intent` (string): Filter by intent (optional)
- `sentiment` (float): Filter by sentiment threshold (optional)

**Response**:
```json
{
  "experiences": [
    {
      "id": "exp-2340",
      "timestamp": "2026-05-25T14:30:00Z",
      "user_query": "What time is it?",
      "jarvis_response": "It is 2:30 PM",
      "intent": "time_query",
      "sentiment": 0.5,
      "success": true
    }
  ],
  "count": 1,
  "total_available": 2340
}
```

**Status Codes**:
- `200 OK` - Experiences retrieved
- `400 Bad Request` - Invalid parameters
- `503 Service Unavailable` - Database unavailable

---

### POST /memory/preferences

Save user preference.

**Request**:
```bash
curl -X POST http://localhost:8000/memory/preferences \
  -H "Content-Type: application/json" \
  -d '{
    "key": "preferred_language",
    "value": "pt-BR"
  }'
```

**Response**:
```json
{
  "status": "saved",
  "key": "preferred_language",
  "value": "pt-BR"
}
```

---

### GET /memory/preferences/:key

Get user preference.

**Request**:
```bash
curl http://localhost:8000/memory/preferences/preferred_language
```

**Response**:
```json
{
  "key": "preferred_language",
  "value": "pt-BR"
}
```

---

## Agent Endpoints

### POST /agents/orchestrate

Request multi-agent orchestration for complex tasks.

**Request**:
```bash
curl -X POST http://localhost:8000/agents/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Create a detailed project plan for building a web API",
    "context": "We have 2 weeks"
  }'
```

**Request Body**:
```json
{
  "goal": "string (required)",
  "context": "string (optional)",
  "agents": ["planner", "executor", "critic"]
}
```

**Response**:
```json
{
  "status": "complete",
  "plan": "1. Design API schema\n2. Setup database\n3. Implement endpoints...",
  "tasks": [
    {"id": 1, "title": "Design API schema", "priority": "high"},
    {"id": 2, "title": "Setup database", "priority": "high"}
  ],
  "approval_rounds": 1,
  "processing_time_ms": 5234
}
```

---

### GET /agents/status

Get agent system status.

**Request**:
```bash
curl http://localhost:8000/agents/status
```

**Response**:
```json
{
  "agents": {
    "planner": {"status": "ready", "queue_size": 0},
    "executor": {"status": "ready", "queue_size": 0},
    "critic": {"status": "ready", "queue_size": 0},
    "memory": {"status": "ready", "queue_size": 0}
  },
  "message_bus": {"status": "operational", "messages_processed": 15234}
}
```

---

## WebSocket API

### Connection

Connect to WebSocket for real-time communication:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/jarvis');

ws.onopen = () => {
    console.log('Connected to JARVIS');
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log('Received:', message);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('Disconnected from JARVIS');
};
```

### Message Protocol

#### Send Chat Message

```json
{
  "type": "message",
  "data": "Hello JARVIS",
  "session_id": "user-session-123"
}
```

#### Receive Response Stream

```json
{
  "type": "response_token",
  "data": "Hello",
  "index": 0
}
```

```json
{
  "type": "response_complete",
  "data": {
    "full_response": "Hello, how can I help you?",
    "intent": "greeting",
    "confidence": 0.95
  }
}
```

#### Audio Streaming

Send audio chunks for voice input:

```json
{
  "type": "audio_chunk",
  "data": "base64_encoded_audio_chunk"
}
```

Receive synthesized audio:

```json
{
  "type": "audio_output",
  "data": "base64_encoded_audio_chunk"
}
```

#### State Changes

Receive voice state updates:

```json
{
  "type": "state_change",
  "data": {
    "state": "LISTENING",
    "timestamp": "2026-05-26T10:30:00Z"
  }
}
```

Possible states:
- `IDLE` - Listening for wake word
- `LISTENING` - User speaking
- `RECORDING` - Capturing audio
- `PROCESSING` - Running recognition/LLM
- `SPEAKING` - Playing response
- `WAKE_DETECTED` - Wake word recognized

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Error title",
  "message": "Detailed error message",
  "code": "ERROR_CODE",
  "timestamp": "2026-05-26T10:30:00Z"
}
```

### Common Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `INVALID_REQUEST` | 400 | Invalid request parameters |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests (10/minute) |
| `AUTHENTICATION_FAILED` | 401 | Invalid or missing session |
| `LLM_UNAVAILABLE` | 503 | LLM service not responding |
| `DATABASE_ERROR` | 503 | Database connection failed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### Example Error Response

```json
{
  "error": "Rate limit exceeded",
  "message": "You have exceeded the rate limit of 10 requests per minute",
  "code": "RATE_LIMIT_EXCEEDED",
  "timestamp": "2026-05-26T10:30:00Z",
  "retry_after_seconds": 45
}
```

---

## Authentication

Currently, JARVIS uses session-based authentication via `session_id`.

For future OAuth integration, include Authorization header:

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/chat
```

---

## Rate Limiting

- **Limit**: 10 requests per minute per IP
- **Headers**: 
  - `X-RateLimit-Limit: 10`
  - `X-RateLimit-Remaining: 7`
  - `X-RateLimit-Reset: 1685094600`

---

## Pagination

List endpoints support pagination:

```bash
curl "http://localhost:8000/memory/experiences?limit=20&offset=40"
```

**Parameters**:
- `limit`: Items per page (default: 10, max: 100)
- `offset`: Starting position (default: 0)

---

## Testing

### Using curl

```bash
# Test health
curl http://localhost:8000/health | jq

# Send chat message
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}' | jq

# Stream chat response
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me something"}' \
  --no-buffer
```

### Using Python

```python
import httpx
import asyncio

async def test_api():
    async with httpx.AsyncClient() as client:
        # Health check
        resp = await client.get("http://localhost:8000/health")
        print(resp.json())
        
        # Chat
        resp = await client.post(
            "http://localhost:8000/chat",
            json={"message": "Hello"}
        )
        print(resp.json())

asyncio.run(test_api())
```

### Using JavaScript

```javascript
// Health check
fetch('http://localhost:8000/health')
  .then(r => r.json())
  .then(d => console.log(d));

// Chat
fetch('http://localhost:8000/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message: 'Hello'})
})
.then(r => r.json())
.then(d => console.log(d));
```

---

## Support

- **Documentation**: `/docs` (auto-generated Swagger UI)
- **GitHub**: https://github.com/cibernetico/JARVIS
- **Issues**: https://github.com/cibernetico/JARVIS/issues

**Last Updated**: May 26, 2026  
**Version**: 6.0
