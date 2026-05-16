import logging
from typing import Generator

from fastapi import HTTPException
from services.session_store import get_history, append_message, SYSTEM_PROMPT
from services.llm_router import route
from services.planner import build_plan
from services.executor import execute_plan
from services.memory_service import save_memory, get_memory
from services.preference_extractor import extract_async
from services.task_manager import is_autonomous_goal, create_task, run_task, build_task_report
from services.cache_service import get_cached, set_cached
from actions.action_loader import get_system_prompt
from services.llm_service import call_llm, call_llm_stream
from services.ai_router import route_with_intent
from services.ai_router import decide_action
from core.context_memory import save_intent, build_context_summary
from agents.intent_orchestrator import get_intent_orchestrator
from services.autodev_bridge import needs_full_autodev, run_autodev_from_intent

log = logging.getLogger(__name__)


def _seed_history(session_id: str) -> list[dict]:
    """Return session history, seeded from persistent memory if the session is new."""
    session_history = get_history(session_id)
    if not session_history:
        seeded: list[dict] = []
        for mem_msg, mem_resp in get_memory(session_id, limit=5):
            seeded.append({"role": "user",      "content": mem_msg})
            seeded.append({"role": "assistant", "content": mem_resp})
        return seeded
    return list(session_history)


def _inject_intent_context(
    seeded: list[dict],
    intent_model,
    ctx_summary: str,
) -> list[dict]:
    """
    Prepend an intent + project context system message to the seeded history.
    This ensures every LLM call is aware of WHAT the user is trying to build
    and WHERE the conversation is in the project lifecycle.
    """
    lines: list[str] = []
    if ctx_summary:
        lines.append(f"[Contexto do projeto]\n{ctx_summary}")
    subgoals_str  = ", ".join(intent_model.subgoals)  or "N/A"
    outputs_str   = ", ".join(intent_model.expected_outputs) or "N/A"
    lines.append(
        f"[Inten\u00e7\u00e3o detectada]\n"
        f"Objetivo: {intent_model.goal}\n"
        f"Dom\u00ednio: {intent_model.domain}\n"
        f"Sub-objetivos: {subgoals_str}\n"
        f"Sa\u00eddas esperadas: {outputs_str}"
    )
    system_msg = {"role": "system", "content": "\n\n".join(lines)}
    return [system_msg] + seeded


def _should_fast_path_chat(message: str) -> bool:
    # Extract actual user query — memory context is prepended with \n\n separator
    if "\n\n" in message:
        stripped = message.split("\n\n")[-1].strip()
    else:
        stripped = message.strip()
    if not stripped or len(stripped) > 160:
        return False
    if "```" in stripped or "\n" in stripped or stripped.startswith("/"):
        return False

    action, _ = decide_action(stripped)
    return action == "chat"


def _build_direct_chat_messages(message: str, session_id: str) -> list[dict]:
    # Extract actual user query — memory context is prepended with \n\n separator
    if "\n\n" in message:
        user_query = message.split("\n\n")[-1].strip()
    else:
        user_query = message.strip()

    seeded = _seed_history(session_id)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if seeded:
        messages.extend(seeded[-4:])  # reduced from 8 to 4 for local model efficiency
    messages.append({"role": "user", "content": user_query})
    return messages


def _persist_response(session_id: str, message: str, response: str, action: str) -> None:
    append_message(session_id, "user", message)
    append_message(session_id, "assistant", response)
    save_memory(session_id, message, response, action=action)
    extract_async(session_id, message)
    set_cached(session_id, message, response)


def process_message(message: str, session_id: str) -> str:
    # ── Cache hit ────────────────────────────────────────────────────────────
    cached = get_cached(session_id, message)
    if cached:
        log.debug("[session=%s] cache hit", session_id)
        return cached

    if _should_fast_path_chat(message):
        response = call_llm(_build_direct_chat_messages(message, session_id), force_local=True)
        _persist_response(session_id, message, response, action="chat_fast")
        return response

    # ── Autonomous goal path ─────────────────────────────────────────────────
    if is_autonomous_goal(message):
        task = create_task(session_id, message)
        task = run_task(task.id)
        response = build_task_report(task)

        _persist_response(session_id, message, response, action="task")
        return response

    # ── Standard single/multi-step path ─────────────────────────────────────
    intent, content, intent_model = route_with_intent(message, session_id)

    # FASE 3: Full AutoDev pipeline for complex multi-file projects
    if needs_full_autodev(intent_model):
        log.info("[session=%s] FASE 3: AutoDev bridge | domain=%s subgoals=%d",
                 session_id, intent_model.domain, len(intent_model.subgoals))
        response = run_autodev_from_intent(intent_model, message, session_id)
        _persist_response(session_id, message, response, action=f"autodev_{intent_model.domain}")
        save_intent(session_id, message, intent_model, response)
        return response

    # FASE 2: Try domain-aware agent-chain orchestration first
    orch_result = get_intent_orchestrator().orchestrate(intent_model, message, session_id)
    if orch_result:
        response = orch_result.output
        _persist_response(session_id, message, response, action=f"orchestrated_{intent_model.domain}")
        return response

    plan = build_plan(content, intent)
    log.debug("[session=%s] plan=%r", session_id, plan)

    seeded = _seed_history(session_id)
    ctx_summary = build_context_summary(session_id)
    seeded = _inject_intent_context(seeded, intent_model, ctx_summary)

    try:
        exec_result = execute_plan(plan, seeded, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Executor error: {e}")

    response       = exec_result.final_response
    primary_action = exec_result.primary_action

    _persist_response(session_id, message, response, action=primary_action)
    save_intent(session_id, message, intent_model, response)

    return response


def process_message_stream(
    message: str,
    session_id: str,
) -> Generator[dict, None, None]:
    """
    Streaming variant. Yields SSE-ready dicts:
      {"type": "plan",  "steps": [...]}
      {"type": "token", "content": "..."}
      {"type": "done",  "action": "...", "task_id": None}
      {"type": "error", "detail": "..."}
    """
    if _should_fast_path_chat(message):
        full_response_parts: list[str] = []
        try:
            for token in call_llm_stream(_build_direct_chat_messages(message, session_id)):
                full_response_parts.append(token)
                yield {"type": "token", "content": token}
        except Exception as e:
            yield {"type": "error", "detail": str(e)}
            return

        response = "".join(full_response_parts)
        _persist_response(session_id, message, response, action="chat_fast")
        yield {"type": "done", "action": "chat_fast", "task_id": None}
        return

    # ── Autonomous goal path (stream progress events, not tokens) ────────────
    if is_autonomous_goal(message):
        task = create_task(session_id, message)
        yield {
            "type":  "plan",
            "steps": [
                {"description": s.description, "action": s.action}
                for s in task.steps
            ],
            "task_id": task.id,
        }

        completed_task = run_task(task.id)
        report = build_task_report(completed_task)

        _persist_response(session_id, message, report, action="task")

        # Stream the report as tokens
        for word in report.split(" "):
            yield {"type": "token", "content": word + " "}

        yield {"type": "done", "action": "task", "task_id": task.id}
        return

    # ── Standard streaming path ──────────────────────────────────────────────
    intent, content, intent_model = route_with_intent(message, session_id)

    # FASE 3: Full AutoDev pipeline for complex multi-file projects (stream word-by-word)
    if needs_full_autodev(intent_model):
        log.info("[session=%s] FASE 3 stream: AutoDev bridge | domain=%s", session_id, intent_model.domain)
        yield {"type": "plan", "steps": [{"action": f"autodev_{intent_model.domain}", "input": message[:120]}], "task_id": None}
        response = run_autodev_from_intent(intent_model, message, session_id)
        for word in response.split(" "):
            yield {"type": "token", "content": word + " "}
        _persist_response(session_id, message, response, action=f"autodev_{intent_model.domain}")
        save_intent(session_id, message, intent_model, response)
        yield {"type": "done", "action": f"autodev_{intent_model.domain}", "task_id": None}
        return

    # FASE 2: Try domain-aware agent-chain orchestration first (stream as word tokens)
    orch_result = get_intent_orchestrator().orchestrate(intent_model, message, session_id)
    if orch_result:
        yield {"type": "plan", "steps": [{"action": f"orchestrated_{intent_model.domain}", "input": message[:120]}], "task_id": None}
        for word in orch_result.output.split(" "):
            yield {"type": "token", "content": word + " "}
        _persist_response(session_id, message, orch_result.output, action=f"orchestrated_{intent_model.domain}")
        yield {"type": "done", "action": f"orchestrated_{intent_model.domain}", "task_id": None}
        return

    plan = build_plan(content, intent)

    yield {
        "type":  "plan",
        "steps": [
            {"action": s.action, "input": s.input[:120]}
            for s in plan.content_steps
        ],
        "task_id": None,
    }

    seeded = _seed_history(session_id)
    ctx_summary = build_context_summary(session_id)
    seeded = _inject_intent_context(seeded, intent_model, ctx_summary)

    # For multi-step plans, run non-streaming (executor handles chaining)
    # then stream the final response word-by-word for perceived performance.
    if plan.is_multi:
        try:
            exec_result = execute_plan(plan, seeded, session_id=session_id)
        except Exception as e:
            yield {"type": "error", "detail": str(e)}
            return

        response       = exec_result.final_response
        primary_action = exec_result.primary_action

        _persist_response(session_id, message, response, action=primary_action)
        save_intent(session_id, message, intent_model, response)

        for word in response.split(" "):
            yield {"type": "token", "content": word + " "}
        yield {"type": "done", "action": primary_action, "task_id": None}
        return

    # Single-step — true token streaming
    first_step = plan.content_steps[0]
    sys_prompt = get_system_prompt(first_step.action, SYSTEM_PROMPT)

    from services.memory_service import build_context_for_task
    messages: list[dict] = [{"role": "system", "content": sys_prompt}]

    ctx_block = build_context_for_task(session_id, content, task_type=first_step.action)
    if ctx_block:
        messages.append({"role": "system", "content": f"Personalization context:\n{ctx_block}"})

    messages.extend(seeded)
    messages.append({"role": "user", "content": content})

    full_response_parts: list[str] = []
    try:
        for token in call_llm_stream(messages):
            full_response_parts.append(token)
            yield {"type": "token", "content": token}
    except Exception as e:
        yield {"type": "error", "detail": str(e)}
        return

    response       = "".join(full_response_parts)
    primary_action = first_step.action

    _persist_response(session_id, message, response, action=primary_action)
    save_intent(session_id, message, intent_model, response)

    yield {"type": "done", "action": primary_action, "task_id": None}
