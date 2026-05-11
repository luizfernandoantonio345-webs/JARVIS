"""
JARVIS Core Orchestrator — Single Entry Point (v2, optimized)
=============================================================
ALL inputs (voice, API, autonomy, agent calls) flow through here.

Optimized pipeline:
  Input
  → Cache Check           (intent + memory query cache — zero latency on hit)
  → Memory Injection      (async, parallel where possible)
  → Pre-LLM Fast Path     (rule-based, no LLM cost for simple intents)
  → LLM Intent Decision   (only when fast-path misses)
  → Risk Engine
  → Confirmation Gate
  → Tool Execution        (isolated, with retry + timeout)
  → Behavior Logger       (async, non-blocking)
  → Memory Writer         (async, non-blocking, dedup-guarded)
  → Autonomy Analyzer     (async, non-blocking)
  → UX Response Formatter
  → Output
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from core.intent_cache import cache_get, cache_put, fast_path_intent
from core.logger import log_error, log_execution, log_intent, log_memory, log_system
from core.risk_engine import RiskDecision, evaluate_risk
from intents.intent_parser import parse_intent
from intents.schemas import Intent
from memory_v2.memory_manager import get_context, store_memory


# ── Public API ─────────────────────────────────────────────────────────────────

class OrchestratorResult:
    """Serialisable result returned by the orchestrator."""

    __slots__ = ("session_id", "input_text", "intent", "risk", "executed",
                 "output", "errors", "elapsed_ms", "suggestions", "stage_timings",
                 "cache_hit", "source")

    def __init__(
        self,
        session_id: str,
        input_text: str,
        intent: Intent | None,
        risk: RiskDecision,
        executed: bool,
        output: str,
        errors: list[str],
        elapsed_ms: float,
        suggestions: list[str],
        stage_timings: dict[str, float] | None = None,
        cache_hit: bool = False,
        source: str = "api",
    ) -> None:
        self.session_id = session_id
        self.input_text = input_text
        self.intent = intent
        self.risk = risk
        self.executed = executed
        self.output = output
        self.errors = errors
        self.elapsed_ms = elapsed_ms
        self.suggestions = suggestions
        self.stage_timings = stage_timings or {}
        self.cache_hit = cache_hit
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        from core.system_mode import format_response  # noqa: PLC0415
        meta: dict[str, Any] = {
            "session_id": self.session_id,
            "intent": self.intent.model_dump() if self.intent else None,
            "risk": self.risk.value,
            "executed": self.executed,
            "errors": self.errors,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "suggestions": self.suggestions,
            "stage_timings": self.stage_timings,
            "cache_hit": self.cache_hit,
            "source": self.source,
        }
        return format_response(output=self.output, metadata=meta)


class CoreOrchestrator:
    """
    Singleton-friendly orchestrator. Instantiate once at startup.
    """

    def __init__(self) -> None:
        self._autonomy_v2: Any = None
        log_system("CoreOrchestrator initialised")

    def set_autonomy_v2(self, manager: Any) -> None:
        """Inject AutonomyManager after boot to avoid circular imports."""
        self._autonomy_v2 = manager

    # ── Main entry point ───────────────────────────────────────────────────────

    async def process(
        self,
        user_input: str,
        *,
        session_id: str | None = None,
        source: str = "api",
        history: list[dict] | None = None,
        force_chat: bool = False,
        force_local: bool = False,
        force_api: bool = False,
    ) -> OrchestratorResult:
        t0 = time.monotonic()
        timings: dict[str, float] = {}
        session_id = session_id or str(uuid.uuid4())
        errors: list[str] = []
        suggestions: list[str] = []
        cache_hit = False

        log_system(
            "orchestrator.process",
            session_id=session_id,
            source=source,
            input_preview=user_input[:120],
        )

        # ── STEP 1: Cache Check ────────────────────────────────────────────────
        _t = time.monotonic()
        intent: Intent | None = None
        chat_response: str = ""

        if not force_chat:
            intent = cache_get(user_input)
            if intent is not None:
                cache_hit = True
                log_intent(
                    "intent_cache_hit",
                    session_id=session_id,
                    action=intent.action,
                )
        timings["cache_check_ms"] = round((time.monotonic() - _t) * 1000, 2)

        # ── STEP 2: Memory Injection (parallel with fast-path when possible) ──
        _t = time.monotonic()
        # Kick off memory retrieval asynchronously; we'll await before step 4
        mem_task = asyncio.create_task(self._inject_memory(user_input, session_id))

        # ── STEP 3: Fast-Path + LLM Intent ────────────────────────────────────
        if not force_chat and not cache_hit:
            # Stage 3a: rule-based fast path (no I/O)
            fast = fast_path_intent(user_input)
            if fast is not None:
                intent = fast
                log_intent(
                    "intent_fast_path",
                    session_id=session_id,
                    action=intent.action,
                )
                timings["intent_ms"] = 0.0
            else:
                # Stage 3b: LLM intent parsing
                _ti = time.monotonic()
                try:
                    intent = await asyncio.wait_for(parse_intent(user_input), timeout=20.0)
                    cache_put(user_input, intent)   # warm cache for next time
                    log_intent(
                        "intent_parsed",
                        session_id=session_id,
                        action=intent.action,
                        risk=intent.risk_level,
                    )
                except asyncio.TimeoutError:
                    log_error("intent_parse_timeout", session_id=session_id)
                    force_chat = True
                except Exception as exc:
                    log_error("intent_parse_failed", session_id=session_id, error=str(exc))
                    force_chat = True
                timings["intent_ms"] = round((time.monotonic() - _ti) * 1000, 2)

        # Await memory (was running in parallel)
        context_snippets = await mem_task
        timings["memory_inject_ms"] = round((time.monotonic() - _t) * 1000, 2)

        if force_chat or intent is None:
            _tc = time.monotonic()
            chat_response = await self._run_chat(
                user_input, history or [], context_snippets, force_local, force_api
            )
            timings["chat_ms"] = round((time.monotonic() - _tc) * 1000, 2)
            intent = None

        # ── STEP 4: Risk Engine ────────────────────────────────────────────────
        risk = evaluate_risk(intent) if intent else RiskDecision.LOW

        # ── STEP 5: Confirmation Gate ──────────────────────────────────────────
        confirmed = await self._confirmation_gate(intent, risk, session_id)
        if not confirmed:
            elapsed = (time.monotonic() - t0) * 1000
            return OrchestratorResult(
                session_id=session_id,
                input_text=user_input,
                intent=intent,
                risk=risk,
                executed=False,
                output="Action requires confirmation or was rejected.",
                errors=errors,
                elapsed_ms=elapsed,
                suggestions=suggestions,
                stage_timings=timings,
            )

        # ── STEP 6: Tool Execution ─────────────────────────────────────────────
        exec_output = chat_response
        executed = False

        if intent:
            _te = time.monotonic()
            try:
                exec_output, executed = await self._execute_intent(intent, session_id)
            except Exception as exc:
                error_msg = f"execution_error: {exc}"
                log_error(error_msg, session_id=session_id, action=intent.action)
                errors.append(error_msg)
                exec_output = f"Execution failed: {exc}"
            timings["tool_ms"] = round((time.monotonic() - _te) * 1000, 2)

        # ── STEP 7: Behavior + Autonomy (async, non-blocking) ─────────────────
        asyncio.create_task(
            self._log_behavior(
                session_id=session_id,
                user_input=user_input,
                intent=intent,
                risk=risk,
                output=exec_output,
                success=not errors,
            )
        )
        asyncio.create_task(
            self._write_memory(user_input, exec_output, session_id, intent)
        )
        if self._autonomy_v2 is not None:
            asyncio.create_task(
                self._analyze_for_autonomy(user_input, intent, session_id)
            )

        elapsed = (time.monotonic() - t0) * 1000
        timings["total_ms"] = round(elapsed, 2)
        log_execution(
            "orchestrator.done",
            session_id=session_id,
            elapsed_ms=round(elapsed, 2),
            executed=executed,
            risk=risk.value,
            cache_hit=cache_hit,
            timings=timings,
        )

        return OrchestratorResult(
            session_id=session_id,
            input_text=user_input,
            intent=intent,
            risk=risk,
            executed=executed,
            output=exec_output,
            errors=errors,
            elapsed_ms=elapsed,
            suggestions=suggestions,
            stage_timings=timings,
            cache_hit=cache_hit,
        )

    # ── Internal Steps ─────────────────────────────────────────────────────────

    async def _inject_memory(self, query: str, session_id: str) -> list[str]:
        snippets = await get_context(query, top_k=5)
        log_memory("memory_injected", session_id=session_id, count=len(snippets))
        return snippets

    async def _run_chat(
        self,
        user_input: str,
        history: list[dict],
        context_snippets: list[str],
        force_local: bool,
        force_api: bool,
    ) -> str:
        try:
            from services.chat_service import process_message  # type: ignore
            context_block = "\n".join(context_snippets)
            enriched = user_input
            if context_block:
                enriched = f"[Context]\n{context_block}\n\n[User]\n{user_input}"
            return await asyncio.wait_for(
                asyncio.to_thread(process_message, enriched, "orchestrator"),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            log_error("chat_service_timeout")
            return "I'm taking too long to respond. Please try again."
        except Exception as exc:
            log_error("chat_service_error", error=str(exc))
            return "I'm currently unable to process that request. Please try again shortly."

    async def _confirmation_gate(
        self, intent: Intent | None, risk: RiskDecision, session_id: str
    ) -> bool:
        if intent is None:
            return True

        if risk == RiskDecision.HIGH or intent.requires_confirmation:
            try:
                from intents.confirmation_manager import request_confirmation  # type: ignore
                return await request_confirmation(intent)
            except Exception as exc:
                log_error("confirmation_gate_error", session_id=session_id, error=str(exc))
                return False

        return True

    async def _execute_intent(
        self, intent: Intent, session_id: str
    ) -> tuple[str, bool]:
        from tools.executor import execute_intent as tools_execute  # type: ignore
        log_execution(
            "intent_executing",
            session_id=session_id,
            action=intent.action,
            risk=intent.risk_level,
        )
        result = await tools_execute(intent)
        log_execution(
            "intent_executed",
            session_id=session_id,
            action=intent.action,
            success=result.success,
        )
        # FIX: explicit if/else avoids ambiguous ternary precedence
        if result.success:
            output = result.message or result.data.get("output", "")
        else:
            output = result.message
        return output, result.success

    async def _log_behavior(
        self,
        session_id: str,
        user_input: str,
        intent: Intent | None,
        risk: RiskDecision,
        output: str,
        success: bool,
    ) -> None:
        try:
            from behavior.profile_manager import get_profile_manager  # type: ignore
            mgr = get_profile_manager()
            action_label = intent.action if intent else "chat"
            task_type = intent.parameters.get("task_type", "chat") if intent else "chat"
            await asyncio.to_thread(
                mgr.update_from_observation,
                action_label,
                output[:500],
                success,
                task_type,
            )
        except Exception as exc:
            log_error("behavior_log_error", session_id=session_id, error=str(exc))

    async def _write_memory(
        self,
        user_input: str,
        output: str,
        session_id: str,
        intent: Intent | None,
    ) -> None:
        if not output or len(output.strip()) < 10:
            return
        try:
            text = f"User: {user_input}\nJarvis: {output}"
            meta: dict[str, Any] = {"session_id": session_id, "type": "interaction"}
            if intent:
                meta["action"] = intent.action
                meta["risk"] = intent.risk_level
            await store_memory(text, meta)
            log_memory("memory_stored", session_id=session_id)
        except Exception as exc:
            log_error("memory_write_error", session_id=session_id, error=str(exc))

    async def _analyze_for_autonomy(
        self, user_input: str, intent: Intent | None, session_id: str
    ) -> None:
        try:
            await self._autonomy_v2.track_activity(
                user_input=user_input,
                action=intent.action if intent else "chat",
                session_id=session_id,
            )
        except Exception as exc:
            log_error("autonomy_track_error", session_id=session_id, error=str(exc))


# ── Module-level singleton ─────────────────────────────────────────────────────

_orchestrator: CoreOrchestrator | None = None


def get_orchestrator() -> CoreOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CoreOrchestrator()
    return _orchestrator


