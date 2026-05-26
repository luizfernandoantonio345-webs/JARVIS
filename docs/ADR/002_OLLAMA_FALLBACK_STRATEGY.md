# ADR-002: Ollama Fallback Strategy

**Status**: Accepted  
**Date**: May 25, 2026  
**Participants**: JARVIS Team  

---

## Context

JARVIS v6.0 is designed to run with **local Ollama models** as primary LLM, but requires handling scenarios where:
- Ollama service is not available / not running
- Model is not downloaded locally
- Ollama connection times out
- Network latency to Ollama is high
- User wants to use cloud-based LLMs for better quality

The system must:
- Detect Ollama availability gracefully
- Provide fallback options without crashing
- Allow manual switching between providers
- Maintain consistent response quality
- Handle partial failures (e.g., Ollama works but specific model missing)

---

## Decision

Implement a **three-tier fallback chain** with automatic detection and user configuration:

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM FALLBACK STRATEGY                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TIER 1: LOCAL OLLAMA (Primary)                                │
│  ┌────────────────────────────────────┐                        │
│  │ Ollama (http://127.0.0.1:11434)    │                        │
│  │ Model: qwen2:0.5b (default)        │                        │
│  │ Context: 2048 tokens               │                        │
│  │ Pros: Free, offline, fast          │                        │
│  │ Cons: Limited context, quality     │                        │
│  └────────────────────────────────────┘                        │
│                    ↓ (if fails)                                 │
│                                                                 │
│  TIER 2: LOCAL FALLBACK MODEL (Optional)                       │
│  ┌────────────────────────────────────┐                        │
│  │ Alternative Ollama Model           │                        │
│  │ e.g., mistral:latest or phi        │                        │
│  │ Pros: Still offline, more capable  │                        │
│  │ Cons: Requires second model        │                        │
│  └────────────────────────────────────┘                        │
│                    ↓ (if fails)                                 │
│                                                                 │
│  TIER 3: CLOUD PROVIDERS (External)                            │
│  ┌────────────────────────────────────┐                        │
│  │ Option A: Anthropic Claude         │                        │
│  │ - claude-3-haiku (fast, cost)      │                        │
│  │ - claude-3-opus (high quality)     │                        │
│  │                                    │                        │
│  │ Option B: OpenAI GPT               │                        │
│  │ - gpt-4o-mini (balanced)           │                        │
│  │ - gpt-4o (best quality)            │                        │
│  │                                    │                        │
│  │ Pros: Best quality, higher limits  │                        │
│  │ Cons: API keys required, cost      │                        │
│  └────────────────────────────────────┘                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Configuration Options

In `.env` file:

```env
# ────────────────────────────────────────────────────────────────
# PRIMARY: Ollama Local
# ────────────────────────────────────────────────────────────────
JARVIS_LLM_PROVIDER=ollama          # or 'anthropic' or 'openai'
JARVIS_OLLAMA_URL=http://127.0.0.1:11434
JARVIS_MODEL=qwen2:0.5b
JARVIS_MODEL_CONTEXT=2048
JARVIS_OLLAMA_TIMEOUT=15            # seconds

# ────────────────────────────────────────────────────────────────
# FALLBACK: Alternative Local Model
# ────────────────────────────────────────────────────────────────
JARVIS_FALLBACK_MODEL=mistral:latest
JARVIS_FALLBACK_ENABLED=true

# ────────────────────────────────────────────────────────────────
# FALLBACK: Cloud Providers (API Keys)
# ────────────────────────────────────────────────────────────────
JARVIS_ANTHROPIC_API_KEY=sk-ant-...
JARVIS_ANTHROPIC_MODEL=claude-3-haiku-20240307
JARVIS_ANTHROPIC_ENABLED=false      # Enable as fallback

JARVIS_OPENAI_API_KEY=sk-proj-...
JARVIS_OPENAI_MODEL=gpt-4o-mini
JARVIS_OPENAI_ENABLED=false         # Enable as fallback
```

### Implementation: LLM Service

```python
# backend/services/llm_service.py

async def call_llm(prompt: str, context: str = "") -> str:
    """Call LLM with automatic fallback chain."""
    
    # Tier 1: Try primary Ollama
    try:
        response = await call_ollama(prompt, context)
        logger.info(f"✓ Ollama response: {len(response)} chars")
        return response
    except OllamaConnectionError as e:
        logger.warning(f"⚠ Ollama unavailable: {e}")
    except OllamaTimeoutError as e:
        logger.warning(f"⚠ Ollama timeout: {e}")
    
    # Tier 2: Try fallback Ollama model (if configured)
    if config.FALLBACK_ENABLED:
        try:
            response = await call_ollama(
                prompt, context, 
                model=config.FALLBACK_MODEL
            )
            logger.warning(f"⚠ Using fallback model: {config.FALLBACK_MODEL}")
            return response
        except Exception as e:
            logger.warning(f"⚠ Fallback model failed: {e}")
    
    # Tier 3: Try cloud providers (if configured)
    
    # 3a. Anthropic Claude
    if config.ANTHROPIC_ENABLED and config.ANTHROPIC_API_KEY:
        try:
            response = await call_anthropic(prompt, context)
            logger.warning(f"⚠ Using Anthropic Claude fallback")
            return response
        except Exception as e:
            logger.warning(f"⚠ Anthropic failed: {e}")
    
    # 3b. OpenAI GPT
    if config.OPENAI_ENABLED and config.OPENAI_API_KEY:
        try:
            response = await call_openai(prompt, context)
            logger.warning(f"⚠ Using OpenAI GPT fallback")
            return response
        except Exception as e:
            logger.warning(f"⚠ OpenAI failed: {e}")
    
    # All providers failed
    logger.error("✗ All LLM providers exhausted")
    raise AllLLMProvidersFailed(
        "No LLM providers available. "
        "Please check Ollama or configure cloud API keys."
    )
```

### Health Check Integration

Monitor provider availability:

```python
# backend/services/watchdog_service.py

async def check_llm_health():
    """Check LLM provider availability."""
    
    health = {
        "ollama": await check_ollama_health(),
        "anthropic": await check_anthropic_health(),
        "openai": await check_openai_health(),
    }
    
    # Determine active provider
    active = None
    if health["ollama"]["ok"]:
        active = "ollama"
    elif health["anthropic"]["ok"]:
        active = "anthropic"
    elif health["openai"]["ok"]:
        active = "openai"
    
    return {
        "status": "ok" if active else "degraded",
        "active_provider": active,
        "providers": health
    }
```

---

## Rationale

### Why Three Tiers?

1. **Tier 1 (Local Ollama)**: Cost-free, offline, low latency - ideal for interactive use
2. **Tier 2 (Fallback Model)**: Allows graceful degradation within same provider
3. **Tier 3 (Cloud)**: Safety net for critical operations or when quality matters more than cost

### Why This Order?

- **Cost optimization**: Free → Free (alt model) → Paid
- **Latency**: Local → Local → Remote
- **Privacy**: Local → Local → External
- **Availability**: Most reliable first (typically local if running)

### Why Both Claude & GPT?

- **Claude (Anthropic)**: Better for reasoning, longer context, lower cost for haiku
- **GPT (OpenAI)**: Better for coding, reasoning, general knowledge
- **Belt-and-suspenders**: If one provider down, another available

---

## Consequences

### Positive

✅ **Resilience**: System continues working even if primary fails  
✅ **Flexibility**: Users choose cost vs. quality tradeoff  
✅ **Offline-first**: Default works without internet/API keys  
✅ **Cost control**: Free tier by default, opt-in for paid  
✅ **Graceful degradation**: Quality varies but no crashes  

### Negative

❌ **Complexity**: Multiple providers to manage and test  
❌ **Inconsistent results**: Responses vary by provider  
❌ **API costs**: Fallback to cloud can incur charges  
❌ **State management**: Must track which provider is active  
❌ **Latency variability**: Response times vary by provider  

### Mitigations

- Extensive logging of provider switches for debugging
- Fallback-triggered metrics/alerts for operations
- Configuration validation to catch missing API keys early
- Rate limiting on cloud provider calls to control costs
- User-facing message indicating which provider was used

---

## Alternatives Considered

### Alternative 1: Single Provider (Ollama only)

**Pros**: Simple, no external dependencies  
**Cons**: System unusable if Ollama not running, limits quality

**Decision**: ❌ Rejected - too fragile for production

### Alternative 2: Load Balancing (Round-robin across providers)

**Pros**: Better utilization of available capacity  
**Cons**: Inconsistent responses, complex cost management

**Decision**: ❌ Rejected - sequential fallback simpler and more predictable

### Alternative 3: Always use cloud (hybrid prefers cloud)

**Pros**: Consistent high quality  
**Cons**: No offline capability, high cost, requires internet

**Decision**: ❌ Rejected - conflicts with user's offline-first requirement

---

## Implementation Status

| Component | Status | Details |
|-----------|--------|---------|
| Ollama primary | ✅ Complete | qwen2:0.5b working |
| Fallback model detection | ✅ Complete | Auto-detects available models |
| Anthropic integration | ✅ Complete | claude-3-haiku fallback |
| OpenAI integration | ✅ Complete | gpt-4o-mini fallback |
| Health monitoring | ✅ Complete | Per-provider health checks |
| Fallback detection | ✅ Complete | Automatic on connection error |
| Cost tracking | ⚠️ Partial | Logs calls, needs billing integration |

---

## Cost Model

**Monthly costs** (estimate at 1000 chats/day):

| Scenario | Provider | Monthly Cost | Notes |
|----------|----------|-------------|-------|
| Local only | Ollama | $0 | Free (user runs Ollama) |
| With Claude fallback | Claude-3-haiku | ~$50 | ~20% fallback rate |
| With GPT fallback | GPT-4o-mini | ~$75 | ~20% fallback rate |
| Cloud-first | Claude Opus | ~$300+ | High quality, high cost |

---

## Monitoring Dashboard

Track provider usage:

```
LLM Provider Usage (Last 24h)
┌────────────────┬────────────┬──────────┐
│ Provider       │ Requests   │ Success% │
├────────────────┼────────────┼──────────┤
│ Ollama         │ 950        │ 98%      │
│ Claude         │ 45         │ 100%     │
│ GPT-4o-mini    │ 5          │ 100%     │
└────────────────┴────────────┴──────────┘

Cost Breakdown (Last 30d)
Ollama:    $0.00
Claude:    $2.35
GPT:       $0.15
Total:     $2.50
```

---

## Testing Strategy

```python
# tests/test_llm_fallback.py

async def test_ollama_fallback_to_claude():
    """Test automatic fallback from Ollama to Claude."""
    
    # Mock Ollama as down
    with patch('ollama_service.call_ollama') as mock_ollama:
        mock_ollama.side_effect = OllamaConnectionError()
        
        response = await call_llm("test prompt")
        
        # Verify Claude was called
        assert "claude" in response.metadata.provider

async def test_claude_fallback_to_openai():
    """Test fallback chain: Ollama → Claude → OpenAI."""
    
    # Mock both Ollama and Claude as down
    with patch('ollama_service.call_ollama') as mock_ollama, \
         patch('anthropic_service.call_anthropic') as mock_claude:
        mock_ollama.side_effect = OllamaConnectionError()
        mock_claude.side_effect = RateLimitError()
        
        response = await call_llm("test prompt")
        
        # Verify OpenAI was called
        assert "openai" in response.metadata.provider
```

---

## References

- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Anthropic Claude API](https://docs.anthropic.com)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Fallback Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)

---

**Approved by**: JARVIS Development Team  
**Last Updated**: May 25, 2026
