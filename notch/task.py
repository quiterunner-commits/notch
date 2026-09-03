"""Ячейка как задача: метаданные + исполнение."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

Status = Literal["todo", "doing", "done", "blocked"]
Kind = Literal["func", "file", "shell", "note"]
Owner = Literal["agent", "human"]


class TaskResult(BaseModel):
    ok: bool
    output: Any = None
    seconds: float = 0.0


class Task(BaseModel):
    id: str
    title: str
    status: Status = "todo"
    priority: int = Field(default=3, ge=1, le=5)
    kind: Kind = "func"
    owner: Owner = "agent"
    depends_on: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    result: TaskResult | None = None

    def model_post_init(self, __context: Any) -> None:
        registry.add(self)

    def run(self, fn: Callable[[], Any] | None = None) -> TaskResult:
        """Выполнить тело задачи. Для kind=note ничего не делает."""
        if self.kind == "note" or fn is None:
            self.result = TaskResult(ok=True)
            return self.result
        self.status = "doing"
        t0 = time.perf_counter()
        try:
            out = fn()
            self.result = TaskResult(ok=True, output=out, seconds=time.perf_counter() - t0)
            self.status = "done"
        except Exception as exc:  # noqa: BLE001
            self.result = TaskResult(ok=False, output=str(exc), seconds=time.perf_counter() - t0)
            self.status = "blocked"
        return self.result


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        self._tasks[task.id] = task

    def all(self) -> list[Task]:
        return sorted(self._tasks.values(), key=lambda t: (t.priority, t.id))

    def rows(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "kind": t.kind,
                "owner": t.owner,
                "depends_on": ", ".join(t.depends_on),
                "comments": len(t.comments),
                "ok": None if t.result is None else t.result.ok,
            }
            for t in self.all()
        ]

    def clear(self) -> None:
        self._tasks.clear()


registry = TaskRegistry()


def run_shell(cmd: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, check=True)
    return proc.stdout
