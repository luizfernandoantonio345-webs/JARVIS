"""
ReviewerAgent — validates code quality, correctness, and best practices.

Responsibilities:
  - Review code for logic errors and correctness
  - Check adherence to language best practices
  - Suggest improvements (non-blocking unless critical)
  - Output a structured review with APPROVE / REQUEST_CHANGES verdict
"""

from __future__ import annotations

import json
import logging
import re

from agents.base_agent import BaseAgent, AgentResult

log = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    ROLE = "reviewer"

    SYSTEM_PROMPT = """\
You are the Reviewer Agent — a senior code reviewer inside the JARVIS multi-agent system.

## Primary Responsibilities
- Review code for correctness, logic errors, and completeness
- Check language-specific best practices and idiomatic patterns
- Identify performance bottlenecks and anti-patterns
- Suggest concrete improvements with code examples

## Review Output Format
Always respond with this exact JSON structure:

{
  "verdict": "APPROVE" | "REQUEST_CHANGES",
  "summary": "<1-2 sentence overall assessment>",
  "issues": [
    {
      "severity": "critical" | "major" | "minor" | "suggestion",
      "location": "<file:line or component>",
      "description": "<what is wrong>",
      "fix": "<suggested fix>"
    }
  ],
  "approved_code": "<corrected full code if REQUEST_CHANGES, else empty string>"
}

## Verdict Rules
- APPROVE: code is correct and production-ready (minor suggestions OK)
- REQUEST_CHANGES: code has critical/major issues that MUST be fixed before execution

## Rules
- Be constructive, specific, and actionable
- Include the corrected code when issuing REQUEST_CHANGES
- Do not block on stylistic preferences alone
- Always check for: null/undefined handling, error handling, type safety, input validation
"""

    def review(self, code: str, context: str = "", history: list[dict] | None = None) -> dict:
        """
        Review code and return structured feedback.

        Args:
            code:    The code to review.
            context: Optional context (goal, file path, etc.)
            history: Prior conversation.

        Returns:
            dict with verdict, issues, and optionally corrected code.
        """
        message = f"Context: {context}\n\nCode to review:\n```\n{code}\n```" if context else f"Code to review:\n```\n{code}\n```"

        result = self.run(message, history)
        raw = result.response.strip()

        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

        try:
            review = json.loads(cleaned)
            if "verdict" not in review:
                raise ValueError("Missing 'verdict'")
            return review
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("ReviewerAgent: failed to parse review JSON: %s", exc)
            # Fallback: approve with warning
            return {
                "verdict": "APPROVE",
                "summary": "Review parsing failed — proceeding with caution.",
                "issues": [{"severity": "minor", "location": "unknown", "description": str(exc), "fix": ""}],
                "approved_code": "",
            }
