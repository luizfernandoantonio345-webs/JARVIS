"""
Intent Engine — FASE 1: JARVIS Intelligence Layer

Extracts structured intent from raw user messages via LLM (force_api=True).
Falls back to heuristic extraction when no API key is available.

IntentModel drives:
  - enhanced action routing via ai_router.route_with_intent()
  - context enrichment injected into every LLM prompt
  - agent dispatch in future phases

Usage
-----
>>> from core.intent_engine import extract_intent, intent_to_action
>>> intent = extract_intent("cria um site de mecânica com React e FastAPI", context_summary)
>>> action  = intent_to_action(intent)   # "arch"
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# ── Domains ────────────────────────────────────────────────────────────────────

DOMAINS: frozenset[str] = frozenset({
    "web_dev", "mobile", "api", "data", "security",
    "devops", "system", "automation", "analysis", "chat",
})

# Maps IntentModel.domain → existing action routing key used by planner/executor
_DOMAIN_TO_ACTION: dict[str, str] = {
    "web_dev":    "arch",
    "mobile":     "arch",
    "api":        "arch",
    "data":       "analyze",
    "security":   "analyze",
    "devops":     "run",
    "system":     "run",
    "automation": "run",
    "analysis":   "analyze",
    "chat":       "chat",
}

# ── LLM extraction prompt ──────────────────────────────────────────────────────

_INTENT_SYSTEM = """\
You are JARVIS Intent Analyzer. Extract structured intent from the user message.
Return ONLY valid JSON matching this exact schema — no markdown fences, no explanation:
{
  "goal": "primary objective in one clear sentence (max 15 words)",
  "domain": "ONE of: web_dev | mobile | api | data | security | devops | system | automation | analysis | chat",
  "subgoals": ["concrete sub-task 1", "sub-task 2"],
  "constraints": ["tech/framework/language/style constraint explicitly mentioned"],
  "expected_outputs": ["artifact user expects — e.g. 'working FastAPI app', 'API endpoint list'"],
  "ambiguity_score": 0.0
}
Strict rules:
- domain: choose the SINGLE most relevant domain
- subgoals: 2–5 actionable implementation steps; empty array [] for simple chat
- constraints: only what is EXPLICITLY mentioned (language, framework, DB, style)
- expected_outputs: concrete deliverables; empty array [] for conversational messages
- ambiguity_score: 0.0 = crystal-clear intent, 1.0 = very vague/ambiguous
- Simple greetings / chitchat: domain="chat", subgoals=[], expected_outputs=[], ambiguity_score ≤ 0.2
Return ONLY the JSON object. No other text.\
"""

# ── Data model ─────────────────────────────────────────────────────────────────

class IntentModel(BaseModel):
    goal: str = Field(description="Primary objective in one sentence")
    domain: str = Field(description="Task domain from DOMAINS set")
    subgoals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    ambiguity_score: float = Field(default=0.5, ge=0.0, le=1.0)


# ── Trivial message detection ──────────────────────────────────────────────────

_TRIVIAL_RE = re.compile(
    r"^(hi|hello|hey|oi|ol[aá]|tudo\s*bem|como\s*vai|ok|sim|n[aã]o"
    r"|thanks|obrigad[oa]|blz|valeu|tchau|bye|certo|entendi)[\W]*$",
    re.IGNORECASE,
)


def _is_trivial(message: str) -> bool:
    """Return True for greetings / very short messages — no LLM cost needed."""
    s = message.strip()
    return bool(_TRIVIAL_RE.match(s)) or len(s) < 12


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_intent(message: str, context: Optional[str] = None) -> IntentModel:
    """
    Extract structured intent from *message*.

    Uses force_api=True for quality on non-trivial inputs.
    Gracefully falls back to heuristic extraction on LLM failure or missing key.

    Parameters
    ----------
    message : Raw user message.
    context : Optional project context summary (from context_memory.build_context_summary).
              Injected before the user message to help the LLM understand continuations.
    """
    if _is_trivial(message):
        return _fallback_intent(message)

    # Local import to avoid circular deps at module load time
    from services.llm_service import call_llm  # noqa: PLC0415

    user_content = message
    if context:
        user_content = f"[Current project context]\n{context}\n\n[User message]\n{message}"

    messages = [
        {"role": "system", "content": _INTENT_SYSTEM},
        {"role": "user",   "content": user_content},
    ]

    try:
        raw = call_llm(messages, force_api=True)

        # Strip markdown fences if the model wraps JSON in them
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\n?```\s*$",           "", raw.strip())

        data: dict = json.loads(raw)

        # Normalise domain to the known set; coerce unknown values to "chat"
        if data.get("domain") not in DOMAINS:
            data["domain"] = "chat"

        # Clamp ambiguity score
        data["ambiguity_score"] = max(0.0, min(1.0, float(data.get("ambiguity_score", 0.5))))

        return IntentModel(**data)

    except Exception as exc:
        log.warning("IntentEngine LLM extraction failed (%s) — using heuristic fallback", exc)
        return _fallback_intent(message)


def intent_to_action(intent: IntentModel) -> str:
    """Map IntentModel.domain → existing action routing key (e.g. 'arch', 'analyze', 'chat')."""
    return _DOMAIN_TO_ACTION.get(intent.domain, "chat")


# ── Heuristic fallback ─────────────────────────────────────────────────────────

_DOMAIN_HINTS: list[tuple[str, list[str]]] = [
    ("web_dev",    ["site", "website", "frontend", "html", "css", "react", "vue",
                    "angular", "next", "svelte", "tailwind", "bootstrap"]),
    ("api",        ["api", "endpoint", "rest", "restful", "fastapi", "flask",
                    "django", "express", "graphql", "openapi", "swagger"]),
    ("security",   ["segurança", "security", "vulnerab", "exploit", "pentest",
                    "owasp", "xss", "sqli", "csrf", "hack", "cve", "auth bypass"]),
    ("data",       ["dados", "data", "análise", "análysis", "pandas", "sql",
                    "database", "csv", "excel", "visualiz", "machine learning", "ml"]),
    ("automation", ["automação", "automation", "automat", "script", "cron",
                    "schedule", "bot", "pipeline", "task", "workflow"]),
    ("devops",     ["docker", "kubernetes", "k8s", "ci/cd", "pipeline",
                    "deploy", "nginx", "terraform", "ansible", "helm"]),
    ("system",     ["sistema", "system", "monitor", "cpu", "memory", "ram",
                    "process", "terminal", "shell", "comando", "command"]),
    ("analysis",   ["analisa", "analise", "analisar", "review", "analyz",
                    "debug", "debugar", "bug", "erro", "error", "traceback"]),
    ("mobile",     ["mobile", "android", "ios", "flutter", "react native",
                    "kotlin", "swift", "app mobile"]),
]


def _fallback_intent(message: str) -> IntentModel:
    """Heuristic intent extraction — no LLM, no I/O."""
    msg_lower = message.lower()

    domain = "chat"
    for d, hints in _DOMAIN_HINTS:
        if any(h in msg_lower for h in hints):
            domain = d
            break

    # Shorter messages tend to be more ambiguous
    length = len(message.strip())
    ambiguity = round(max(0.05, min(0.95, 1.0 - length / 250)), 2)

    return IntentModel(
        goal=message.strip()[:120],
        domain=domain,
        subgoals=[],
        constraints=[],
        expected_outputs=[],
        ambiguity_score=ambiguity,
    )
