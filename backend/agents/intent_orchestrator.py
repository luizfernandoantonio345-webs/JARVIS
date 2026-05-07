"""
Intent Orchestrator — FASE 2: Orchestration Master

Bridges FASE 1 IntentModel → domain-specific agent chain execution.

Routing table
-------------
  domain=web_dev/mobile/api  → architect → dev → reviewer → security
  domain=security            → security  → reviewer
  domain=analysis            → debugger  → reviewer
  domain=data                → dev       → reviewer
  domain=devops/system/automation → dev  → reviewer
  domain=chat or ambiguity > 0.75 → return None (standard pipeline handles it)

Design decisions
----------------
  • Fully SYNCHRONOUS — compatible with both sync (chat_service) and async
    contexts without event-loop gymnastics.
  • Uses call_llm(force_api=True) for all agent steps — quality first.
  • Critique-correction loop per task: max MAX_ROUNDS rounds.
  • Returns None to signal "fallthrough" — caller uses standard pipeline.

Usage
-----
>>> from agents.intent_orchestrator import get_intent_orchestrator
>>> result = get_intent_orchestrator().orchestrate(intent_model, raw_msg, "sess-001")
>>> if result:
...     return result.output   # final orchestrated response
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.intent_engine import IntentModel
from core.jarvis_persona import build_agent_prompt
from services.llm_service import call_llm

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

# Domains that benefit from multi-agent orchestration
_ORCHESTRATED_DOMAINS: frozenset[str] = frozenset({
    "web_dev", "mobile", "api", "data",
    "security", "devops", "system", "automation", "analysis",
})

# Domain → ordered list of agent roles to run
_DOMAIN_CHAIN: dict[str, list[str]] = {
    "web_dev":    ["architect", "dev", "reviewer", "security"],
    "mobile":     ["architect", "dev", "reviewer"],
    "api":        ["architect", "dev", "reviewer", "security"],
    "data":       ["dev", "reviewer"],
    "security":   ["security", "reviewer"],
    "devops":     ["dev", "reviewer"],
    "system":     ["dev", "reviewer"],
    "automation": ["dev", "reviewer"],
    "analysis":   ["debugger", "reviewer"],
}

MAX_ROUNDS = 2   # max critique-correction cycles per agent output

# ── Agent system prompts ───────────────────────────────────────────────────────

_AGENT_PROMPTS: dict[str, str] = {
    "architect": """\
You are the Architect Agent inside JARVIS.
Given a goal and constraints, produce:
1. System architecture overview (components and responsibilities)
2. File/module structure (directory tree)
3. Technology choices with brief rationale
4. Key interfaces and data models

Be specific and actionable — the Dev Agent will implement from this spec.
Reply in structured markdown.""",

    "dev": """\
You are the Dev Agent inside JARVIS — an elite software engineer.
Given a goal (and optionally an architecture spec), produce:
1. Complete, working code implementation ready to run
2. Brief explanation of key design decisions (2-3 sentences)

Rules:
- Write real, complete code — never pseudocode
- Follow language idioms (PEP 8 for Python, ESLint rules for JS/TS)
- Flag security concerns with inline comments
- If building on an architecture spec, follow it exactly""",

    "reviewer": """\
You are the Reviewer Agent inside JARVIS.
Evaluate the output for:
- Correctness: does it satisfy the stated goal?
- Completeness: are all required parts present?
- Quality: is the code idiomatic and free of obvious bugs?

Reply with exactly:
APPROVED — <one sentence reason>
or
REQUEST_CHANGES — <specific changes needed, bullet list>""",

    "security": """\
You are the Security Agent inside JARVIS.
Analyze the output for OWASP Top 10 vulnerabilities:
  A01 Broken Access Control, A02 Cryptographic Failures, A03 Injection (SQL/XSS/Command),
  A04 Insecure Design, A05 Security Misconfiguration, A07 Auth failures,
  A08 Software and Data Integrity Failures, A09 Logging failures.

Reply with:
SECURE — <brief assessment>
or
VULNERABILITIES_FOUND:
  - [SEVERITY] vulnerability description + fix suggestion""",

    "debugger": """\
You are the Debugger Agent inside JARVIS.
Analyze code or error output and:
1. Identify the root cause of each issue
2. Provide a corrected, complete implementation
3. Explain what went wrong and why (2-3 sentences)

Reply with the complete fixed implementation, ready to run.""",
}

# ── Sync critique ──────────────────────────────────────────────────────────────

_CRITIC_PROMPT = """\
You are a code/output quality reviewer.
Reply ONLY with valid JSON — no markdown, no prose:
{"approved": true|false, "reason": "one sentence", "correction_hint": "actionable fix or empty string"}
Rules:
- approved=true only if output correctly satisfies the goal AND is complete
- correction_hint must name the exact fix needed (e.g. "add JWT auth middleware")
- Empty correction_hint when approved
"""


def _critique(goal: str, output: str) -> dict:
    """Synchronous critique call. Returns approved/reason/correction_hint."""
    messages = [
        {"role": "system", "content": _CRITIC_PROMPT},
        {"role": "user",   "content": f"Goal:\n{goal}\n\nOutput:\n{output[:3000]}"},
    ]
    try:
        raw = call_llm(messages, force_api=True)
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\n?```\s*$", "", raw.strip())
        return json.loads(raw)
    except Exception as exc:
        log.debug("_critique parse failed: %s", exc)
        return {"approved": True, "reason": "critique skipped", "correction_hint": ""}


def _run_agent(
    role: str,
    goal: str,
    context: str = "",
    correction_hint: str = "",
) -> str:
    """Execute one agent step synchronously via LLM."""
    base_prompt = _AGENT_PROMPTS.get(
        role, "You are a helpful AI agent. Complete the given task precisely."
    )
    sys_prompt = build_agent_prompt(role, base_prompt)

    user_parts: list[str] = [f"Task:\n{goal}"]
    if context:
        user_parts.append(f"\nContext from previous step:\n{context}")
    if correction_hint:
        user_parts.append(
            f"\n⚠️ Correction required — please fix this issue:\n{correction_hint}"
        )

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user",   "content": "\n".join(user_parts)},
    ]
    result = call_llm(messages, force_api=True)
    return result or "(no output)"


# ── Result model ───────────────────────────────────────────────────────────────

@dataclass
class OrchestrationResult:
    source: str                                         # always "intent_orchestrator"
    output: str                                         # final assembled response
    intent: IntentModel
    agents_used: list[str] = field(default_factory=list)
    duration: float = 0.0
    metadata: dict = field(default_factory=dict)


# ── IntentOrchestrator ─────────────────────────────────────────────────────────

class IntentOrchestrator:
    """
    Synchronous domain-aware agent-chain orchestrator.

    Returns None when the intent should fall through to the standard pipeline
    (domain=chat, very ambiguous, or trivially short).
    """

    def orchestrate(
        self,
        intent: IntentModel,
        raw_message: str,
        session_id: str,
        on_event: Optional[Callable[[str], None]] = None,
    ) -> Optional[OrchestrationResult]:
        """
        Run a domain-specific agent chain for *intent*.

        Returns None if:
          - domain == "chat"
          - ambiguity_score > 0.75  (too vague for structured execution)
          - no subgoals AND message under 40 chars  (likely a simple Q&A)
        """
        if intent.domain not in _ORCHESTRATED_DOMAINS:
            return None
        if intent.ambiguity_score > 0.75:
            return None
        if not intent.subgoals and len(raw_message.strip()) < 40:
            return None

        t0 = time.monotonic()
        chain = _DOMAIN_CHAIN.get(intent.domain, ["dev", "reviewer"])

        self._emit(on_event, f"🤖 IntentOrchestrator | domain={intent.domain} | agents={' → '.join(chain)}")

        enriched_goal = self._build_enriched_goal(intent, raw_message)
        last_output   = ""
        agents_used: list[str] = []
        step_outputs: list[str] = []

        for agent_role in chain:
            # Skip security for non-code domains (data, devops, etc.), but keep
            # the security agent for explicit security tasks.
            if agent_role == "security" and intent.domain not in {"web_dev", "api", "mobile", "security"}:
                continue

            self._emit(on_event, f"▶ [{agent_role}] running…")
            agents_used.append(agent_role)

            # First agent gets the full enriched goal; later agents get the original goal
            agent_goal = enriched_goal if not last_output else intent.goal
            try:
                output = _run_agent(agent_role, agent_goal, context=last_output)
            except Exception as agent_exc:
                # FASE 5: record failure for self-improver
                try:
                    from services.self_improver import get_improver
                    get_improver().record_failure(agent_role, intent.domain, error=str(agent_exc), session_id=session_id)
                except Exception:
                    pass
                raise

            self._emit(on_event, f"  [{agent_role}] → {len(output)} chars")

            # Critique-correction loop for reviewer and security
            if agent_role in ("reviewer", "security"):
                for attempt in range(1, MAX_ROUNDS + 1):
                    critique = _critique(agent_goal, output)
                    approved = bool(critique.get("approved", True))
                    reason   = critique.get("reason", "")
                    hint     = critique.get("correction_hint", "")

                    self._emit(on_event, f"  Critique {attempt}/{MAX_ROUNDS}: approved={approved} | {reason}")

                    if approved:
                        break

                    if attempt < MAX_ROUNDS and hint:
                        # Ask the previous content agent (dev/architect/debugger) to self-correct
                        prev_role = self._prev_content_agent(chain, agent_role)
                        self._emit(on_event, f"  Correction → [{prev_role}]")
                        corrected = _run_agent(prev_role, agent_goal, context=last_output, correction_hint=hint)
                        # Re-evaluate corrected output
                        output = corrected
                        last_output = corrected

            last_output = output
            step_outputs.append(f"**[{agent_role.upper()}]**\n{output}")

        # Persist outcome to context memory (silent — never crash the pipeline)
        self._persist(session_id, raw_message, intent, last_output)

        # Format: single agent → clean output; multi-agent → sectioned
        if len(step_outputs) == 1:
            final = step_outputs[0].split("\n", 1)[1].lstrip() if "\n" in step_outputs[0] else step_outputs[0]
        else:
            final = "\n\n---\n\n".join(step_outputs)

        # FASE 3: Extract and write any embedded files from agent output
        files_written: list[str] = []
        workspace_dir: str = ""
        if intent.domain in {"web_dev", "mobile", "api", "data", "devops", "system", "automation"}:
            write_result = self._write_files(session_id, final)
            files_written = write_result.files_written
            workspace_dir = write_result.workspace_dir
            if files_written:
                self._emit(on_event, f"📁 FASE 3: {len(files_written)} arquivo(s) escrito(s) em {workspace_dir}")
                final = final + "\n\n" + write_result.summary()

        duration = round(time.monotonic() - t0, 2)
        self._emit(on_event, f"✅ IntentOrchestrator done | {len(agents_used)} agents | {duration}s")

        # FASE 5: Record agent performance for self-learning
        try:
            from services.self_improver import get_improver
            from core.learning_loop import get_learning_loop
            improver = get_improver()
            per_agent_dur = duration / max(len(agents_used), 1)
            for role in agents_used:
                improver.record_success(role, intent.domain, duration_s=per_agent_dur, session_id=session_id)
            # Trigger background learning analysis (rate-limited internally)
            get_learning_loop().analyze_in_background()
        except Exception:
            pass  # never break the pipeline

        return OrchestrationResult(
            source="intent_orchestrator",
            output=final,
            intent=intent,
            agents_used=agents_used,
            duration=duration,
            metadata={"files_written": files_written, "workspace_dir": workspace_dir},
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_enriched_goal(self, intent: IntentModel, raw_message: str) -> str:
        """Assemble a rich task description for the first agent in the chain."""
        lines: list[str] = [f"Primary goal: {intent.goal}"]

        if intent.subgoals:
            steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(intent.subgoals))
            lines.append(f"\nRequired implementation steps:\n{steps}")

        if intent.constraints:
            lines.append(f"\nTechnology constraints: {', '.join(intent.constraints)}")

        if intent.expected_outputs:
            lines.append(f"\nExpected deliverables: {', '.join(intent.expected_outputs)}")

        lines.append(f"\nOriginal user request: \"{raw_message}\"")
        return "\n".join(lines)

    def _prev_content_agent(self, chain: list[str], current_role: str) -> str:
        """Find the last non-review agent before *current_role* in the chain."""
        content_agents = [r for r in chain if r not in ("reviewer", "security")]
        if content_agents:
            return content_agents[-1]
        idx = chain.index(current_role)
        return chain[idx - 1] if idx > 0 else current_role

    def _write_files(self, session_id: str, text: str):
        """FASE 3: Extract file blocks from *text* and write them to workspace."""
        try:
            from core.code_writer import extract_and_write
            return extract_and_write(session_id, text)
        except Exception as exc:
            log.debug("IntentOrchestrator._write_files failed: %s", exc)
            # Return a no-op result so callers don't need to handle None
            from core.code_writer import CodeWriteResult
            return CodeWriteResult(session_id=session_id, workspace_dir="")

    def _persist(self, session_id: str, raw_message: str, intent: IntentModel, output: str) -> None:
        try:
            from core.context_memory import save_intent
            save_intent(session_id, raw_message, intent, output)
        except Exception as exc:
            log.debug("IntentOrchestrator._persist failed: %s", exc)

    def _emit(self, on_event: Optional[Callable], msg: str) -> None:
        log.info("intent_orchestrator: %s", msg)
        if on_event:
            try:
                on_event(msg)
            except Exception:
                pass


# ── Module-level singleton factory ────────────────────────────────────────────

_instance: Optional[IntentOrchestrator] = None


def get_intent_orchestrator() -> IntentOrchestrator:
    """Return the shared IntentOrchestrator singleton."""
    global _instance
    if _instance is None:
        _instance = IntentOrchestrator()
    return _instance
