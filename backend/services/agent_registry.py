"""
Agent Registry — central registry for all JARVIS specialized agents.

Usage:
    from services.agent_registry import get_agent, list_agents

    agent = get_agent("security")
    result = agent.run(message, history)

Agents registered:
  "dev"        → DevAgent
  "architect"  → ArchitectAgent
  "security"   → SecurityAgent
  "debugger"   → DebuggerAgent
  "planner"    → PlannerAgent   (Phase 5)
  "reviewer"   → ReviewerAgent  (Phase 5)
  "executor"   → ExecutorAgent  (Phase 5)
  "coder"      → DevAgent alias (Phase 5)
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent
from agents.dev_agent import DevAgent
from agents.architect_agent import ArchitectAgent
from agents.security_agent import SecurityAgent
from agents.debugger_agent import DebuggerAgent
from agents.planner_agent import PlannerAgent
from agents.reviewer_agent import ReviewerAgent
from agents.executor_agent import ExecutorAgent
from agents.system_agent import SystemAgent

log = logging.getLogger(__name__)

# ── Registry ──────────────────────────────────────────────────────────────

_REGISTRY: dict[str, BaseAgent] = {
    "dev":        DevAgent(),
    "architect":  ArchitectAgent(),
    "security":   SecurityAgent(),
    "debugger":   DebuggerAgent(),
    "planner":    PlannerAgent(),
    "reviewer":   ReviewerAgent(),
    "executor":   ExecutorAgent(),
    "system":     SystemAgent(),
}

# Aliases for natural language routing
_ALIASES: dict[str, str] = {
    "developer":   "dev",
    "coder":       "dev",      # Phase 5: coder maps to dev
    "coding":      "dev",
    "arch":        "architect",
    "architecture":"architect",
    "design":      "architect",
    "sec":         "security",
    "vuln":        "security",
    "vulnerability": "security",
    "pentest":     "security",
    "debug":       "debugger",
    "bug":         "debugger",
    "fix":         "debugger",
    "error":       "debugger",
    "plan":        "planner",
    "review":      "reviewer",
    "exec":        "executor",
    "run":         "executor",
    "os":          "system",
    "browser":     "system",
    "clipboard":   "system",
}


def get_agent(role: str) -> BaseAgent:
    """
    Return the agent instance for the given role.

    Accepts both canonical names ("security") and aliases ("sec", "vuln").

    Raises:
        KeyError: if the role is not registered.
    """
    canonical = _ALIASES.get(role.lower(), role.lower())
    agent = _REGISTRY.get(canonical)
    if agent is None:
        available = list_agents()
        raise KeyError(
            f"Unknown agent role: {role!r}. Available: {available}"
        )
    log.debug("Registry: resolved %r → %r", role, canonical)
    return agent


def list_agents() -> list[str]:
    """Return the canonical role names of all registered agents."""
    return list(_REGISTRY.keys())


def agent_info() -> list[dict]:
    """Return metadata for all registered agents (for API discovery)."""
    descriptions = {
        "dev":       "Writes clean, production-ready code in any language.",
        "architect": "Designs scalable system architectures and data flows.",
        "security":  "Detects OWASP Top 10 vulnerabilities and suggests secure fixes.",
        "debugger":  "Diagnoses bugs, traces root causes, and produces minimal fixes.",
        "planner":   "Breaks a high-level goal into a structured multi-step plan.",
        "reviewer":  "Validates code quality and correctness; issues APPROVE or REQUEST_CHANGES.",
        "executor":  "Safely runs commands and projects via the shell whitelist.",
        "system":    "OS/browser automation: read files, browse URLs, manage clipboard.",
    }
    return [
        {
            "role":        role,
            "class":       agent.__class__.__name__,
            "description": descriptions.get(role, "Specialized JARVIS agent."),
        }
        for role, agent in _REGISTRY.items()
    ]
