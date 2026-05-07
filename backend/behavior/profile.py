"""
profile — FASE 11B

Pydantic schema for Jarvis's Behavior Profile — a living document that
defines and evolves the operational personality of the system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class BehaviorProfile(BaseModel):
    """Operational personality profile for Jarvis."""

    # LLM routing preferences
    llm_routing: dict[str, str] = Field(
        default_factory=lambda: {
            "code_gen":  "claude",
            "analysis":  "claude",
            "quick":     "gpt-4o-mini",
            "default":   "ollama",
        },
        description="Map of task type → preferred LLM backend",
    )

    # Response verbosity
    verbosity: Literal["minimal", "normal", "detailed"] = "minimal"

    # Code style preferences
    code_style: dict[str, Any] = Field(
        default_factory=lambda: {
            "python": {
                "formatter": "black",
                "max_line": 88,
                "type_hints": True,
                "docstrings": "google",
            }
        },
        description="Per-language code style preferences",
    )

    # Test generation preference
    test_preference: Literal["always", "when_asked", "never"] = "always"

    # Autonomy risk tolerance
    risk_tolerance: Literal["low", "medium", "high"] = "medium"
    # low:    confirm all file writes
    # medium: confirm only destructive operations (delete, overwrite)
    # high:   act freely, only log

    # Confidence threshold before acting autonomously (0.0 – 1.0)
    escalation_threshold: float = Field(default=0.65, ge=0.0, le=1.0)

    # Maximum autonomous actions allowed per hour
    max_autonomous_actions_per_hour: int = Field(default=20, ge=1, le=200)

    # Observed behavioral patterns (populated by Profile Evolution)
    learned_patterns: list[dict[str, Any]] = Field(default_factory=list)

    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    update_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_llm_routing(self) -> "BehaviorProfile":
        valid_backends = {"ollama", "claude", "gpt-4o-mini", "openai", "auto"}
        for task, backend in self.llm_routing.items():
            if backend not in valid_backends:
                # Unknown backend — silently keep it (user may know best)
                pass
        return self

    def get_llm_for_task(self, task_type: str) -> str:
        """Return preferred LLM backend for a given task type."""
        return self.llm_routing.get(task_type, self.llm_routing.get("default", "ollama"))

    def prompt_snippet(self, task_type: str = "default") -> str:
        """
        Return a concise system-prompt snippet summarising relevant preferences
        for the given task type.  Injected by ProfileInjector.
        """
        lines = []

        # Verbosity
        v_map = {
            "minimal":  "Responda de forma concisa — apenas o resultado final, sem explicações extensas.",
            "normal":   "Use um nível de detalhe equilibrado nas respostas.",
            "detailed": "Forneça explicações detalhadas e passo a passo quando relevante.",
        }
        lines.append(v_map.get(self.verbosity, ""))

        # Code style (only for code-related tasks)
        if task_type in {"code_gen", "refactor", "fix", "default"}:
            py = self.code_style.get("python", {})
            if py:
                hints = []
                if py.get("type_hints"):
                    hints.append("type hints obrigatórios")
                if py.get("formatter"):
                    hints.append(f"formatter: {py['formatter']}")
                if py.get("max_line"):
                    hints.append(f"max {py['max_line']} chars/linha")
                if hints:
                    lines.append("Estilo Python: " + ", ".join(hints) + ".")

        # Tests
        t_map = {
            "always":     "Sempre gere testes unitários junto com o código.",
            "when_asked": "Gere testes somente quando solicitado.",
            "never":      "Não gere testes a menos que explicitamente pedido.",
        }
        lines.append(t_map.get(self.test_preference, ""))

        # Risk
        r_map = {
            "low":    "Confirme qualquer operação que modifique o sistema de arquivos antes de executar.",
            "medium": "Confirme apenas operações destrutivas (delete, sobrescrita). Outras, execute diretamente.",
            "high":   "Aja livremente sem solicitar confirmações — apenas registre as ações.",
        }
        lines.append(r_map.get(self.risk_tolerance, ""))

        return "\n".join(ln for ln in lines if ln)
