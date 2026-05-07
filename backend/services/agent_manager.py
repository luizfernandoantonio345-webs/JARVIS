"""
AgentManager — orchestrates multi-agent workflows in JARVIS.

Flow:
  User Goal → PlannerAgent → [CoderAgent → ReviewerAgent → SecurityAgent → ExecutorAgent]

Rules:
  - Max 5 steps per task
  - Each step assigned to ONE agent
  - ReviewerAgent must approve before ExecutorAgent runs
  - SecurityAgent can BLOCK execution
  - No recursive agent calls
  - Fail gracefully with structured errors

Usage:
    from services.agent_manager import AgentManager
    manager = AgentManager()
    result = manager.run(goal="create a FastAPI app", agent_mode=True)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

MAX_STEPS = 5


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class AgentStepResult:
    step_id: int
    agent: str
    action: str
    input: str
    output: str
    success: bool
    blocked: bool = False
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "agent": self.agent,
            "action": self.action,
            "output": self.output,
            "success": self.success,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


@dataclass
class AgentManagerResult:
    goal: str
    steps_executed: list[AgentStepResult] = field(default_factory=list)
    final_output: str = ""
    success: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps_executed": [s.to_dict() for s in self.steps_executed],
            "final_output": self.final_output,
            "success": self.success,
            "error": self.error,
        }

    def to_text(self) -> str:
        lines = [f"## Goal: {self.goal}", ""]
        for s in self.steps_executed:
            status = "✅" if s.success else ("🚫" if s.blocked else "❌")
            lines.append(f"### Step {s.step_id} — {s.agent} ({s.action}) {status}")
            if s.blocked:
                lines.append(f"**BLOCKED**: {s.block_reason}")
            else:
                lines.append(s.output[:1000])
            lines.append("")
        if self.final_output:
            lines += ["---", "## Final Result", self.final_output]
        if self.error:
            lines += ["---", f"**Error**: {self.error}"]
        return "\n".join(lines)


# ── AgentManager ───────────────────────────────────────────────────────────────

class AgentManager:
    """
    Orchestrates multi-agent execution pipeline.

    Maintains:
    - A running context passed between agents
    - Security gate that can block execution
    - Reviewer gate that must approve before execution
    """

    def __init__(self) -> None:
        self._log = logging.getLogger("services.agent_manager")

    def run(
        self,
        goal: str,
        history: list[dict] | None = None,
        agent_mode: bool = True,
        session_id: str = "",
    ) -> AgentManagerResult:
        """
        Execute a multi-agent pipeline for the given goal.

        Args:
            goal:        High-level user objective.
            history:     Prior conversation context.
            agent_mode:  If False, falls back to single-agent dev execution.
            session_id:  Optional session identifier for the message bus channel.

        Returns:
            AgentManagerResult — always populated, never raises.
        """
        if not agent_mode:
            return self._single_agent_fallback(goal, history)

        self._log.info("AgentManager: starting pipeline for goal: %s", goal[:100])

        # ── MessageBus: create channel for this task ───────────────────────────
        channel_id = session_id or f"task-{uuid.uuid4().hex[:8]}"
        try:
            from services.message_bus import get_bus, BusMessage, MsgType
            bus = get_bus()
            bus.create_channel(channel_id)
            bus.publish(channel_id, BusMessage.task(
                from_agent="manager", to_agent="planner",
                task=goal,
                context=channel_id,
            ))
        except Exception as exc:
            self._log.debug("MessageBus unavailable: %s", exc)
            bus = None

        # ── SelfImprover: record context ───────────────────────────────────────
        try:
            from services.self_improver import get_improver
            improver = get_improver()
        except Exception:
            improver = None

        result = AgentManagerResult(goal=goal)
        context = ""  # Accumulated context passed between agents

        # ── Step 1: Plan ───────────────────────────────────────────────────────
        t0 = time.monotonic()
        try:
            plan = self._plan(goal, history)
        except Exception as exc:
            result.error = f"Planning failed: {exc}"
            result.final_output = f"❌ {result.error}"
            if improver:
                improver.record_failure("planner", "plan", str(exc), session_id=channel_id)
            return result

        if improver:
            improver.record_success("planner", "plan", time.monotonic() - t0, session_id=channel_id)

        steps = plan.get("steps", [])
        if not steps:
            result.error = "Planner returned empty plan"
            result.final_output = f"❌ {result.error}"
            return result

        # Cap steps
        steps = steps[:MAX_STEPS]

        # ── Step execution ─────────────────────────────────────────────────────
        last_code = ""
        reviewer_approved = True  # Default allow if no reviewer step

        for step_def in steps:
            step_id    = step_def.get("id", 0)
            agent_name = step_def.get("agent", "coder")
            action     = step_def.get("action", "implement")
            inp        = step_def.get("input", goal)

            # Check if bus has received a BLOCK signal for this channel
            if bus:
                try:
                    from services.message_bus import MsgType as MT
                    if bus.is_blocked(channel_id):
                        result.error = "Pipeline blocked via message bus"
                        result.final_output = "🚫 Execution blocked by security gate."
                        return result
                except Exception as exc:
                    log.debug("[services.agent_manager] suppressed exception", exc_info=exc)
                    pass

            # Build step context from prior outputs
            step_input = inp
            if context:
                step_input = f"Prior context:\n{context[:2000]}\n\nTask:\n{inp}"

            self._log.info("AgentManager: step %d — %s: %s", step_id, agent_name, action[:60])

            t_step = time.monotonic()
            try:
                step_result = self._dispatch_step(
                    step_id=step_id,
                    agent_name=agent_name,
                    action=action,
                    step_input=step_input,
                    last_code=last_code,
                    reviewer_approved=reviewer_approved,
                    history=history,
                )
            except Exception as exc:
                self._log.error("AgentManager: step %d raised: %s", step_id, exc)
                step_result = AgentStepResult(
                    step_id=step_id,
                    agent=agent_name,
                    action=action,
                    input=step_input,
                    output=f"❌ Step error: {exc}",
                    success=False,
                )

            step_dur = time.monotonic() - t_step
            result.steps_executed.append(step_result)

            # ── MessageBus: publish step result ───────────────────────────────
            if bus:
                try:
                    if step_result.blocked:
                        bus.publish(channel_id, BusMessage.block(
                            from_agent=agent_name, to_agent="manager",
                            payload={"reason": step_result.block_reason, "step": step_id},
                        ))
                    elif step_result.success:
                        bus.publish(channel_id, BusMessage.result(
                            from_agent=agent_name, to_agent="manager",
                            payload={"output": step_result.output[:500], "step": step_id},
                        ))
                    else:
                        bus.publish(channel_id, BusMessage.error(
                            from_agent=agent_name, to_agent="manager",
                            payload={"output": step_result.output[:300], "step": step_id},
                        ))
                except Exception as exc:
                    log.debug("[services.agent_manager] suppressed exception", exc_info=exc)
                    pass

            # ── SelfImprover: record step outcome ─────────────────────────────
            if improver:
                if step_result.success:
                    improver.record_success(agent_name, action, step_dur, channel_id)
                else:
                    improver.record_failure(agent_name, action,
                                            step_result.block_reason or step_result.output[:80],
                                            step_dur, channel_id)

            if step_result.blocked:
                result.error = f"Blocked at step {step_id}: {step_result.block_reason}"
                result.final_output = f"🚫 {result.error}"
                return result

            # Update shared context
            context = step_result.output

            # Track last code output for reviewer/security
            if agent_name in ("coder", "dev"):
                last_code = step_result.output

            # Track reviewer approval
            if agent_name == "reviewer":
                reviewer_approved = "REQUEST_CHANGES" not in step_result.output.upper()

        # ── Final output ───────────────────────────────────────────────────────
        if result.steps_executed:
            last = result.steps_executed[-1]
            result.final_output = last.output
            result.success = last.success
        else:
            result.final_output = "No steps were executed."

        return result

    # ── Private helpers ────────────────────────────────────────────────────────

    def _plan(self, goal: str, history: list[dict] | None) -> dict:
        """Run PlannerAgent and return the plan dict."""
        from services.agent_registry import get_agent
        planner = get_agent("planner")
        # PlannerAgent has a .plan() convenience method
        if hasattr(planner, "plan"):
            return planner.plan(goal, history)  # type: ignore[attr-defined]
        result = planner.run(goal, history)
        import json, re
        raw = re.sub(r"```(?:json)?\s*", "", result.response).strip().rstrip("`")
        return json.loads(raw)

    def _dispatch_step(
        self,
        step_id: int,
        agent_name: str,
        action: str,
        step_input: str,
        last_code: str,
        reviewer_approved: bool,
        history: list[dict] | None,
    ) -> AgentStepResult:
        """Route a plan step to the correct agent with safety gates."""
        from services.agent_registry import get_agent

        # ── Security gate: block executor if security found critical issues ──
        if agent_name == "executor" and not reviewer_approved:
            return AgentStepResult(
                step_id=step_id,
                agent=agent_name,
                action=action,
                input=step_input,
                output="",
                success=False,
                blocked=True,
                block_reason="Reviewer requested changes — execution blocked until code is fixed.",
            )

        try:
            agent = get_agent(agent_name)
        except KeyError:
            # Unknown agent: use dev as fallback
            self._log.warning("Unknown agent %r — falling back to dev", agent_name)
            agent = get_agent("dev")

        # ── Reviewer: pass code explicitly ────────────────────────────────────
        if agent_name == "reviewer" and last_code:
            if hasattr(agent, "review"):
                review = agent.review(last_code, context=step_input, history=history)  # type: ignore[attr-defined]
                import json
                output = json.dumps(review, indent=2)
                verdict = review.get("verdict", "APPROVE")
                return AgentStepResult(
                    step_id=step_id,
                    agent=agent_name,
                    action=action,
                    input=step_input,
                    output=output,
                    success=verdict == "APPROVE",
                )

        # ── Security agent: can block ──────────────────────────────────────────
        if agent_name == "security":
            agent_result = agent.run(step_input, history)
            output = agent_result.response
            # Block if critical vulnerability found
            is_blocked = any(
                kw in output.upper()
                for kw in ("CRITICAL", "HIGH RISK", "BLOCKED", "DANGEROUS")
            )
            if is_blocked:
                return AgentStepResult(
                    step_id=step_id,
                    agent=agent_name,
                    action=action,
                    input=step_input,
                    output=output,
                    success=False,
                    blocked=True,
                    block_reason="Security agent detected critical vulnerability.",
                )
            return AgentStepResult(
                step_id=step_id,
                agent=agent_name,
                action=action,
                input=step_input,
                output=output,
                success=True,
            )

        # ── Executor agent ────────────────────────────────────────────────────
        if agent_name == "executor":
            if hasattr(agent, "execute_command") and step_input.strip():
                agent_result = agent.execute_command(step_input)  # type: ignore[attr-defined]
            else:
                agent_result = agent.run(step_input, history)
            return AgentStepResult(
                step_id=step_id,
                agent=agent_name,
                action=action,
                input=step_input,
                output=agent_result.response,
                success="❌" not in agent_result.response,
            )

        # ── Default: run agent normally ───────────────────────────────────────
        agent_result = agent.run(step_input, history)
        return AgentStepResult(
            step_id=step_id,
            agent=agent_name,
            action=action,
            input=step_input,
            output=agent_result.response,
            success=True,
        )

    def _single_agent_fallback(self, goal: str, history: list[dict] | None) -> AgentManagerResult:
        """Fallback: route to DevAgent directly (agent_mode=False)."""
        from services.agent_registry import get_agent
        self._log.info("AgentManager: single-agent fallback for goal: %s", goal[:80])
        try:
            agent = get_agent("dev")
            agent_result = agent.run(goal, history)
            return AgentManagerResult(
                goal=goal,
                steps_executed=[
                    AgentStepResult(
                        step_id=1,
                        agent="dev",
                        action="implement",
                        input=goal,
                        output=agent_result.response,
                        success=True,
                    )
                ],
                final_output=agent_result.response,
                success=True,
            )
        except Exception as exc:
            return AgentManagerResult(
                goal=goal,
                final_output=f"❌ Agent error: {exc}",
                success=False,
                error=str(exc),
            )


# ── Singleton ──────────────────────────────────────────────────────────────────

_manager: AgentManager | None = None


def get_manager() -> AgentManager:
    """Return the global AgentManager singleton."""
    global _manager
    if _manager is None:
        _manager = AgentManager()
    return _manager
