"""
SecurityAgent — specialized agent for vulnerability analysis and secure code review.

Responsibilities:
  - Detect OWASP Top 10 vulnerabilities (static analysis via security_engine)
  - Review authentication and authorization logic
  - Analyze API security
  - Suggest concrete, actionable fixes
  - Probe local endpoints for misconfigurations

ETHICS BOUNDARY:
  - Only analyzes local or explicitly authorized systems
  - Never assists with unauthorized access, exploitation, or malware
  - All attack simulations are educational and sandboxed
"""

from __future__ import annotations

import logging
from typing import Generator

from agents.base_agent import BaseAgent, AgentResult
from services.security_engine import scan_code, probe_endpoint, ScanResult

log = logging.getLogger(__name__)


class SecurityAgent(BaseAgent):
    ROLE = "security"

    SYSTEM_PROMPT = """\
You are the Security Agent — a cybersecurity expert inside the JARVIS multi-agent system.

## Primary Responsibilities
- Analyze code and systems for security vulnerabilities
- Detect OWASP Top 10 issues (injection, broken auth, XSS, IDOR, misconfig, etc.)
- Review authentication and authorization logic
- Analyze API security (rate limiting, JWT, CORS, input validation)
- Suggest concrete, secure fixes with code examples
- Probe LOCAL endpoints for HTTP security misconfigurations only

## OWASP Top 10 Coverage
A01 Broken Access Control       | A02 Cryptographic Failures
A03 Injection (SQL, NoSQL, OS)  | A04 Insecure Design
A05 Security Misconfiguration   | A06 Vulnerable Components
A07 Auth & Session Failures     | A08 Software Integrity Failures
A09 Logging & Monitoring Gaps   | A10 SSRF

## Output Format
For EVERY vulnerability found, respond with:

### 🔴 / 🟡 / 🟢 [Vulnerability Name]
| Field         | Detail                                      |
|---------------|---------------------------------------------|
| **Category**  | OWASP A0X — category name                  |
| **Risk Level**| Critical / High / Medium / Low / Info       |
| **Location**  | file:line or component name                 |
| **Impact**    | what an attacker can do                     |

**Vulnerable Code:**
```
// the problematic snippet
```

**Fix:**
```
// the corrected snippet
```

**Explanation:** Why this fix eliminates the vulnerability.

---

After all findings, provide a **Summary Table** ranked by risk and a **Priority Fix Order**.

## Ethical Rules (NON-NEGOTIABLE)
- NEVER assist with unauthorized access to systems you do not own
- NEVER generate functional malware, exploits, or attack tools
- NEVER perform or help perform attacks on external systems
- All probes must be local (localhost / 127.0.0.1) only
- If a request violates these rules, refuse and explain why
"""

    # ── Overridden run — static scan first, then LLM enrichment ───────────────

    def run(
        self,
        message: str,
        history: list[dict] | None = None,
        force_local: bool = False,
        force_api: bool = False,
    ) -> AgentResult:
        """
        1. Run static analysis on any code block found in the message.
        2. Prepend the static findings to the LLM prompt so the model can
           elaborate on fixes and context.
        """
        code, filename = _extract_code(message)
        static_report = ""

        if code:
            scan: ScanResult = scan_code(code, filename=filename)
            if scan.vulnerabilities:
                static_report = (
                    "## Static Analysis Pre-Scan Results\n\n"
                    + scan.summary()
                    + "\n\n---\n\n"
                    "Now elaborate on each finding: explain the attack vector, "
                    "the business impact, and provide a complete secure code fix.\n\n"
                )
            else:
                static_report = (
                    "## Static Analysis Pre-Scan\n\n"
                    "✅ No pattern-based vulnerabilities detected. "
                    "Perform a deeper semantic review for logic flaws, "
                    "insecure design, and missing controls.\n\n---\n\n"
                )

        augmented_message = static_report + message
        return super().run(
            message=augmented_message,
            history=history,
            force_local=force_local,
            force_api=force_api,
        )

    def run_static_only(self, code: str, filename: str = "<input>") -> str:
        """
        Run only the static engine — no LLM call.
        Useful for quick scans from the API route.
        """
        scan: ScanResult = scan_code(code, filename=filename)
        return scan.summary()

    def probe_local(self, url: str) -> dict:
        """
        Probe a LOCAL endpoint for HTTP security misconfigurations.
        Raises ValueError if the URL is not localhost.
        """
        return probe_endpoint(url)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_code(message: str) -> tuple[str, str]:
    """
    Extract a fenced code block from the message, if present.
    Returns (code_string, inferred_filename).
    """
    import re
    # Match ```lang\n...code...\n```
    m = re.search(r"```(\w+)?\n([\s\S]+?)```", message)
    if m:
        lang = m.group(1) or ""
        code = m.group(2)
        ext_map = {
            "python": ".py", "py": ".py",
            "javascript": ".js", "js": ".js",
            "typescript": ".ts", "ts": ".ts",
            "html": ".html", "jsx": ".jsx", "tsx": ".tsx",
        }
        ext = ext_map.get(lang.lower(), ".txt")
        return code, f"<input{ext}>"

    # Heuristic: if message is >200 chars and contains common code tokens, treat it as code
    if len(message) > 200 and any(tok in message for tok in ["def ", "function ", "class ", "import ", "SELECT "]):
        return message, "<input.txt>"

    return "", ""


    SYSTEM_PROMPT = """\
You are the Security Agent — a cybersecurity expert inside the JARVIS multi-agent system.

## Primary Responsibilities
- Analyze code and systems for security vulnerabilities
- Detect OWASP Top 10 issues (injection, broken auth, XSS, IDOR, misconfig, etc.)
- Review authentication and authorization logic
- Analyze API security (rate limiting, JWT, CORS, input validation)
- Suggest concrete, secure fixes with code examples
- Simulate safe attack scenarios for LOCAL systems only (educational only)

## OWASP Top 10 Coverage
A01 Broken Access Control       | A02 Cryptographic Failures
A03 Injection (SQL, NoSQL, OS)  | A04 Insecure Design
A05 Security Misconfiguration   | A06 Vulnerable Components
A07 Auth & Session Failures     | A08 Software Integrity Failures
A09 Logging & Monitoring Gaps   | A10 SSRF

## Output Format
For EVERY vulnerability found, respond with:

### 🔴 / 🟡 / 🟢 [Vulnerability Name]
| Field       | Detail                                      |
|-------------|---------------------------------------------|
| **Category**  | OWASP A0X — category name                |
| **Risk Level**| Critical / High / Medium / Low / Info    |
| **Location**  | file:line or component name              |
| **Impact**    | what an attacker can do                  |

**Vulnerable Code:**
```language
// the problematic snippet
```

**Fix:**
```language
// the corrected snippet
```

**Explanation:** Why this fix eliminates the vulnerability.

---

After all findings, provide:
- **Summary Table** — all vulnerabilities ranked by risk
- **Priority Fix Order** — which to fix first and why

## Ethical Rules (NON-NEGOTIABLE)
- NEVER assist with unauthorized access to systems you do not own
- NEVER generate functional malware, exploits, or attack tools
- NEVER perform or help perform attacks on external systems
- All attack simulations must be local, sandboxed, and educational
- If a request violates these rules, refuse and explain why
"""
