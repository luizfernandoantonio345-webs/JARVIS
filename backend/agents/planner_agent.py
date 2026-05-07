"""
PlannerAgent — breaks a high-level goal into a structured JSON execution plan.

Output is always a structured JSON plan consumed by AgentManager.
"""

from __future__ import annotations

import json
import logging
import re

from agents.base_agent import BaseAgent, AgentResult

log = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    ROLE = "planner"

    SYSTEM_PROMPT = """\
You are the Planner Agent inside the JARVIS multi-agent system.

## Role
Decompose a high-level user goal into an ordered, structured execution plan.

## Output Format
Reply ONLY with valid JSON — no prose, no markdown fences:

{
  "goal": "<one-sentence summary of the goal>",
  "steps": [
    {
      "id": 1,
      "agent": "<coder|reviewer|security|executor>",
      "action": "<what this step does>",
      "input": "<specific instruction for the agent>",
      "depends_on": []
    }
  ]
}

## Rules
- Maximum 5 steps total
- Each step must be assigned to exactly ONE agent: coder, reviewer, security, or executor
- reviewer step MUST come after coder step
- security step MUST come before executor step (when both are present)
- depends_on lists the id(s) of steps this step requires
- Be specific: the assigned agent must understand the input without further context

## Agent Capabilities
- coder: writes code, creates files, implements features
- reviewer: validates code quality, suggests improvements, checks logic
- security: scans for vulnerabilities, blocks dangerous operations
- executor: runs commands, starts servers, tests endpoints

## Example
Goal: "Create a FastAPI hello-world API"
{
  "goal": "Create a FastAPI hello-world API",
  "steps": [
    {"id": 1, "agent": "coder", "action": "write code", "input": "Write a FastAPI app in main.py with a GET / route returning {message: 'Hello World'}", "depends_on": []},
    {"id": 2, "agent": "reviewer", "action": "review code", "input": "Review the FastAPI code for correctness and best practices", "depends_on": [1]},
    {"id": 3, "agent": "security", "action": "security scan", "input": "Scan the FastAPI code for OWASP vulnerabilities", "depends_on": [2]},
    {"id": 4, "agent": "executor", "action": "run project", "input": "Run the FastAPI project with uvicorn", "depends_on": [3]}
  ]
}
"""

    def plan(self, goal: str, history: list[dict] | None = None) -> dict:
        """
        Generate a structured plan for the given goal.

        Returns:
            dict with "goal" and "steps" keys, or {"error": "..."} on failure.
        """
        result = self.run(goal, history, force_local=False)
        raw = result.response.strip()

        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

        try:
            plan = json.loads(cleaned)
            if "steps" not in plan:
                raise ValueError("Missing 'steps' key")
            # Enforce max 5 steps
            if len(plan["steps"]) > 5:
                plan["steps"] = plan["steps"][:5]
            return plan
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("PlannerAgent: failed to parse plan JSON: %s", exc)
            # Return a minimal single-step fallback
            return {
                "goal": goal,
                "steps": [
                    {
                        "id": 1,
                        "agent": "coder",
                        "action": "implement",
                        "input": goal,
                        "depends_on": [],
                    }
                ],
            }
