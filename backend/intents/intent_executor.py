from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from backend.intents.confirmation_manager import request_confirmation
from backend.intents.intent_registry import get_handler
from backend.intents.risk_evaluator import evaluate_risk
from backend.intents.schemas import Intent, IntentResult
from backend.core.safety_gate import Action, safety_gate

log = logging.getLogger(__name__)
STEP_TIMEOUT_SECONDS = 10.0


async def execute_intent(intent: Intent) -> IntentResult:
    started = datetime.utcnow()
    intent = evaluate_risk(intent)
    result = IntentResult(
        success=False,
        action=intent.action,
        risk_level=intent.risk_level,
        requires_confirmation=intent.requires_confirmation,
        started_at=started,
    )

    try:
        handler = get_handler(intent.action)
        if handler is None:
            result.message = f"No handler registered for action '{intent.action}'"
            result.errors.append(result.message)
            return result

        safety_decision = await safety_gate.evaluate(
            Action(
                action_type=intent.action,
                target=str(
                    intent.parameters.get("path")
                    or intent.parameters.get("target")
                    or intent.parameters.get("url")
                    or intent.parameters.get("app")
                    or ""
                ),
                parameters=intent.parameters,
            )
        )
        result.data["safety"] = safety_decision.model_dump()
        if not safety_decision.allowed:
            result.message = safety_decision.reason
            if safety_decision.preview:
                result.message += f" Preview: {safety_decision.preview}"
            return result

        if intent.requires_confirmation:
            approved = await request_confirmation(intent)
            if not approved:
                result.message = "Execution denied or confirmation timed out"
                return result

        log.info("intent.execute action=%s risk=%s params=%s", intent.action, intent.risk_level, intent.parameters)
        data = await asyncio.wait_for(handler(intent.parameters), timeout=STEP_TIMEOUT_SECONDS)
        try:
            from behavior.behavior_manager import get_behavior_manager
            from behavior.schemas import BehaviorEvent
            get_behavior_manager().record_event(
                BehaviorEvent(
                    type="intent_execution",
                    action=intent.action,
                    metadata={"risk_level": intent.risk_level, "success": True},
                )
            )
        except Exception:
            pass
        result.success = True
        result.executed = True
        result.data = data
        result.message = f"Executed intent '{intent.action}'"
        return result
    except asyncio.TimeoutError:
        result.message = f"Intent step timed out after {STEP_TIMEOUT_SECONDS:.0f}s"
        result.errors.append(result.message)
        return result
    except Exception as exc:
        log.exception("intent.execute_failed action=%s", intent.action)
        result.message = "Intent execution failed"
        result.errors.append(str(exc))
        return result
    finally:
        result.finished_at = datetime.utcnow()
