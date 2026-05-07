"""
LLM-based intent router.

Priority chain:
  1. Explicit command prefix  (/run, /analyze, ...)  → zero LLM cost
  2. Keyword regex patterns   (fast, no LLM cost)
  3. LLM classification       (natural language, force_local)
  4. Fallback                 → "chat"
"""

import re
import logging
from typing import Tuple

from services.llm_service import call_llm

log = logging.getLogger(__name__)

# ── 1. Explicit command aliases ───────────────────────────────────────────────
_COMMAND_ALIASES: dict[str, list[str]] = {
    "analyze":        ["/analyze", "/analisar", "/code", "/review"],
    "arch":           ["/arch", "/arquitetura", "/architecture", "/design"],
    "run":            ["/run", "/executar", "/exec", "/rodar"],
    "explain":        ["/explain", "/explique"],
    "refactor":       ["/refactor", "/refatorar", "/improve"],
    "web_search":     ["/search", "/buscar", "/web", "/find"],
    "github_analyze": ["/github", "/repo", "/gh"],
    "file_reader":    ["/file", "/read", "/open"],
    "system_monitor": ["/monitor", "/system", "/sysinfo", "/status"],
}

# ── 2. Keyword regex patterns (fast path — no LLM) ────────────────────────────
_KEYWORD_PATTERNS: list[Tuple[str, str]] = [
    ("github_analyze",
        r"\b(github\.com/|github repo|analyze repo|analyze.*repository|repo analysis)\b"),
    ("web_search",
        r"\b(search (the web|online|internet)|find online|look up|web search|"
        r"latest (news|info) (on|about)|current (price|weather|version))\b"),
    ("file_reader",
        r"\b(read (the |this )?(file|config|script)|show (file|contents of)|"
        r"open file|what.?s in)\b"),
    ("system_monitor",
        r"\b(system (status|monitor|metrics|health)|cpu (usage|load)|"
        r"memory usage|ram usage|running processes|disk usage)\b"),
    ("refactor",
        r"\b(refactor|refatorar|clean up (this|the) code|improve (this |the )?code|"
        r"make (this |the )?code (better|cleaner|faster))\b"),
    ("analyze",
        r"\b(analise|analisa|analisar|analys[ei]|review|bug|debug|"
        r"o que h[aá] de errado|what.?s wrong with|code review)\b"),
    ("arch",
        r"\b(arquitetura|architecture|system design|escal[aá]vel|microservice|"
        r"monolito|design pattern|infrastructure|how (to|should) (structure|design))\b"),
    ("run",
        r"\b(execute|execut[ae]|rode|run this|calcul[ae]|compute|resultado de)\b"),
    ("explain",
        r"\b(explique|explicar|o que [eé]|como funciona|explain|what is|"
        r"how does|what.?s (a|an|the)|tell me about)\b"),
]

# Valid intents the LLM may return
_VALID_INTENTS = {
    "analyze", "arch", "run", "explain", "chat",
    "refactor", "web_search", "github_analyze", "file_reader", "system_monitor",
}

# ── Objective detection ───────────────────────────────────────────────────────
_OBJECTIVE_SYSTEM = """\
Classify if the user message is a HIGH-LEVEL OBJECTIVE (True) or simple request (False).

Objective examples: "Build a full stack app", "Analyze this repo and improve it", "Create a trading dashboard".

Simple: "Explain Python", "Run this code".

Reply ONLY 'True' or 'False'. No prose.\
"""

def _is_objective_llm(message: str) -> bool:
    """LLM classify objective. force_local. Fallback False."""
    messages = [
        {"role": "system", "content": _OBJECTIVE_SYSTEM},
        {"role": "user", "content": message},
    ]
    try:
        raw = call_llm(messages, force_local=True)
        return raw.strip().lower() == 'true'
    except Exception:
        log.warning("Objective LLM failed — default False")
        return False

_OBJECTIVE_SYSTEM = """\
Classify if the user message is a HIGH-LEVEL OBJECTIVE (True) or simple request (False).

Objective examples: "Build a full stack app", "Analyze this repo and improve it", "Create a trading dashboard".

Simple: "Explain Python", "Run this code".

Reply ONLY 'True' or 'False'. No prose.\
"""

def _is_objective_llm(message: str) -> bool:
    """LLM classify objective. force_local. Fallback False."""
    messages = [
        {"role": "system", "content": _OBJECTIVE_SYSTEM},
        {"role": "user", "content": message},
    ]
    try:
        raw = call_llm(messages, force_local=True)
        return raw.strip().lower() == 'true'
    except Exception:
        log.warning("Objective LLM failed — default False")
        return False

# ── 3. LLM classification prompt ─────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are an intent classifier for an AI assistant. Classify the user message into EXACTLY ONE of:
  analyze        - review, debug, audit, or find bugs in code
  arch           - system design, architecture, or infrastructure planning
  run            - execute or compute code/scripts
  explain        - explain a concept, term, or technology
  refactor       - improve or clean up existing code
  web_search     - search the internet for current information
  github_analyze - analyze a GitHub repository
  file_reader    - read or inspect a local file
  system_monitor - check CPU, RAM, disk, or running processes
  chat           - general conversation, greetings, questions not fitting above

Rules:
- Reply with ONLY the single snake_case word (e.g. "web_search").
- No punctuation, no explanation, no extra words.
- When uncertain, reply "chat".\
"""


def _match_command_alias(message: str) -> Tuple[str, str] | None:
    """Return (action, stripped_content) if message starts with a command alias."""
    msg = message.strip()
    for action, prefixes in _COMMAND_ALIASES.items():
        for prefix in prefixes:
            if msg.lower().startswith(prefix.lower()):
                content = re.sub(r"^\S+\s*", "", msg, count=1).strip()
                return action, content or msg
    return None


def _match_keyword(message: str) -> str | None:
    """Return action if a keyword pattern matches. No LLM cost."""
    lower = message.lower()
    for action, pattern in _KEYWORD_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return action
    return None


def _classify_with_llm(message: str) -> str:
    """Ask the local LLM to classify intent. Returns a validated intent string."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": message},
    ]
    try:
        raw: str = call_llm(messages, force_local=True)
        intent = raw.strip().lower().split()[0]
        intent = re.sub(r"[^a-z_]", "", intent)
        if intent in _VALID_INTENTS:
            return intent
        log.warning("LLM returned unknown intent %r — falling back to 'chat'", raw)
    except Exception as exc:
        log.error("LLM router error: %s — falling back to 'chat'", exc)
    return "chat"


def route(message: str) -> Tuple[str, str]:
    """
    Determine (intent, content) for a user message.

    Returns
    -------
    intent  : one of _VALID_INTENTS
    content : the message body after stripping any command prefix
    """
    # Priority 1 — explicit slash command
    alias_match = _match_command_alias(message)
    if alias_match:
        return alias_match

    # Priority 2 — keyword regex (zero LLM cost)
    keyword_match = _match_keyword(message)
    if keyword_match:
        return keyword_match, message.strip()

    # Priority 3 — LLM classification
    intent = _classify_with_llm(message)
    return intent, message.strip()
