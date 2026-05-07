"""
profile_injector — FASE 11B

Prepends relevant BehaviorProfile preferences to LLM system prompts.
Only injects the subset relevant to the current task — not the full profile.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_PROFILE_SYSTEM_PREFIX = "## Preferências operacionais do Jarvis\n"


def inject_profile_if_needed(
    messages: list[dict],
    task_type: str = "default",
) -> list[dict]:
    """
    Prepend a behavior-profile snippet to the message list's system prompt.

    If a system message already exists, the snippet is prepended to it.
    If not, a new system message is inserted at index 0.

    Args:
        messages:  OpenAI-format message list
        task_type: hint used to select the relevant profile subset

    Returns:
        Modified message list (new list, original unchanged)
    """
    try:
        from behavior.profile_manager import get_profile_manager
        profile = get_profile_manager().get()
        snippet = profile.prompt_snippet(task_type=task_type)
        if not snippet:
            return messages

        messages = list(messages)  # shallow copy
        header = _PROFILE_SYSTEM_PREFIX + snippet + "\n\n"

        if messages and messages[0].get("role") == "system":
            messages[0] = {
                "role": "system",
                "content": header + messages[0].get("content", ""),
            }
        else:
            messages.insert(0, {"role": "system", "content": header})

        try:
            from memory_v2.semantic_store import get_semantic_memory
            query = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
            context = get_semantic_memory().get_context_for_prompt_sync(query)
            if context:
                semantic_block = "\n\nCONTEXTO RELEVANTE:\n" + context + "\n\n"
                if messages and messages[0].get("role") == "system":
                    messages[0] = {
                        "role": "system",
                        "content": messages[0].get("content", "") + semantic_block,
                    }
                else:
                    messages.insert(0, {"role": "system", "content": semantic_block})
        except Exception:
            pass

        log.debug("ProfileInjector: injected profile snippet for task_type='%s'", task_type)
    except Exception as exc:
        log.debug("ProfileInjector: skipped (%s)", exc)

    return messages


def get_task_type_from_messages(messages: list[dict]) -> str:
    """
    Heuristically detect task type from message content.
    Used when callers don't pass an explicit task_type.
    """
    text = " ".join(
        m.get("content", "") for m in messages if m.get("role") != "system"
    ).lower()

    if any(w in text for w in ("def ", "class ", "function", "código", "code", "implement")):
        return "code_gen"
    if any(w in text for w in ("analise", "analyze", "review", "erro", "bug", "debug")):
        return "analysis"
    if any(w in text for w in ("o que", "qual", "explique", "summarize", "lista")):
        return "quick"
    return "default"
