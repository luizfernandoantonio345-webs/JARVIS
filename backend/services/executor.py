"""
Plan Executor — runs a Plan step-by-step with retry, self-correction,
and validation gate.

Execution model:
  1. Steps are run in declared order, respecting depends_on (topological).
  2. Each step gets up to MAX_RETRIES attempts before being marked failed.
  3. On failure, a self-correction prompt is sent to ask the LLM to fix
     its own output (max SELF_CORRECT_ROUNDS rounds total per step).
  4. After all content steps, the optional validation Step (is_validation=True)
     runs: if valid=False and a corrected_output exists, it replaces the
     final response.
  5. Errors are isolated — a failing step never crashes the entire plan.
  6. STEP 1: Added evaluate_step_output after each execution for quality gate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from services.planner import Plan, Step, validate_plan_output
from services.execute_service import run_python
from services.llm_service import call_llm
from services.memory_service import (
    build_context_for_task,
    record_failure,
    resolve_failure,
    get_known_failures,
)
from services.session_store import SYSTEM_PROMPT
from actions.action_loader import get_system_prompt, preprocess_content, get_action

log = logging.getLogger(__name__)

MAX_RETRIES          = 2   # attempts per step before giving up
SELF_CORRECT_ROUNDS  = 2   # max self-correction iterations per failure
MAX_STEPS_PER_TASK   = 5   # global safety cap — no recursive explosion

# Step types that bypass the LLM pipeline
_CONTROL_STEP_TYPES = frozenset({"fs", "vscode", "shell"})

# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class StepResult:
    step: Step
    output: str
    success: bool = True
    attempts: int = 1
    corrected: bool = False
    eval_success: bool = True
    eval_reason: str = ""

@dataclass
class ExecutionResult:
    step_results: list[StepResult] = field(default_factory=list)
    validation_passed: bool = True
    validation_issues: list[str] = field(default_factory=list)
    early_stop: bool = False
    stop_reason: str = ""

    @property
    def final_response(self) -> str:
        content = [sr for sr in self.step_results if not sr.step.is_validation]
        if len(content) == 1:
            return content[0].output

        parts: list[str] = []
        for i, sr in enumerate(content, 1):
            status = " ⚠️" if not sr.success else (" 🔁" if sr.corrected else "")
            header = f"### Passo {i} — `{sr.step.action}`{status}"
            parts.append(f"{header}\n\n{sr.output}")
        return "\n\n---\n\n".join(parts)

    @property
    def primary_action(self) -> str:
        for sr in self.step_results:
            if not sr.step.is_validation:
                return sr.step.action
        return "chat"


# ── Self-correction ────────────────────────────────────────────────────────────

_SELF_CORRECT_SYSTEM = """\
You are a self-correcting AI assistant. The previous attempt produced an
unsatisfactory result. Review the original request, the failed output, and
the error/issue described. Produce a corrected, complete response.
Reply ONLY with the corrected content — no meta-commentary.\
"""

def evaluate_step_output(step: Step, output: str) -> dict[str, Any]:
    """
    STEP 1: After each step execution:
    - Rule checks: errors, incomplete, invalid
    - LLM: nuanced quality assessment
    """
    stripped = output.strip()
    if not stripped:
        return {'success': False, 'reason': 'empty'}
    if stripped.startswith('❌'):
        return {'success': False, 'reason': 'error'}
    if len(stripped) < 50:
        return {'success': False, 'reason': 'incomplete'}
    
    # LLM nuanced eval
    try:
        messages = [
            {'role': 'system', 'content': 'JSON evaluator. Reply only valid JSON: {"success": bool, "reason": str}'},
            {'role': 'user', 'content': f"Action: {step.action}\nInput: {step.input[:300]}\nOutput: {stripped[:1000]}\nEvaluate quality."}
        ]
        resp = call_llm(messages)
        import re, json
        m = re.search(r'\{[^{{}}]*\}', resp)
        if m:
            return json.loads(m.group())
    except Exception as e:
        log.debug('Eval LLM failed: %s', e)
    
    return {'success': True, 'reason': 'passed rules'}

def _self_correct(step: Step, bad_output: str, issue: str) -> str:
    messages = [
        {"role": "system", "content": _SELF_CORRECT_SYSTEM},
        {"role": "user",   "content": (
            f"Original request: {step.input}\n\n"
            f"Failed output:\n{bad_output}\n\n"
            f"Issue: {issue}"
        )},
    ]
    return call_llm(messages)


# ── Control-layer dispatch (Phase 4.5) ────────────────────────────────────────

def _execute_fs(step: Step) -> str:
    """Handle 'fs' step type — filesystem operations via FSController."""
    from services.fs_controller import get_fs
    fs = get_fs()

    raw = step.input.strip()
    # Expected format: "operation path [content]"
    # e.g. "read main.py", "write utils/helpers.py <content>", "list .", "delete old.py"
    parts = raw.split(maxsplit=2)
    if not parts:
        return "❌ fs: empty command"

    op = parts[0].lower()

    if op == "read":
        path = parts[1] if len(parts) > 1 else ""
        res = fs.read_file(path)
    elif op == "write":
        path = parts[1] if len(parts) > 1 else ""
        content = parts[2] if len(parts) > 2 else ""
        res = fs.write_file(path, content)
    elif op == "append":
        path = parts[1] if len(parts) > 1 else ""
        content = parts[2] if len(parts) > 2 else ""
        res = fs.append_file(path, content)
    elif op in ("list", "ls"):
        path = parts[1] if len(parts) > 1 else "."
        res = fs.list_dir(path)
    elif op in ("delete", "rm"):
        path = parts[1] if len(parts) > 1 else ""
        res = fs.delete_file(path)
    elif op == "mkdir":
        path = parts[1] if len(parts) > 1 else ""
        res = fs.make_dir(path)
    else:
        return f"❌ fs: unknown operation '{op}'. Use read/write/append/list/delete/mkdir"

    if res.success:
        data = res.data
        if isinstance(data, list):
            return "\n".join(data) if data else "(empty directory)"
        return str(data)
    return f"❌ fs error: {res.error}"


def _execute_vscode(step: Step) -> str:
    """Handle 'vscode' step type — VS Code integration."""
    from actions.vscode_control import execute as vscode_execute
    return vscode_execute(step.input)


def _execute_shell(step: Step) -> str:
    """Handle 'shell' step type — controlled shell execution."""
    from actions.shell_exec import run_process
    result = run_process(step.input)
    return result.to_text()


# ── Step dispatch ──────────────────────────────────────────────────────────────

def _execute_run(step: Step, _context: str) -> str:
    output = run_python(step.input)
    return f"```\n{output}\n```"


def _execute_llm(
    step: Step,
    context: str,
    session_messages: list[dict],
    session_id: str,
) -> str:
    sys_prompt = get_system_prompt(step.action, SYSTEM_PROMPT)
    processed  = preprocess_content(step.action, step.input)

    messages: list[dict] = [{"role": "system", "content": sys_prompt}]

    # Full three-tier memory context — task-aware, capped at CONTEXT_LIMIT
    if session_id:
        context_block = build_context_for_task(session_id, step.input, task_type=step.action)
        if context_block:
            messages.append({
                "role": "system",
                "content": f"Personalization context:\n{context_block}",
            })

    # Session history (only for first step; subsequent steps get chained context)
    if session_messages:
        messages.extend(session_messages)

    # Prior step output
    if context:
        messages.append({
            "role": "system",
            "content": f"Context from previous step:\n{context}",
        })

    messages.append({"role": "user", "content": processed})
    return call_llm(messages)


# ── Step runner with retry + self-correction + failure memory + circuit breaker ──

def _run_step_with_retry(
    step: Step,
    context: str,
    session_messages: list[dict],
    session_id: str,
) -> StepResult:
    last_output = ""
    last_exc: Exception | None = None
    corrected = False
    last_eval_reason: str = ""

    # Phase D: circuit breaker check before expensive LLM calls
    if step.action not in _CONTROL_STEP_TYPES:
        try:
            from core.circuit_breaker import get_llm_circuit_breaker
            if get_llm_circuit_breaker().is_tripped("ollama"):
                msg = "❌ LLM circuit breaker tripped — skipping retries"
                log.warning("Executor: %s (step=%r)", msg, step.action)
                return StepResult(step=step, output=msg, success=False, attempts=0,
                                  eval_reason="circuit_breaker_tripped")
        except Exception as exc:
            log.debug("[executor] circuit breaker check skipped", exc_info=exc)

    # Phase B: load known failures to inform self-correction
    known_failures: list[dict] = []
    if session_id and step.action not in _CONTROL_STEP_TYPES:
        try:
            known_failures = get_known_failures(session_id, step.action, step.input)
            if known_failures:
                log.info(
                    "Executor: %d known failure(s) found for step=%r — will guide correction",
                    len(known_failures), step.action,
                )
        except Exception as exc:
            log.debug("[executor] get_known_failures skipped", exc_info=exc)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # ── Control-layer routing (Phase 4.5) ──────────────────────────
            if step.action == "fs":
                output = _execute_fs(step)
                return StepResult(step=step, output=output, success=not output.startswith("❌"), attempts=attempt)
            if step.action == "vscode":
                output = _execute_vscode(step)
                return StepResult(step=step, output=output, success=not output.startswith("❌"), attempts=attempt)
            if step.action == "shell":
                output = _execute_shell(step)
                success = "❌ Security" not in output
                return StepResult(step=step, output=output, success=success, attempts=attempt)

            if step.action == "run":
                output = _execute_run(step, context)
            else:
                action_module = get_action(step.action)
                if action_module and hasattr(action_module, "execute"):
                    output = action_module.execute(step.input)
                else:
                    sm = session_messages if attempt == 1 else []
                    output = _execute_llm(step, context, sm, session_id)

            # Result Evaluation Layer (STEP 1)
            eval_result  = evaluate_step_output(step, output)
            eval_success = eval_result["success"]
            eval_reason  = eval_result["reason"]
            log.info("Eval %s: %s", step.action, eval_reason)

            if not eval_success:
                # Phase C: stuck detection — same reason twice → break early
                if eval_reason == last_eval_reason and attempt > 1:
                    log.warning(
                        "Executor: stuck on same eval_reason=%r (step=%r) — stopping early",
                        eval_reason, step.action,
                    )
                    break
                last_eval_reason = eval_reason

                # Build self-correction hint enriched with known failures
                failure_hint = ""
                if known_failures:
                    past = "; ".join(
                        f"[{f['strategy'] or f['step_type']}]: {f['error_snippet'][:80]}"
                        for f in known_failures[:3]
                    )
                    failure_hint = f"\n\nPreviously failed strategies to AVOID: {past}"

                log.warning("Eval fail — self-correcting (attempt %d): %s", attempt, eval_reason)
                corrected = True
                output = _self_correct(step, output, eval_reason + failure_hint)
                eval_result  = evaluate_step_output(step, output)
                eval_success = eval_result["success"]
                eval_reason  = eval_result["reason"]

            return StepResult(
                step=step, output=output, success=eval_success,
                attempts=attempt, corrected=corrected,
                eval_success=eval_success, eval_reason=eval_reason,
            )

        except Exception as exc:
            last_exc = exc
            last_output = f"❌ Erro (tentativa {attempt}): {exc}"
            log.warning("Step %r attempt %d raised: %s", step.action, attempt, exc)

            if attempt < MAX_RETRIES:
                try:
                    last_output = _self_correct(step, last_output, str(exc))
                    corrected = True
                except Exception as exc2:
                    log.debug("[services.executor] suppressed exception", exc_info=exc2)

    # Phase B: record exhausted failure to memory
    if session_id and step.action not in _CONTROL_STEP_TYPES:
        try:
            fid = record_failure(
                session_id=session_id,
                step_type=step.action,
                goal=step.input,
                strategy="default",
                error_snippet=str(last_exc or last_eval_reason)[:500],
                attempts=MAX_RETRIES,
            )
            log.info("Executor: recorded failure id=%d for step=%r", fid, step.action)
        except Exception as exc:
            log.debug("[executor] record_failure skipped", exc_info=exc)

    log.error("Step %r exhausted %d retries. Last error: %s", step.action, MAX_RETRIES, last_exc)
    return StepResult(
        step=step, output=last_output, success=False,
        attempts=MAX_RETRIES, corrected=corrected,
        eval_reason=last_eval_reason,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def execute_plan(
    plan: Plan,
    session_messages: list[dict],
    session_id: str = "",
) -> ExecutionResult:
    """
    Execute every content Step in the Plan, then run the validation gate.

    Parameters
    ----------
    plan             : Plan from planner.build_plan()
    session_messages : conversation history for context injection
    session_id       : used for semantic memory retrieval

    Returns
    -------
    ExecutionResult — always populated, never raises.
    """
    result = ExecutionResult()
    accumulated_context = ""
    step_outputs: list[str] = []
    consecutive_failures = 0

    content_steps = plan.content_steps

    # ── Safety cap (Phase 4.5) ─────────────────────────────────────────────────
    if len(content_steps) > MAX_STEPS_PER_TASK:
        log.warning(
            "execute_plan: plan has %d steps, capping at %d",
            len(content_steps), MAX_STEPS_PER_TASK,
        )
        content_steps = content_steps[:MAX_STEPS_PER_TASK]

    for i, step in enumerate(content_steps):
        # Resolve dependency context: concatenate outputs of declared deps
        if step.depends_on:
            dep_context_parts = [
                step_outputs[d]
                for d in step.depends_on
                if d < len(step_outputs)
            ]
            dep_context = "\n\n".join(dep_context_parts)
        else:
            dep_context = accumulated_context

        # Only pass session history to the very first step
        sm = session_messages if i == 0 else []

        log.debug(
            "Executing step %d/%d action=%r deps=%r",
            i + 1, len(content_steps), step.action, step.depends_on,
        )

        sr = _run_step_with_retry(step, dep_context, sm, session_id)
        result.step_results.append(sr)
        step_outputs.append(sr.output)
        accumulated_context = sr.output  # linear chain fallback

        # Phase C: consecutive-failure early stop
        if not sr.success:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                remaining = len(content_steps) - (i + 1)
                if remaining > 0:
                    result.early_stop = True
                    result.stop_reason = (
                        f"{consecutive_failures} consecutive step failures — "
                        f"skipping {remaining} remaining step(s)"
                    )
                    log.warning("execute_plan: early stop. %s", result.stop_reason)
                    break
        else:
            consecutive_failures = 0

    # ── Validation gate ────────────────────────────────────────────────────────
    validation_step = plan.validation_step
    if validation_step and len(content_steps) > 1:
        original_message = validation_step.input
        combined = "\n\n".join(
            f"Step {i+1} ({sr.step.action}):\n{sr.output}"
            for i, sr in enumerate(result.step_results)
        )
        validation = validate_plan_output(original_message, combined)
        result.validation_passed = validation["valid"]
        result.validation_issues = validation.get("issues", [])

        if not validation["valid"]:
            log.info("Validation failed: %s", validation["issues"])
            corrected_output = validation.get("corrected_output", "")
            if corrected_output:
                # Replace the last content step output with the corrected version
                if result.step_results:
                    last = result.step_results[-1]
                    result.step_results[-1] = StepResult(
                        step=last.step,
                        output=corrected_output,
                        success=True,
                        attempts=last.attempts,
                        corrected=True,
                        eval_success=True,
                        eval_reason="validation_corrected",
                    )

        # Record the validation step itself (not shown to user, but available for logs)
        result.step_results.append(StepResult(
            step=validation_step,
            output=str(validation),
            success=validation["valid"],
        ))

    return result


