"""Memoria persistente automatica para fatos do usuario."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

MEMORY_PATH = Path("backend/data/jarvis_memory.json")


def _load_memory() -> dict:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MEMORY_PATH.exists():
        try:
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_memory_file(data: dict) -> None:
    MEMORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_memory(parameters: dict, player=None) -> str:
    category = parameters.get("category", "notes")
    key = parameters.get("key", "")
    value = parameters.get("value", "")

    if not key or not value:
        return "Chave e valor sao obrigatorios."

    try:
        memory = _load_memory()
        if category not in memory:
            memory[category] = {}

        memory[category][key] = {
            "value": value,
            "saved_at": datetime.now().isoformat(),
        }
        _save_memory_file(memory)

        if player:
            player.write_log(f"Memory: {category}/{key} = {value}")

        return "ok"
    except Exception as e:
        return f"Erro save_memory: {e}"


def load_user_memory() -> str:
    memory = _load_memory()
    if not memory:
        return ""

    lines = ["[MEMORIA DO USUARIO]"]
    for category, items in memory.items():
        for key, data in items.items():
            value = data.get("value", data) if isinstance(data, dict) else data
            lines.append(f"- {category}/{key}: {value}")

    return "\n".join(lines)


def get_memory_summary() -> dict:
    memory = _load_memory()
    total = sum(len(items) for items in memory.values())
    return {
        "categories": list(memory.keys()),
        "total_facts": total,
        "memory": memory,
    }
