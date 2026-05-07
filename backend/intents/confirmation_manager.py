from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from intents.schemas import ConfirmationRequest, Intent

log = logging.getLogger(__name__)
_pending: dict[str, asyncio.Future[bool]] = {}
_requests: dict[str, ConfirmationRequest] = {}


async def request_confirmation(intent: Intent, timeout_seconds: float = 30.0) -> bool:
    if not intent.requires_confirmation:
        return True

    confirmation_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[bool] = loop.create_future()
    _pending[confirmation_id] = fut
    _requests[confirmation_id] = ConfirmationRequest(
        confirmation_id=confirmation_id,
        intent=intent,
        prompt=f"Confirm execution of high-risk action '{intent.action}'?",
        expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
    )
    log.warning("intent.confirmation_required id=%s action=%s", confirmation_id, intent.action)

    try:
        return await asyncio.wait_for(fut, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        log.warning("intent.confirmation_timeout id=%s action=%s", confirmation_id, intent.action)
        return False
    finally:
        _pending.pop(confirmation_id, None)
        _requests.pop(confirmation_id, None)


def respond_confirmation(confirmation_id: str, approved: bool) -> bool:
    fut = _pending.get(confirmation_id)
    if not fut or fut.done():
        return False
    fut.set_result(bool(approved))
    return True


def list_pending_confirmations() -> list[ConfirmationRequest]:
    return list(_requests.values())

