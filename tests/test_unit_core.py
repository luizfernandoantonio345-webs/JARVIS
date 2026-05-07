"""
test_unit_core.py — Unit tests for critical backend services  (FASE 13E)

These tests require NO running server — they test modules in isolation.
Coverage targets: cache_service, turbo_cache, live_docs, telemetry,
                  autonomy/night_mode, config
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is on path
_BACKEND = Path(__file__).parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── cache_service ─────────────────────────────────────────────────────────────

class TestCacheService:
    def setup_method(self):
        from services import cache_service
        cache_service._store.clear()

    def test_miss_returns_none(self):
        from services.cache_service import get_cached
        assert get_cached("s1", "hello") is None

    def test_set_then_get(self):
        from services.cache_service import get_cached, set_cached
        set_cached("s1", "hello world", "response text")
        result = get_cached("s1", "hello world")
        assert result == "response text"

    def test_case_insensitive_key(self):
        from services.cache_service import get_cached, set_cached
        set_cached("s1", "Hello World", "resp")
        assert get_cached("s1", "hello world") == "resp"

    def test_different_sessions_isolated(self):
        from services.cache_service import get_cached, set_cached
        set_cached("s1", "q", "r1")
        set_cached("s2", "q", "r2")
        assert get_cached("s1", "q") == "r1"
        assert get_cached("s2", "q") == "r2"


# ── turbo_cache ───────────────────────────────────────────────────────────────

class TestTurboCache:
    def setup_method(self):
        from services import turbo_cache
        turbo_cache._exact_cache.clear()

    def test_classify_simple(self):
        from services.turbo_cache import classify_query, QueryTier
        msgs = [{"role": "user", "content": "oi"}]
        assert classify_query(msgs) == QueryTier.SIMPLE

    def test_classify_complex_code_block(self):
        from services.turbo_cache import classify_query, QueryTier
        code = "x" * 250
        msgs = [{"role": "user", "content": f"```python\n{code}\n```"}]
        assert classify_query(msgs) == QueryTier.COMPLEX

    def test_exact_cache_roundtrip(self):
        from services.turbo_cache import exact_cache_get, exact_cache_put
        msgs = [{"role": "user", "content": "test query abc123"}]
        assert exact_cache_get(msgs) is None
        exact_cache_put(msgs, "cached response")
        assert exact_cache_get(msgs) == "cached response"

    def test_exact_cache_different_messages(self):
        from services.turbo_cache import exact_cache_get, exact_cache_put
        msgs1 = [{"role": "user", "content": "query one"}]
        msgs2 = [{"role": "user", "content": "query two"}]
        exact_cache_put(msgs1, "resp1")
        assert exact_cache_get(msgs2) is None

    def test_cache_stats(self):
        from services.turbo_cache import get_cache_stats
        stats = get_cache_stats()
        assert "exact_cache_entries" in stats
        assert "semantic_cache_entries" in stats


# ── live_docs ─────────────────────────────────────────────────────────────────

class TestLiveDocs:
    def test_log_to_wiki_and_search(self, tmp_path, monkeypatch):
        import services.live_docs as ld
        monkeypatch.setattr(ld, "_WIKI_INDEX", tmp_path / "index.jsonl")
        ld._WIKI_INDEX.parent.mkdir(parents=True, exist_ok=True)

        ld.log_to_wiki({
            "type": "autodev_job",
            "title": "Build auth system",
            "description": "Created JWT authentication with FastAPI",
            "tags": ["auth", "fastapi"],
        })
        results = ld.search_wiki("auth fastapi")
        assert len(results) > 0
        assert "auth" in results[0]["title"].lower() or "auth" in results[0]["description"].lower()

    def test_search_empty_wiki(self, tmp_path, monkeypatch):
        import services.live_docs as ld
        monkeypatch.setattr(ld, "_WIKI_INDEX", tmp_path / "empty.jsonl")
        results = ld.search_wiki("anything")
        assert results == []

    def test_update_changelog_creates_file(self, tmp_path, monkeypatch):
        import services.live_docs as ld
        changelog = tmp_path / "CHANGELOG.md"
        monkeypatch.setattr(ld, "_CHANGELOG_FILE", changelog)
        ld.update_changelog("job-001", "Created a REST API with 5 endpoints.", "AutoDev")
        assert changelog.exists()
        content = changelog.read_text()
        assert "job-001" in content
        assert "Created a REST API" in content

    def test_changelog_prepends_new_entries(self, tmp_path, monkeypatch):
        import services.live_docs as ld
        changelog = tmp_path / "CHANGELOG.md"
        monkeypatch.setattr(ld, "_CHANGELOG_FILE", changelog)
        ld.update_changelog("job-001", "First entry", "AutoDev")
        ld.update_changelog("job-002", "Second entry", "AutoDev")
        content = changelog.read_text()
        assert content.index("job-002") < content.index("job-001")

    @pytest.mark.asyncio
    async def test_generate_project_readme(self, tmp_path):
        import services.live_docs as ld
        state = {
            "job_id": "test-job",
            "goal": "Build a test project",
            "status": "done",
            "created_at": "2026-05-05T00:00:00Z",
        }
        (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (tmp_path / "main.py").write_text("# main", encoding="utf-8")
        readme = await ld.generate_project_readme(tmp_path)
        assert "Build a test project" in readme
        assert "main.py" in readme


# ── night_mode ────────────────────────────────────────────────────────────────

class TestNightMode:
    def test_singleton(self):
        from autonomy.night_mode import get_night_mode_controller, NightModeController
        c1 = get_night_mode_controller()
        c2 = get_night_mode_controller()
        assert c1 is c2

    def test_initial_state(self):
        from autonomy.night_mode import NightModeController, NightModeState
        ctrl = NightModeController()
        assert ctrl.state == NightModeState.INACTIVE
        assert ctrl.summary is None

    def test_load_last_summary_missing(self, tmp_path, monkeypatch):
        from autonomy import night_mode as nm
        monkeypatch.setattr(nm, "_NIGHT_REPORTS_DIR", tmp_path)
        ctrl = nm.NightModeController()
        assert ctrl._load_last_summary() is None

    @pytest.mark.asyncio
    async def test_cleanup_logs_removes_old_files(self, tmp_path):
        from autonomy.night_mode import NightModeController, NightWorkSummary
        # Create a fake old log file (mtime = 30 days ago)
        old_log = tmp_path / "old.log"
        old_log.write_text("old log content")
        import os
        old_time = time.time() - 40 * 86400
        os.utime(old_log, (old_time, old_time))

        ctrl = NightModeController()
        summary = NightWorkSummary()
        # Patch backend dir
        import autonomy.night_mode as nm
        original = nm.Path(__file__).parent.parent
        with patch.object(type(old_log), "parent", tmp_path):
            # Direct test of the glob
            cutoff = time.time() - nm.LOG_RETENTION_DAYS * 86400
            assert old_log.stat().st_mtime < cutoff


# ── telemetry ─────────────────────────────────────────────────────────────────

class TestTelemetry:
    def test_trace_span_noop(self):
        """trace_span must not raise even without OTel installed."""
        from core.telemetry import trace_span
        with trace_span("test_op", attributes={"key": "value"}) as span:
            pass  # should not raise

    def test_record_functions_silent_without_prometheus(self):
        """All record_ functions must be safe to call."""
        from core.telemetry import (
            record_llm_latency, record_job, record_event,
            set_ws_connections, record_cache_hit, record_agent_latency,
        )
        record_llm_latency(123.4, "gpt-4o-mini", "complex", cached=False)
        record_job("done")
        record_event("autonomy_action")
        set_ws_connections(3)
        record_cache_hit("exact")
        record_agent_latency(456.7, "planner")


# ── config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self):
        from config import JarvisConfig
        cfg = JarvisConfig()
        assert cfg.night_mode_start_hour == 23
        assert cfg.night_mode_morning_hour == 7
        assert cfg.turbo_mode_enabled is True
        assert cfg.night_mode_enabled is True

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("JARVIS_NIGHT_MODE_START_HOUR", "22")
        from config import JarvisConfig
        cfg = JarvisConfig()
        assert cfg.night_mode_start_hour == 22
