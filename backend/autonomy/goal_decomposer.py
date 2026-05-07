"""
goal_decomposer — FASE 12B

Receives a high-level daily goal and decomposes it into a structured workplan
with prioritised tasks, saved to autonomy/workplan_{date}.json.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

WORKPLAN_DIR = Path(__file__).parent


def _today_str() -> str:
    return date.today().isoformat()


class GoalDecomposer:
    """
    Uses the LLM to decompose a daily goal into a structured task list.
    """

    def decompose(self, goal: str, context: str = "") -> dict:
        """
        Decompose goal into workplan dict.

        Returns:
            Workplan dict with tasks list.
        """
        prompt = _DECOMPOSE_PROMPT.format(goal=goal, context=context or "Nenhum contexto adicional.")
        try:
            from services.llm_service import call_llm
            raw = call_llm([{"role": "user", "content": prompt}], force_api=True)
            workplan = self._parse_workplan(raw, goal)
        except Exception as exc:
            log.warning("GoalDecomposer: LLM call failed, using stub: %s", exc)
            workplan = self._stub_workplan(goal)

        workplan["date"] = _today_str()
        workplan["created_at"] = datetime.utcnow().isoformat()
        workplan["status"] = "pending"
        return workplan

    def save(self, workplan: dict) -> Path:
        path = WORKPLAN_DIR / f"workplan_{workplan.get('date', _today_str())}.json"
        path.write_text(json.dumps(workplan, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("GoalDecomposer: saved workplan to %s", path)
        return path

    def load_today(self) -> dict | None:
        path = WORKPLAN_DIR / f"workplan_{_today_str()}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                log.debug("[autonomy.goal_decomposer] suppressed exception", exc_info=exc)
                pass
        return None

    def update_task_status(self, workplan: dict, task_id: int, status: str, notes: str = "") -> dict:
        for t in workplan.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
                t["notes"] = notes
                t["completed_at"] = datetime.utcnow().isoformat() if status == "done" else None
        return workplan

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_workplan(self, raw: str, goal: str) -> dict:
        """Extract JSON workplan from LLM response."""
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            block = m.group(1)
        else:
            m = re.search(r"(\{[\s\S]+\})", raw)
            block = m.group(1) if m else "{}"
        try:
            data = json.loads(block)
            # Normalise
            if "tasks" not in data:
                data = {"goal": goal, "tasks": [], "strategy": "sequencial"}
            for i, t in enumerate(data.get("tasks", []), 1):
                t.setdefault("id", i)
                t.setdefault("status", "pending")
                t.setdefault("priority", "medium")
                t.setdefault("estimated_hours", 1.0)
            data.setdefault("estimated_total",
                            sum(t.get("estimated_hours", 1) for t in data.get("tasks", [])))
            return data
        except Exception:
            return self._stub_workplan(goal)

    def _stub_workplan(self, goal: str) -> dict:
        return {
            "goal": goal,
            "tasks": [
                {"id": 1, "description": goal, "estimated_hours": 2.0,
                 "priority": "high", "status": "pending"},
            ],
            "estimated_total": 2.0,
            "strategy": "sequencial",
        }


_DECOMPOSE_PROMPT = """
Você é o planejador do Jarvis. O usuário definiu o seguinte objetivo para hoje:

"{goal}"

Contexto adicional:
{context}

Decompõe esse objetivo em tarefas concretas e ordenadas. Responda APENAS com um
bloco JSON no seguinte formato (sem texto extra antes ou depois):

```json
{{
  "goal": "descrição resumida do objetivo",
  "tasks": [
    {{"id": 1, "description": "...", "estimated_hours": 1.5, "priority": "high"}},
    {{"id": 2, "description": "...", "estimated_hours": 0.5, "priority": "medium"}}
  ],
  "estimated_total": 2.0,
  "strategy": "sequencial"
}}
```

Regras:
- Máximo 8 tarefas
- priority: "high", "medium" ou "low"
- strategy: "sequencial" (uma por vez) ou "paralelo" (independentes)
- estimated_hours: estimativa realista em horas decimais
"""
