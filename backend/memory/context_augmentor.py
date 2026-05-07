from __future__ import annotations

from .semantic_engine import SemanticMemory


class ContextAugmentor:
    async def augment(self, user_input: str, system_prompt: str) -> str:
        return await augment_with_memory(user_input, system_prompt)


async def augment_with_memory(user_input: str, system_prompt: str) -> str:
    augmented = system_prompt
    relevant = await SemanticMemory().get_relevant_context(user_input)
    if relevant:
        augmented += f"\n\n{relevant}"
    try:
        from expertise.domain_memory import DomainMemory
        domain_context = await DomainMemory().get_relevant_knowledge(user_input)
        if domain_context:
            augmented += f"\n\nCONHECIMENTO PREVIO DO DOMINIO:\n{domain_context}"
    except Exception:
        pass
    try:
        from services.memory_service import get_known_failures
        errors = get_known_failures("default", "expert_analysis", user_input, limit=3)
        if errors:
            augmented += "\n\nERROS SIMILARES JA RESOLVIDOS:\n" + "\n".join(str(e) for e in errors)
    except Exception:
        pass
    return augmented

