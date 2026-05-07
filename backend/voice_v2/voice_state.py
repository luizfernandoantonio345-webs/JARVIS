from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class VoiceState:
    listening: bool = False
    speaking: bool = False
    lock: asyncio.Lock = asyncio.Lock()

