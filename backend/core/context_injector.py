"""
context_injector — FASE 11 Boot Context Injection

Lightweight middleware that prepends restored session context into LLM prompts.

How it works
------------
1. Before the LLM is called, `inject_boot_context_if_needed(messages)` is called.
2. If a boot_context exists in session store AND has not been injected yet,
   a system message is prepended describing the prior session state.
3. The context is marked "injected" so it only prepends once per server session.

Usage (in llm_service or chat_service)
---------------------------------------
>>> from backend.core.context_injector import inject_boot_context_if_needed
>>> messages = inject_boot_context_if_needed(messages)
>>> response = call_llm(messages)

The injector is intentionally stateless and cheap — it reads from the in-memory
session store, not from disk, so it adds < 1 ms overhead.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Maximum chars from history/preferences to include in the injected context
_MAX_HISTORY_CHARS   = 800
_MAX_PREF_ITEMS      = 3


def inject_boot_context_if_needed(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    Prepend restored session context to *messages* if:
      - A BootContext exists in the session store
      - It has not already been injected this session

    Parameters
    ----------
    messages : List of {"role": str, "content": str} dicts for the LLM.

    Returns
    -------
    The same list (possibly with a new system message prepended).

    Usage
    -----
    >>> msgs = inject_boot_context_if_needed(msgs)
    """
    try:
        from core.boot_restorer import get_boot_context, mark_boot_context_injected
        ctx = get_boot_context()
    except Exception:
        return messages

    if ctx is None or ctx.injected:
        return messages

    # ── Build injection text ───────────────────────────────────────────────────
    lines: list[str] = ["[Contexto restaurado da sessão anterior]"]

    # Active job
    if ctx.active_job:
        aj = ctx.active_job
        lines.append(
            f"Último job ativo: {aj.job_id} — status: {aj.status} "
            f"({aj.files_completed} arquivo(s) concluído(s))"
        )
        goal_preview = aj.goal[:150] + ("…" if len(aj.goal) > 150 else "")
        lines.append(f"Objetivo do job: {goal_preview}")

    # Project context
    if ctx.project:
        proj_name = ctx.project.get("name") or ctx.project.get("project_name", "")
        if proj_name:
            lines.append(f"Projeto ativo: {proj_name}")
        for k, v in list(ctx.project.items())[:3]:
            lines.append(f"  Contexto — {k}: {v[:100]}")

    # Top preferences
    if ctx.preferences:
        top_prefs = list(ctx.preferences.items())[:_MAX_PREF_ITEMS]
        pref_str  = ", ".join(f"{k}={v}" for k, v in top_prefs)
        lines.append(f"Preferências: {pref_str}")

    # Recent history (last 3 interactions condensed)
    if ctx.recent_history:
        lines.append("Histórico recente:")
        shown = 0
        total_chars = 0
        for entry in reversed(ctx.recent_history[:3]):
            msg_preview  = entry.get("message", "")[:120]
            resp_preview = entry.get("response", "")[:120]
            chunk = f"  U: {msg_preview} | A: {resp_preview}"
            total_chars += len(chunk)
            if total_chars > _MAX_HISTORY_CHARS:
                break
            lines.append(chunk)
            shown += 1
        if shown == 0:
            lines.pop()  # Remove "Histórico recente:" header

    injection = "\n".join(lines)

    # Prepend as a system message (before any existing system messages)
    augmented = [{"role": "system", "content": injection}] + messages

    # Mark as injected so we don't repeat on the next call
    mark_boot_context_injected()

    log.debug(
        "context_injector: injected boot context (%d chars)",
        len(injection),
    )
    return augmented


def build_boot_context_summary() -> str:
    """
    Return a human-readable summary of the current boot context.

    Used by GET /session/context.
    """
    try:
        from core.boot_restorer import get_boot_context
        ctx = get_boot_context()
    except Exception:
        return "(boot context unavailable)"

    if ctx is None:
        return "(no previous session context found)"

    parts: list[str] = [f"Restored at: {ctx.restored_at}"]

    if ctx.active_job:
        aj = ctx.active_job
        parts.append(
            f"Active job: {aj.job_id} | status: {aj.status} | "
            f"files done: {aj.files_completed}"
        )
        parts.append(f"Job goal: {aj.goal[:200]}")

    if ctx.project:
        parts.append(f"Project context: {dict(list(ctx.project.items())[:5])}")

    if ctx.preferences:
        parts.append(f"Preferences: {dict(list(ctx.preferences.items())[:5])}")

    parts.append(f"History entries: {len(ctx.recent_history)}")
    parts.append(f"Already injected: {ctx.injected}")

    return "\n".join(parts)
