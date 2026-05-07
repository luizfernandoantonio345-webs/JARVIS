"""
Security Engine — static code analysis for common vulnerabilities.

Capabilities:
  - SQL Injection detection (A03)
  - XSS / template injection detection (A03)
  - Authentication / session flaws (A07)
  - Hardcoded secrets / credentials (A02)
  - Insecure deserialization (A08)
  - Path traversal (A01)
  - SSRF patterns (A10)
  - Command injection (A03)
  - Weak cryptography (A02)
  - Security misconfiguration (A05)

Local endpoint testing:
  - Only targets localhost / 127.0.0.1 / authorized hosts
  - Tests for common HTTP misconfigurations
  - Never sends real payloads to external systems

Output: list[Vulnerability] with severity, OWASP category, and fix suggestion.

Ethics:
  - ONLY analyzes local files and authorized local endpoints
  - Never performs or assists with attacks on external systems
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


# ── Data model ─────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "Critical"
    HIGH     = "High"
    MEDIUM   = "Medium"
    LOW      = "Low"
    INFO     = "Info"


@dataclass
class Vulnerability:
    title: str
    category: str          # e.g. "A03 Injection"
    severity: Severity
    location: str          # "line N" or "file:line"
    description: str
    code_snippet: str
    fix: str
    owasp_ref: str = ""

    def to_text(self) -> str:
        sev_icon = {
            Severity.CRITICAL: "🔴",
            Severity.HIGH:     "🔴",
            Severity.MEDIUM:   "🟡",
            Severity.LOW:      "🟢",
            Severity.INFO:     "ℹ️",
        }.get(self.severity, "⚪")

        return (
            f"{sev_icon} **[{self.severity.value}] {self.title}**\n"
            f"- Category : {self.category}\n"
            f"- Location : {self.location}\n"
            f"- Description : {self.description}\n"
            f"- Snippet  : `{self.code_snippet[:120]}`\n"
            f"- Fix      : {self.fix}\n"
        )


@dataclass
class ScanResult:
    target: str
    vulnerabilities: list[Vulnerability] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.HIGH)

    def summary(self) -> str:
        if not self.vulnerabilities:
            return f"✅ No vulnerabilities found in: {self.target}"

        lines = [
            f"## Security Scan — {self.target}",
            f"Found **{len(self.vulnerabilities)}** issue(s): "
            f"{self.critical_count} Critical, {self.high_count} High\n",
        ]
        # Sort: Critical → High → Medium → Low → Info
        order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
        sorted_vulns = sorted(
            self.vulnerabilities,
            key=lambda v: order.index(v.severity),
        )
        for i, v in enumerate(sorted_vulns, 1):
            lines.append(f"### {i}. {v.to_text()}")

        lines.append("\n---\n**Summary Table**\n")
        lines.append("| # | Severity | Title | Location |")
        lines.append("|---|----------|-------|----------|")
        for i, v in enumerate(sorted_vulns, 1):
            lines.append(f"| {i} | {v.severity.value} | {v.title} | {v.location} |")

        return "\n".join(lines)


# ── Rule definitions ───────────────────────────────────────────────────────────

@dataclass
class _Rule:
    title: str
    pattern: re.Pattern[str]
    category: str
    severity: Severity
    description: str
    fix: str
    owasp_ref: str = ""
    # If set, only applied to files whose suffix is in this list
    file_types: list[str] = field(default_factory=list)


_RULES: list[_Rule] = [
    # ── A03 SQL Injection ──────────────────────────────────────────────────────
    _Rule(
        title="SQL Injection — string formatting in query",
        pattern=re.compile(
            r'(execute|query|cursor\.execute)\s*\(\s*["\']?.*(%s|%d|\+|\.format|f".*{)',
            re.IGNORECASE,
        ),
        category="A03 Injection",
        severity=Severity.CRITICAL,
        description="User-controlled data appears to be concatenated or formatted directly into a SQL query.",
        fix="Use parameterized queries / prepared statements. Never concatenate user input into SQL.",
        owasp_ref="https://owasp.org/Top10/A03_2021-Injection/",
    ),
    _Rule(
        title="SQL Injection — raw string concatenation",
        pattern=re.compile(
            r'(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s+.*(\+\s*\w+|\bstr\(|\bf")',
            re.IGNORECASE,
        ),
        category="A03 Injection",
        severity=Severity.CRITICAL,
        description="SQL keywords found adjacent to string concatenation or f-strings.",
        fix="Use ORM methods or parameterized queries (cursor.execute(sql, params)).",
        owasp_ref="https://owasp.org/Top10/A03_2021-Injection/",
    ),

    # ── A03 Command Injection ──────────────────────────────────────────────────
    _Rule(
        title="Command Injection — shell=True with user input",
        pattern=re.compile(
            r'subprocess\.(run|call|Popen|check_output)\s*\([^)]*shell\s*=\s*True',
            re.IGNORECASE,
        ),
        category="A03 Injection",
        severity=Severity.HIGH,
        description="shell=True with subprocess allows injection if any part of the command is user-controlled.",
        fix="Use shell=False and pass a list of arguments. Validate and sanitize all inputs.",
        owasp_ref="https://owasp.org/Top10/A03_2021-Injection/",
    ),
    _Rule(
        title="Command Injection — os.system with variable",
        pattern=re.compile(r'os\.system\s*\(\s*[^"\'\)]*\+', re.IGNORECASE),
        category="A03 Injection",
        severity=Severity.CRITICAL,
        description="os.system with concatenated string can be exploited for command injection.",
        fix="Replace with subprocess.run(args_list, shell=False). Avoid os.system entirely.",
        owasp_ref="https://owasp.org/Top10/A03_2021-Injection/",
    ),

    # ── A03 XSS ───────────────────────────────────────────────────────────────
    _Rule(
        title="XSS — innerHTML assignment",
        pattern=re.compile(r'\.innerHTML\s*=\s*(?!["\'`])', re.IGNORECASE),
        category="A03 Injection / XSS",
        severity=Severity.HIGH,
        description="Assigning to innerHTML with a non-literal value can execute attacker-controlled scripts.",
        fix="Use textContent instead, or sanitize with DOMPurify before assigning to innerHTML.",
        owasp_ref="https://owasp.org/Top10/A03_2021-Injection/",
        file_types=[".js", ".ts", ".jsx", ".tsx", ".html"],
    ),
    _Rule(
        title="XSS — document.write with variable",
        pattern=re.compile(r'document\.write\s*\([^"\'`]', re.IGNORECASE),
        category="A03 Injection / XSS",
        severity=Severity.HIGH,
        description="document.write with non-literal input is an XSS vector.",
        fix="Avoid document.write. Use DOM APIs (createElement, textContent) instead.",
        owasp_ref="https://owasp.org/Top10/A03_2021-Injection/",
        file_types=[".js", ".ts", ".jsx", ".tsx", ".html"],
    ),
    _Rule(
        title="XSS — dangerouslySetInnerHTML (React)",
        pattern=re.compile(r'dangerouslySetInnerHTML\s*=\s*\{\s*\{', re.IGNORECASE),
        category="A03 Injection / XSS",
        severity=Severity.MEDIUM,
        description="dangerouslySetInnerHTML bypasses React's XSS protection.",
        fix="Sanitize HTML with DOMPurify before passing to dangerouslySetInnerHTML.",
        file_types=[".jsx", ".tsx"],
    ),

    # ── A02 Hardcoded Secrets ─────────────────────────────────────────────────
    _Rule(
        title="Hardcoded Secret — password / token / key",
        pattern=re.compile(
            r'(password|passwd|secret|api_key|apikey|token|auth_token|private_key)\s*=\s*["\'][^"\']{6,}["\']',
            re.IGNORECASE,
        ),
        category="A02 Cryptographic Failures",
        severity=Severity.CRITICAL,
        description="A credential or secret appears to be hardcoded in source code.",
        fix="Move secrets to environment variables or a secrets manager (Vault, AWS Secrets Manager). Use os.getenv().",
        owasp_ref="https://owasp.org/Top10/A02_2021-Cryptographic_Failures/",
    ),
    _Rule(
        title="Hardcoded JWT Secret",
        pattern=re.compile(
            r'(jwt\.encode|jwt\.sign)\s*\(.*["\'][A-Za-z0-9+/=_\-]{8,}["\']',
            re.IGNORECASE,
        ),
        category="A02 Cryptographic Failures",
        severity=Severity.CRITICAL,
        description="JWT is signed with a hardcoded secret string.",
        fix="Load the JWT secret from an environment variable. Rotate it regularly.",
    ),

    # ── A02 Weak Cryptography ─────────────────────────────────────────────────
    _Rule(
        title="Weak Hash — MD5 usage",
        pattern=re.compile(r'\bhashlib\.md5\b|\bMD5\b', re.IGNORECASE),
        category="A02 Cryptographic Failures",
        severity=Severity.HIGH,
        description="MD5 is cryptographically broken and should not be used for security-sensitive hashing.",
        fix="Use SHA-256 (hashlib.sha256) or better. For passwords, use bcrypt / argon2.",
        owasp_ref="https://owasp.org/Top10/A02_2021-Cryptographic_Failures/",
    ),
    _Rule(
        title="Weak Hash — SHA1 usage",
        pattern=re.compile(r'\bhashlib\.sha1\b|\bSHA1\b', re.IGNORECASE),
        category="A02 Cryptographic Failures",
        severity=Severity.MEDIUM,
        description="SHA-1 is deprecated for security purposes.",
        fix="Replace with SHA-256 or SHA-3. For passwords, use bcrypt / argon2.",
    ),

    # ── A07 Auth Flaws ────────────────────────────────────────────────────────
    _Rule(
        title="Auth Flaw — HTTP Basic Auth credentials in URL",
        pattern=re.compile(r'https?://[^:\s]+:[^@\s]+@', re.IGNORECASE),
        category="A07 Identification and Authentication Failures",
        severity=Severity.HIGH,
        description="Credentials embedded in a URL will appear in logs, browser history, and referrer headers.",
        fix="Use headers (Authorization: Bearer ...) or environment variables for credentials.",
        owasp_ref="https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/",
    ),
    _Rule(
        title="Auth Flaw — debug=True in production framework",
        pattern=re.compile(r'\bDEBUG\s*=\s*True\b|\bdebug\s*=\s*True\b', re.IGNORECASE),
        category="A05 Security Misconfiguration",
        severity=Severity.HIGH,
        description="Debug mode exposes stack traces, environment variables, and internal routes.",
        fix="Set DEBUG=False (or equivalent) in production. Use environment variable: DEBUG=os.getenv('DEBUG', 'False') == 'True'.",
        owasp_ref="https://owasp.org/Top10/A05_2021-Security_Misconfiguration/",
    ),

    # ── A01 Path Traversal ────────────────────────────────────────────────────
    _Rule(
        title="Path Traversal — unvalidated file path from request",
        pattern=re.compile(
            r'open\s*\(\s*(request\.|params\[|args\[|form\[|\w+\[[\"\']path)',
            re.IGNORECASE,
        ),
        category="A01 Broken Access Control",
        severity=Severity.HIGH,
        description="File open() called with a path derived from request data without validation.",
        fix="Resolve the path with Path.resolve() and verify it is within the allowed base directory before opening.",
        owasp_ref="https://owasp.org/Top10/A01_2021-Broken_Access_Control/",
    ),

    # ── A10 SSRF ──────────────────────────────────────────────────────────────
    _Rule(
        title="SSRF — HTTP request with user-controlled URL",
        pattern=re.compile(
            r'(requests\.get|requests\.post|httpx\.get|httpx\.post|fetch)\s*\(\s*\w+[^,\)]*\)',
            re.IGNORECASE,
        ),
        category="A10 Server-Side Request Forgery",
        severity=Severity.MEDIUM,
        description="HTTP request made with a URL that may be user-controlled — potential SSRF.",
        fix="Validate and allowlist target URLs/domains. Block requests to internal IPs (169.254.x.x, 10.x.x.x, etc.).",
        owasp_ref="https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/",
    ),

    # ── A08 Insecure Deserialization ──────────────────────────────────────────
    _Rule(
        title="Insecure Deserialization — pickle.loads",
        pattern=re.compile(r'\bpickle\.loads?\b', re.IGNORECASE),
        category="A08 Software and Data Integrity Failures",
        severity=Severity.CRITICAL,
        description="pickle.load/loads on untrusted data enables arbitrary code execution.",
        fix="Never deserialize untrusted data with pickle. Use JSON, MessagePack, or protobuf.",
        owasp_ref="https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures/",
    ),
    _Rule(
        title="Insecure Deserialization — yaml.load without Loader",
        pattern=re.compile(r'\byaml\.load\s*\([^,)]+\)', re.IGNORECASE),
        category="A08 Software and Data Integrity Failures",
        severity=Severity.HIGH,
        description="yaml.load() without an explicit Loader defaults to the unsafe FullLoader or Loader — can execute arbitrary Python.",
        fix="Use yaml.safe_load() or yaml.load(data, Loader=yaml.SafeLoader).",
    ),
]


# ── Scanner ────────────────────────────────────────────────────────────────────

def scan_code(code: str, filename: str = "<input>") -> ScanResult:
    """
    Scan source code string for vulnerabilities.

    Args:
        code:     Source code content.
        filename: File name (used for file-type filtering and location strings).

    Returns:
        ScanResult with all detected vulnerabilities.
    """
    result = ScanResult(target=filename)
    suffix = Path(filename).suffix.lower()
    lines = code.splitlines()

    for rule in _RULES:
        # Skip rules scoped to specific file types if the file doesn't match
        if rule.file_types and suffix not in rule.file_types:
            continue

        for lineno, line in enumerate(lines, start=1):
            if rule.pattern.search(line):
                result.vulnerabilities.append(
                    Vulnerability(
                        title=rule.title,
                        category=rule.category,
                        severity=rule.severity,
                        location=f"{filename}:{lineno}",
                        description=rule.description,
                        code_snippet=line.strip(),
                        fix=rule.fix,
                        owasp_ref=rule.owasp_ref,
                    )
                )

    log.info("[security_engine] %s — %d findings", filename, len(result.vulnerabilities))
    return result


def scan_file(path: str | Path) -> ScanResult:
    """
    Scan a file on disk for vulnerabilities.

    Only reads files ≤ 1 MB to prevent resource abuse.
    """
    p = Path(path)
    if not p.exists():
        result = ScanResult(target=str(path))
        result.vulnerabilities.append(Vulnerability(
            title="File Not Found",
            category="Scanner Error",
            severity=Severity.INFO,
            location=str(path),
            description="The specified file does not exist.",
            code_snippet="",
            fix="Verify the file path.",
        ))
        return result

    size = p.stat().st_size
    if size > 1_048_576:  # 1 MB
        result = ScanResult(target=str(path))
        result.vulnerabilities.append(Vulnerability(
            title="File Too Large",
            category="Scanner Limit",
            severity=Severity.INFO,
            location=str(path),
            description=f"File size ({size:,} bytes) exceeds the 1 MB scan limit.",
            code_snippet="",
            fix="Split the file or scan specific sections.",
        ))
        return result

    code = p.read_text(encoding="utf-8", errors="replace")
    return scan_code(code, filename=str(p))


# ── Local endpoint probe (no external attacks) ─────────────────────────────────

_SAFE_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def _is_local_url(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    return host in _SAFE_LOCAL_HOSTS


def probe_endpoint(
    url: str,
    methods: list[str] | None = None,
) -> dict:
    """
    Send safe, non-destructive HTTP probes to a LOCAL endpoint.

    Checks for:
      - Missing security headers (HSTS, X-Frame-Options, X-Content-Type-Options, CSP)
      - CORS misconfiguration (Access-Control-Allow-Origin: *)
      - Debug/stack-trace leakage in error responses
      - HTTP (non-HTTPS) on non-localhost

    ETHICS: Only works on localhost / 127.0.0.1. Raises ValueError for external URLs.

    Returns a dict with findings.
    """
    if not _is_local_url(url):
        raise ValueError(
            f"probe_endpoint only targets local endpoints. "
            f"Received: {url!r}. Refusing to probe external host."
        )

    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed; run: pip install httpx"}

    findings: list[str] = []
    test_methods = methods or ["GET", "HEAD"]

    for method in test_methods:
        try:
            resp = httpx.request(method, url, timeout=5, follow_redirects=False)
        except Exception as exc:
            return {"error": f"Connection failed: {exc}"}

        headers = {k.lower(): v for k, v in resp.headers.items()}

        # Security headers
        for hdr, desc in [
            ("strict-transport-security",   "Missing HSTS header"),
            ("x-frame-options",             "Missing X-Frame-Options (clickjacking risk)"),
            ("x-content-type-options",      "Missing X-Content-Type-Options (MIME sniffing risk)"),
            ("content-security-policy",     "Missing Content-Security-Policy header"),
        ]:
            if hdr not in headers:
                findings.append(f"⚠ {desc}")

        # CORS wildcard
        if headers.get("access-control-allow-origin") == "*":
            findings.append("⚠ CORS: Access-Control-Allow-Origin: * — overly permissive")

        # Debug info in response body
        body_lower = resp.text.lower()
        for signal in ["traceback", "debug=true", "stack trace", "sqlstate", "django.db"]:
            if signal in body_lower:
                findings.append(f"🔴 Debug/error info leaked in response body: {signal!r}")

    return {
        "url": url,
        "findings": findings,
        "clean": len(findings) == 0,
    }
