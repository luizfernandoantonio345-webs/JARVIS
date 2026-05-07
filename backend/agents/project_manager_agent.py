"""
Project Manager Agent — FASE 2: Orchestration Master

Tracks the active project state across the session and provides:
  - Formatted status summary for LLM context injection
  - Next recommended action (LLM-driven, single step)
  - File registration coordination with context_memory

Used by IntentOrchestrator and chat_service to maintain project awareness
across multiple user messages.

Usage
-----
>>> from agents.project_manager_agent import get_project_manager
>>> pm = get_project_manager()
>>> status = pm.get_project_status("sess-001")
>>> pm.register_files("sess-001", ["main.py", "models.py"])
>>> next_step = pm.get_next_action("sess-001", "add authentication")
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.base_agent import BaseAgent, AgentResult

log = logging.getLogger(__name__)


class ProjectManagerAgent(BaseAgent):
    """
    Manages active project state and provides next-action intelligence.

    Reads from context_memory (active_project + context_memory tables).
    Writes file paths back to context_memory via add_project_file().
    """

    ROLE = "project_manager"

    SYSTEM_PROMPT = """\
You are the Project Manager Agent inside JARVIS.

## Role
Track the current project state and recommend the single most important next action.

## Responsibilities
- Maintain awareness of what has been built (files, stack, domain)
- Identify the gap between current state and the stated goal
- Recommend one concrete, actionable next step per request

## Output Format (status requests)
**Project**: <goal>
**Domain**: <domain>
**Status**: <active | completed | blocked>
**Stack**: <comma-separated technologies>
**Files created**: <comma-separated paths or "none yet">
**Next action**: <single sentence — the most important thing to do now>

## Output Format (next-action requests)
One sentence only: what JARVIS should do next. Max 20 words.
Examples:
  "Create the FastAPI authentication middleware with JWT token validation."
  "Add SQLAlchemy models for User and Session tables."
  "Write unit tests for the payment processing module."
"""

    # ── Public methods ─────────────────────────────────────────────────────────

    def get_project_status(self, session_id: str) -> str:
        """
        Return a formatted project status string.
        Reads from context_memory — never raises, always returns a string.
        """
        try:
            from core.context_memory import get_active_project, get_recent_intents

            project = get_active_project(session_id)
            if not project or not project.get("goal"):
                return "Nenhum projeto ativo nesta sessão."

            stack_str = (
                ", ".join(project["stack"]) if project["stack"] else "não definida"
            )
            files_str = (
                ", ".join(project["files"][:10]) if project["files"] else "nenhum ainda"
            )

            lines = [
                f"**Projeto**: {project['goal']}",
                f"**Domínio**: {project['domain']}",
                f"**Stack**: {stack_str}",
                f"**Status**: {project['status']}",
                f"**Arquivos criados**: {files_str}",
            ]

            # Append goal history for context
            recent = get_recent_intents(session_id, limit=4)
            goals = [
                r["intent"].get("goal", "")
                for r in recent
                if r["intent"].get("domain") not in (None, "chat")
                and r["intent"].get("goal")
            ]
            if goals:
                lines.append(f"**Histórico de ações**: {' → '.join(goals[:3])}")

            return "\n".join(lines)

        except Exception as exc:
            log.warning("ProjectManagerAgent.get_project_status failed: %s", exc)
            return "Status do projeto indisponível."

    def get_next_action(self, session_id: str, intent_goal: str = "") -> str:
        """
        Ask the LLM to recommend the single most important next action.

        Uses force_local=True (cheap call — just needs basic reasoning).
        Falls back to a generic message on failure.
        """
        status = self.get_project_status(session_id)

        parts = [f"Current project state:\n{status}"]
        if intent_goal:
            parts.append(f"\nMost recent user intent: {intent_goal}")
        parts.append(
            "\nWhat is the single most important next action JARVIS should take? "
            "One sentence, max 20 words, be specific."
        )

        try:
            result = self.run("\n".join(parts), force_local=True)
            return result.response.strip()
        except Exception as exc:
            log.warning("ProjectManagerAgent.get_next_action failed: %s", exc)
            return "Continue building the project incrementally."

    def register_files(self, session_id: str, file_paths: list[str]) -> None:
        """
        Record newly created files into the active project's file list.
        Silently ignores errors — never breaks the calling pipeline.
        """
        try:
            from core.context_memory import add_project_file
            for fp in file_paths:
                if fp.strip():
                    add_project_file(session_id, fp.strip())
            log.debug(
                "ProjectManagerAgent: registered %d file(s) for session %s",
                len(file_paths), session_id,
            )
        except Exception as exc:
            log.warning("ProjectManagerAgent.register_files failed: %s", exc)

    def build_prompt_context(self, session_id: str) -> str:
        """
        Build a compact project context string suitable for LLM prompt injection.

        Returns empty string if no project is active.
        Used by chat_service to enrich prompts beyond FASE 1 context_summary.
        """
        try:
            from core.context_memory import build_context_summary
            return build_context_summary(session_id)
        except Exception as exc:
            log.warning("ProjectManagerAgent.build_prompt_context failed: %s", exc)
            return ""


# ── Module-level singleton factory ────────────────────────────────────────────

_instance: Optional[ProjectManagerAgent] = None


def get_project_manager() -> ProjectManagerAgent:
    """Return the shared ProjectManagerAgent singleton."""
    global _instance
    if _instance is None:
        _instance = ProjectManagerAgent()
    return _instance
