"""
BaseAgent — shared interface for all JARVIS specialized agents.

Every agent:
  - has a unique ROLE name and SYSTEM_PROMPT
  - exposes run(message, history) → str
  - exposes stream(message, history) → Generator[str, None, None]
  - tracks token usage per call
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Generator

from core.jarvis_persona import build_agent_prompt
from services.llm_service import call_llm, call_llm_stream

log = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Structured output returned by every agent."""

    agent: str
    response: str
    usage: dict = field(default_factory=dict)   # {"prompt_tokens": n, "completion_tokens": n}
    metadata: dict = field(default_factory=dict)  # arbitrary extra info per agent


class BaseAgent:
    """
    Abstract base for all specialized agents.

    Subclasses MUST define:
      ROLE        : str   — short identifier, e.g. "dev", "security"
      SYSTEM_PROMPT : str — full system prompt injected as the first message
    """

    ROLE: str = "base"
    SYSTEM_PROMPT: str = "You are a helpful AI assistant."

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._log = logging.getLogger(f"agents.{self.ROLE}")

    # ── Core API ───────────────────────────────────────────────────────────────

    def run(
        self,
        message: str,
        history: list[dict] | None = None,
        force_local: bool = False,
        force_api: bool = False,
    ) -> AgentResult:
        """
        Execute the agent synchronously.

        Args:
            message:      The user input or inter-agent message.
            history:      Prior conversation turns (list of {role, content}).
            force_local:  Route to local Ollama regardless of complexity.
            force_api:    Route to external API regardless of complexity.

        Returns:
            AgentResult with the agent's response.
        """
        messages = self._build_messages(message, history)
        self._log.info("[%s] run — %d chars", self.ROLE, len(message))

        response = call_llm(
            messages,
            force_local=force_local,
            force_api=force_api,
        )

        return AgentResult(
            agent=self.ROLE,
            response=response,
        )

    def stream(
        self,
        message: str,
        history: list[dict] | None = None,
        force_local: bool = False,
        force_api: bool = False,
    ) -> Generator[str, None, None]:
        """
        Execute the agent with streaming output.

        Yields raw text chunks.
        """
        messages = self._build_messages(message, history)
        self._log.info("[%s] stream — %d chars", self.ROLE, len(message))

        yield from call_llm_stream(
            messages,
            force_local=force_local,
            force_api=force_api,
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _build_messages(
        self,
        message: str,
        history: list[dict] | None,
    ) -> list[dict]:
        """
        Assemble the messages list:
          [system_prompt] + history (optional) + [user message]
        """
        msgs: list[dict] = [
            {"role": "system", "content": build_agent_prompt(self.ROLE, self.SYSTEM_PROMPT)}
        ]

        if history:
            for turn in history:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    msgs.append({"role": role, "content": content})

        msgs.append({"role": "user", "content": message})
        return msgs

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} role={self.ROLE!r}>"
