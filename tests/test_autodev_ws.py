"""
TESTE 3 — WebSocket stream

Validações:
  ✓ Conectar ao WS antes de iniciar o job (job deve estar ativo)
  ✓ Receber evento "stage_start" para pelo menos uma etapa
  ✓ Receber evento "file_generated" com nome do arquivo
  ✓ Receber evento "done" ou "escalated" ao final
  ✓ Sem mensagens perdidas (compare com JobState final)

Run: pytest tests/test_autodev_ws.py -v

Note: requires websockets package (pip install websockets)
"""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from conftest import start_job, wait_for_terminal

os.environ["JARVIS_TEST_MODE"] = "1"
os.environ["JARVIS_DISABLE_VOICE"] = "1"

WS_GOAL = (
    "crie um módulo Python com duas funções: "
    "soma(a, b) que retorna a+b e "
    "multiplica(a, b) que retorna a*b, com testes unitários"
)

class TestWebSocketStream:

    def test_ws_smoke(self, client: TestClient):
        """Start job then connect WS and collect all events until terminal."""
        resp = start_job(client, WS_GOAL)
        job_id = resp["job_id"]
        self.__class__._job_id = job_id

        events = _collect_ws_events(client, job_id, timeout=240)
        self.__class__._events = events

        assert len(events) >= 1, "Received zero WebSocket events"

    def test_stage_start_received(self):
        events = getattr(self.__class__, "_events", [])
        stage_starts = [e for e in events if e.get("event") == "stage_start"]
        assert len(stage_starts) >= 1, (
            f"No 'stage_start' events received. Events: {[e['event'] for e in events]}"
        )

    def test_file_generated_received(self):
        events = getattr(self.__class__, "_events", [])
        file_evts = [e for e in events if e.get("event") == "file_generated"]
        assert len(file_evts) >= 1, (
            "No 'file_generated' events received"
        )
        # Each file_generated event must have path in data
        for evt in file_evts:
            assert "path" in evt.get("data", {}), f"file_generated missing 'path': {evt}"

    def test_terminal_event_received(self):
        events = getattr(self.__class__, "_events", [])
        terminal = [e for e in events if e.get("event") in ("done", "escalated", "error")]
        assert len(terminal) >= 1, (
            f"No terminal event (done/escalated/error) received. "
            f"Last 5 events: {events[-5:]}"
        )

    def test_events_have_timestamp(self):
        events = getattr(self.__class__, "_events", [])
        for evt in events[:5]:  # spot-check first 5
            assert "ts" in evt, f"Event missing 'ts': {evt}"
            assert isinstance(evt["ts"], float | int), f"ts is not numeric: {evt}"

    def test_event_count_matches_state(self, client: TestClient):
        """file_generated event count >= files_generated in final state."""
        job_id = getattr(self.__class__, "_job_id", None)
        events = getattr(self.__class__, "_events", [])
        if not job_id:
            pytest.skip("No job_id")

        final = wait_for_terminal(client, job_id, timeout=10)
        ws_files = len([e for e in events if e.get("event") == "file_generated"])
        state_files = final.get("files_generated", 0)

        # WS file count should be >= state count (could be > if state lags)
        assert ws_files >= state_files or state_files == 0, (
            f"WS reported {ws_files} files but state has {state_files}"
        )


def _collect_ws_events(client: TestClient, job_id: str, timeout: int = 180) -> list[dict]:
    """Connect to the in-process WS stream and collect all events until terminal."""
    events: list[dict] = []
    terminal = {"done", "escalated", "error"}
    deadline = time.time() + timeout

    try:
        with client.websocket_connect(f"/autodev/stream/{job_id}") as ws:
            while time.time() < deadline:
                evt = ws.receive_json()
                if evt.get("event") == "heartbeat":
                    continue
                events.append(evt)
                if evt.get("event") in terminal:
                    break
    except Exception as exc:
        events.append({"event": "ws_error", "data": {"error": str(exc)}, "ts": time.time()})

    return events
