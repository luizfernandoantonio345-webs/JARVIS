"""
Sentinel v2 - File-system watchdog + contextual security scanner.
Broadcasts risk findings to JARVIS Orb via /system/update (HTTP).

Features:
- Contextual regex scan (strips Python # and JS // comments before matching)
- Skips test files (_test.py, .spec.ts, .test.ts)
- Skips benign password assignments (None, empty string, False)
- RiskFinding model with file, line, pattern, severity, snippet
- HTTP retry with exponential backoff: delays = [1, 3, 5]
- sentinel_queue.json local queue when API down; flushed on reconnect
- Dedicated logs/sentinel.log with RotatingFileHandler (10 MB x 5)
- Env vars: JARVIS_SENTINEL_DEBOUNCE, JARVIS_SENTINEL_POLL_INTERVAL
- Stats counters accessible via /sentinel/status
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

try:
    from schemas.ws_messages import RiskFinding, error_msg, idle_msg
    _HAS_SCHEMA = True
except ImportError:
    _HAS_SCHEMA = False
    RiskFinding = None

JARVIS_API_URL     = os.getenv("JARVIS_API_URL", "http://localhost:8000")
DEBOUNCE_SECS      = float(os.getenv("JARVIS_SENTINEL_DEBOUNCE", "2.0"))
POLL_INTERVAL_SECS = float(os.getenv("JARVIS_SENTINEL_POLL_INTERVAL", "5.0"))
WATCH_PATH         = Path(os.getenv("JARVIS_WATCH_PATH", str(Path(__file__).parent.parent)))

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "sentinel.log"

sentinel_log = logging.getLogger("javis.sentinel")
if not sentinel_log.handlers:
    _rh = RotatingFileHandler(_LOG_FILE, maxBytes=10_485_760, backupCount=5, encoding="utf-8")
    _rh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    sentinel_log.addHandler(_rh)
    sentinel_log.addHandler(logging.StreamHandler())
sentinel_log.setLevel(logging.INFO)

_QUEUE_FILE = Path(__file__).parent / "sentinel_queue.json"


def _load_queue() -> list:
    if _QUEUE_FILE.exists():
        try:
            data = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_queue(queue: list) -> None:
    try:
        _QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    except OSError as exc:
        sentinel_log.warning("Could not persist queue: %s", exc)


_stats: dict[str, Any] = {
    "events_today": 0,
    "risks_found_today": 0,
    "last_scan": 0.0,
    "files_monitored": 0,
    "running": False,
}


def get_stats() -> dict:
    return {**_stats, "queue_pending": len(_load_queue())}


_RISK_PATTERNS: list = [
    ("hardcoded_secret",
     re.compile(r'(?:password|passwd|secret|api_key|token)\s*=\s*["\'][^"\']{4,}["\']', re.IGNORECASE),
     "critical"),
    ("jwt_hardcoded",
     re.compile(r'jwt\.encode\([^,]+,\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
     "critical"),
    ("eval_usage",       re.compile(r'\beval\s*\(', re.IGNORECASE), "high"),
    ("exec_usage",       re.compile(r'\bexec\s*\(', re.IGNORECASE), "high"),
    ("shell_true",       re.compile(r'shell\s*=\s*True', re.IGNORECASE), "high"),
    ("sql_concat",
     re.compile(r'(?:SELECT|INSERT|UPDATE|DELETE)\b.*\+\s*(?:f?["\']|str\(|\w+\s*\+)', re.IGNORECASE),
     "high"),
    ("open_bind",        re.compile(r'bind\s*\(\s*["\']0\.0\.0\.0["\']', re.IGNORECASE), "medium"),
    ("debug_true",       re.compile(r'\bDEBUG\s*=\s*True', re.IGNORECASE), "medium"),
    ("print_secret",     re.compile(r'\bprint\s*\([^\)]*(?:password|secret|token)', re.IGNORECASE), "medium"),
]

_BENIGN_PASSWORD_RE = re.compile(
    r'(?:password|passwd|secret)\s*=\s*(?:None|False|True|""|\'\')',
    re.IGNORECASE,
)
_TEST_SUFFIXES = ("_test.py", ".spec.ts", ".test.ts", "_test.ts", "test_")
_WATCH_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".env", ".json", ".yaml", ".yml"}


def _is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(s) or name.startswith(s) for s in _TEST_SUFFIXES)


def _strip_line_comments(line: str, ext: str) -> str:
    if ext == ".py":
        code, _, _ = line.partition(" #")
        return code
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        code, _, _ = line.partition("//")
        return code
    return line


def scan_file(filepath: Path) -> list:
    findings: list = []
    ext = filepath.suffix.lower()
    if ext not in _WATCH_EXTENSIONS or _is_test_file(filepath):
        return findings
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        sentinel_log.debug("Cannot read %s: %s", filepath, exc)
        return findings

    in_block_comment = False
    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if ext in (".ts", ".tsx", ".js", ".jsx"):
            if "/*" in stripped:
                in_block_comment = True
            if "*/" in stripped:
                in_block_comment = False
                continue
            if in_block_comment:
                continue
        if ext == ".py" and (stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''")):
            continue
        code_line = _strip_line_comments(raw_line, ext)
        if _BENIGN_PASSWORD_RE.search(code_line):
            continue
        for pattern_name, regex, severity in _RISK_PATTERNS:
            if regex.search(code_line):
                snippet = raw_line.strip()[:120]
                finding = {"file": str(filepath.relative_to(WATCH_PATH)), "line": lineno,
                           "pattern": pattern_name, "severity": severity, "snippet": snippet}
                findings.append(finding)
                sentinel_log.warning("RISK [%s] %s:%d - %s", severity.upper(), finding["file"], lineno, snippet)
                break
    return findings


def _build_broadcast_payload(findings: list) -> dict:
    message = f"Sentinel: {len(findings)} risco(s) detectado(s)"
    if _HAS_SCHEMA:
        risk_objects = []
        for f in findings:
            try:
                risk_objects.append(RiskFinding(**f).model_dump())
            except Exception:
                risk_objects.append(f)
        return error_msg(message, findings=risk_objects, source="sentinel")
    return {"status": "error", "message": message, "source": "sentinel",
            "ts": time.time(), "data": {"findings": findings}}


def _broadcast_findings(findings: list) -> bool:
    payload = _build_broadcast_payload(findings)
    delays = [1, 3, 5]
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = requests.post(f"{JARVIS_API_URL}/system/update", json=payload, timeout=5)
            resp.raise_for_status()
            sentinel_log.info("Broadcast OK (attempt %d): %d findings", attempt, len(findings))
            return True
        except requests.RequestException as exc:
            sentinel_log.warning("Broadcast attempt %d failed: %s", attempt, exc)
            if attempt < len(delays):
                time.sleep(delay)
    return False


def _broadcast_idle(message: str) -> None:
    if _HAS_SCHEMA:
        payload = idle_msg(message, source="sentinel")
    else:
        payload = {"status": "idle", "message": message, "source": "sentinel", "ts": time.time()}
    try:
        requests.post(f"{JARVIS_API_URL}/system/update", json=payload, timeout=3)
    except requests.RequestException:
        pass


def _flush_queue() -> None:
    queue = _load_queue()
    if not queue:
        return
    sentinel_log.info("Flushing %d queued findings...", len(queue))
    remaining = []
    for item in queue:
        payload = _build_broadcast_payload(item.get("findings", []))
        try:
            resp = requests.post(f"{JARVIS_API_URL}/system/update", json=payload, timeout=5)
            resp.raise_for_status()
        except requests.RequestException:
            remaining.append(item)
    _save_queue(remaining)
    if remaining:
        sentinel_log.warning("%d items remain in queue after flush", len(remaining))
    else:
        sentinel_log.info("Queue flushed successfully")


class SentinelHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self._timers: dict = {}
        self._lock = threading.Lock()

    def _debounced_scan(self, path_str: str) -> None:
        with self._lock:
            if path_str in self._timers:
                self._timers[path_str].cancel()
            timer = threading.Timer(DEBOUNCE_SECS, self._do_scan, args=(path_str,))
            self._timers[path_str] = timer
            timer.start()

    def _do_scan(self, path_str: str) -> None:
        with self._lock:
            self._timers.pop(path_str, None)
        path = Path(path_str)
        if not path.exists() or not path.is_file():
            return
        _stats["events_today"] += 1
        _stats["last_scan"] = time.time()
        findings = scan_file(path)
        if not findings:
            return
        _stats["risks_found_today"] += len(findings)
        success = _broadcast_findings(findings)
        if not success:
            queue = _load_queue()
            queue.append({"ts": time.time(), "file": path_str, "findings": findings})
            _save_queue(queue)
            sentinel_log.error("Broadcast failed - queued %d findings from %s", len(findings), path_str)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._debounced_scan(str(event.src_path))

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._debounced_scan(str(event.src_path))


_observer = None
_sentinel_handler = None


def start_sentinel() -> None:
    global _observer, _sentinel_handler
    if _stats["running"]:
        sentinel_log.info("Sentinel already running")
        return
    _stats["files_monitored"] = sum(
        1 for p in WATCH_PATH.rglob("*")
        if p.is_file() and p.suffix.lower() in _WATCH_EXTENSIONS
    )
    _sentinel_handler = SentinelHandler()
    _observer = Observer()
    _observer.schedule(_sentinel_handler, str(WATCH_PATH), recursive=True)
    _observer.start()
    _stats["running"] = True
    sentinel_log.info("Sentinel v2 started. Watching: %s | Files: %d | Debounce: %.1fs",
                      WATCH_PATH, _stats["files_monitored"], DEBOUNCE_SECS)
    _flush_queue()
    _broadcast_idle("Sentinel v2 ativo. Monitorando repositorio.")


def stop_sentinel() -> None:
    global _observer
    if _observer and _stats["running"]:
        _observer.stop()
        _observer.join(timeout=5)
        _stats["running"] = False
        sentinel_log.info("Sentinel stopped.")


# Backwards-compat shim for code using the old start_watchdog() API
def start_watchdog(path_to_watch: str = None, on_change=None):
    if path_to_watch:
        import os as _os
        _os.environ.setdefault("JARVIS_WATCH_PATH", path_to_watch)
    start_sentinel()