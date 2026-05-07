"""
Tool registry — maps intent actions to tool handler coroutines.
Each handler is:
  - isolated (no shared state)
  - stateless (no global side effects)
  - reusable (can be called from multiple flows)

Bug #8 fix: tools are lazy-loaded per call so a broken tool module
does NOT crash the entire registry. Missing tool → logged + graceful skip.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)

# ── Lazy loader ────────────────────────────────────────────────────────────────

def _lazy(module: str, fn: str) -> Callable[..., Coroutine[Any, Any, dict]]:
    """Return a coroutine that imports `module.fn` on first call."""
    async def _handler(parameters: dict) -> dict:
        import importlib
        try:
            mod = importlib.import_module(module)
            return await getattr(mod, fn)(parameters)
        except ImportError as exc:
            log.error("tool_import_error module=%s fn=%s error=%s", module, fn, exc)
            raise RuntimeError(f"Tool '{fn}' unavailable: {exc}") from exc
    _handler.__name__ = fn
    _handler.__qualname__ = f"{module}.{fn}"
    return _handler


# ── Registry ───────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Callable[..., Coroutine[Any, Any, dict]]] = {
    # Desktop / UI
    "open_app":     _lazy("tools.desktop",    "open_app"),
    "open_browser": _lazy("tools.desktop",    "open_browser"),
    "go_to_url":    _lazy("tools.desktop",    "go_to_url"),
    "navigate":     _lazy("tools.desktop",    "go_to_url"),
    # File system
    "read_file":    _lazy("tools.filesystem", "read_file"),
    "write_file":   _lazy("tools.filesystem", "write_file"),
    "delete_file":  _lazy("tools.filesystem", "delete_file"),
    # Git
    "git_clone":    _lazy("tools.git_tool",   "git_clone"),
    "git_commit":   _lazy("tools.git_tool",   "git_commit"),
    # Shell
    "run_shell":    _lazy("tools.shell",      "run_shell"),
    "system_change":_lazy("tools.shell",      "run_shell"),
}

