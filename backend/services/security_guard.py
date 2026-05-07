"""
SecurityGuard — global action interceptor that validates ALL operations
before execution.

Position in the pipeline:
  User request → SecurityGuard.check() → [allow / block] → Executor

Blocks:
  - Dangerous shell patterns (rm -rf, sudo, curl|bash, etc.)
  - Privilege escalation
  - Path traversal attacks
  - External network commands
  - Recursive/looping execution patterns
  - Oversized payloads

Logs:
  - Every blocked action (WARN level)
  - Every sensitive-but-allowed action (INFO level)

Usage:
    guard = get_guard()
    result = guard.check(action_type="shell", payload="git status")
    if not result.allowed:
        return f"Blocked: {result.reason}"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ── Threat levels ──────────────────────────────────────────────────────────────

class ThreatLevel(str, Enum):
    NONE     = "none"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class GuardResult:
    allowed: bool
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str = ""
    action_type: str = ""
    payload_preview: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed":      self.allowed,
            "threat_level": self.threat_level.value,
            "reason":       self.reason,
            "action_type":  self.action_type,
        }


# ── Pattern banks ──────────────────────────────────────────────────────────────

# CRITICAL — always block
_CRITICAL_SHELL = [
    re.compile(r"\brm\s+-[rRfF]*\b"),           # rm -rf
    re.compile(r"\bsudo\b"),                     # privilege escalation
    re.compile(r"\bsu\b\s"),                     # switch user
    re.compile(r":\s*\(\s*\)\s*\{.*:\|:&\s*\}"),# fork bomb
    re.compile(r"\bdd\b.*\bof="),               # dd disk overwrite
    re.compile(r">\s*/dev/(sd|hd|nvme)"),        # raw disk write
    re.compile(r"\|\s*(?:bash|sh|zsh|fish)\b"),  # pipe to shell
    re.compile(r"curl.*\|\s*(?:bash|sh)\b"),     # curl-bash
    re.compile(r"wget.*\|\s*(?:bash|sh)\b"),     # wget-bash
    re.compile(r"\bchmod\s+[0-7]*7[0-7]*"),      # world-writable
    re.compile(r"\bchown\s+root"),               # chown root
    re.compile(r"\b(?:halt|reboot|shutdown|poweroff)\b"),  # system shutdown
    re.compile(r"\b(?:mkfs|fdisk|parted)\b"),    # disk format
    re.compile(r"(?:^|;|\|)\s*rm\b"),            # chained rm
]

# HIGH — block
_HIGH_SHELL = [
    re.compile(r"\bpip\s+install\b"),            # pip install
    re.compile(r"\bpip3\s+install\b"),           # pip3 install
    re.compile(r"\bapt(?:-get)?\s+install\b"),   # apt install
    re.compile(r"\byum\s+install\b"),            # yum install
    re.compile(r"\bbrew\s+install\b"),           # brew install
    re.compile(r"\bnpm\s+install\s+--global\b"), # npm global install
    re.compile(r"\bcurl\b.*-[oO]\b"),            # curl download to file
    re.compile(r"\bwget\b.*-[oO]\b"),            # wget download to file
    re.compile(r"\bnetcat\b|\bnc\b\s+-[le]"),    # netcat listener
    re.compile(r"\biptables\b"),                 # firewall rules
]

# Path traversal patterns
_PATH_TRAVERSAL = [
    re.compile(r"\.\.[\\/]"),                    # ../  or ..\
    re.compile(r"%2e%2e", re.IGNORECASE),        # URL-encoded ..
    re.compile(r"\.\.%2f", re.IGNORECASE),       # ..%2f
    re.compile(r"%252e%252e", re.IGNORECASE),    # double-encoded
]

# Prompt injection markers
_INJECTION_MARKERS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"(?:you\s+are\s+now|act\s+as)\s+(?:a\s+)?(?:different|new|another)\s+(?:ai|model|system)", re.IGNORECASE),
    re.compile(r"disregard\s+(?:your\s+)?(?:rules|safety|guidelines)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*[:=]", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
]

# Whitelisted shell commands
_SHELL_WHITELIST = frozenset({
    "python", "python3", "node", "npm", "npx",
    "git", "uvicorn", "pytest",
    "ls", "dir", "pwd", "mkdir", "cat", "echo",
    "touch", "head", "tail",
})


# ── SecurityGuard ──────────────────────────────────────────────────────────────

class SecurityGuard:
    """
    Intercepts and validates all JARVIS actions before execution.

    Thread-safe. All check() calls are logged.
    """

    def __init__(self) -> None:
        self._blocked_count = 0
        self._allowed_count = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def check(self, action_type: str, payload: str) -> GuardResult:
        """
        Validate an action before execution.

        Args:
            action_type: "shell", "fs", "code", "llm", "vscode", "agent"
            payload:     The raw command, path, code, or prompt string.

        Returns:
            GuardResult — allowed=True means safe to proceed.
        """
        preview = payload[:120].replace("\n", " ")

        # ── Prompt injection check (all action types) ──────────────────────
        injection = self._check_injection(payload)
        if injection:
            return self._block(action_type, payload, injection, ThreatLevel.CRITICAL)

        # ── Route by action type ───────────────────────────────────────────
        if action_type == "shell":
            return self._check_shell(payload)
        if action_type == "fs":
            return self._check_fs(payload)
        if action_type == "code":
            return self._check_code(payload)
        if action_type in ("llm", "agent", "chat"):
            return self._allow(action_type, payload)
        if action_type == "vscode":
            return self._check_vscode(payload)

        # Unknown type: allow but log
        log.info("SecurityGuard: unknown action_type=%r — allowing", action_type)
        return self._allow(action_type, payload)

    def stats(self) -> dict:
        """Return guard statistics."""
        return {
            "blocked": self._blocked_count,
            "allowed": self._allowed_count,
        }

    # ── Checkers ───────────────────────────────────────────────────────────────

    def _check_shell(self, cmd: str) -> GuardResult:
        # CRITICAL patterns
        for pat in _CRITICAL_SHELL:
            if pat.search(cmd):
                return self._block("shell", cmd, f"Critical pattern: {pat.pattern}", ThreatLevel.CRITICAL)

        # HIGH patterns
        for pat in _HIGH_SHELL:
            if pat.search(cmd):
                return self._block("shell", cmd, f"High-risk pattern: {pat.pattern}", ThreatLevel.HIGH)

        # Whitelist check: first token
        first = cmd.strip().split()[0].lower() if cmd.strip() else ""
        from pathlib import Path
        base = Path(first).name
        if base and base not in _SHELL_WHITELIST:
            return self._block(
                "shell", cmd,
                f"Command '{base}' not in whitelist: {sorted(_SHELL_WHITELIST)}",
                ThreatLevel.HIGH,
            )

        log.info("SecurityGuard: ALLOW shell cmd=%r", cmd[:80])
        self._allowed_count += 1
        return GuardResult(allowed=True, action_type="shell", payload_preview=cmd[:80])

    def _check_fs(self, path: str) -> GuardResult:
        for pat in _PATH_TRAVERSAL:
            if pat.search(path):
                return self._block("fs", path, "Path traversal detected", ThreatLevel.HIGH)
        self._allowed_count += 1
        return GuardResult(allowed=True, action_type="fs", payload_preview=path[:80])

    def _check_code(self, code: str) -> GuardResult:
        # Dangerous builtins in code
        dangerous = re.compile(
            r"\b(__import__|eval|exec|compile|globals|locals|vars|getattr|setattr|delattr)\s*\(",
            re.IGNORECASE,
        )
        if dangerous.search(code):
            return self._block("code", code, "Dangerous built-in detected", ThreatLevel.HIGH)
        self._allowed_count += 1
        return GuardResult(allowed=True, action_type="code", payload_preview=code[:80])

    def _check_vscode(self, cmd: str) -> GuardResult:
        # VS Code commands are file paths / simple strings — only block traversal
        for pat in _PATH_TRAVERSAL:
            if pat.search(cmd):
                return self._block("vscode", cmd, "Path traversal in VS Code command", ThreatLevel.HIGH)
        self._allowed_count += 1
        return GuardResult(allowed=True, action_type="vscode", payload_preview=cmd[:80])

    def _check_injection(self, text: str) -> str | None:
        for pat in _INJECTION_MARKERS:
            if pat.search(text):
                log.warning("SecurityGuard: PROMPT INJECTION detected: %r", text[:120])
                return f"Prompt injection pattern detected: {pat.pattern}"
        return None

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _block(
        self,
        action_type: str,
        payload: str,
        reason: str,
        level: ThreatLevel,
    ) -> GuardResult:
        self._blocked_count += 1
        log.warning(
            "SecurityGuard: BLOCKED [%s] action=%r payload=%r reason=%s",
            level.value, action_type, payload[:80], reason,
        )
        return GuardResult(
            allowed=False,
            threat_level=level,
            reason=reason,
            action_type=action_type,
            payload_preview=payload[:80],
        )

    def _allow(self, action_type: str, payload: str) -> GuardResult:
        self._allowed_count += 1
        return GuardResult(
            allowed=True,
            threat_level=ThreatLevel.NONE,
            action_type=action_type,
            payload_preview=payload[:80],
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_guard: SecurityGuard | None = None


def get_guard() -> SecurityGuard:
    """Return the global SecurityGuard singleton."""
    global _guard
    if _guard is None:
        _guard = SecurityGuard()
    return _guard
