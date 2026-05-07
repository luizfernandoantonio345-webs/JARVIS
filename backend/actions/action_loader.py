"""
Action auto-discovery loader.

Convention — any .py file dropped into the `actions/` package is
automatically registered if it defines:

  ACTION_NAME : str          (required) — unique identifier, e.g. "analyze"
  SYSTEM_PROMPT : str        (optional) — overrides the default system prompt
  preprocess(content) -> str (optional) — transforms user input before LLM

No manual registration is needed. Adding a new action is as simple as:
  1. Create  actions/my_action.py
  2. Set     ACTION_NAME = "my_action"
  3. Restart the server

Discovery runs once at import time. A reload can be triggered at runtime
via reload_actions().
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from types import ModuleType

import actions as _actions_pkg

log = logging.getLogger(__name__)

# Built-in synthetic actions (no module — handled outside the LLM pipeline)
_SYNTHETIC_ACTIONS: list[str] = ["run", "chat"]

# Registry: action_name → module
_registry: dict[str, ModuleType] = {}


# ── Discovery ──────────────────────────────────────────────────────────────────

def _discover() -> dict[str, ModuleType]:
    """
    Walk the `actions` package and import every sub-module.
    Modules that define ACTION_NAME are registered under that name.
    """
    found: dict[str, ModuleType] = {}
    pkg_path = Path(_actions_pkg.__file__).parent  # type: ignore[arg-type]

    for module_info in pkgutil.iter_modules([str(pkg_path)]):
        if module_info.name in ("action_loader",):
            continue  # skip self

        full_name = f"actions.{module_info.name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as exc:
            log.error("Failed to import action module %r: %s", full_name, exc)
            continue

        action_name: str | None = getattr(module, "ACTION_NAME", None)
        if not action_name:
            log.debug("Module %r has no ACTION_NAME — skipped", full_name)
            continue

        if action_name in found:
            log.warning(
                "Duplicate ACTION_NAME %r in %r — previous registration kept",
                action_name, full_name,
            )
            continue

        found[action_name] = module
        log.debug("Registered action %r from %r", action_name, full_name)

    return found


def reload_actions() -> None:
    """Force re-discovery (useful after hot-reloading modules at runtime)."""
    global _registry
    _registry = _discover()
    log.info("Actions reloaded: %s", list(_registry.keys()))


# Run discovery at import time
_registry = _discover()


# ── Public API ─────────────────────────────────────────────────────────────────

def get_system_prompt(action_name: str, default: str) -> str:
    module = _registry.get(action_name)
    if module and hasattr(module, "SYSTEM_PROMPT"):
        return module.SYSTEM_PROMPT  # type: ignore[return-value]
    return default


def preprocess_content(action_name: str, content: str) -> str:
    module = _registry.get(action_name)
    if module and hasattr(module, "preprocess"):
        return module.preprocess(content)  # type: ignore[return-value]
    return content


def list_actions() -> list[str]:
    """Return all registered action names including synthetic ones."""
    return sorted(_registry.keys()) + _SYNTHETIC_ACTIONS


def get_action(action_name: str) -> ModuleType | None:
    """Return the raw module for a registered action, or None."""
    return _registry.get(action_name)
