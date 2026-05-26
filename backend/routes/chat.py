import json
import os
import time

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from actions.save_memory import load_user_memory
from services.chat_service import process_message, process_message_stream
from core.intent_classifier import get_intent_classifier
from core.telemetry import trace_span, record_cache_hit, record_llm_latency

from services.session_store import clear_session
from services.memory_service import get_memory, clear_memory, get_session_list
from services.llm_service import get_model_info
from services.llm_service import call_llm
from services.session_store import SYSTEM_PROMPT
from utils.env import env_flag
from config import get_config

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str


def _with_memory_context(message: str) -> str:
    memory_context = load_user_memory()
    if memory_context:
        return f"{memory_context}\n\n{message}"
    return message


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest):
    if env_flag("JARVIS_TEST_MODE"):
        return ChatResponse(
            response="resposta mock do LLM",
            session_id=request.session_id,
        )

    # Fast-path: skip all expensive work if Ollama is down and no API keys
    from services.llm_service import _ANTHROPIC_KEY, _OPENAI_KEY
    if not _ANTHROPIC_KEY and not _OPENAI_KEY:
        from ai.client import is_ollama_available
        if not is_ollama_available():
            cfg = get_config()
            return ChatResponse(
                response=(
                    f"JARVIS offline - Ollama nao responde em {cfg.ollama_url}. "
                    "Verifique se o servico esta rodando e se JARVIS_OLLAMA_URL esta correto."
                ),
                session_id=request.session_id,
            )

    enriched_message = _with_memory_context(request.message)

    # Low-latency fast path for short natural messages.
    # This avoids planner/orchestrator overhead that can stall on constrained local setups.
    raw_message = (request.message or "").strip()
    if raw_message and len(raw_message) <= 160 and "```" not in raw_message and "\n" not in raw_message:
        quick_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_message},
        ]
        quick_response = call_llm(quick_messages, force_local=True)
        return ChatResponse(response=quick_response, session_id=request.session_id)

    t0 = time.monotonic() * 1000
    classifier = get_intent_classifier()
    tier = classifier.classify(enriched_message)
    record_cache_hit(f"classifier_{tier}")

    if tier != "complex":
        simple_resp = classifier.get_simple_response(enriched_message, request.session_id)
        if simple_resp:
            latency = (time.monotonic() * 1000 - t0)
            record_llm_latency(latency, "turbo_sync", tier, cached=True)
            return ChatResponse(response=simple_resp, session_id=request.session_id)

    response = process_message(enriched_message, request.session_id)
    latency = (time.monotonic() * 1000 - t0)
    record_llm_latency(latency, "chat_sync", "complex")
    return ChatResponse(response=response, session_id=request.session_id)


@router.post("/process", response_model=ChatResponse)
def chat_process_alias(request: ChatRequest):
    """Alias para compatibilidade retroativa com clientes que usam /chat/process"""
    return chat(request)


@router.post("/stream")
def chat_stream(request: ChatRequest):
    """
    Server-Sent Events endpoint — streams tokens as they are generated.

    Event format (newline-delimited JSON):
      data: {"type": "plan",  "steps": [...]}          ← plan emitted first
      data: {"type": "token", "content": "word "}      ← repeated per token
      data: {"type": "turbo", "tier": "simple|cached", "response": "..."}   ← turbo fast path <500ms
      data: {"type": "done",  "action": "chat|turbo",
             "task_id": null | "uuid", "tier": "simple|cached|complex"}     ← final event
      data: {"type": "error", "detail": "..."}          ← on failure
    """
    t0 = time.monotonic() * 1000
    enriched_message = _with_memory_context(request.message)

    def _generate():
        try:
            classifier = get_intent_classifier()
            tier = classifier.classify(enriched_message)
            record_cache_hit(f"classifier_{tier}")

            if tier != "complex":
                simple_resp = classifier.get_simple_response(enriched_message, request.session_id)
                if simple_resp:
                    latency = (time.monotonic() * 1000 - t0)
                    record_llm_latency(latency, "turbo_stream", tier, cached=True)
                    yield f'data: {json.dumps({{"type": "turbo", "tier": tier, "response": simple_resp}})}\n\n'
                    yield f'data: {json.dumps({{"type": "done", "action": "turbo", "tier": tier}})}\n\n'
                    return

            # Full LLM stream for complex queries
            for event in process_message_stream(enriched_message, request.session_id):
                yield f"data: {json.dumps(event)}\n\n"
            
            latency = (time.monotonic() * 1000 - t0)
            record_llm_latency(latency, "chat_stream", "complex")

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/model-info")
def model_info():
    """Return which LLM providers are configured and active thresholds."""
    return get_model_info()


@router.get("/memory/{session_id}")
def get_memory_route(session_id: str, limit: int = 20):
    history = get_memory(session_id, limit=limit)
    return {
        "session_id": session_id,
        "history": [{"message": m, "response": r} for m, r in history],
    }


@router.get("/sessions")
def list_sessions():
    return {"sessions": get_session_list()}


@router.delete("/{session_id}")
def clear(session_id: str):
    clear_session(session_id)
    clear_memory(session_id)
    return {"cleared": session_id}

# Turbo stats endpoint (bonus)
@router.get("/turbo/stats")
def turbo_stats():
    classifier = get_intent_classifier()
    return classifier.stats()

