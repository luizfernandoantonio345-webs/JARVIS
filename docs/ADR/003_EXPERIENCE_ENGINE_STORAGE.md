# ADR-003: Experience Engine Storage & Memory Management

**Status**: Accepted  
**Date**: May 25, 2026  
**Participants**: JARVIS Development Team  

---

## Context

JARVIS v6.0 requires persistent memory of past interactions to:
- Learn user preferences over time
- Provide personalized responses
- Maintain conversation context across sessions
- Store decision history for continuous improvement
- Build experience database for pattern recognition

The system must handle:
- Fast reads for context injection (< 100ms)
- Reliable writes without data corruption
- Scalability (thousands of experience entries)
- Data retention policies (30-day default)
- Query capabilities (filter by date, topic, sentiment)

---

## Decision

Implement a **SQLite-based experience engine** with the following architecture:

```
┌──────────────────────────────────────────────────────────────────┐
│              EXPERIENCE ENGINE ARCHITECTURE                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  WRITE PATH (Save Experiences)                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ 1. User interaction (query + response)               │       │
│  │ 2. Extract metadata (intent, sentiment, duration)    │       │
│  │ 3. Create ExperienceEntry object                     │       │
│  │ 4. Validate & enrich with context                    │       │
│  │ 5. Write to SQLite (with retry logic)                │       │
│  │ 6. Broadcast event (Memory Agent watches)            │       │
│  └──────────────────────────────────────────────────────┘       │
│                         ↓                                        │
│                   data/jarvis_memory.db                         │
│                   (SQLite3 file)                               │
│                   Max: 500MB                                    │
│                   Retention: 30 days                            │
│                                                                  │
│  READ PATH (Inject Context)                                    │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ 1. LLM processing new query                          │       │
│  │ 2. Memory Agent: Query recent experiences            │       │
│  │    - Last 10 interactions (time window: last 7 days) │       │
│  │    - Similar topics (semantic similarity)            │       │
│  │    - High-value memories (sentiment > 0.7)          │       │
│  │ 3. Rank by relevance & recency                       │       │
│  │ 4. Format context string (max 1000 tokens)           │       │
│  │ 5. Inject into LLM system prompt                     │       │
│  └──────────────────────────────────────────────────────┘       │
│         ↓                                 ↓                      │
│    LLM Orchestrator                 Response generation        │
│    (Better personalized response)                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Database Schema

```sql
CREATE TABLE experiences (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_query TEXT NOT NULL,
    jarvis_response TEXT NOT NULL,
    
    -- Metadata
    intent TEXT,
    sentiment REAL,              -- -1.0 to +1.0
    duration_seconds REAL,
    
    -- Context
    session_id TEXT,
    language TEXT DEFAULT 'pt-BR',
    user_mood TEXT,
    location TEXT,
    
    -- Quality Metrics
    success BOOLEAN,
    user_satisfaction INTEGER,  -- 1-5 scale
    follow_up_count INTEGER,
    
    -- Search fields
    topics TEXT,                 -- JSON array
    tags TEXT,                   -- JSON array
    
    -- Lifecycle
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,         -- 30 days from created
    
    INDEX idx_timestamp (timestamp),
    INDEX idx_session_id (session_id),
    INDEX idx_intent (intent),
    INDEX idx_tags (tags)
);

CREATE TABLE preferences (
    user_id TEXT,
    key TEXT,
    value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT,              -- active, completed, archived
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    metadata TEXT              -- JSON
);
```

### Configuration (`.env`)

```env
# ────────────────────────────────────────────────────────────────
# MEMORY/EXPERIENCE ENGINE
# ────────────────────────────────────────────────────────────────
JARVIS_MEMORY_DB_PATH=data/jarvis_memory.db
JARVIS_MEMORY_MAX_SIZE=500MB
JARVIS_MEMORY_RETENTION_DAYS=30
JARVIS_MEMORY_CONTEXT_WINDOW=1000      # tokens for LLM context
JARVIS_MEMORY_RECENT_INTERACTIONS=10   # for context window
JARVIS_MEMORY_TIME_WINDOW_DAYS=7       # for recent experiences
JARVIS_MEMORY_ENABLE_VACUUM=true       # periodic defragmentation
```

### Implementation: Memory Agent

```python
# backend/agents/memory_agent.py

class MemoryAgent(Agent):
    """Centralized memory read/write for multi-agent system."""
    
    async def write_episodic_memory(
        self,
        user_query: str,
        jarvis_response: str,
        metadata: Dict = None
    ) -> ExperienceEntry:
        """Write user interaction to experience database."""
        
        entry = ExperienceEntry(
            id=generate_id(),
            timestamp=datetime.now(),
            user_query=user_query,
            jarvis_response=jarvis_response,
            **metadata
        )
        
        # Validate before write
        await self.validate_entry(entry)
        
        # Write to database (with retry)
        try:
            result = await self.db.insert(
                "experiences",
                entry.to_dict()
            )
            logger.info(f"✓ Memory written: {entry.id}")
            return entry
        except sqlite3.OperationalError:
            # Retry with exponential backoff
            await asyncio.sleep(0.1)
            return await self.write_episodic_memory(
                user_query, jarvis_response, metadata
            )
    
    async def query_context(
        self,
        current_query: str,
        limit: int = 10
    ) -> str:
        """Retrieve relevant context for LLM."""
        
        # 1. Find recent experiences
        recent = await self.db.query(
            f"""
            SELECT user_query, jarvis_response, sentiment
            FROM experiences
            WHERE timestamp > datetime('now', '-{config.TIME_WINDOW_DAYS} days')
            ORDER BY timestamp DESC
            LIMIT {limit}
            """
        )
        
        # 2. Calculate semantic similarity to current query
        similarities = []
        for exp in recent:
            sim = await self.semantic_similarity(
                current_query,
                exp['user_query']
            )
            similarities.append((exp, sim))
        
        # 3. Rank by relevance & recency
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # 4. Format context (max 1000 tokens)
        context_parts = []
        token_count = 0
        
        for exp, sim in similarities[:5]:  # Top 5 most relevant
            if token_count > config.CONTEXT_WINDOW:
                break
            
            text = f"[Similar: {sim:.0%}] Q: {exp['user_query']}\nA: {exp['jarvis_response']}\n\n"
            context_parts.append(text)
            token_count += len(text.split())
        
        return "\n".join(context_parts)
```

### Experience Write Flow

```python
# backend/routers/chat.py

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Chat endpoint with automatic memory integration."""
    
    # 1. Process user query
    response = await orchestrator.process(request.message)
    
    # 2. Create memory entry
    metadata = {
        "intent": response.intent,
        "sentiment": await analyze_sentiment(response.content),
        "duration_seconds": response.processing_time,
        "session_id": request.session_id,
        "success": response.success,
    }
    
    # 3. Write to experience engine (async, don't wait)
    asyncio.create_task(
        memory_agent.write_episodic_memory(
            user_query=request.message,
            jarvis_response=response.content,
            metadata=metadata
        )
    )
    
    return response
```

### Experience Read Flow (LLM Context Injection)

```python
# backend/services/llm_service.py

async def call_ollama_with_context(prompt: str) -> str:
    """Call Ollama with injected experience context."""
    
    # 1. Query relevant past experiences
    context = await memory_agent.query_context(prompt, limit=10)
    
    # 2. Prepare system prompt with context
    system_prompt = f"""You are JARVIS, a helpful AI assistant.
    
Based on past interactions with the user:

{context}

Please provide helpful, personalized responses."""
    
    # 3. Call Ollama with context-enhanced prompt
    response = await ollama_service.call_ollama(
        prompt=prompt,
        system=system_prompt,
        model=config.MODEL
    )
    
    return response
```

---

## Rationale

### Why SQLite?

| Criteria | SQLite | PostgreSQL | MongoDB |
|----------|--------|-----------|---------|
| Setup | ✅ Zero config | ❌ Requires server | ❌ Requires server |
| Offline | ✅ Works offline | ❌ Needs network | ❌ Needs network |
| Cost | ✅ Free | ✅ Free (OSS) | ✅ Free (OSS) |
| Scalability | ⚠️ Good for 1GB | ✅ Enterprise scale | ✅ Unlimited |
| Queries | ✅ SQL | ✅ SQL | ⚠️ NoSQL |
| Transactions | ✅ Yes | ✅ Yes | ⚠️ Limited |

**Decision**: SQLite wins for single-user, offline-first deployment

### Why This Schema?

- **Episodic memory**: Record user interactions with metadata
- **Preferences**: Store user customizations (voice speed, language, etc.)
- **Projects**: Track long-running tasks and goals
- **Flexible metadata**: JSON fields for extensibility

### Why 30-Day Retention?

- **Balance**: Enough data to learn patterns (~900 interactions)
- **Privacy**: Automatic data cleanup
- **Size control**: ~500MB max database keeps queries fast
- **Configurable**: Can be adjusted per deployment

---

## Consequences

### Positive

✅ **Offline operation**: No external database required  
✅ **Zero ops**: No server setup, monitoring, or backups needed (just file copy)  
✅ **Privacy**: Data stays on user's machine  
✅ **Personalization**: System learns and improves over time  
✅ **Transaction safety**: ACID guarantees prevent corruption  
✅ **Query flexibility**: SQL allows complex context retrieval  

### Negative

❌ **Single-writer limitation**: Can't scale beyond one instance easily  
❌ **File locking**: Database lock can cause brief write delays  
❌ **Schema migration**: Changing schema requires backup/restore  
❌ **Data export**: No native cloud sync (must be manual)  
❌ **Multi-device**: Each device has separate database  

### Mitigations

- Single-writer pattern enforced via Memory Agent
- Write retries with exponential backoff for lock conflicts
- Schema versioning in database metadata
- Backup scripts for regular file copy
- Sync script for multi-device scenarios (optional)

---

## Alternatives Considered

### Alternative 1: PostgreSQL (Distributed)

**Pros**: Multi-instance, cloud-ready, better scalability  
**Cons**: Setup complexity, requires server, cost, internet dependency

**Decision**: ❌ Rejected - overkill for single-user, conflicts with offline-first

### Alternative 2: Redis (In-memory cache only)

**Pros**: Fast, simple, good for caching  
**Cons**: Volatile (loses data on crash), no persistence by default

**Decision**: ❌ Rejected - need reliable persistent memory

### Alternative 3: File-based JSON (Simpler)

**Pros**: Human-readable, no schema, simple format  
**Cons**: Slow for large datasets, no query capabilities, prone to corruption

**Decision**: ❌ Rejected - performance suffers with many experiences

---

## Maintenance Tasks

### Weekly Maintenance

```bash
# Vacuum database (defragment, reclaim space)
sqlite3 data/jarvis_memory.db "VACUUM;"

# Analyze query performance
sqlite3 data/jarvis_memory.db "ANALYZE;"

# Check integrity
sqlite3 data/jarvis_memory.db "PRAGMA integrity_check;"
```

### Monthly Tasks

```bash
# Backup
cp data/jarvis_memory.db backups/jarvis_$(date +%Y%m%d).db

# Cleanup expired entries (older than 30 days)
sqlite3 data/jarvis_memory.db \
  "DELETE FROM experiences WHERE expires_at < datetime('now');"
```

### Monitoring Metrics

```python
memory_db_size_bytes        # Current database file size
memory_experience_count     # Total experience entries
memory_query_latency_ms     # Context query response time
memory_write_latency_ms     # Experience write latency
memory_lock_waits           # Database lock contentions
```

---

## Performance Characteristics

| Operation | Typical Time | Conditions |
|-----------|-------------|-----------|
| Write experience | 5-10ms | Indexed, < 500MB |
| Query context (10 items) | 20-30ms | Recent index hit |
| Analyze sentiment | 50-100ms | Depends on text length |
| Vacuum database | 2-5 seconds | Offline only |
| Full backup | < 1 second | Typical 100-200MB file |

---

## References

- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [SQLite JSON Functions](https://www.sqlite.org/json1.html)
- [Experience Sampling Method (ESM)](https://en.wikipedia.org/wiki/Experience_sampling_method)
- [Memory Consolidation in AI](https://arxiv.org/abs/2106.05151)

---

**Approved by**: JARVIS Development Team  
**Last Updated**: May 25, 2026
