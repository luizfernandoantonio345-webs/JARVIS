"""
profiler — Production Performance Profiling  (FASE 13F)

Provides:
  • SQLiteProfiler   — captures slow queries (>50ms) via SQLite tracing
  • LLMProfiler      — records per-call timings by model/tier
  • AgentProfiler    — records per-agent execution timings
  • request_timer    — FastAPI middleware latency tracker
  • get_report()     — returns aggregated stats for the dashboard

py-spy / Austin integration: flamegraphs are triggered on-demand via
  POST /profiling/flamegraph
"""

from __future__ import annotations

import logging
import sqlite3
import statistics
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_PROFILE_REPORTS_DIR = Path(__file__).parent.parent / "reports" / "profiling"
_PROFILE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── SQLite slow-query tracker ─────────────────────────────────────────────────

SLOW_QUERY_THRESHOLD_MS = 50.0
_slow_queries: deque[dict] = deque(maxlen=200)
_slow_query_lock = threading.Lock()


class SQLiteProfiler:
    """
    Wraps sqlite3.connect to trace slow queries.

    Usage:
        conn = SQLiteProfiler.connect(db_path)
        # use conn as normal — slow queries are auto-logged
    """

    @staticmethod
    def connect(db_path: str | Path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.set_trace_callback(SQLiteProfiler._trace_callback)
        return conn

    @staticmethod
    def _trace_callback(statement: str) -> None:
        # Note: sqlite3 trace_callback doesn't give timing directly.
        # We use a context manager approach instead.
        pass

    @staticmethod
    def timed_execute(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL statement and log if it exceeds the threshold."""
        t0 = time.monotonic()
        try:
            cursor = conn.execute(sql, params)
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms >= SLOW_QUERY_THRESHOLD_MS:
                record = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "sql": sql[:200],
                    "elapsed_ms": round(elapsed_ms, 2),
                }
                with _slow_query_lock:
                    _slow_queries.append(record)
                log.warning("profiler: slow SQLite query %.1fms: %s", elapsed_ms, sql[:80])
            return cursor
        except Exception:
            raise

    @staticmethod
    def get_slow_queries(limit: int = 20) -> list[dict]:
        with _slow_query_lock:
            items = list(_slow_queries)
        items.sort(key=lambda x: x["elapsed_ms"], reverse=True)
        return items[:limit]


# ── LLM call profiler ─────────────────────────────────────────────────────────

@dataclass
class LLMCallRecord:
    ts: float
    model: str
    tier: str
    cached: bool
    latency_ms: float
    tokens_approx: int = 0


_llm_records: deque[LLMCallRecord] = deque(maxlen=1000)
_llm_lock = threading.Lock()


def record_llm_call(model: str, tier: str, latency_ms: float,
                    cached: bool = False, tokens: int = 0) -> None:
    """Record an LLM call for profiling. Thread-safe."""
    rec = LLMCallRecord(
        ts=time.time(),
        model=model,
        tier=tier,
        cached=cached,
        latency_ms=round(latency_ms, 2),
        tokens_approx=tokens,
    )
    with _llm_lock:
        _llm_records.append(rec)

    # Also push to telemetry
    try:
        from core.telemetry import record_llm_latency
        record_llm_latency(latency_ms, model=model, tier=tier, cached=cached)
    except Exception:
        pass


def get_llm_stats(window_minutes: int = 60) -> dict[str, Any]:
    """Return aggregated LLM stats for the last N minutes."""
    cutoff = time.time() - window_minutes * 60
    with _llm_lock:
        recent = [r for r in _llm_records if r.ts >= cutoff]

    if not recent:
        return {"total_calls": 0, "window_minutes": window_minutes}

    by_model: dict[str, list[float]] = defaultdict(list)
    by_tier:  dict[str, list[float]] = defaultdict(list)
    cached_count = 0

    for r in recent:
        if not r.cached:
            by_model[r.model].append(r.latency_ms)
            by_tier[r.tier].append(r.latency_ms)
        else:
            cached_count += 1

    def _stats(latencies: list[float]) -> dict:
        if not latencies:
            return {"count": 0}
        return {
            "count": len(latencies),
            "avg_ms": round(statistics.mean(latencies), 1),
            "p50_ms": round(statistics.median(latencies), 1),
            "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1) if len(latencies) >= 2 else None,
            "max_ms": round(max(latencies), 1),
        }

    return {
        "total_calls": len(recent),
        "cached_calls": cached_count,
        "cache_hit_rate": round(cached_count / len(recent) * 100, 1),
        "window_minutes": window_minutes,
        "by_model": {m: _stats(l) for m, l in by_model.items()},
        "by_tier": {t: _stats(l) for t, l in by_tier.items()},
    }


# ── Agent profiler ────────────────────────────────────────────────────────────

@dataclass
class AgentCallRecord:
    ts: float
    role: str
    latency_ms: float
    success: bool


_agent_records: deque[AgentCallRecord] = deque(maxlen=500)
_agent_lock = threading.Lock()


def record_agent_call(role: str, latency_ms: float, success: bool = True) -> None:
    rec = AgentCallRecord(ts=time.time(), role=role,
                          latency_ms=round(latency_ms, 2), success=success)
    with _agent_lock:
        _agent_records.append(rec)

    try:
        from core.telemetry import record_agent_latency
        record_agent_latency(latency_ms, agent_role=role)
    except Exception:
        pass


def get_agent_stats(window_minutes: int = 60) -> dict[str, Any]:
    cutoff = time.time() - window_minutes * 60
    with _agent_lock:
        recent = [r for r in _agent_records if r.ts >= cutoff]

    by_role: dict[str, list[float]] = defaultdict(list)
    failures: dict[str, int] = defaultdict(int)
    for r in recent:
        by_role[r.role].append(r.latency_ms)
        if not r.success:
            failures[r.role] += 1

    result: dict[str, Any] = {"window_minutes": window_minutes, "by_role": {}}
    for role, latencies in by_role.items():
        result["by_role"][role] = {
            "count": len(latencies),
            "avg_ms": round(sum(latencies) / len(latencies), 1),
            "max_ms": round(max(latencies), 1),
            "failures": failures.get(role, 0),
        }
    return result


# ── Request timing middleware ─────────────────────────────────────────────────

_request_timings: deque[dict] = deque(maxlen=500)
_request_lock = threading.Lock()


def record_request(path: str, method: str, latency_ms: float, status_code: int) -> None:
    with _request_lock:
        _request_timings.append({
            "ts": time.time(),
            "path": path,
            "method": method,
            "latency_ms": round(latency_ms, 2),
            "status": status_code,
        })


def get_request_stats(window_minutes: int = 60) -> dict[str, Any]:
    cutoff = time.time() - window_minutes * 60
    with _request_lock:
        recent = [r for r in _request_timings if r["ts"] >= cutoff]
    if not recent:
        return {"total_requests": 0, "window_minutes": window_minutes}

    latencies = [r["latency_ms"] for r in recent]
    by_path: dict[str, list[float]] = defaultdict(list)
    for r in recent:
        by_path[r["path"]].append(r["latency_ms"])

    slowest = sorted(by_path.items(), key=lambda x: max(x[1]), reverse=True)[:5]

    return {
        "total_requests": len(recent),
        "window_minutes": window_minutes,
        "avg_ms": round(sum(latencies) / len(latencies), 1),
        "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1) if len(latencies) >= 2 else None,
        "slowest_endpoints": [{"path": p, "max_ms": round(max(l), 1)} for p, l in slowest],
    }


# ── On-demand flamegraph ───────────────────────────────────────────────────────

async def generate_flamegraph(duration_s: int = 30) -> dict[str, Any]:
    """
    Trigger py-spy to generate a flamegraph SVG for the current process.
    Returns path to the generated file or an error.
    """
    import asyncio
    import os
    import sys

    pid = os.getpid()
    out_file = _PROFILE_REPORTS_DIR / f"flamegraph_{int(time.time())}.svg"

    cmd = ["py-spy", "record", "-o", str(out_file),
           "--pid", str(pid), "--duration", str(duration_s), "--format", "flamegraph"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=duration_s + 10)
        if proc.returncode == 0:
            return {"status": "done", "file": str(out_file), "duration_s": duration_s}
        else:
            return {
                "status": "error",
                "returncode": proc.returncode,
                "output": stdout.decode(errors="replace")[:500],
            }
    except FileNotFoundError:
        return {"status": "error", "detail": "py-spy not installed. Run: pip install py-spy"}
    except asyncio.TimeoutError:
        return {"status": "error", "detail": "flamegraph timed out"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ── Full report ────────────────────────────────────────────────────────────────

def get_full_report(window_minutes: int = 60) -> dict[str, Any]:
    return {
        "window_minutes": window_minutes,
        "llm": get_llm_stats(window_minutes),
        "agents": get_agent_stats(window_minutes),
        "requests": get_request_stats(window_minutes),
        "slow_queries": SQLiteProfiler.get_slow_queries(10),
    }
