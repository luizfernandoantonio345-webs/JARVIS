from __future__ import annotations

from behavior_v2.pattern_detector import detect_patterns
from behavior_v2.routine_engine import generate_routines
from behavior_v2.schemas import BehaviorEvent, Routine, Suggestion
from behavior_v2.suggestion_engine import generate_suggestion


class BehaviorManager:
    def __init__(self) -> None:
        self.events: list[BehaviorEvent] = []
        self.routines: dict[str, Routine] = {}
        self.automation_enabled = True

    def record_event(self, event: BehaviorEvent) -> None:
        self.events = (self.events + [event])[-500:]

    def suggestions(self) -> list[Suggestion]:
        patterns = [p.model_dump() for p in detect_patterns([e.model_dump() for e in self.events])]
        suggestion = generate_suggestion({"patterns": patterns})
        return [suggestion] if suggestion else []

    def get_routines(self) -> list[Routine]:
        patterns = detect_patterns([e.model_dump() for e in self.events])
        for routine in generate_routines(patterns):
            self.routines.setdefault(routine.name, routine)
        return list(self.routines.values())

    def approve_routine(self, routine_id: str, approved: bool) -> bool:
        for routine in self.routines.values():
            if routine.id == routine_id:
                routine.approved = approved
                return True
        return False


_manager = BehaviorManager()


def get_behavior_manager() -> BehaviorManager:
    return _manager

