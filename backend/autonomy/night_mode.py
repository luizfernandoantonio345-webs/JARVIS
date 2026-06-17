"""
Night Mode Controller — JARVIS Autonomy
Controla operações autônomas em background durante período inativo.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.night_mode")

LOG_RETENTION_DAYS = 30
_NIGHT_REPORTS_DIR = Path(__file__).parent.parent / "logs" / "night_reports"
_NIGHT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

_SINGLETON: Optional["NightModeController"] = None


class NightModeState(Enum):
    INACTIVE = auto()
    ACTIVATING = auto()
    ACTIVE = auto()
    WINDING_DOWN = auto()


@dataclass
class NightWorkSummary:
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    improvements_made: list[str] = field(default_factory=list)
    logs_cleaned: int = 0
    memory_compacted: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "improvements_made": self.improvements_made,
            "logs_cleaned": self.logs_cleaned,
            "memory_compacted": self.memory_compacted,
            "notes": self.notes,
        }


class NightModeController:
    def __init__(self):
        self.state = NightModeState.INACTIVE
        self.summary: Optional[NightWorkSummary] = None
        self._start_time: Optional[float] = None

    def _load_last_summary(self) -> Optional[NightWorkSummary]:
        try:
            reports = sorted(_NIGHT_REPORTS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not reports:
                return None
            data = json.loads(reports[0].read_text(encoding="utf-8"))
            s = NightWorkSummary()
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            return s
        except Exception:
            return None

    def activate(self) -> None:
        if self.state == NightModeState.INACTIVE:
            self.state = NightModeState.ACTIVATING
            self.summary = NightWorkSummary()
            self._start_time = time.time()
            self.state = NightModeState.ACTIVE
            log.info("[NIGHT_MODE] Ativado")

    def deactivate(self) -> Optional[NightWorkSummary]:
        if self.state != NightModeState.INACTIVE:
            self.state = NightModeState.WINDING_DOWN
            if self.summary:
                self.summary.end_time = time.time()
                self._save_summary(self.summary)
            self.state = NightModeState.INACTIVE
            log.info("[NIGHT_MODE] Desativado")
            return self.summary
        return None

    def _save_summary(self, summary: NightWorkSummary) -> None:
        try:
            fname = _NIGHT_REPORTS_DIR / f"night_{int(time.time())}.json"
            fname.write_text(json.dumps(summary.to_dict()), encoding="utf-8")
            self._cleanup_old_logs()
        except Exception as e:
            log.warning("[NIGHT_MODE] Erro ao salvar sumário: %s", e)

    def _cleanup_old_logs(self) -> int:
        removed = 0
        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        try:
            for f in _NIGHT_REPORTS_DIR.glob("*.json"):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
        except Exception:
            pass
        return removed

    @property
    def is_active(self) -> bool:
        return self.state == NightModeState.ACTIVE


def get_night_mode_controller() -> NightModeController:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = NightModeController()
    return _SINGLETON
