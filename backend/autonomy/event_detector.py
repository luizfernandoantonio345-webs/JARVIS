"""
event_detector — FASE 11A (OPTIMIZED WITH WATCHDOG)

Four parallel async watchers that detect events from the environment:
  - FileSystemWatcher : file create/modify/delete in watched dirs (using watchdog for efficiency)
  - LogWatcher        : ERROR/CRITICAL patterns + stuck jobs in jarvis.log
  - ScheduleWatcher   : cron-like tasks from schedule.json
  - IdleWatcher       : system idle detection based on last activity

OPTIMIZATION: Uses watchdog (inotify/FSEvents) instead of polling with rglob().
              This eliminates constant filesystem traversal and latency.
              Event deduplication prevents duplicate events within debounce window.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Literal

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    # Dummy classes for when watchdog not available
    class FileSystemEventHandler:
        pass
    FileModifiedEvent = None
    FileCreatedEvent = None
    FileDeletedEvent = None
    Observer = None
    log_warn = print  # Fallback during import

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_DEBOUNCE_MS          = 500        # ignore duplicate fs events within 500ms
_LOG_POLL_INTERVAL    = 5.0        # seconds between log tail reads
_SCHEDULE_POLL_INTERVAL = 60.0     # seconds between schedule checks
_IDLE_CHECK_INTERVAL  = 30.0       # seconds between idle checks
_STUCK_JOB_MINUTES    = 10         # job considered stuck after N minutes without update

_IGNORE_DIRS = frozenset({"__pycache__", ".git", "node_modules", ".mypy_cache",
                           ".pytest_cache", "dist", "build", ".venv", "venv"})
_IGNORE_EXTS = frozenset({".pyc", ".pyo", ".pyd", ".swp", ".swo", ".tmp", ".log"})

SCHEDULE_FILE = Path(__file__).parent / "schedule.json"

# ── Event dataclasses ──────────────────────────────────────────────────────────

@dataclass
class FileEvent:
    event_type: Literal["file"] = "file"
    path: str = ""
    change_type: Literal["created", "modified", "deleted"] = "modified"
    timestamp: float = field(default_factory=time.time)


@dataclass
class LogEvent:
    event_type: Literal["log"] = "log"
    level: str = "ERROR"
    message: str = ""
    source: str = "jarvis.log"
    job_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ScheduleEvent:
    event_type: Literal["schedule"] = "schedule"
    task_name: str = ""
    goal: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class IdleEvent:
    event_type: Literal["idle"] = "idle"
    idle_since: float = field(default_factory=time.time)
    pending_jobs_count: int = 0
    timestamp: float = field(default_factory=time.time)


AnyEvent = FileEvent | LogEvent | ScheduleEvent | IdleEvent


# ── FileSystemWatcher (with watchdog for efficiency) ─────────────────────────

class _WatchdogEventHandler(FileSystemEventHandler):
    """Watchdog handler that converts fs events to async queue."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self._queue = queue
        self._loop = loop
        self._debounce_cache: dict[str, float] = {}  # path → last event timestamp

    def _should_ignore(self, path: str) -> bool:
        p = Path(path)
        parts = set(p.parts)
        if parts & _IGNORE_DIRS:
            return True
        if p.suffix in _IGNORE_EXTS:
            return True
        return False

    def _should_queue(self, path: str) -> bool:
        """Check if event should be queued (apply debouncing)."""
        now = time.time()
        last = self._debounce_cache.get(path, 0.0)
        if (now - last) * 1000 < _DEBOUNCE_MS:
            return False
        self._debounce_cache[path] = now
        return True

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        if not self._should_queue(event.src_path):
            return
        try:
            self._loop.call_soon_threadsafe(
                asyncio.create_task,
                self._queue_event("modified", event.src_path)
            )
        except Exception as exc:
            log.debug(f"_WatchdogEventHandler.on_modified error: {exc}")

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        if not self._should_queue(event.src_path):
            return
        try:
            self._loop.call_soon_threadsafe(
                asyncio.create_task,
                self._queue_event("created", event.src_path)
            )
        except Exception as exc:
            log.debug(f"_WatchdogEventHandler.on_created error: {exc}")

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        if not self._should_queue(event.src_path):
            return
        try:
            self._loop.call_soon_threadsafe(
                asyncio.create_task,
                self._queue_event("deleted", event.src_path)
            )
        except Exception as exc:
            log.debug(f"_WatchdogEventHandler.on_deleted error: {exc}")

    async def _queue_event(self, change_type: str, path: str) -> None:
        """Queue file event to async queue."""
        try:
            await self._queue.put(FileEvent(path=path, change_type=change_type))
        except Exception as exc:
            log.warning(f"_WatchdogEventHandler._queue_event error: {exc}")


class FileSystemWatcher:
    """Watches directories for file changes using watchdog (efficient native events)."""

    def __init__(self, watch_dirs: list[str], queue: asyncio.Queue) -> None:
        self._dirs = [Path(d) for d in watch_dirs if Path(d).exists()]
        self._queue = queue
        self._observer: Observer | None = None
        self._handler: _WatchdogEventHandler | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _init_watchdog(self) -> bool:
        """Initialize watchdog observer. Fallback to polling if unavailable."""
        if not HAS_WATCHDOG:
            log.warning("watchdog not installed, falling back to polling (slower)")
            return False
        
        try:
            self._loop = asyncio.get_running_loop()
            self._observer = Observer()
            self._handler = _WatchdogEventHandler(self._queue, self._loop)
            
            for d in self._dirs:
                self._observer.schedule(self._handler, str(d), recursive=True)
            
            self._observer.start()
            log.info(f"FileSystemWatcher: watching {len(self._dirs)} dirs with watchdog")
            return True
        except Exception as exc:
            log.error(f"Failed to initialize watchdog: {exc}, falling back to polling")
            return False

    async def run(self) -> None:
        # Try to use watchdog; fallback to polling if unavailable
        if not self._init_watchdog():
            await self._run_polling()
        else:
            # Watchdog is running; just keep the coroutine alive
            try:
                while True:
                    await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                if self._observer:
                    self._observer.stop()
                    self._observer.join(timeout=5.0)
                raise

    async def _run_polling(self) -> None:
        """Fallback: poll filesystem for changes (legacy behavior)."""
        snapshots: dict[str, float] = {}
        last_event: dict[str, float] = {}
        
        log.info(f"FileSystemWatcher: polling {len(self._dirs)} dirs (watchdog unavailable)")
        
        while True:
            await asyncio.sleep(2.0)
            try:
                current = self._snapshot()
                now = time.time()

                # Detect created + modified
                for path, mtime in current.items():
                    last_evt = last_event.get(path, 0.0)
                    if (now - last_evt) * 1000 < _DEBOUNCE_MS:
                        continue
                    if path not in snapshots:
                        await self._queue.put(FileEvent(path=path, change_type="created"))
                        last_event[path] = now
                    elif mtime != snapshots[path]:
                        await self._queue.put(FileEvent(path=path, change_type="modified"))
                        last_event[path] = now

                # Detect deleted
                for path in snapshots:
                    if path not in current:
                        last_evt = last_event.get(path, 0.0)
                        if (now - last_evt) * 1000 >= _DEBOUNCE_MS:
                            await self._queue.put(FileEvent(path=path, change_type="deleted"))
                            last_event[path] = now

                snapshots = current
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(f"FileSystemWatcher polling error: {exc}")

    def _snapshot(self) -> dict[str, float]:
        """Snapshot current filesystem state (for polling fallback)."""
        result: dict[str, float] = {}
        for d in self._dirs:
            try:
                for p in d.rglob("*"):
                    if p.is_file() and not self._should_ignore(p):
                        result[str(p)] = p.stat().st_mtime
            except Exception as exc:
                log.debug(f"snapshot error: {exc}")
        return result

    def _should_ignore(self, p: Path) -> bool:
        """Check if path should be ignored."""
        parts = set(p.parts)
        if parts & _IGNORE_DIRS:
            return True
        if p.suffix in _IGNORE_EXTS:
            return True
        return False


# ── LogWatcher ────────────────────────────────────────────────────────────────

class LogWatcher:
    """Tails jarvis.log for ERROR/CRITICAL patterns and stuck job detection."""

    _ERROR_RE = re.compile(r"\b(ERROR|CRITICAL)\b", re.IGNORECASE)
    _JOB_STUCK_RE = re.compile(r"job[_\s]id[=:\s]+([a-zA-Z0-9_-]+)", re.IGNORECASE)

    def __init__(self, log_path: Path, queue: asyncio.Queue) -> None:
        self._path = log_path
        self._queue = queue
        self._pos = 0

    async def run(self) -> None:
        # Seek to end to avoid replaying old errors on startup
        if self._path.exists():
            self._pos = self._path.stat().st_size
        log.debug("LogWatcher: tailing %s", self._path)
        while True:
            await asyncio.sleep(_LOG_POLL_INTERVAL)
            try:
                await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("LogWatcher error: %s", exc)

    async def _poll(self) -> None:
        if not self._path.exists():
            return
        size = self._path.stat().st_size
        if size <= self._pos:
            return
        with open(self._path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self._pos)
            new_content = f.read()
            self._pos = f.tell()

        for line in new_content.splitlines():
            line = line.strip()
            if not line:
                continue
            if self._ERROR_RE.search(line):
                level = "CRITICAL" if "CRITICAL" in line.upper() else "ERROR"
                job_match = self._JOB_STUCK_RE.search(line)
                await self._queue.put(LogEvent(
                    level=level,
                    message=line[:500],
                    job_id=job_match.group(1) if job_match else "",
                ))


# ── ScheduleWatcher ───────────────────────────────────────────────────────────

class ScheduleWatcher:
    """Fires ScheduleEvents based on cron-like schedule.json entries."""

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._last_fired: dict[str, str] = {}  # task_name → last fired "HH:MM"

    def _load_schedule(self) -> list[dict]:
        if not SCHEDULE_FILE.exists():
            return []
        try:
            return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _should_fire(self, task: dict, now: datetime) -> bool:
        cron = task.get("cron", "")
        parts = cron.split()
        if len(parts) != 5:
            return False
        minute, hour = parts[0], parts[1]
        # Only support exact hour:minute (day/month/dow wildcards accepted)
        try:
            if hour != "*" and int(hour) != now.hour:
                return False
            if minute != "*" and int(minute) != now.minute:
                return False
        except ValueError:
            return False
        return True

    async def run(self) -> None:
        log.debug("ScheduleWatcher: watching %s", SCHEDULE_FILE)
        while True:
            await asyncio.sleep(_SCHEDULE_POLL_INTERVAL)
            try:
                now = datetime.now()
                clock_key = f"{now.hour:02d}:{now.minute:02d}"
                for task in self._load_schedule():
                    name = task.get("name", "unnamed")
                    if self._last_fired.get(name) == clock_key:
                        continue  # Already fired this minute
                    if self._should_fire(task, now):
                        await self._queue.put(ScheduleEvent(
                            task_name=name,
                            goal=task.get("goal", ""),
                        ))
                        self._last_fired[name] = clock_key
                        log.info("ScheduleWatcher: fired task '%s'", name)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("ScheduleWatcher error: %s", exc)


# ── IdleWatcher ───────────────────────────────────────────────────────────────

class IdleWatcher:
    """Emits IdleEvent when system has been idle for longer than the threshold."""

    def __init__(
        self,
        queue: asyncio.Queue,
        idle_threshold_minutes: float = 5.0,
    ) -> None:
        self._queue = queue
        self._threshold = idle_threshold_minutes * 60.0
        self._last_activity = time.time()

    def record_activity(self) -> None:
        """Call this whenever user or system is active."""
        self._last_activity = time.time()

    def _count_pending_jobs(self) -> int:
        try:
            from autodev.loop import _active_jobs
            return sum(
                1 for loop in _active_jobs.values()
                if not loop._state or loop._state.status not in {"done", "escalated", "error"}
            )
        except Exception:
            return 0

    async def run(self) -> None:
        log.debug("IdleWatcher: threshold=%.1f min", self._threshold / 60)
        _fired_idle = False
        while True:
            await asyncio.sleep(_IDLE_CHECK_INTERVAL)
            try:
                idle_secs = time.time() - self._last_activity
                if idle_secs >= self._threshold:
                    if not _fired_idle:
                        pending = self._count_pending_jobs()
                        await self._queue.put(IdleEvent(
                            idle_since=self._last_activity,
                            pending_jobs_count=pending,
                        ))
                        _fired_idle = True
                        log.info("IdleWatcher: idle %.1f min, pending_jobs=%d",
                                 idle_secs / 60, pending)
                else:
                    _fired_idle = False
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("IdleWatcher error: %s", exc)


# ── EventDetector ─────────────────────────────────────────────────────────────

class EventDetector:
    """
    Runs all four watchers in parallel and exposes a single async queue of events.
    """

    def __init__(
        self,
        watch_dirs: list[str] | None = None,
        log_path: Path | None = None,
        idle_minutes: float = 5.0,
    ) -> None:
        _env_dirs = os.getenv("JARVIS_WATCH_DIRS", "")
        _default_dirs = [str(Path(__file__).parent.parent.parent)]
        self._watch_dirs = watch_dirs or (
            [d for d in _env_dirs.split(":") if d] if _env_dirs else _default_dirs
        )
        self._log_path = log_path or (Path(__file__).parent.parent.parent / "jarvis.log")
        self._idle_minutes = idle_minutes

        self._queue: asyncio.Queue[AnyEvent] = asyncio.Queue(maxsize=500)
        self._tasks: list[asyncio.Task] = []
        self._idle_watcher: IdleWatcher | None = None

    def record_activity(self) -> None:
        if self._idle_watcher:
            self._idle_watcher.record_activity()

    async def start(self) -> None:
        """Start all watchers as background tasks."""
        fs = FileSystemWatcher(self._watch_dirs, self._queue)
        lw = LogWatcher(self._log_path, self._queue)
        sw = ScheduleWatcher(self._queue)
        iw = IdleWatcher(self._queue, self._idle_minutes)
        self._idle_watcher = iw

        self._tasks = [
            asyncio.create_task(fs.run(), name="fs-watcher"),
            asyncio.create_task(lw.run(), name="log-watcher"),
            asyncio.create_task(sw.run(), name="schedule-watcher"),
            asyncio.create_task(iw.run(), name="idle-watcher"),
        ]
        log.info("EventDetector: all watchers started (%d dirs watched)", len(self._watch_dirs))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        log.info("EventDetector: stopped")

    async def events(self) -> AsyncGenerator[AnyEvent, None]:
        """Async generator that yields events as they arrive."""
        while True:
            yield await self._queue.get()
