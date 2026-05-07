import os
from collections import defaultdict
from typing import Dict, List

from core.jarvis_persona import MAIN_SYSTEM_PROMPT

# In-memory store: session_id -> list of messages
_sessions: Dict[str, List[Dict[str, str]]] = defaultdict(list)

# Max messages kept in session history (keeps RAM bounded on 8 GB machines).
# Oldest messages are evicted when the cap is reached.
_SESSION_HISTORY_CAP = int(os.getenv("SESSION_HISTORY_CAP", "40"))

SYSTEM_PROMPT = MAIN_SYSTEM_PROMPT


def get_history(session_id: str) -> List[Dict[str, str]]:
    return _sessions[session_id]


def append_message(session_id: str, role: str, content: str) -> None:
    _sessions[session_id].append({"role": role, "content": content})
    # Evict oldest pairs (user+assistant) when over cap
    history = _sessions[session_id]
    while len(history) > _SESSION_HISTORY_CAP:
        # Remove the oldest two messages (user + assistant pair)
        history.pop(0)
        if history:
            history.pop(0)


def clear_session(session_id: str) -> None:
    _sessions[session_id] = []
