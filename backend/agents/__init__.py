"""
Multi-Agent System — Phases 4.5 / 5 / 6

Specialized agents available:
  - DevAgent         → writes and reviews code (alias: coder)
  - ArchitectAgent   → system design and architecture
  - SecurityAgent    → vulnerability analysis (OWASP Top 10)
  - DebuggerAgent    → error diagnosis and bug fixes
  - PlannerAgent     → breaks goals into structured plans
  - ReviewerAgent    → validates code; APPROVE / REQUEST_CHANGES
  - ExecutorAgent    → runs commands safely
  - SystemAgent      → OS + browser automation
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

# Master orchestrator
from backend.agents.master_orchestrator import get_orchestrator, MasterOrchestrator
__all__ += ["get_orchestrator", "MasterOrchestrator"]
