from __future__ import annotations

from memory.semantic_store import get_semantic_memory


class ContextAugmentor:
    """Injects semantic context into system prompts when available."""

    async def augment(self, user_input: str, system_prompt: str) -> str:
        try:
            context = await get_semantic_memory().get_context_for_prompt(user_input)
        except Exception:
            context = ""

        if not context:
            return system_prompt

        return (
            f"{system_prompt}\n\n"
            "Relevant memory context:\n"
            f"{context}\n"
        )
