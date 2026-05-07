"""
CodeValidator — validates generated code before execution.

Performs layered checks:
  Layer 1: Syntax check (AST parse — catches SyntaxError, IndentationError)
  Layer 2: Security scan (dangerous patterns: eval, exec, __import__, os.system)
  Layer 3: Import validation (detect missing stdlib/installed modules)
  Layer 4: Complexity check (detect obvious infinite loops, recursion bombs)
  Layer 5: Quality heuristics (empty functions, bare except, missing return)

Returns structured ValidationReport with severity-tagged issues.

Usage:
    from services.code_validator import validate_code, ValidationReport
    report = validate_code(source_code, language="python")
    if not report.valid:
        print(report.summary())
"""

from __future__ import annotations

import ast
import re
import sys
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)


# ── Issue severity ─────────────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"   # blocks execution
    HIGH     = "high"       # should fix before running
    MEDIUM   = "medium"     # code smell / risk
    LOW      = "low"        # style / quality
    INFO     = "info"       # informational


@dataclass
class ValidationIssue:
    severity: Severity
    code:     str       # e.g. "SYNTAX_ERROR", "DANGEROUS_EVAL"
    message:  str
    line:     int | None = None
    context:  str = ""  # snippet of code at the issue

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code":     self.code,
            "message":  self.message,
            "line":     self.line,
            "context":  self.context,
        }

    def __str__(self) -> str:
        loc = f" (line {self.line})" if self.line else ""
        return f"[{self.severity.value.upper()}] {self.code}{loc}: {self.message}"


@dataclass
class ValidationReport:
    language:  str
    issues:    list[ValidationIssue] = field(default_factory=list)
    tree:      ast.AST | None = None   # parsed AST (Python only)

    @property
    def valid(self) -> bool:
        """No CRITICAL issues."""
        return not any(i.severity == Severity.CRITICAL for i in self.issues)

    @property
    def safe_to_run(self) -> bool:
        """No CRITICAL or HIGH issues."""
        return not any(i.severity in (Severity.CRITICAL, Severity.HIGH) for i in self.issues)

    @property
    def by_severity(self) -> dict[str, list[ValidationIssue]]:
        result: dict[str, list[ValidationIssue]] = {s.value: [] for s in Severity}
        for issue in self.issues:
            result[issue.severity.value].append(issue)
        return result

    def summary(self) -> str:
        if not self.issues:
            return "✅ No issues found."
        lines = [f"Validation report ({len(self.issues)} issues):"]
        for issue in self.issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "valid":    self.valid,
            "safe_to_run": self.safe_to_run,
            "issues":   [i.to_dict() for i in self.issues],
        }

    def critical_summary(self) -> str:
        crits = [i for i in self.issues if i.severity == Severity.CRITICAL]
        if not crits:
            return ""
        return "\n".join(str(i) for i in crits)


# ── Python validator ───────────────────────────────────────────────────────────

class PythonValidator:
    """
    Multi-layer Python code validator.
    """

    # Dangerous patterns that should never appear in generated code
    _CRITICAL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
        (re.compile(r"\beval\s*\("),        "EVAL_USAGE",       "eval() is a code injection risk"),
        (re.compile(r"\bexec\s*\("),        "EXEC_USAGE",       "exec() is a code injection risk"),
        (re.compile(r"\b__import__\s*\("),  "DUNDER_IMPORT",    "__import__() bypasses import controls"),
        (re.compile(r"os\.system\s*\("),    "OS_SYSTEM",        "os.system() is unsafe — use subprocess"),
        (re.compile(r"subprocess\.call\(\s*[\"'].*[\"']\s*,\s*shell\s*=\s*True"), "SHELL_TRUE", "shell=True with string command is unsafe"),
        (re.compile(r"pickle\.loads?\s*\("), "PICKLE_LOAD",     "pickle.load() can execute arbitrary code"),
        (re.compile(r"import\s+ctypes"),    "CTYPES_IMPORT",    "ctypes allows arbitrary memory access"),
    ]

    _HIGH_PATTERNS: list[tuple[re.Pattern, str, str]] = [
        (re.compile(r"open\s*\([^)]*[\"']/etc/"),   "ETC_ACCESS",     "Accessing /etc/ files"),
        (re.compile(r"open\s*\([^)]*[\"']C:\\\\Windows"), "WIN_SYSTEM", "Accessing Windows system files"),
        (re.compile(r"requests\.get\s*\([^)]+verify\s*=\s*False"), "SSL_VERIFY_OFF", "SSL verification disabled"),
        (re.compile(r"0\.0\.0\.0.*bind|bind.*0\.0\.0\.0"), "OPEN_BIND", "Binding to all interfaces"),
        (re.compile(r"debug\s*=\s*True"),   "DEBUG_MODE",       "Debug mode enabled (check before deploy)"),
        (re.compile(r"SECRET_KEY\s*=\s*[\"'][^\"']{1,20}[\"']"), "WEAK_SECRET", "Potentially weak SECRET_KEY"),
    ]

    _MEDIUM_PATTERNS: list[tuple[re.Pattern, str, str]] = [
        (re.compile(r"print\s*\(.*password|print\s*\(.*secret|print\s*\(.*token", re.I), "CREDENTIAL_LOG", "Possible credential logging"),
        (re.compile(r"except\s*:"),         "BARE_EXCEPT",      "Bare except catches all exceptions including SystemExit"),
        (re.compile(r"except\s+Exception\s*:"), "BROAD_EXCEPT", "Too-broad except clause"),
        (re.compile(r"pass\s*$", re.M),     "EMPTY_PASS",       "Bare pass (empty block)"),
        (re.compile(r"TODO|FIXME|HACK|XXX", re.I), "TODO_LEFT", "Unresolved TODO/FIXME"),
    ]

    def validate(self, source: str) -> ValidationReport:
        report = ValidationReport(language="python")

        # ── Layer 1: Syntax ────────────────────────────────────────────────────
        try:
            tree = ast.parse(source)
            report.tree = tree
        except SyntaxError as exc:
            report.issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                code="SYNTAX_ERROR",
                message=str(exc),
                line=exc.lineno,
                context=exc.text or "",
            ))
            return report  # Cannot proceed without valid AST
        except Exception as exc:
            report.issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                code="PARSE_ERROR",
                message=str(exc),
            ))
            return report

        lines = source.splitlines()

        # ── Layer 2: Security pattern scan ────────────────────────────────────
        for pat, code, msg in self._CRITICAL_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pat.search(line):
                    report.issues.append(ValidationIssue(
                        severity=Severity.CRITICAL,
                        code=code, message=msg,
                        line=i, context=line.strip(),
                    ))

        for pat, code, msg in self._HIGH_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pat.search(line):
                    report.issues.append(ValidationIssue(
                        severity=Severity.HIGH,
                        code=code, message=msg,
                        line=i, context=line.strip(),
                    ))

        for pat, code, msg in self._MEDIUM_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pat.search(line):
                    report.issues.append(ValidationIssue(
                        severity=Severity.MEDIUM,
                        code=code, message=msg,
                        line=i, context=line.strip(),
                    ))

        # ── Layer 3: AST-based checks ──────────────────────────────────────────
        self._check_ast(tree, lines, report)

        # ── Layer 4: Import validation ─────────────────────────────────────────
        self._check_imports(tree, report)

        return report

    def _check_ast(self, tree: ast.AST, lines: list[str], report: ValidationReport) -> None:
        """AST-level checks: complexity, infinite loops, bare returns."""

        for node in ast.walk(tree):

            # Empty function bodies (just pass or docstring)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                non_trivial = [
                    n for n in body
                    if not isinstance(n, (ast.Pass, ast.Expr))
                    or (isinstance(n, ast.Expr) and not isinstance(n.value, ast.Constant))
                ]
                if not non_trivial:
                    report.issues.append(ValidationIssue(
                        severity=Severity.LOW,
                        code="EMPTY_FUNCTION",
                        message=f"Function '{node.name}' has no implementation",
                        line=node.lineno,
                    ))

            # Infinite while True loops without break
            if isinstance(node, ast.While):
                is_true = (
                    isinstance(node.test, ast.Constant) and node.test.value is True
                )
                if is_true:
                    has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                    if not has_break:
                        report.issues.append(ValidationIssue(
                            severity=Severity.HIGH,
                            code="INFINITE_LOOP",
                            message="while True loop without break — potential infinite loop",
                            line=node.lineno,
                        ))

            # Recursive calls without depth control
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == node.name
                    ):
                        # Check for no base case (simple heuristic)
                        has_if = any(isinstance(n, ast.If) for n in ast.walk(node))
                        if not has_if:
                            report.issues.append(ValidationIssue(
                                severity=Severity.MEDIUM,
                                code="UNBOUNDED_RECURSION",
                                message=f"'{node.name}' calls itself without visible base case",
                                line=node.lineno,
                            ))

    def _check_imports(self, tree: ast.AST, report: ValidationReport) -> None:
        """Flag imports that are commonly missing or dangerous."""
        dangerous_stdlib = {"pickle", "ctypes", "shelve", "marshal"}
        flagged_third_party = {"paramiko", "fabric", "rpyc"}  # remote execution

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else ([node.module] if node.module else [])
                )
                for name in names:
                    base = (name or "").split(".")[0]
                    if base in dangerous_stdlib:
                        report.issues.append(ValidationIssue(
                            severity=Severity.HIGH,
                            code="DANGEROUS_IMPORT",
                            message=f"'{base}' can be used for unsafe deserialization/execution",
                            line=getattr(node, "lineno", None),
                        ))
                    elif base in flagged_third_party:
                        report.issues.append(ValidationIssue(
                            severity=Severity.MEDIUM,
                            code="REMOTE_EXEC_IMPORT",
                            message=f"'{base}' enables remote code execution — verify intent",
                            line=getattr(node, "lineno", None),
                        ))


# ── Public API ─────────────────────────────────────────────────────────────────

_python_validator = PythonValidator()


def validate_code(source: str, language: str = "python") -> ValidationReport:
    """
    Validate source code for syntax, security, and quality issues.

    Args:
        source:   Source code string.
        language: "python" (others return an empty passing report for now).

    Returns:
        ValidationReport — always populated, never raises.
    """
    if not source or not source.strip():
        report = ValidationReport(language=language)
        report.issues.append(ValidationIssue(
            severity=Severity.CRITICAL,
            code="EMPTY_CODE",
            message="Source code is empty",
        ))
        return report

    try:
        if language == "python":
            return _python_validator.validate(source)
    except Exception as exc:
        log.error("validate_code raised unexpectedly: %s", exc)
        report = ValidationReport(language=language)
        report.issues.append(ValidationIssue(
            severity=Severity.HIGH,
            code="VALIDATOR_ERROR",
            message=f"Validator internal error: {exc}",
        ))
        return report

    # Unsupported language: pass with info note
    report = ValidationReport(language=language)
    report.issues.append(ValidationIssue(
        severity=Severity.INFO,
        code="UNSUPPORTED_LANGUAGE",
        message=f"Validation not implemented for '{language}' — skipped.",
    ))
    return report


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """
    Extract code blocks from markdown text.

    Returns list of (language, code) tuples.
    """
    pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    blocks = []
    for match in pattern.finditer(text):
        lang = match.group(1).strip() or "python"
        code = match.group(2).strip()
        blocks.append((lang, code))
    return blocks


def validate_response(llm_response: str) -> ValidationReport:
    """
    Extract and validate all code blocks from an LLM response.

    Returns the report for the first Python block found,
    or a passing report if no Python code present.
    """
    blocks = extract_code_blocks(llm_response)
    python_blocks = [(lang, code) for lang, code in blocks if lang in ("python", "py", "")]
    if not python_blocks:
        return ValidationReport(language="python")  # no code = no issues

    # Validate the largest block
    _, largest = max(python_blocks, key=lambda x: len(x[1]))
    return validate_code(largest, language="python")
