from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROFILE_PATH = Path(__file__).with_name("jarvis_profile.json")
SAVE_INTERVAL_S = 300.0


class ProfileLearner:
    def __init__(self) -> None:
        self.profile = self._load()
        self._last_save = time.monotonic()
        self._dirty = False
        self._detect_owner()

    def after_command(
        self,
        command: str,
        *,
        intent: str | None = None,
        success: bool = True,
        session_id: str = "default",
    ) -> None:
        history = self.profile.setdefault("history", {})
        patterns = self.profile.setdefault("patterns", {})
        history["total_commands"] = int(history.get("total_commands", 0)) + 1
        history["last_session"] = session_id
        self._bump_list_counter(patterns, "most_used_commands", intent or command[:80])
        self._bump_list_counter(patterns, "peak_hours", datetime.now().strftime("%H:00"))
        self._dirty = True
        self._maybe_save()

    def after_session(self, session_id: str = "default") -> None:
        history = self.profile.setdefault("history", {})
        history["total_sessions"] = int(history.get("total_sessions", 0)) + 1
        history["last_session"] = session_id
        self._dirty = True
        self._maybe_save(force=True)

    def after_error_fixed(self, error: str, solution: str = "") -> None:
        patterns = self.profile.setdefault("patterns", {})
        errors = patterns.setdefault("common_errors", [])
        errors.append(
            {
                "error": error[:300],
                "solution": solution[:500],
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        patterns["common_errors"] = errors[-50:]
        history = self.profile.setdefault("history", {})
        history["bugs_fixed"] = int(history.get("bugs_fixed", 0)) + 1
        self._dirty = True
        self._maybe_save()

    def record_file_created(self, path: str) -> None:
        suffix = Path(path).suffix.lower()
        language = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript"}.get(suffix)
        owner = self.profile.setdefault("owner", {})
        if language:
            languages = list(owner.get("languages", []))
            if language not in languages:
                languages.append(language)
                owner["languages"] = languages[-10:]
        history = self.profile.setdefault("history", {})
        history["files_created"] = int(history.get("files_created", 0)) + 1
        self._dirty = True
        self._maybe_save()

    def save(self) -> None:
        PROFILE_PATH.write_text(json.dumps(self.profile, indent=2, ensure_ascii=False), encoding="utf-8")
        self._dirty = False
        self._last_save = time.monotonic()

    def _load(self) -> dict[str, Any]:
        if PROFILE_PATH.exists():
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return {}

    def _detect_owner(self) -> None:
        owner = self.profile.setdefault("owner", {})
        try:
            name = subprocess.check_output(["git", "config", "--global", "user.name"], text=True, timeout=3).strip()
            if name:
                owner["git_username"] = name
                if owner.get("name") == "detectado automaticamente":
                    owner["name"] = name
                self._dirty = True
        except Exception:
            pass

    def _bump_list_counter(self, root: dict[str, Any], key: str, value: str) -> None:
        current = root.get(key, [])
        counter = Counter()
        for item in current:
            if isinstance(item, dict):
                counter[str(item.get("value", ""))] += int(item.get("count", 1))
            else:
                counter[str(item)] += 1
        counter[value] += 1
        root[key] = [{"value": item, "count": count} for item, count in counter.most_common(20)]

    def _maybe_save(self, *, force: bool = False) -> None:
        if self._dirty and (force or time.monotonic() - self._last_save >= SAVE_INTERVAL_S):
            self.save()


_learner: ProfileLearner | None = None


def get_profile_learner() -> ProfileLearner:
    global _learner
    if _learner is None:
        _learner = ProfileLearner()
    return _learner
