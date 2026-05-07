"""
System Mode Controller — configures JARVIS operational behavior.

DEV       → verbose JSON logs (DEBUG level), debug endpoints enabled
ASSISTANT → normal logs (INFO level), standard operation
SILENT    → ERROR-only logs, minimal output, production behavior

Response envelope spec (all modes):
  {
    "message": "...",           ← natural language, user-facing
    "status": "success|pending|error",
    "actions": [...],           ← list of executed action names (may be empty)
    "meta": {
      "latency_ms": 123,
      "mode": "assistant"
    }
  }
DEV mode adds: meta.intent, meta.risk, meta.stage_timings, meta.errors
"""
from __future__ import annotations

import logging
import re
from typing import Any, Literal

OperationalMode = Literal["dev", "assistant", "silent"]

_LOG_LEVELS: dict[OperationalMode, int] = {
    "dev":       logging.DEBUG,
    "assistant": logging.INFO,
    "silent":    logging.ERROR,
}

_current_mode: OperationalMode = "assistant"

# ── Technical-to-human phrase map ─────────────────────────────────────────────
_PHRASE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"intent executed.*successfully", re.I), "Done."),
    (re.compile(r"execution failed[:\s]+(.+)", re.I), r"I couldn't complete that: \1"),
    (re.compile(r"no handler registered for action '(.+)'", re.I),
     r"I don't know how to '\1' yet."),
    (re.compile(r"action requires confirmation or was rejected", re.I),
     "I need your confirmation before doing that."),
    (re.compile(r"i'm taking too long to respond.*", re.I),
     "Give me a moment — I'm still thinking."),
    (re.compile(r"i'm currently unable to process.*", re.I),
     "I ran into a problem. Please try again."),
    (re.compile(r"intent step timed out.*", re.I),
     "That took too long. Please try again."),
    (re.compile(r"execution_error:\s*(.+)", re.I), r"Something went wrong: \1"),
    (re.compile(r"tool '(.+?)' unavailable.*", re.I), r"The '\1' tool is not available right now."),
    (re.compile(r"command blocked by security policy.*", re.I),
     "I can't run that — it's blocked for safety reasons."),
]


def _humanize(text: str) -> str:
    """Convert internal technical messages into natural assistant language."""
    if not text:
        return text
    for pattern, replacement in _PHRASE_MAP:
        if pattern.search(text):
            return pattern.sub(replacement, text).strip()
    return text


def apply_mode(mode: OperationalMode) -> None:
    """Apply a system mode — adjusts log levels and verbosity across all loggers."""
    global _current_mode
    _current_mode = mode

    level = _LOG_LEVELS[mode]
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            if name.startswith("jarvis") or name in ("uvicorn", "fastapi"):
                logger.setLevel(level)
    logging.getLogger("jarvis").setLevel(level)
    if mode == "dev":
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.WARNING)


def get_mode() -> OperationalMode:
    return _current_mode


def is_dev() -> bool:
    return _current_mode == "dev"


def is_silent() -> bool:
    return _current_mode == "silent"


def format_response(output: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Build the canonical JARVIS response envelope.

    All modes return the same top-level structure for predictable clients.
    Internal technical strings are humanized before being surfaced.
    """
    mode = _current_mode
    meta = metadata or {}

    errors: list[str] = meta.get("errors", [])
    executed: bool = meta.get("executed", False)
    elapsed: float = float(meta.get("elapsed_ms", 0.0))

    # Derive status
    if errors:
        status = "error"
    elif not executed and not output:
        status = "pending"
    else:
        status = "success"

    # Humanize message (strip technical leakage in non-dev modes)
    message = output if mode == "dev" else _humanize(output)
    if not message:
        message = "Done." if status == "success" else "An error occurred."

    # Build actions list from intent if available
    actions: list[str] = []
    intent = meta.get("intent")
    if intent and isinstance(intent, dict) and intent.get("action"):
        actions = [intent["action"]]

    response: dict[str, Any] = {
        "message": message,
        "status": status,
        "actions": actions,
        "meta": {
            "latency_ms": round(elapsed, 1),
            "mode": mode,
        },
    }

    if mode == "dev":
        response["meta"]["intent"] = intent
        response["meta"]["risk"] = meta.get("risk", "low")
        response["meta"]["errors"] = errors
        response["meta"]["session_id"] = meta.get("session_id", "")
        response["meta"]["suggestions"] = meta.get("suggestions", [])
        if "stage_timings" in meta:
            response["meta"]["stage_timings"] = meta["stage_timings"]
    elif mode == "assistant":
        if errors:
            response["errors"] = [_humanize(e) for e in errors]
        response["meta"]["session_id"] = meta.get("session_id", "")

    # SILENT: minimal — just message + status + meta (no extras)

    return response

