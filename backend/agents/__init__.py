"""
Multi-Agent System — Phases 4.5 / 5 / 6
"""

try:
    from backend.agents.dev_agent import DevAgent
    from backend.agents.architect_agent import ArchitectAgent
    from backend.agents.security_agent import SecurityAgent
    from backend.agents.debugger_agent import DebuggerAgent
    from backend.agents.planner_agent import PlannerAgent
    from backend.agents.reviewer_agent import ReviewerAgent
    from backend.agents.executor_agent import ExecutorAgent
    from backend.agents.system_agent import SystemAgent
    __all__ = [
        "DevAgent", "ArchitectAgent", "SecurityAgent", "DebuggerAgent",
        "PlannerAgent", "ReviewerAgent", "ExecutorAgent", "SystemAgent",
    ]
except ImportError:
    __all__ = []
