"""
Raciocínio Chain-of-Thought Explícito — Phase 2 (~2 days)

Before every major LLM call / agent action, JARVIS writes explicit reasoning to
jarvis/thoughts/{trace_id}.md (YYYY-MM-DD_HH-MMss-traceid.md)

Format:
# Thought Trace ID: {trace_id}
**Timestamp:** {ts}
**Context:** {context summary}
**Input:** {user_query / goal}
**Reasoning:** [LLM-generated CoT steps]
**Decision:** {planned action / agents / params}
**Confidence:** low/medium/high
**Risk:** {score}

Dashboard shows current thought live.

Usage:
  with trace_span("agent_plan"):
    thought = await ThoughtLogger.generate_cot(
      goal, context, trace_id=get_current_trace_id()
    )
    ThoughtLogger.persist(thought)
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

from core.telemetry import get_current_trace_id
from services.llm_service import call_llm

log = logging.getLogger(__name__)

THOUGHTS_DIR = Path(__file__).parent.parent / "jarvis" / "thoughts"
THOUGHTS_DIR.mkdir(parents=True, exist_ok=True)


class Thought:
    trace_id: str
    timestamp: str
    context: str
    goal: str
    reasoning: str
    decision: str
    confidence: str  # "low" | "medium" | "high"
    risk_score: float

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_markdown(self) -> str:
        return f"""# Thought Trace ID: {self.trace_id}

**Timestamp:** {self.timestamp}

**Context:** {self.context[:200]}...

**Goal:** {self.goal}

**Reasoning:** {self.reasoning}

**Decision:** {self.decision}

**Confidence:** {self.confidence}

**Risk:** {self.risk_score:.1f}"""


class ThoughtLogger:
    @staticmethod
    def get_trace_id() -> str:
        return get_current_trace_id() or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    @staticmethod
    async def generate_cot(goal: str, context: str = "", trace_id: Optional[str] = None) -> Thought:
        """
        LLM generates CoT reasoning before action.
        """
        trace_id = trace_id or ThoughtLogger.get_trace_id()
        system_prompt = """\
You are JARVIS. Before acting, write explicit Chain-of-Thought reasoning.

Format EXACTLY as JSON (no markdown):
{
  "reasoning": "3-5 bullet steps explaining thought process",
  "decision": "clear next action / agent / params",
  "confidence": "low|medium|high",
  "risk_score": 0.0-100.0
}

Be concise. Focus on WHY this decision.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: {context}\n\nGoal: {goal}"}
        ]

        try:
            raw = await asyncio.to_thread(call_llm, messages, force_api=True)
            data = json.loads(raw.strip("```json\n").strip("```"))
            return Thought(
                trace_id=trace_id,
                timestamp=datetime.datetime.now().isoformat(),
                context=context,
                goal=goal,
                reasoning=data.get("reasoning", "No reasoning generated."),
                decision=data.get("decision", "Undecided"),
                confidence=data.get("confidence", "medium"),
                risk_score=float(data.get("risk_score", 50.0))
            )
        except Exception as exc:
            log.warning("CoT generation failed: %s", exc)
            return Thought(
                trace_id=trace_id,
                timestamp=datetime.datetime.now().isoformat(),
                context=context,
                goal=goal,
                reasoning="Fallback: CoT generation error.",
                decision="Proceed with default plan.",
                confidence="low",
                risk_score=75.0
            )

    @staticmethod
    def persist(thought: Thought) -> Path:
        filename = f"{thought.timestamp.replace(':', '').replace('-', '').replace('.', '_')}-{thought.trace_id[:8]}.md"
        path = THOUGHTS_DIR / filename
        path.write_text(thought.to_markdown())
        log.info("CoT persisted: %s", path.name)
        return path

    @staticmethod
    def get_recent(n: int = 5) -> list[Path]:
        return sorted(THOUGHTS_DIR.glob("*.md"), reverse=True)[:n]


# Usage example:
# async def agent_plan(goal):
#   trace_id = get_current_trace_id()
#   thought = await ThoughtLogger.generate_cot(goal, trace_id=trace_id)
#   ThoughtLogger.persist(thought)

