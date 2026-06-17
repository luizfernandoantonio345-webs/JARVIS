"""
Memory service — three semantic tiers:

  Tier 1 · Episodic   — individual message/response pairs (existing)
  Tier 2 · Preference — extracted user preferences (language, style, stack, etc.)
  Tier 3 · Project    — long-lived project context (goals, tech, constraints)

All three tiers store embeddings and support cosine similarity retrieval.
"""

import logging
import math
import sqlite3
import struct
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from config import get_config

log = logging.getLogger(__name__)

DB_PATH              = get_config().memory_db_path
LOCAL_EMBED_MODEL    = "nomic-embed-text"
_EMBED_DIM_FALLBACK  = 256
_lock                = threading.Lock()

# ── Scoring constants ──────────────────────────────────────────────────────────
SCORE_DECAY_PER_DAY = 0.97   # effective_score = base_score * decay^days_elapsed
SCORE_THRESHOLD     = 0.60   # entries below this are excluded from context
MIN_EFFECTIVE_SCORE = 0.20   # entries below this are pruned from the episodic table
CONTEXT_LIMIT       = 5      # max items injected into a single prompt
SCORE_BOOST_ON_USE  = 0.10   # base_score += this when an entry is retrieved
_VACUUM_EVERY       = 20     # vacuum stale memories after this many saves
_save_counter       = 0


# ── DB bootstrap ───────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)

    # WAL mode: faster concurrent reads, no reader/writer blocking
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")   # safe with WAL; faster than FULL
    conn.execute("PRAGMA cache_size=-8000")     # 8 MB page cache
    conn.execute("PRAGMA mmap_size=134217728")  # 128 MB memory-mapped I/O
    conn.execute("PRAGMA busy_timeout=5000")    # wait up to 5s instead of failing immediately

    # Tier 1 — episodic memory
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL,
            message    TEXT    NOT NULL,
            response   TEXT    NOT NULL,
            action     TEXT    DEFAULT 'chat',
            embedding  BLOB,
            score      REAL    DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON memory(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_score ON memory(score)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_created ON memory(created_at)")

    # Tier 2 — user preferences
    conn.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL,
            key        TEXT    NOT NULL,
            value      TEXT    NOT NULL,
            embedding  BLOB,
            score      REAL    DEFAULT 1.0,
            confidence REAL    DEFAULT 0.85,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pref_session ON preferences(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pref_confidence ON preferences(confidence)")

    # Tier 3 — project context
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_context (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL,
            name       TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            embedding  BLOB,
            score      REAL    DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_proj_session ON project_context(session_id)")

    # Tier 4 — failure memory (cross-job, shared pattern tracking)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS failures (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT    NOT NULL,
            step_type     TEXT    NOT NULL,
            goal_hash     TEXT    NOT NULL,
            goal_snippet  TEXT    NOT NULL,
            strategy      TEXT    NOT NULL DEFAULT '',
            error_snippet TEXT    NOT NULL DEFAULT '',
            attempts      INTEGER NOT NULL DEFAULT 1,
            resolved      INTEGER NOT NULL DEFAULT 0,
            embedding     BLOB,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fail_session ON failures(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fail_type_hash ON failures(step_type, goal_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fail_resolved ON failures(resolved)")

    conn.commit()
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add score/confidence columns to existing tables (idempotent)."""
    for sql in [
        "ALTER TABLE memory ADD COLUMN score REAL DEFAULT 1.0",
        "ALTER TABLE preferences ADD COLUMN score REAL DEFAULT 1.0",
        "ALTER TABLE preferences ADD COLUMN confidence REAL DEFAULT 0.85",
        "ALTER TABLE project_context ADD COLUMN score REAL DEFAULT 1.0",
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


def _effective_score(base_score: float, ts_str: str) -> float:
    """Compute time-decayed score: base_score * DECAY_PER_DAY ^ days_elapsed."""
    try:
        ts   = datetime.fromisoformat(ts_str)
        days = max(0.0, (datetime.utcnow() - ts).total_seconds() / 86400)
        return base_score * (SCORE_DECAY_PER_DAY ** days)
    except Exception:
        return base_score


def _boost_score(table: str, row_id: int) -> None:
    """Increment base_score when an entry is retrieved (capped at 1.0)."""
    with _lock:
        _conn.execute(
            f"UPDATE {table} SET score = MIN(1.0, score + ?) WHERE id = ?",
            (SCORE_BOOST_ON_USE, row_id),
        )
        _conn.commit()


def _vacuum() -> None:
    """Remove episodic entries whose effective score dropped below MIN_EFFECTIVE_SCORE."""
    rows  = _conn.execute("SELECT id, score, created_at FROM memory").fetchall()
    stale = [r[0] for r in rows if _effective_score(r[1] or 1.0, r[2] or "2000-01-01") < MIN_EFFECTIVE_SCORE]
    if stale:
        _conn.execute(f"DELETE FROM memory WHERE id IN ({','.join('?'*len(stale))})", stale)
        _conn.commit()
        log.info("Vacuumed %d stale memory entries", len(stale))


_conn = _get_conn()


# ── Embedding ──────────────────────────────────────────────────────────────────

def _embed_ollama(text: str) -> list[float]:
    from ai.client import get_ai_client
    return get_ai_client().embed(text)


def _embed_fallback(text: str) -> list[float]:
    tokens = text.lower().split()
    vec    = [0.0] * _EMBED_DIM_FALLBACK
    for tok in tokens:
        idx     = hash(tok) % _EMBED_DIM_FALLBACK
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _embed(text: str) -> list[float]:
    try:
        vec = _embed_ollama(text)
        if not vec:
            log.warning("Embedding returned empty list — using fallback")
            return _embed_fallback(text)
        return vec
    except Exception as exc:
        log.warning("Ollama embedding failed (%s) — using fallback", exc)
        return _embed_fallback(text)


def _vec_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


# ── Similarity ─────────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    denom  = norm_a * norm_b
    return dot / denom if denom else 0.0


# ── Tier 1 — Episodic memory ───────────────────────────────────────────────────

def save_memory(
    session_id: str,
    message: str,
    response: str,
    action: str = "chat",
) -> None:
    global _save_counter
    vec  = _embed(message)
    blob = _vec_to_blob(vec)
    with _lock:
        _conn.execute(
            "INSERT INTO memory (session_id, message, response, action, embedding) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, message, response, action, blob),
        )
        _conn.commit()
    _save_counter += 1
    if _save_counter >= _VACUUM_EVERY:
        _save_counter = 0
        threading.Thread(target=_vacuum, daemon=True, name="memory-vacuum").start()


def get_relevant_memory(
    session_id: str,
    query: str,
    limit: int = 5,
) -> List[Tuple[str, str]]:
    query_vec = _embed(query)
    cursor    = _conn.execute(
        "SELECT id, message, response, embedding, score, created_at "
        "FROM memory WHERE session_id = ?",
        (session_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        return []

    candidates: list[tuple[float, int, str, str]] = []
    for row_id, msg, resp, blob, base_score, ts in rows:
        if not blob:
            continue
        eff = _effective_score(base_score or 1.0, ts or "2000-01-01")
        if eff < SCORE_THRESHOLD:
            continue
        combined = _cosine(query_vec, _blob_to_vec(blob)) * eff
        candidates.append((combined, row_id, msg, resp))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:limit]
    for _, row_id, _, _ in top:
        _boost_score("memory", row_id)

    return [(msg, resp) for _, _, msg, resp in top]


def get_memory(session_id: str, limit: int = 5) -> List[Tuple[str, str]]:
    """Recency-based retrieval — backward compat."""
    cursor = _conn.execute(
        "SELECT message, response FROM memory "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    )
    return list(reversed(cursor.fetchall()))


# ── Tier 2 — User preferences ──────────────────────────────────────────────────

def set_preference(session_id: str, key: str, value: str, confidence: float = 0.85) -> None:
    """
    Upsert a user preference.
    Conflict resolution: only overwrites if new confidence >= stored confidence.
    Score is boosted on each confirmed update.
    """
    blob = _vec_to_blob(_embed(f"{key}: {value}"))
    with _lock:
        _conn.execute(
            """INSERT INTO preferences (session_id, key, value, embedding, score, confidence, updated_at)
               VALUES (?, ?, ?, ?, 1.0, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(session_id, key) DO UPDATE SET
                 value=excluded.value,
                 embedding=excluded.embedding,
                 score=MIN(1.0, preferences.score + ?),
                 confidence=excluded.confidence,
                 updated_at=CURRENT_TIMESTAMP
               WHERE excluded.confidence >= preferences.confidence""",
            (session_id, key, value, blob, confidence, SCORE_BOOST_ON_USE),
        )
        _conn.commit()
    log.debug("Preference set [session=%s] %r = %r (conf=%.2f)", session_id, key, value, confidence)


def get_preferences(session_id: str) -> dict[str, str]:
    """Return all preferences for a session as a plain dict."""
    cursor = _conn.execute(
        "SELECT key, value FROM preferences WHERE session_id = ? ORDER BY key",
        (session_id,),
    )
    return dict(cursor.fetchall())


def get_relevant_preferences(
    session_id: str,
    query: str,
    limit: int = 5,
) -> dict[str, str]:
    """Return preferences most relevant to query, filtered by effective score."""
    query_vec = _embed(query)
    cursor    = _conn.execute(
        "SELECT id, key, value, embedding, score, updated_at FROM preferences WHERE session_id = ?",
        (session_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        return {}

    candidates: list[tuple[float, int, str, str]] = []
    for row_id, key, value, blob, base_score, ts in rows:
        if not blob:
            continue
        eff = _effective_score(base_score or 1.0, ts or "2000-01-01")
        if eff < SCORE_THRESHOLD:
            continue
        combined = _cosine(query_vec, _blob_to_vec(blob)) * eff
        candidates.append((combined, row_id, key, value))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:limit]
    for _, row_id, _, _ in top:
        _boost_score("preferences", row_id)

    return {k: v for _, _, k, v in top}


# ── Tier 3 — Project context ───────────────────────────────────────────────────

def set_project_context(session_id: str, name: str, content: str) -> None:
    """
    Upsert a named project context entry.
    Examples: name="stack", content="Python + FastAPI + PostgreSQL"
              name="goals", content="Build a real-time trading dashboard"
    """
    blob = _vec_to_blob(_embed(f"{name}: {content}"))
    with _lock:
        _conn.execute(
            """INSERT INTO project_context (session_id, name, content, embedding, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(session_id, name) DO UPDATE SET
                 content=excluded.content,
                 embedding=excluded.embedding,
                 updated_at=CURRENT_TIMESTAMP""",
            (session_id, name, content, blob),
        )
        _conn.commit()
    log.debug("Project context set [session=%s] %r", session_id, name)


def get_project_context(session_id: str) -> dict[str, str]:
    """Return all project context entries for a session."""
    cursor = _conn.execute(
        "SELECT name, content FROM project_context WHERE session_id = ? ORDER BY name",
        (session_id,),
    )
    return dict(cursor.fetchall())


def get_relevant_project_context(
    session_id: str,
    query: str,
    limit: int = 3,
) -> dict[str, str]:
    """Return project context entries most relevant to query, filtered by effective score."""
    query_vec = _embed(query)
    cursor    = _conn.execute(
        "SELECT id, name, content, embedding, score, updated_at FROM project_context WHERE session_id = ?",
        (session_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        return {}

    candidates: list[tuple[float, int, str, str]] = []
    for row_id, name, content, blob, base_score, ts in rows:
        if not blob:
            continue
        eff = _effective_score(base_score or 1.0, ts or "2000-01-01")
        if eff < SCORE_THRESHOLD:
            continue
        combined = _cosine(query_vec, _blob_to_vec(blob)) * eff
        candidates.append((combined, row_id, name, content))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:limit]
    for _, row_id, _, _ in top:
        _boost_score("project_context", row_id)

    return {n: c for _, _, n, c in top}


# ── Context builders ───────────────────────────────────────────────────────────

# Per-task tier budgets: (episodic_items, preference_items, project_items).
# The sum across all three must not exceed CONTEXT_LIMIT.
_TASK_TIERS: dict[str, tuple[int, int, int]] = {
    "run":            (2, 0, 1),  # code exec: recent examples + stack, skip style prefs
    "analyze":        (2, 1, 2),  # code analysis: project-context heavy
    "arch":           (1, 1, 3),  # architecture: project context dominates
    "explain":        (2, 2, 1),  # explanations: verbosity/language prefs matter
    "refactor":       (2, 1, 2),  # refactor: project style + examples
    "web_search":     (1, 1, 1),  # external lookup: minimal context
    "file_reader":    (1, 1, 1),  # file ops: minimal context
    "system_monitor": (0, 0, 0),  # sysmon: no context needed
    "chat":           (2, 2, 1),  # general: balanced
}
_DEFAULT_TIERS: tuple[int, int, int] = (2, 2, 1)


def build_context_for_task(session_id: str, query: str, task_type: str = "chat") -> str:
    """
    Build a prompt-ready context string capped at CONTEXT_LIMIT items total.

    Selects entries across all three memory tiers based on task_type.
    Only includes entries with effective_score > SCORE_THRESHOLD.
    Accessing entries boosts their base_score (reinforces useful memories).
    """
    ep_limit, pref_limit, proj_limit = _TASK_TIERS.get(task_type, _DEFAULT_TIERS)
    parts: list[str] = []
    used  = 0

    if pref_limit > 0:
        prefs = get_relevant_preferences(session_id, query, limit=pref_limit)
        if prefs:
            parts.append("User preferences:\n" + "\n".join(f"  {k}: {v}" for k, v in prefs.items()))
            used += len(prefs)

    if proj_limit > 0 and used < CONTEXT_LIMIT:
        proj = get_relevant_project_context(
            session_id, query, limit=min(proj_limit, CONTEXT_LIMIT - used)
        )
        if proj:
            parts.append("Project context:\n" + "\n".join(f"  {n}: {c}" for n, c in proj.items()))
            used += len(proj)

    if ep_limit > 0 and used < CONTEXT_LIMIT:
        episodes = get_relevant_memory(
            session_id, query, limit=min(ep_limit, CONTEXT_LIMIT - used)
        )
        if episodes:
            parts.append(
                "Relevant past interactions:\n"
                + "\n".join(f"  Q: {m}\n  A: {r[:200]}" for m, r in episodes)
            )

    return "\n\n".join(parts)


def build_context_block(session_id: str, query: str) -> str:
    """Backward-compatible alias — delegates to build_context_for_task(task_type='chat')."""
    return build_context_for_task(session_id, query, task_type="chat")


# ── Admin ──────────────────────────────────────────────────────────────────────

def get_session_list() -> List[dict]:
    cursor = _conn.execute(
        """SELECT session_id, COUNT(*) as turns, MAX(created_at) as last_seen
           FROM memory GROUP BY session_id ORDER BY last_seen DESC LIMIT 20"""
    )
    return [{"session_id": r[0], "turns": r[1], "last_seen": r[2]} for r in cursor.fetchall()]


def clear_memory(session_id: str) -> None:
    with _lock:
        _conn.execute("DELETE FROM memory WHERE session_id = ?", (session_id,))
        _conn.execute("DELETE FROM preferences WHERE session_id = ?", (session_id,))
        _conn.execute("DELETE FROM project_context WHERE session_id = ?", (session_id,))
        _conn.commit()


# ── Failure memory (Tier 4) ────────────────────────────────────────────────────

import hashlib as _hashlib

def record_failure(
    session_id: str,
    step_type: str,
    goal: str,
    strategy: str,
    error_snippet: str,
    attempts: int,
) -> int:
    """
    Persist a failed step for future avoidance.
    Returns the new failure row id.
    """
    goal_hash = _hashlib.sha1(goal.encode()).hexdigest()[:16]
    goal_snippet = goal[:200]
    emb: bytes | None = None
    try:
        emb = _vec_to_blob(_embed(goal))
    except Exception as exc:
        log.debug("record_failure: embedding skipped", exc_info=exc)

    with _lock:
        cur = _conn.execute(
            """
            INSERT INTO failures
                (session_id, step_type, goal_hash, goal_snippet, strategy,
                 error_snippet, attempts, resolved, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (session_id, step_type, goal_hash, goal_snippet,
             strategy, error_snippet[:500], attempts, emb),
        )
        _conn.commit()
    return cur.lastrowid


def resolve_failure(failure_id: int) -> None:
    """Mark a previously recorded failure as resolved (succeeded on retry)."""
    with _lock:
        _conn.execute(
            "UPDATE failures SET resolved = 1 WHERE id = ?",
            (failure_id,),
        )
        _conn.commit()


def get_known_failures(
    session_id: str,
    step_type: str,
    goal: str,
    limit: int = 5,
) -> list[dict]:
    """
    Return unresolved failures whose goal is semantically similar to *goal*.
    Falls back to hash + keyword match when embeddings are unavailable.
    """
    goal_hash = _hashlib.sha1(goal.encode()).hexdigest()[:16]

    # Fast path: exact hash match
    rows = _conn.execute(
        """
        SELECT id, step_type, goal_snippet, strategy, error_snippet, attempts, created_at
        FROM   failures
        WHERE  resolved = 0 AND step_type = ? AND goal_hash = ?
        ORDER  BY created_at DESC
        LIMIT  ?
        """,
        (step_type, goal_hash, limit),
    ).fetchall()

    if not rows:
        # Semantic fallback: compare embeddings
        try:
            q_emb = _embed(goal)
            cand = _conn.execute(
                """
                SELECT id, step_type, goal_snippet, strategy, error_snippet,
                       attempts, created_at, embedding
                FROM   failures
                WHERE  resolved = 0 AND step_type = ? AND embedding IS NOT NULL
                ORDER  BY created_at DESC
                LIMIT  50
                """,
                (step_type,),
            ).fetchall()
            scored: list[tuple[float, tuple]] = []
            for r in cand:
                r_emb = _blob_to_vec(r[7])
                sim = _cosine(q_emb, r_emb)
                if sim >= 0.75:
                    scored.append((sim, r[:7]))
            scored.sort(key=lambda x: x[0], reverse=True)
            rows = [s[1] for s in scored[:limit]]
        except Exception as exc:
            log.debug("get_known_failures: semantic search skipped", exc_info=exc)

    return [
        {
            "id":            r[0],
            "step_type":     r[1],
            "goal_snippet":  r[2],
            "strategy":      r[3],
            "error_snippet": r[4],
            "attempts":      r[5],
            "created_at":    r[6],
        }
        for r in rows
    ]


def get_recent_failures(limit: int = 20) -> list[dict]:
    """Admin: all recent unresolved failures across sessions."""
    rows = _conn.execute(
        """
        SELECT id, session_id, step_type, goal_snippet, strategy,
               error_snippet, attempts, resolved, created_at
        FROM   failures
        ORDER  BY created_at DESC
        LIMIT  ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id":            r[0],
            "session_id":    r[1],
            "step_type":     r[2],
            "goal_snippet":  r[3],
            "strategy":      r[4],
            "error_snippet": r[5],
            "attempts":      r[6],
            "resolved":      bool(r[7]),
            "created_at":    r[8],
        }
        for r in rows
    ]


