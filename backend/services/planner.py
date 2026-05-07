from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from services.llm_service import call_llm
from actions.action_loader import list_actions

log = logging.getLogger(__name__)

MAX_STEPS = 5

# Built-in non-LLM actions that are always single-step
_ALWAYS_SINGLE = {"run"}

# Control-layer actions added in Phase 4.5 (always available regardless of action loader)
_CONTROL_ACTIONS = {"fs", "vscode", "shell"}


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class Step:
    action: str
    input: str
    depends_on: list[int] = field(default_factory=list)   # indices of prerequisite steps
    is_validation: bool = False                            # True for the auto-added gate step

    def __post_init__(self) -> None:
        valid = set(list_actions()) | _ALWAYS_SINGLE | _CONTROL_ACTIONS
        if self.action not in valid:
            log.warning("Unknown action %r — coercing to 'chat'", self.action)
            self.action = "chat"


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)

    @property
    def is_multi(self) -> bool:
        return len(self.steps) > 1

    @property
    def content_steps(self) -> list[Step]:
        return [s for s in self.steps if not s.is_validation]

    @property
    def validation_step(self) -> Step | None:
        for s in self.steps:
            if s.is_validation:
                return s
        return None

    def __repr__(self) -> str:  # pragma: no cover
        parts = []
        for i, s in enumerate(self.steps):
            tag = " [VALIDATE]" if s.is_validation else ""
            dep = f" deps={s.depends_on}" if s.depends_on else ""
            parts.append(f"  {i+1}. [{s.action}]{tag}{dep} {s.input[:60]}")
        return "Plan(\n" + "\n".join(parts) + "\n)"


# ── Prompts ────────────────────────────────────────────────────────────────────

def _build_planner_prompt(valid_actions: list[str]) -> str:
    actions_str = ", ".join(valid_actions)
    return f"""\
You are a task planner for an AI assistant called JARVIS.
Given a user message, decompose it into an ordered list of sub-tasks.

Rules:
- Reply with ONLY a valid JSON array — no prose, no markdown fences.
- Each element: {{"action": "<action>", "input": "<what to do>", "depends_on": [<indices>]}}
- "depends_on" is a list of 0-based indices of steps this step requires. Omit if none.
- Valid actions: {actions_str}
- Maximum {MAX_STEPS} steps. Minimum 1 step.
- Single atomic requests → exactly 1 step with no depends_on.
- Preserve the user's original language in the "input" field.

Example (multi-step with dependency):
[
  {{"action": "explain", "input": "what is a binary search tree", "depends_on": []}},
  {{"action": "run",     "input": "implement binary search tree in Python", "depends_on": [0]}}
]

Example (single-step):
[
  {{"action": "chat", "input": "how are you?"}}
]\
"""


_VALIDATION_PROMPT = """\
You are a plan validator for an AI assistant called JARVIS.
Review the plan steps and their outputs. Determine if the overall result
is coherent, complete, and correctly answers the original request.

Reply with ONLY a JSON object:
{
  "valid": true | false,
  "issues": ["<issue 1>", ...],    // empty list if valid
  "corrected_output": "<string>"   // only if valid=false: improved final answer
}
No prose, no markdown fences.\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _single_plan(action: str, message: str) -> Plan:
    return Plan(steps=[Step(action=action, input=message)])


def _append_validation(plan: Plan, original_message: str) -> Plan:
    """Add a validation gate step to multi-step plans."""
    if plan.is_multi:
        plan.steps.append(Step(
            action="chat",
            input=original_message,
            depends_on=list(range(len(plan.steps))),
            is_validation=True,
        ))
    return plan


def _parse_llm_response(raw: str, original_message: str) -> Plan:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                log.warning("Planner: JSON rescue failed — single-step fallback")
                return _single_plan("chat", original_message)
        else:
            log.warning("Planner: no JSON found — single-step fallback")
            return _single_plan("chat", original_message)

    if not isinstance(data, list) or not data:
        return _single_plan("chat", original_message)

    steps: list[Step] = []
    for item in data[:MAX_STEPS]:
        if not isinstance(item, dict):
            continue
        action   = str(item.get("action", "chat")).strip().lower()
        inp      = str(item.get("input", original_message)).strip()
        deps_raw = item.get("depends_on", [])
        deps     = [int(d) for d in deps_raw if isinstance(d, (int, float))] if isinstance(deps_raw, list) else []
        steps.append(Step(action=action, input=inp or original_message, depends_on=deps))

    return Plan(steps=steps) if steps else _single_plan("chat", original_message)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_plan(message: str, intent: str) -> Plan:
    """
    Build an execution Plan for the given message.

    Parameters
    ----------
    message : user message (post-prefix-strip from llm_router)
    intent  : primary intent from llm_router

    Returns
    -------
    Plan — at least 1 step; multi-step plans include a validation gate.
    """
    if intent in _ALWAYS_SINGLE:
        return _single_plan(intent, message)

    valid_actions = [a for a in list_actions() if a not in ("run", "chat")]
    valid_actions += ["run", "chat"]
    # Include Phase 4.5 control actions
    valid_actions += [a for a in sorted(_CONTROL_ACTIONS) if a not in valid_actions]

    system_prompt = _build_planner_prompt(valid_actions)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": message},
    ]
    try:
        raw  = call_llm(messages, force_local=True)
        plan = _parse_llm_response(raw, message)
        plan = _append_validation(plan, message)
        log.debug("Plan built: %r", plan)
        return plan
    except Exception as exc:
        log.error("Planner error: %s — single-step fallback", exc)
        return _single_plan(intent, message)


def validate_plan_output(
    original_message: str,
    step_summaries: str,
) -> dict:
    """
    Ask the LLM to validate the combined step outputs.

    Returns parsed dict with keys: valid (bool), issues (list), corrected_output (str).
    Falls back to {"valid": True, "issues": [], "corrected_output": ""} on error.
    """
    messages = [
        {"role": "system", "content": _VALIDATION_PROMPT},
        {"role": "user",   "content": (
            f"Original request:\n{original_message}\n\n"
            f"Step outputs:\n{step_summaries}"
        )},
    ]

    try:
        raw     = call_llm(messages, force_local=True)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        result  = json.loads(cleaned)
        return {
            "valid":            bool(result.get("valid", True)),
            "issues":           result.get("issues", []),
            "corrected_output": result.get("corrected_output", ""),
        } # pyright: ignore[reportUnknownVariableType]
    except Exception as exc:
        log.warning("Validation LLM call failed: %s — assuming valid", exc)
        return {"valid": True, "issues": [], "corrected_output": ""} # pyright: ignore[reportUnknownVariableType]