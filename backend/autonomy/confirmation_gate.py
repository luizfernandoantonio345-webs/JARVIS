"""
confirmation_gate — FASE 12B

Contextual confirmation mechanism based on Behavior Profile risk tolerance.

Rules:
  risk_tolerance=high:   no confirmations — act freely
  risk_tolerance=medium: confirm delete/overwrite operations only
  risk_tolerance=low:    confirm all filesystem write operations
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

log = logging.getLogger(__name__)

_DESTRUCTIVE_KEYWORDS = frozenset({
    "delet", "remov", "apag", "sobrescrev", "overwrite", "drop", "truncat",
    "git push", "git reset", "rm ", "rmdir",
})
_WRITE_KEYWORDS = frozenset({
    "escrev", "cri", "salv", "grav", "modific", "atualiz", "alter",
    "write", "creat", "save", "update", "modif",
})

ConfirmResult = Literal["approved", "rejected", "timeout", "skipped"]


class ConfirmationGate:
    """
    Decides whether an action requires confirmation and waits for it.
    """

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds

    def _get_risk_tolerance(self) -> str:
        try:
            from behavior.profile_manager import get_profile_manager
            return get_profile_manager().get().risk_tolerance
        except Exception:
            return "medium"

    def requires_confirmation(self, goal: str) -> bool:
        risk = self._get_risk_tolerance()
        if risk == "high":
            return False
        goal_lower = goal.lower()
        if risk == "medium":
            return any(kw in goal_lower for kw in _DESTRUCTIVE_KEYWORDS)
        # low: confirm all writes
        return any(kw in goal_lower for kw in _WRITE_KEYWORDS | _DESTRUCTIVE_KEYWORDS)

    async def request(self, goal: str) -> ConfirmResult:
        """
        Request confirmation via the message bus (WebSocket broadcast).
        Falls back to auto-approve if bus is unavailable.
        """
        if not self.requires_confirmation(goal):
            return "skipped"

        confirm_id = f"gate_{int(time.time() * 1000)}"
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[bool] = loop.create_future()

        # Register with autonomy controller so WebSocket /confirm endpoint can resolve it
        try:
            from autonomy.controller import get_autonomy_controller
            ctrl = get_autonomy_controller()
            ctrl._pending_confirmations[confirm_id] = fut
        except Exception as exc:
            log.debug("[autonomy.confirmation_gate] suppressed exception", exc_info=exc)
            pass

        # Broadcast to dashboard / voice
        try:
            from services.message_bus import MessageBus
            await MessageBus.get_instance().broadcast({
                "event": "confirmation_required",
                "confirm_id": confirm_id,
                "goal": goal,
                "timeout": self._timeout,
            })
            log.info("ConfirmationGate: awaiting confirmation for '%s' (id=%s)", goal[:60], confirm_id)
        except Exception as exc:
            log.warning("ConfirmationGate: broadcast failed (%s), auto-approving", exc)
            return "approved"

        try:
            approved = await asyncio.wait_for(fut, timeout=self._timeout)
            result: ConfirmResult = "approved" if approved else "rejected"
            log.info("ConfirmationGate: %s '%s'", result, goal[:60])
            return result
        except asyncio.TimeoutError:
            log.info("ConfirmationGate: timeout for '%s'", goal[:60])
            return "timeout"
        finally:
            try:
                from autonomy.controller import get_autonomy_controller
                get_autonomy_controller()._pending_confirmations.pop(confirm_id, None)
            except Exception as exc:
                log.debug("[autonomy.confirmation_gate] suppressed exception", exc_info=exc)
                pass
