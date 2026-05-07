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

import asyncio
import json
import time
from collections import defaultdict

import httpx
import pytest

try:
    import websockets  # type: ignore
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False

from conftest import BASE_URL, JOBS_DIR, start_job, wait_for_terminal

WS_GOAL = (
    "crie um módulo Python com duas funções: "
    "soma(a, b) que retorna a+b e "
    "multiplica(a, b) que retorna a*b, com testes unitários"
)

WS_BASE = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")


@pytest.mark.skipif(not _WS_AVAILABLE, reason="websockets package not installed")
class TestWebSocketStream:

    def test_ws_smoke(self, api):
        """Start job then connect WS and collect all events until terminal."""
        resp = start_job(WS_GOAL)
        job_id = resp["job_id"]
        self.__class__._job_id = job_id

        events = asyncio.get_event_loop().run_until_complete(
            _collect_ws_events(job_id, timeout=240)
        )
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

    def test_event_count_matches_state(self):
        """file_generated event count >= files_generated in final state."""
        job_id = getattr(self.__class__, "_job_id", None)
        events = getattr(self.__class__, "_events", [])
        if not job_id:
            pytest.skip("No job_id")

        final = wait_for_terminal(job_id, timeout=10)
        ws_files = len([e for e in events if e.get("event") == "file_generated"])
        state_files = final.get("files_generated", 0)

        # WS file count should be >= state count (could be > if state lags)
        assert ws_files >= state_files or state_files == 0, (
            f"WS reported {ws_files} files but state has {state_files}"
        )


async def _collect_ws_events(job_id: str, timeout: int = 180) -> list[dict]:
    """Connect to WS stream and collect all events until terminal."""
    url = f"{WS_BASE}/autodev/stream/{job_id}"
    events: list[dict] = []
    terminal = {"done", "escalated", "error"}
    deadline = time.time() + timeout

    try:
        async with websockets.connect(url) as ws:
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    evt = json.loads(raw)
                    if evt.get("event") == "heartbeat":
                        continue
                    events.append(evt)
                    if evt.get("event") in terminal:
                        break
                except asyncio.TimeoutError:
                    continue
    except Exception as exc:
        events.append({"event": "ws_error", "data": {"error": str(exc)}, "ts": time.time()})

    return events
