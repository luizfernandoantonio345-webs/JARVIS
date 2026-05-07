"""
night_mode — Autonomous Night Mode  (FASE 13A)

Lifecycle
---------
  23:00  enter()
           • Sets operational_mode = "silent"  (no voice, no notifications)
           • Records start timestamp + previous mode
  23:00+  process_pending_jobs()
           • Iterates jobs/ directory; runs jobs with risk_score <= LOW_RISK_MAX
           • Skips any job already done, failed, or escalated
           • Calls the AutoDev bridge to resume/run each job
  ∼01:00  run_tests()
           • Runs pytest on the tests/ directory
           • Captures stdout + exit code
           • Saves report to reports/night/<date>/test_report.txt
  ∼02:00  maintenance()
           • SQLite VACUUM on memory.db
           • Deletes log files older than LOG_RETENTION_DAYS
           • Rotates night reports older than REPORT_RETENTION_DAYS
  07:00   generate_morning_summary()
           • Reads persisted NightWorkSummary
           • Returns a human-readable briefing string
           • Persisted to reports/night/<date>/summary.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from config import get_config

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LOW_RISK_MAX         = 40          # risk score threshold for unattended execution
LOG_RETENTION_DAYS   = 7
REPORT_RETENTION_DAYS = 30
_NIGHT_REPORTS_DIR   = Path(__file__).parent.parent / "reports" / "night"


# ── Data model ────────────────────────────────────────────────────────────────

class NightModeState(str, Enum):
    INACTIVE   = "inactive"
    ENTERING   = "entering"
    ACTIVE     = "active"
    COMPLETING = "completing"
    DONE       = "done"


@dataclass
class JobResult:
    job_id: str
    status: str          # "processed" | "skipped" | "failed"
    reason: str = ""
    duration_s: float = 0.0


@dataclass
class NightWorkSummary:
    date: str = field(default_factory=lambda: date.today().isoformat())
    started_at: str = ""
    ended_at: str = ""
    previous_mode: str = "assistant"
    jobs_processed: int = 0
    jobs_skipped: int = 0
    jobs_failed: int = 0
    job_details: list[JobResult] = field(default_factory=list)
    test_exit_code: int | None = None
    test_passed: int = 0
    test_failed: int = 0
    test_errors: int = 0
    test_report_path: str = ""
    vacuum_done: bool = False
    logs_deleted: int = 0
    maintenance_errors: list[str] = field(default_factory=list)
    state: NightModeState = NightModeState.INACTIVE


# ── Night Mode Controller ─────────────────────────────────────────────────────

class NightModeController:
    """
    Orchestrates all autonomous work performed while the user is away.
    Instantiated lazily via get_night_mode_controller().
    """

    def __init__(self) -> None:
        self._state = NightModeState.INACTIVE
        self._summary: NightWorkSummary | None = None
        self._lock = asyncio.Lock()
        _NIGHT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> NightModeState:
        return self._state

    @property
    def summary(self) -> NightWorkSummary | None:
        return self._summary

    async def run_night_work(self) -> NightWorkSummary:
        """
        Full autonomous night work pipeline.
        Called by NightScheduler at NIGHT_START_HOUR.
        Returns the completed NightWorkSummary.
        """
        async with self._lock:
            if self._state not in (NightModeState.INACTIVE, NightModeState.DONE):
                log.warning("NightMode: already running (state=%s) — skipping", self._state)
                return self._summary or NightWorkSummary()

            summary = NightWorkSummary(
                started_at=datetime.now(timezone.utc).isoformat(),
                date=date.today().isoformat(),
            )
            self._summary = summary
            self._state = NightModeState.ENTERING

        log.info("NightMode: entering silent mode")
        await self._enter_silent_mode(summary)

        self._state = NightModeState.ACTIVE

        try:
            log.info("NightMode: processing pending jobs")
            await self._process_pending_jobs(summary)

            log.info("NightMode: running automated tests")
            await self._run_tests(summary)

            log.info("NightMode: running maintenance tasks")
            await self._maintenance(summary)
        except Exception as exc:
            log.error("NightMode: pipeline error: %s", exc, exc_info=True)
            summary.maintenance_errors.append(f"pipeline_error: {exc}")
        finally:
            self._state = NightModeState.COMPLETING
            summary.ended_at = datetime.now(timezone.utc).isoformat()
            summary.state = NightModeState.DONE
            self._state = NightModeState.DONE
            self._persist_summary(summary)
            log.info(
                "NightMode: complete — jobs=%d tests_passed=%d tests_failed=%d",
                summary.jobs_processed, summary.test_passed, summary.test_failed,
            )

        return summary

    async def generate_morning_summary(self) -> str:
        """
        Compose a human-readable morning briefing from the night work summary.
        Called by NightScheduler at MORNING_HOUR.
        """
        summary = self._load_last_summary()
        if summary is None:
            return "Jarvis trabalhou durante a noite, mas nenhum resumo foi encontrado."

        lines: list[str] = ["=== Relatório Noturno ==="]
        lines.append(f"Período: {summary.get('started_at', '?')[:16]} → {summary.get('ended_at', '?')[:16]}")

        jobs_p = summary.get("jobs_processed", 0)
        jobs_s = summary.get("jobs_skipped", 0)
        jobs_f = summary.get("jobs_failed", 0)
        lines.append(
            f"Jobs: {jobs_p} processados, {jobs_s} pulados, {jobs_f} com falha."
        )

        tc = summary.get("test_exit_code")
        if tc is not None:
            passed  = summary.get("test_passed", 0)
            failed  = summary.get("test_failed", 0)
            errors  = summary.get("test_errors", 0)
            status  = "✅ PASSOU" if tc == 0 else "❌ FALHOU"
            lines.append(f"Testes: {status} — {passed} ok, {failed} falhas, {errors} erros.")
        else:
            lines.append("Testes: não executados.")

        if summary.get("vacuum_done"):
            lines.append("Manutenção: VACUUM do banco concluído.")
        deleted = summary.get("logs_deleted", 0)
        if deleted:
            lines.append(f"Limpeza: {deleted} arquivo(s) de log antigo(s) removido(s).")

        errs = summary.get("maintenance_errors", [])
        if errs:
            lines.append(f"Atenção: {len(errs)} erro(s) durante a madrugada — revise o log.")

        report_path = summary.get("test_report_path", "")
        if report_path:
            lines.append(f"Relatório completo: {report_path}")

        return "\n".join(lines)

    def get_status(self) -> dict[str, Any]:
        """Return current state dict for the REST endpoint."""
        return {
            "state": self._state.value,
            "summary": asdict(self._summary) if self._summary else None,
            "last_summary": self._load_last_summary(),
        }

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _enter_silent_mode(self, summary: NightWorkSummary) -> None:
        cfg = get_config()
        try:
            from core.system_mode import apply_mode, get_current_mode
            summary.previous_mode = get_current_mode()
            apply_mode("silent")
            log.info("NightMode: operational_mode → silent (was %s)", summary.previous_mode)
        except Exception as exc:
            log.warning("NightMode: could not apply silent mode: %s", exc)
            summary.previous_mode = cfg.operational_mode

    async def _process_pending_jobs(self, summary: NightWorkSummary) -> None:
        cfg = get_config()
        jobs_base = cfg.jarvis_jobs_dir
        if not jobs_base.exists():
            log.info("NightMode: jobs dir not found, skipping job processing")
            return

        job_dirs = [d for d in jobs_base.iterdir() if d.is_dir()]
        log.info("NightMode: found %d job directories", len(job_dirs))

        for job_dir in sorted(job_dirs):
            result = await self._process_single_job(job_dir)
            summary.job_details.append(result)
            if result.status == "processed":
                summary.jobs_processed += 1
            elif result.status == "skipped":
                summary.jobs_skipped += 1
            else:
                summary.jobs_failed += 1
            # Brief pause between jobs to avoid overwhelming resources
            await asyncio.sleep(2)

    async def _process_single_job(self, job_dir: Path) -> JobResult:
        job_id = job_dir.name
        state_file = job_dir / "state.json"

        if not state_file.exists():
            return JobResult(job_id=job_id, status="skipped", reason="no state.json")

        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return JobResult(job_id=job_id, status="skipped", reason=f"unreadable state: {exc}")

        status = state.get("status", "")
        if status in {"done", "escalated", "error", "cancelled"}:
            return JobResult(job_id=job_id, status="skipped", reason=f"already {status}")

        # Risk check
        risk_score = state.get("risk_score", 0)
        if risk_score > LOW_RISK_MAX:
            return JobResult(
                job_id=job_id,
                status="skipped",
                reason=f"risk_score={risk_score} > threshold={LOW_RISK_MAX}",
            )

        t0 = time.monotonic()
        try:
            from services.autodev_bridge import AutoDevBridge
            bridge = AutoDevBridge()
            await bridge.resume_job(job_id)
            duration = time.monotonic() - t0
            log.info("NightMode: job %s processed in %.1fs", job_id, duration)
            return JobResult(job_id=job_id, status="processed", duration_s=round(duration, 1))
        except ImportError:
            # AutoDevBridge not available — mark as attempted
            log.debug("NightMode: AutoDevBridge not available, marking job as processed")
            return JobResult(job_id=job_id, status="skipped", reason="AutoDevBridge unavailable")
        except Exception as exc:
            log.warning("NightMode: job %s failed: %s", job_id, exc)
            return JobResult(job_id=job_id, status="failed", reason=str(exc)[:200])

    async def _run_tests(self, summary: NightWorkSummary) -> None:
        report_dir = _NIGHT_REPORTS_DIR / summary.date
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "test_report.txt"

        tests_dir = Path(__file__).parent.parent.parent / "tests"
        if not tests_dir.exists():
            log.warning("NightMode: tests/ directory not found, skipping")
            return

        cmd = [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=short", "--no-header"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(Path(__file__).parent.parent),
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
            output = stdout_bytes.decode(errors="replace")
            summary.test_exit_code = proc.returncode

            # Parse summary line: "X passed, Y failed, Z errors"
            for line in output.splitlines():
                line_l = line.lower()
                if "passed" in line_l or "failed" in line_l or "error" in line_l:
                    import re
                    m = re.search(r"(\d+) passed", line_l)
                    if m:
                        summary.test_passed = int(m.group(1))
                    m = re.search(r"(\d+) failed", line_l)
                    if m:
                        summary.test_failed = int(m.group(1))
                    m = re.search(r"(\d+) error", line_l)
                    if m:
                        summary.test_errors = int(m.group(1))

            report_path.write_text(output, encoding="utf-8")
            summary.test_report_path = str(report_path)
            log.info(
                "NightMode: tests done — exit=%d passed=%d failed=%d",
                proc.returncode, summary.test_passed, summary.test_failed,
            )
        except asyncio.TimeoutError:
            log.error("NightMode: tests timed out after 600s")
            summary.maintenance_errors.append("tests_timeout")
        except Exception as exc:
            log.error("NightMode: test run failed: %s", exc)
            summary.maintenance_errors.append(f"tests_error: {exc}")

    async def _maintenance(self, summary: NightWorkSummary) -> None:
        await asyncio.gather(
            self._vacuum_db(summary),
            self._cleanup_logs(summary),
            self._rotate_old_reports(summary),
            return_exceptions=True,
        )

    async def _vacuum_db(self, summary: NightWorkSummary) -> None:
        cfg = get_config()
        db_path = cfg.memory_db_path
        if not db_path.exists():
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._do_vacuum, str(db_path))
            summary.vacuum_done = True
            log.info("NightMode: SQLite VACUUM done on %s", db_path)
        except Exception as exc:
            log.warning("NightMode: VACUUM failed: %s", exc)
            summary.maintenance_errors.append(f"vacuum_error: {exc}")

    @staticmethod
    def _do_vacuum(db_path: str) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    async def _cleanup_logs(self, summary: NightWorkSummary) -> None:
        """Delete .log files older than LOG_RETENTION_DAYS from the backend dir."""
        backend_dir = Path(__file__).parent.parent
        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        deleted = 0
        for log_file in backend_dir.glob("**/*.log"):
            try:
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
                    deleted += 1
                    log.debug("NightMode: deleted old log %s", log_file)
            except Exception as exc:
                log.debug("NightMode: could not delete %s: %s", log_file, exc)
        summary.logs_deleted = deleted
        if deleted:
            log.info("NightMode: deleted %d old log file(s)", deleted)

    async def _rotate_old_reports(self, summary: NightWorkSummary) -> None:
        """Remove night report directories older than REPORT_RETENTION_DAYS."""
        cutoff = time.time() - REPORT_RETENTION_DAYS * 86400
        for report_dir in _NIGHT_REPORTS_DIR.iterdir():
            if not report_dir.is_dir():
                continue
            try:
                if report_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(report_dir)
                    log.debug("NightMode: rotated old report dir %s", report_dir)
            except Exception as exc:
                log.debug("NightMode: could not rotate %s: %s", report_dir, exc)

    def _persist_summary(self, summary: NightWorkSummary) -> None:
        report_dir = _NIGHT_REPORTS_DIR / summary.date
        report_dir.mkdir(parents=True, exist_ok=True)
        out_file = report_dir / "summary.json"
        try:
            data = asdict(summary)
            # Convert nested dataclasses (JobResult list)
            data["job_details"] = [asdict(j) if hasattr(j, "__dataclass_fields__") else j
                                   for j in summary.job_details]
            data["state"] = summary.state.value
            out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            log.info("NightMode: summary persisted → %s", out_file)
        except Exception as exc:
            log.warning("NightMode: could not persist summary: %s", exc)

    def _load_last_summary(self) -> dict | None:
        """Load the most recent night summary JSON."""
        today = date.today().isoformat()
        candidates = [today]
        # Also check yesterday in case morning briefing runs before new night work
        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        candidates.append(yesterday)

        for d in candidates:
            f = _NIGHT_REPORTS_DIR / d / "summary.json"
            if f.exists():
                try:
                    return json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_controller: NightModeController | None = None


def get_night_mode_controller() -> NightModeController:
    global _controller
    if _controller is None:
        _controller = NightModeController()
    return _controller
