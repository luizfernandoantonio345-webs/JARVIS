import re
from typing import Tuple

# Explicit command aliases (highest priority)
COMMAND_ALIASES = {
    "analyze": ["/analyze", "/analisar", "/code", "/review"],
    "arch":    ["/arch", "/arquitetura", "/architecture", "/design"],
    "run":     ["/run", "/executar", "/exec", "/rodar"],
    "explain": ["/explain", "/explique", "/o que é", "/what is"],
}

# Keyword patterns (fallback routing)
ROUTE_PATTERNS: list[Tuple[str, str]] = [
    ("analyze",  r"\b(analise|analisa|analisar|analys[ei]|review|revise|revisar|bug|debug|debugar|c[oó]digo com (erro|problema|bug)|o que h[aá] de errado)\b"),
    ("arch",     r"\b(arquitetura|architecture|estrutura|design de sistema|escal[aá]vel|microservice|monolito|padr[aã]o de projeto|infraestrutura|como estrutur)\b"),
    ("run",      r"\b(execute|execut[ae]|rode|rodar|roda isso|run this|calcul[ae]|resultado de|saída de)\b"),
    ("explain",  r"\b(explique|explicar|o que [eé]|como funciona|me explica|explain|what is|how does|o que significa|entender)\b"),
]


def decide_action(message: str) -> Tuple[str, str]:
    """Returns (action_name, content_to_process)."""
    msg = message.strip()

    # 1. Explicit command prefix
    for action, prefixes in COMMAND_ALIASES.items():
        for prefix in prefixes:
            if msg.lower().startswith(prefix.lower()):
                content = re.sub(r"^\S+\s*", "", msg, count=1).strip()
                return action, content or msg

    # 2. Keyword-based routing
    msg_lower = msg.lower()
    for action, pattern in ROUTE_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return action, msg

    return "chat", msg


# ── Intent-enhanced routing (FASE 1) ─────────────────────────────────────────

def route_with_intent(message: str, session_id: str) -> tuple:
    """
    Enhanced routing that returns (action_str, content, IntentModel).

    Priority chain:
      1. Explicit command prefix (/run, /analyze, ...) — no LLM cost,
         returns a minimal IntentModel with domain="chat".
      2. Full LLM intent extraction via IntentEngine (force_api=True),
         with active project context pre-injected for continuations.

    Parameters
    ----------
    message    : Raw user message.
    session_id : Used to load project context for the intent extraction.

    Returns
    -------
    Tuple[str, str, IntentModel] — (action, content, intent_model)
    """
    from core.intent_engine import extract_intent, intent_to_action, IntentModel
    from core.context_memory import build_context_summary

    msg = message.strip()

    # 1. Explicit command prefix — highest priority, no LLM call
    for action, prefixes in COMMAND_ALIASES.items():
        for prefix in prefixes:
            if msg.lower().startswith(prefix.lower()):
                content = re.sub(r"^\S+\s*", "", msg, count=1).strip() or msg
                intent = IntentModel(
                    goal=content[:120],
                    domain="chat",
                    ambiguity_score=0.1,
                )
                return action, content, intent

    # 2. Full intent extraction with project context
    context_summary = build_context_summary(session_id)
    intent_model = extract_intent(msg, context_summary or None)
    action = intent_to_action(intent_model)
    return action, msg, intent_model
