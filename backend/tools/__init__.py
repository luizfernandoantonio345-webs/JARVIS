# tools package — advanced shell, feedback-loop utilities
# Re-exports for the unified tools layer
__all__ = ["execute_intent"]


def execute_intent(intent):  # thin re-export, avoids circular imports
    from tools.executor import execute_intent as _exec  # noqa: PLC0415
    return _exec(intent)
