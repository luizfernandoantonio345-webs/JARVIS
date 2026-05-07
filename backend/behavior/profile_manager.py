"""
profile_manager — FASE 11B

Loads, saves, and evolves the BehaviorProfile.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from behavior.profile import BehaviorProfile
from config import get_config

log = logging.getLogger(__name__)

PROFILE_DIR  = Path(__file__).parent
PROFILE_FILE = PROFILE_DIR / "profile.json"
HISTORY_FILE = PROFILE_DIR / "profile_history.jsonl"
REPORTS_DIR  = PROFILE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

DB_PATH = get_config().memory_db_path

_DEFAULT_PROFILE = BehaviorProfile()


class ProfileManager:
    """
    Manages persistence and evolution of the BehaviorProfile.

    Usage:
        pm = ProfileManager()
        profile = pm.load()
        pm.save(profile)
    """

    def __init__(self) -> None:
        self._profile: BehaviorProfile | None = None

    # ── Load / Save ───────────────────────────────────────────────────────────

    def load(self) -> BehaviorProfile:
        """Load profile from disk, creating default if missing."""
        if PROFILE_FILE.exists():
            try:
                raw = PROFILE_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._profile = BehaviorProfile.model_validate(data)
                log.debug("ProfileManager: loaded profile (update_count=%d)",
                          self._profile.update_count)
                return self._profile
            except json.JSONDecodeError as exc:
                broken_path = Path(str(PROFILE_FILE) + ".broken")
                log.error(
                    "❌ ProfileManager: JSON corrompido em %s. Detalhes: %s",
                    PROFILE_FILE, exc,
                )
                try:
                    shutil.move(str(PROFILE_FILE), str(broken_path))
                    log.warning(
                        "Arquivo quebrado renomeado para %s. Usando perfil padrão.",
                        broken_path,
                    )
                except OSError as rename_err:
                    log.error("Não foi possível renomear o arquivo quebrado: %s", rename_err)
            except Exception as exc:
                log.warning("ProfileManager: falha ao ler profile.json, usando padrão: %s", exc)

        self._profile = BehaviorProfile()
        self.save(self._profile)
        return self._profile

    def save(self, profile: BehaviorProfile) -> None:
        """Persist profile to disk and append to history."""
        profile.last_updated = datetime.utcnow()
        PROFILE_FILE.write_text(
            profile.model_dump_json(indent=2),
            encoding="utf-8",
        )
        # Append to history log
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(profile.model_dump_json() + "\n")
        except Exception as exc:
            log.debug("[behavior.profile_manager] suppressed exception", exc_info=exc)
            pass
        self._profile = profile
        log.debug("ProfileManager: saved profile (update_count=%d)", profile.update_count)

    def get(self) -> BehaviorProfile:
        if self._profile is None:
            return self.load()
        return self._profile

    def reset(self) -> BehaviorProfile:
        """Reset to factory defaults."""
        profile = BehaviorProfile()
        self.save(profile)
        log.info("ProfileManager: reset to defaults")
        return profile

    # ── LLM routing helper ────────────────────────────────────────────────────

    def get_llm_for_task(self, task_type: str) -> str:
        return self.get().get_llm_for_task(task_type)

    # ── Learning from feedback ────────────────────────────────────────────────

    def update_from_feedback(self, feedback: str, context: dict | None = None) -> BehaviorProfile:
        """
        Infer profile adjustments from natural language feedback using the LLM.

        Example:
            feedback = "você está sendo muito verboso"
            → verbosity = "minimal"
        """
        profile = self.get()
        try:
            from services.llm_service import call_llm
            prompt = _FEEDBACK_PROMPT.format(
                feedback=feedback,
                current=profile.model_dump_json(indent=2),
            )
            raw = call_llm(
                [{"role": "user", "content": prompt}],
                force_local=True,
            )
            # Extract JSON patch from LLM response
            patch = _extract_json(raw)
            if patch:
                updated = profile.model_dump()
                _deep_update(updated, patch)
                updated["update_count"] = profile.update_count + 1
                new_profile = BehaviorProfile.model_validate(updated)
                self.save(new_profile)
                log.info("ProfileManager: updated from feedback (%d fields patched)",
                         len(patch))
                return new_profile
        except Exception as exc:
            log.warning("ProfileManager.update_from_feedback failed: %s", exc)
        return profile

    def update_from_observation(
        self,
        action: str,
        result: str,
        success: bool,
        task_type: str = "default",
    ) -> None:
        """
        Learn from action outcomes.  If a model consistently fails for a task type,
        switch to a better model.
        """
        profile = self.get()
        pattern = {
            "ts": datetime.utcnow().isoformat(),
            "action": action[:200],
            "task_type": task_type,
            "llm_used": profile.get_llm_for_task(task_type),
            "success": success,
            "result_summary": result[:200],
        }

        # Add to learned_patterns (keep last 50)
        patterns = profile.learned_patterns[-49:] + [pattern]

        # Simple heuristic: if current LLM failed 3 times for this task type, try claude
        recent_failures = [
            p for p in patterns[-10:]
            if p.get("task_type") == task_type
            and not p.get("success")
            and p.get("llm_used") == profile.get_llm_for_task(task_type)
        ]
        if len(recent_failures) >= 3:
            current_llm = profile.llm_routing.get(task_type, "ollama")
            fallback = "claude" if current_llm != "claude" else "gpt-4o-mini"
            profile.llm_routing[task_type] = fallback
            log.info("ProfileManager: switching %s LLM from %s to %s after 3 failures",
                     task_type, current_llm, fallback)

        profile.learned_patterns = patterns
        profile.update_count += 1
        self.save(profile)

    def history(self, limit: int = 20) -> list[dict]:
        """Return last N profile snapshots from history log."""
        if not HISTORY_FILE.exists():
            return []
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines()
        result = []
        for line in reversed(lines[-limit:]):
            try:
                result.append(json.loads(line))
            except Exception as exc:
                log.debug("[behavior.profile_manager] suppressed exception", exc_info=exc)
                pass
        return result

    def generate_evolution_report(self, last_n_actions: int = 50) -> Path:
        """
        Analyse recent autonomous actions and generate a ProfileUpdateReport.
        Called by the weekly_profile_evolution scheduled task.
        """
        profile = self.get()
        try:
            rows = []
            with sqlite3.connect(str(DB_PATH)) as conn:
                rows = conn.execute(
                    "SELECT ts, goal, status, event_type FROM autonomy_log "
                    "ORDER BY ts DESC LIMIT ?",
                    (last_n_actions,),
                ).fetchall()
        except Exception as exc:
            log.debug("[behavior.profile_manager] suppressed exception", exc_info=exc)
            pass

        stats: dict[str, dict] = {}
        for ts, goal, status, evt_type in rows:
            stats.setdefault(evt_type or "unknown", {"ok": 0, "err": 0})
            if status == "success":
                stats[evt_type or "unknown"]["ok"] += 1
            else:
                stats[evt_type or "unknown"]["err"] += 1

        report_path = REPORTS_DIR / f"evolution_{datetime.now().strftime('%Y%m%d')}.json"
        import json as _json
        report_path.write_text(
            _json.dumps({
                "generated_at": datetime.utcnow().isoformat(),
                "actions_analysed": len(rows),
                "stats_by_event_type": stats,
                "current_profile": profile.model_dump(),
            }, indent=2, default=str),
            encoding="utf-8",
        )
        log.info("ProfileManager: evolution report saved to %s", report_path)
        return report_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        block = m.group(1)
    else:
        m = re.search(r"(\{[^{}]+\})", text, re.DOTALL)
        if m:
            block = m.group(1)
        else:
            return None
    try:
        return json.loads(block)
    except Exception:
        return None


def _deep_update(base: dict, patch: dict) -> None:
    for k, v in patch.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


_FEEDBACK_PROMPT = """
Você é o gerenciador de perfil do Jarvis. O usuário deu o seguinte feedback:

"{feedback}"

Perfil atual:
{current}

Baseado no feedback, gere um JSON com APENAS os campos que precisam ser alterados
(patch mínimo). Campos válidos: verbosity, risk_tolerance, test_preference,
escalation_threshold, max_autonomous_actions_per_hour, llm_routing, code_style.

Responda APENAS com um bloco JSON, sem explicações.
Exemplo: {{"verbosity": "minimal"}}
"""


# ── Module-level singleton ────────────────────────────────────────────────────

_manager: ProfileManager | None = None


def get_profile_manager() -> ProfileManager:
    global _manager
    if _manager is None:
        _manager = ProfileManager()
        _manager.load()
    return _manager
