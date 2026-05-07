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

from agents.dev_agent import DevAgent
from agents.architect_agent import ArchitectAgent
from agents.security_agent import SecurityAgent
from agents.debugger_agent import DebuggerAgent
from agents.planner_agent import PlannerAgent
from agents.reviewer_agent import ReviewerAgent
from agents.executor_agent import ExecutorAgent
from agents.system_agent import SystemAgent

__all__ = [
    "DevAgent", "ArchitectAgent", "SecurityAgent", "DebuggerAgent",
    "PlannerAgent", "ReviewerAgent", "ExecutorAgent", "SystemAgent",
]
