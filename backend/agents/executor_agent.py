"""
ExecutorAgent — safely runs commands, starts servers, and validates outputs.

Responsibilities:
  - Execute validated commands via shell_exec whitelist
  - Run projects via project_runner
  - Monitor output for errors
  - Return structured execution results

Security:
  - Delegates all execution to shell_exec (whitelist enforced)
  - Cannot execute code that was blocked by SecurityAgent
  - Hard timeout via JARVIS_EXEC_TIMEOUT
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, AgentResult

log = logging.getLogger(__name__)


class ExecutorAgent(BaseAgent):
    ROLE = "executor"

    SYSTEM_PROMPT = """\
You are the Executor Agent inside the JARVIS multi-agent system.

## Role
Execute approved commands and validate their results.

## When to run what
- "run <file.py>" → python execution
- "run project <path>" → project_runner auto-detection
- "shell <command>" → controlled shell execution (whitelist enforced)
- "check output" → analyze last execution result

## Output Format
Always respond with:

**Command**: `<exact command run>`
**Status**: ✅ Success | ❌ Failed | ⚠️ Partial
**Output**:
```
<captured stdout/stderr>
```
**Analysis**: <brief analysis of the result>
**Next Step**: <what to do next if needed>

## Rules
- NEVER execute commands not in the whitelist: python, node, npm, git, uvicorn
- NEVER run pip install
- ALWAYS report both stdout and stderr
- If a command fails, diagnose the error from the output
- Max 1 retry per command
"""

    def execute_command(self, command: str) -> AgentResult:
        """
        Execute a command via shell_exec and return structured result.

        Args:
            command: Shell command to run (whitelist enforced).

        Returns:
            AgentResult with execution output.
        """
        from actions.shell_exec import run_process
        proc = run_process(command)
        output = proc.to_text()

        # Build a context message for the LLM analysis
        message = (
            f"Command executed: `{command}`\n\n"
            f"Raw output:\n{output}\n\n"
            "Provide a structured execution report."
        )
        return self.run(message)

    def run_project(self, path: str) -> AgentResult:
        """
        Auto-detect and run a project, returning structured result.

        Args:
            path: Path to the project directory.

        Returns:
            AgentResult with run result analysis.
        """
        from services.project_runner import get_runner
        runner = get_runner()
        run_result = runner.run_project(path)
        output_text = run_result.to_text()

        message = (
            f"Project run result:\n{output_text}\n\n"
            "Provide a structured execution report and diagnose any errors."
        )
        return self.run(message)
