from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Literal

from .input import WhisperTranscriber
from .output import speak

try:
    from core.response_engine import response_engine_transform
    from core.telemetry import record_pipeline_trace
    from intents.intent_executor import execute_intent
    from intents.intent_parser import AmbiguousIntentError, parse_intent
    from intents.schemas import Intent
    from services.chat_service import process_message
except ModuleNotFoundError:
    from backend.core.response_engine import response_engine_transform
    from backend.core.telemetry import record_pipeline_trace
    from backend.intents.intent_executor import execute_intent
    from backend.intents.intent_parser import AmbiguousIntentError, parse_intent
    from backend.intents.schemas import Intent
    from backend.services.chat_service import process_message

log = logging.getLogger(__name__)

PipelineSource = Literal["voice", "websocket", "api"]


@dataclass
class PipelineResult:
    transcription: str = ""
    intent: dict | None = None
    response: str = ""
    response_short: str = ""
    timings: dict[str, float] = field(default_factory=dict)
    source: str = "api"
    session_id: str = "default"
    success: bool = True
    error: str | None = None
    audio_path: str | None = None
    fallback_to_chat: bool = False
    intent_confidence: float = 0.0

    def model_dump(self) -> dict:
        return asdict(self)


async def run_jarvis_pipeline(
    input_text: str | None = None,
    input_audio_path: str | None = None,
    session_id: str = "default",
    source: PipelineSource = "api",
    *,
    synthesize_voice: bool | None = None,
) -> PipelineResult:
    result = PipelineResult(source=source, session_id=session_id)
    total_start = time.perf_counter()
    should_tts = source == "voice" if synthesize_voice is None else synthesize_voice

    try:
        text = (input_text or "").strip()
        if input_audio_path:
            started = time.perf_counter()
            text = await asyncio.wait_for(
                WhisperTranscriber().transcribe_audio(input_audio_path),
                timeout=20.0,
            )
            result.timings["transcription_ms"] = _elapsed_ms(started)
        else:
            result.timings["transcription_ms"] = 0.0

        result.transcription = text
        if not text:
            result.success = False
            result.error = "no_input"
            result.response = "Nao entendi o audio." if input_audio_path else "Entrada vazia."
            result.response_short = response_engine_transform(result.response)
            return result

        intent_obj: Intent | None = None
        llm_response = ""

        try:
            started = time.perf_counter()
            intent_obj = await parse_intent(text)
            result.timings["intent_parse_ms"] = _elapsed_ms(started)
            result.intent = intent_obj.model_dump()
            result.intent_confidence = intent_obj.confidence

            if intent_obj.confidence > 0.70:
                started = time.perf_counter()
                intent_result = await execute_intent(intent_obj)
                result.timings["intent_execute_ms"] = _elapsed_ms(started)
                if intent_result.success:
                    llm_response = intent_result.message or "Comando executado."
                    if intent_result.data.get("message"):
                        llm_response = str(intent_result.data["message"])
                else:
                    result.fallback_to_chat = True
                    llm_response = await _chat(text, session_id, result)
            else:
                result.fallback_to_chat = True
                llm_response = await _chat(text, session_id, result)
        except AmbiguousIntentError as exc:
            candidate = exc.candidate
            result.intent = {
                "action": candidate.action,
                "parameters": candidate.parameters,
                "confidence": candidate.confidence,
                "source": "fuzzy_candidate",
            }
            result.intent_confidence = candidate.confidence
            result.timings.setdefault("intent_parse_ms", 0.0)
            llm_response = f"Nao entendi bem. Voce quis dizer {candidate.action}?"
        except Exception as exc:
            log.warning("pipeline intent path failed; falling back to chat: %s", exc)
            result.fallback_to_chat = True
            llm_response = await _chat(text, session_id, result)

        result.response = llm_response

        started = time.perf_counter()
        result.response_short = response_engine_transform(llm_response)
        result.timings["response_engine_ms"] = _elapsed_ms(started)

        if should_tts:
            started = time.perf_counter()
            result.audio_path = await asyncio.wait_for(speak(result.response_short), timeout=15.0)
            result.timings["tts_ms"] = _elapsed_ms(started)
        else:
            result.timings["tts_ms"] = 0.0

        intent_name = result.intent.get("action") if isinstance(result.intent, dict) else None
        asyncio.create_task(
            _post_pipeline_learning(
                text=text,
                response=result.response,
                session_id=session_id,
                intent_name=intent_name,
                success=result.success,
            )
        )

        return result
    except asyncio.TimeoutError:
        result.success = False
        result.error = "timeout"
        result.response = "Timeout no processamento."
        result.response_short = response_engine_transform(result.response)
        return result
    except Exception as exc:
        log.exception("pipeline failed")
        result.success = False
        result.error = str(exc)
        result.response = "Erro interno."
        result.response_short = response_engine_transform(result.response)
        return result
    finally:
        result.timings["total_ms"] = _elapsed_ms(total_start)
        intent_name = None
        if isinstance(result.intent, dict):
            intent_name = result.intent.get("action")
        await record_pipeline_trace(
            source=result.source,
            stages=result.timings,
            intent_detected=intent_name,
            intent_confidence=result.intent_confidence,
            fallback_to_chat=result.fallback_to_chat,
            success=result.success,
            error=result.error,
        )


async def _chat(text: str, session_id: str, result: PipelineResult) -> str:
    started = time.perf_counter()
    response = await asyncio.to_thread(process_message, text, session_id)
    result.timings["llm_ms"] = _elapsed_ms(started)
    return response


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


async def _post_pipeline_learning(
    *,
    text: str,
    response: str,
    session_id: str,
    intent_name: str | None,
    success: bool,
) -> None:
    def _run() -> None:
        try:
            from behavior.profile_learner import get_profile_learner
            get_profile_learner().after_command(
                text,
                intent=intent_name,
                success=success,
                session_id=session_id,
            )
        except Exception:
            pass

        if not success:
            return

        try:
            from memory_v2.semantic_store import get_semantic_memory
            from memory_v2.training_collector import get_training_collector

            context = get_semantic_memory().get_context_for_prompt_sync(text)
            get_training_collector().save_interaction(
                input_text=text,
                context=context,
                output=response,
                rating="positive",
                session_id=session_id,
            )
        except Exception:
            pass

    await asyncio.to_thread(_run)
