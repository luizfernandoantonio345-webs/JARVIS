"""
AutoDev Bridge — FASE 3: Execution Engine

Routes complex multi-file project requests to the full AutoDev pipeline
(scaffold → generate → validate → fix) instead of the lighter-weight
IntentOrchestrator agent chain.

## Decision logic

A request goes to AutoDev when ALL of the following are true:
  1. domain ∈ {web_dev, api, mobile}   — structured project needed
  2. subgoals >= 3                      — sufficient complexity
  3. ambiguity_score <= 0.60           — goal is specific enough to scaffold

Otherwise the IntentOrchestrator (FASE 2) handles it.

## Sync wrapper

`AutoDevLoop.run()` is async.  `run_autodev_from_intent()` bridges this by
running the coroutine in a background thread's event loop so it can be
called from the synchronous `chat_service.process_message()`.

Usage
-----
>>> from services.autodev_bridge import needs_full_autodev, run_autodev_from_intent
>>> if needs_full_autodev(intent_model):
...     response = run_autodev_from_intent(intent_model, "sess-001")
...     return response
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

from core.intent_engine import IntentModel

log = logging.getLogger(__name__)

# Domains that benefit from the full scaffold→generate→validate pipeline
_AUTODEV_DOMAINS: frozenset[str] = frozenset({"web_dev", "api", "mobile"})

# Minimum subgoals for AutoDev routing
_AUTODEV_MIN_SUBGOALS = 3

# Maximum ambiguity allowed for AutoDev
_AUTODEV_MAX_AMBIGUITY = 0.60


# ── Decision gate ──────────────────────────────────────────────────────────────

def needs_full_autodev(intent: IntentModel) -> bool:
    """
    Return True when *intent* should be handled by the full AutoDev loop.

    Criteria (all must be met):
    - domain in {web_dev, api, mobile}
    - at least 3 subgoals (multi-file project)
    - ambiguity_score <= 0.60 (clear enough to auto-scaffold)
    """
    return (
        intent.domain in _AUTODEV_DOMAINS
        and len(intent.subgoals) >= _AUTODEV_MIN_SUBGOALS
        and intent.ambiguity_score <= _AUTODEV_MAX_AMBIGUITY
    )


# ── Goal enrichment ────────────────────────────────────────────────────────────

def _build_autodev_goal(intent: IntentModel, raw_message: str) -> str:
    """
    Combine the structured IntentModel with the raw user message into a single
    rich goal string for the AutoDev scaffolder.
    """
    parts: list[str] = [intent.goal]

    if intent.subgoals:
        steps = "; ".join(intent.subgoals)
        parts.append(f"Required features: {steps}")

    if intent.constraints:
        parts.append(f"Technology stack: {', '.join(intent.constraints)}")

    if intent.expected_outputs:
        parts.append(f"Deliverables: {', '.join(intent.expected_outputs)}")

    parts.append(f"(User request: \"{raw_message}\")")
    return "\n".join(parts)


def _build_constraints(intent: IntentModel) -> dict:
    """Convert IntentModel into AutoDev constraints dict."""
    return {
        "domain": intent.domain,
        "stack": intent.constraints,
        "expected_outputs": intent.expected_outputs,
    }


# ── Sync wrapper ───────────────────────────────────────────────────────────────

def run_autodev_from_intent(
    intent: IntentModel,
    raw_message: str,
    session_id: str,
    on_event: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Run the full AutoDev pipeline synchronously.

    Spins up a new event loop in the current thread to execute the async
    `AutoDevLoop.run()` coroutine.  Safe to call from synchronous FastAPI
    route handlers and chat_service.

    Parameters
    ----------
    intent      : IntentModel from FASE 1
    raw_message : Original user text (for goal enrichment)
    session_id  : Used as the AutoDev job_id for workspace isolation
    on_event    : Optional progress callback (receives string messages)

    Returns
    -------
    Formatted markdown string summarising what was built.
    """
    from autodev.loop import AutoDevLoop

    goal        = _build_autodev_goal(intent, raw_message)
    constraints = _build_constraints(intent)

    _emit(on_event, f"🏗️ AutoDev Bridge: starting full pipeline | domain={intent.domain} | subgoals={len(intent.subgoals)}")

    # Use session_id as job_id so the workspace is predictably located at
    # jobs/<session_id>/ — same location code_writer uses.
    loop_instance = AutoDevLoop(job_id=session_id)

    try:
        # Run the async loop in a new event loop (current thread may not have one)
        result_dict = _run_async(loop_instance.run(goal, constraints))
        return _format_result(result_dict, session_id, on_event)
    except Exception as exc:
        log.error("AutoDev bridge error for session=%s: %s", session_id, exc)
        return (
            f"❌ Erro no AutoDev: {exc}\n\n"
            "O projeto foi parcialmente gerado. Verifique os arquivos no workspace."
        )


def _run_async(coro) -> dict:
    """Run an asyncio coroutine synchronously in a dedicated event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _format_result(result: dict, session_id: str, on_event: Optional[Callable]) -> str:
    """Format AutoDevLoop result dict into a user-facing markdown response."""
    status    = result.get("status", "unknown")
    files     = result.get("files_completed", [])
    stack     = result.get("stack", "")
    workspace = result.get("final_output_dir", f"jobs/{session_id}")
    escalated = result.get("escalations", [])

    lines: list[str] = []

    if status == "done":
        lines.append(f"✅ **Projeto gerado com sucesso!**")
        _emit(on_event, f"✅ AutoDev done | {len(files)} files")
    elif status == "escalated":
        lines.append(f"⚠️ **Projeto gerado com advertências** ({len(escalated)} arquivo(s) precisam revisão manual)")
        _emit(on_event, f"⚠️ AutoDev escalated | {len(escalated)} issues")
    else:
        lines.append(f"⚠️ **Pipeline parcialmente concluído** (status: {status})")
        _emit(on_event, f"AutoDev status={status}")

    if stack:
        lines.append(f"\n**Stack**: {stack}")

    lines.append(f"**Workspace**: `{workspace}`")

    if files:
        lines.append(f"\n**Arquivos criados** ({len(files)}):")
        for f in files[:20]:   # cap to avoid excessively long responses
            lines.append(f"  - `{f}`")
        if len(files) > 20:
            lines.append(f"  - … e mais {len(files) - 20} arquivo(s)")

    if escalated:
        lines.append(f"\n**Erros não resolvidos** (requer revisão manual):")
        for e in escalated[:5]:
            lines.append(f"  - `{e.get('file', '?')}`: {e.get('error', '?')[:80]}")

    # Register written files in context_memory
    _register_files(session_id, files)

    return "\n".join(lines)


def _register_files(session_id: str, files: list[str]) -> None:
    """Best-effort file registration in ProjectManagerAgent."""
    if not files:
        return
    try:
        from agents.project_manager_agent import get_project_manager
        get_project_manager().register_files(session_id, files)
    except Exception as exc:
        log.debug("autodev_bridge._register_files skipped: %s", exc)


def _emit(on_event: Optional[Callable], msg: str) -> None:
    log.info("autodev_bridge: %s", msg)
    if on_event:
        try:
            on_event(msg)
        except Exception:
            pass
