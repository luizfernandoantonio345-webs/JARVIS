"""
Tool Executor — routes an Intent to the correct tool handler.
This is the ONLY entry point to the tools layer from the orchestrator.

Reliability: each tool call retries up to MAX_RETRIES times with
exponential backoff before returning a failure result.
"""
from __future__ import annotations

import asyncio

from core.logger import log_error, log_execution
from intents.schemas import Intent, IntentResult

MAX_RETRIES = 2
RETRY_BASE_DELAY = 0.5   # seconds; doubles each retry
TOOL_TIMEOUT = 30.0      # seconds per tool call attempt


async def execute_intent(intent: Intent) -> IntentResult:
    """Execute an intent by dispatching to the appropriate tool."""
    from tools.registry import TOOL_REGISTRY  # noqa: PLC0415

    handler = TOOL_REGISTRY.get(intent.action)

    if handler is None:
        # Bug #5 fix: fall back to intents.intent_executor (not execute_service).
        # intents.intent_executor already handles unknown-action gracefully.
        try:
            from intents.intent_executor import execute_intent as legacy_execute  # type: ignore
            return await legacy_execute(intent)
        except Exception as exc:
            log_error("execute_intent_fallback_error", action=intent.action, error=str(exc))
            return IntentResult(
                success=False,
                action=intent.action,
                risk_level=intent.risk_level,
                requires_confirmation=intent.requires_confirmation,
                executed=False,
                message=f"No handler for action '{intent.action}': {exc}",
                errors=[str(exc)],
            )

    log_execution("tool_dispatch", action=intent.action, tool=handler.__name__)

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):   # 1..MAX_RETRIES+1
        try:
            data = await asyncio.wait_for(handler(intent.parameters), timeout=TOOL_TIMEOUT)
            if attempt > 1:
                log_execution("tool_retry_success", action=intent.action, attempt=attempt)
            return IntentResult(
                success=True,
                action=intent.action,
                risk_level=intent.risk_level,
                requires_confirmation=intent.requires_confirmation,
                executed=True,
                message=data.get("message", ""),
                data=data,
            )
        except asyncio.TimeoutError as exc:
            last_exc = exc
            log_error("tool_timeout", action=intent.action, attempt=attempt, timeout=TOOL_TIMEOUT)
        except Exception as exc:
            last_exc = exc
            log_error("tool_error", action=intent.action, attempt=attempt, error=str(exc))

        if attempt <= MAX_RETRIES:
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            log_execution("tool_retry", action=intent.action, attempt=attempt, delay=delay)
            await asyncio.sleep(delay)

    # All retries exhausted
    return IntentResult(
        success=False,
        action=intent.action,
        risk_level=intent.risk_level,
        requires_confirmation=intent.requires_confirmation,
        executed=False,
        message=str(last_exc),
        errors=[str(last_exc)],
    )

