"""Fila de tarefas multi-step com prioridade."""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import httpx


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3


class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    goal: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.QUEUED
    result: str = ""
    speak: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)


class TaskQueue:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def submit(self, goal: str, priority: TaskPriority = TaskPriority.NORMAL, speak: Callable = None) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = Task(id=task_id, goal=goal, priority=priority, speak=speak)
        with self._lock:
            self._tasks[task_id] = task
        return task_id

    def get_status(self, task_id: str) -> dict:
        task = self._tasks.get(task_id)
        if not task:
            return {"error": "Task nao encontrada"}
        return {
            "id": task.id,
            "goal": task.goal,
            "status": task.status.value,
            "result": task.result,
        }

    def list_tasks(self) -> list:
        with self._lock:
            return [
                {"id": t.id, "goal": t.goal[:50], "status": t.status.value}
                for t in sorted(self._tasks.values(), key=lambda x: x.priority.value, reverse=True)
            ]

    def _worker(self):
        while True:
            task = self._get_next_task()
            if task:
                self._execute(task)
            else:
                time.sleep(1)

    def _get_next_task(self) -> Optional[Task]:
        with self._lock:
            queued = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
            if not queued:
                return None
            return max(queued, key=lambda x: x.priority.value)

    def _execute(self, task: Task):
        task.status = TaskStatus.RUNNING
        try:
            result = self._run_goal(task.goal)
            task.result = result
            task.status = TaskStatus.DONE
            if task.speak:
                task.speak(f"Tarefa concluida: {result[:200]}")
        except Exception as e:
            task.result = str(e)
            task.status = TaskStatus.FAILED
            if task.speak:
                task.speak(f"Tarefa falhou: {e}")

    def _run_goal(self, goal: str) -> str:
        if os.environ.get("JARVIS_TEST_MODE"):
            return f"Tarefa simulada em modo de teste: {goal}"

        try:
            prompt = (
                f"Voce e um agente executor. Sua tarefa e: {goal}\n\n"
                "Execute a tarefa e descreva o que foi feito em portugues. "
                "Seja conciso e objetivo."
            )
            resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen2:0.5b", "prompt": prompt, "stream": False},
                timeout=60,
            )
            return resp.json().get("response", "Tarefa executada")
        except Exception as e:
            return f"Erro na execucao: {e}"


_queue_instance: Optional[TaskQueue] = None


def get_queue() -> TaskQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = TaskQueue()
    return _queue_instance


def agent_task(parameters: dict, player=None, speak=None) -> str:
    goal = parameters.get("goal", "")
    priority_str = parameters.get("priority", "normal").lower()

    if not goal:
        return "Descreva o objetivo da tarefa."

    priority_map = {
        "low": TaskPriority.LOW,
        "normal": TaskPriority.NORMAL,
        "high": TaskPriority.HIGH,
    }
    priority = priority_map.get(priority_str, TaskPriority.NORMAL)

    task_id = get_queue().submit(goal=goal, priority=priority, speak=speak)

    if player:
        player.write_log(f"AgentTask [{task_id}]: {goal[:100]}")

    return f"Tarefa iniciada (ID: {task_id}). Prioridade: {priority_str}. Executando em background."
