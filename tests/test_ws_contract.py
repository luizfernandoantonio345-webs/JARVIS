
"""
WebSocket contract tests.
Ensures backend schema matches frontend TypeScript types.
"""
from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import os
import re
import sys
from pathlib import Path

os.environ["JARVIS_TEST_MODE"] = "1"
os.environ["JARVIS_DISABLE_VOICE"] = "1"

# Ensure backend is on path
_BACKEND = Path(__file__).parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from schemas.ws_messages import (  # noqa: E402
    JarvisWSMessage,
    OrbStatus,
    error_msg,
    idle_msg,
    listening_msg,
    speaking_msg,
    thinking_msg,
)


def _parse_frontend_orb_status_values(ts_source: str) -> set[str]:
    # Extract: key = "value"
    enum_block = re.search(r"export enum OrbStatus\s*\{(?P<body>.*?)\}", ts_source, re.S)
    assert enum_block, "OrbStatus enum not found in frontend type file"
    values = set(re.findall(r"=\s*\"([^\"]+)\"", enum_block.group("body")))
    return values


def test_orb_status_enum_matches_frontend() -> None:
    ts_path = Path(__file__).parent.parent / "frontend" / "src" / "types" / "ws.ts"
    ts_source = ts_path.read_text(encoding="utf-8")

    frontend_values = _parse_frontend_orb_status_values(ts_source)
    backend_values = {s.value for s in OrbStatus}

    assert backend_values == frontend_values


def test_helper_messages_are_valid_schema() -> None:
    msgs = [
        idle_msg("ready"),
        listening_msg("listening"),
        thinking_msg("thinking"),
        speaking_msg("speaking", audio_url="http://localhost/audio.wav"),
        error_msg("error happened"),
    ]

    for payload in msgs:
        parsed = JarvisWSMessage(**payload)
        assert parsed.status in OrbStatus


def test_ws_model_has_expected_public_fields() -> None:
    expected = {"status", "message", "audio_url", "data", "ts", "source", "task_id"}
    fields = set(JarvisWSMessage.model_fields.keys())
    assert expected.issubset(fields)
