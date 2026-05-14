from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

DATASET_PATH = Path(__file__).resolve().parents[1] / "training_dataset.jsonl"
_lock = Lock()


@dataclass
class TrainingExample:
    input: str
    context: str
    output: str
    rating: str
    timestamp: str
    session_id: str
    example_id: str


class TrainingCollector:
    def save_interaction(
        self,
        *,
        input_text: str,
        output: str,
        context: str = "",
        rating: str = "positive",
        session_id: str = "default",
    ) -> str:
        example = TrainingExample(
            input=input_text,
            context=context,
            output=output,
            rating=rating,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            example_id=str(uuid.uuid4()),
        )
        with _lock:
            with DATASET_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")
        return example.example_id

    def mark_last_for_session(self, session_id: str, rating: str) -> bool:
        rows = self._read_all()
        for row in reversed(rows):
            if row.get("session_id") == session_id:
                row["rating"] = rating
                self._write_all(rows)
                return True
        return False

    def export_jsonl(self) -> str:
        if not DATASET_PATH.exists():
            return ""
        return DATASET_PATH.read_text(encoding="utf-8")

    def stats(self) -> dict:
        rows = self._read_all()
        ratings = Counter(row.get("rating", "unknown") for row in rows)
        return {
            "examples": len(rows),
            "ratings": dict(ratings),
            "path": str(DATASET_PATH),
        }

    def _read_all(self) -> list[dict]:
        if not DATASET_PATH.exists():
            return []
        rows: list[dict] = []
        with _lock:
            for line in DATASET_PATH.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def _write_all(self, rows: list[dict]) -> None:
        with _lock:
            DATASET_PATH.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
                encoding="utf-8",
            )


_collector: TrainingCollector | None = None


def get_training_collector() -> TrainingCollector:
    global _collector
    if _collector is None:
        _collector = TrainingCollector()
    return _collector
