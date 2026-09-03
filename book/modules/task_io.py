"""Слой «ячейка = задача» без marimo (по образцу hub_io.py).

Task накрывает proposal хаба local-event-hub, а не конкурирует с ним:
- пока задача локальная, id — временный (`draft-…`), state ∈ {draft, done};
- после propose() id = proposal_id хаба, state — то, что хаб реально подтверждает:
  awaiting → approved | rejected → consumed → receipt.

Реестр задач = хаб (GET /v1/actions/proposals + GET /v1/events). Локально
держится только кэш в памяти ячейки; писать в book/ нельзя (том :ro).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

HUB_STATES = ("awaiting", "approved", "rejected", "consumed", "receipt")
LOCAL_STATES = ("draft", "done", "blocked")
State = Literal["draft", "done", "blocked", "awaiting", "approved", "rejected", "consumed", "receipt"]
Kind = Literal["func", "file", "shell", "note", "proposal"]
Owner = Literal["agent", "human"]

NO_IDENTITY = "нет сессии: войдите собой на /book/passkey"


class HttpLike(Protocol):
    def get(self, url: str, headers: dict[str, str] | None = ...) -> Any: ...
    def post(self, url: str, json: Any = ..., headers: dict[str, str] | None = ...) -> Any: ...


class Evidence(BaseModel):
    ok: bool
    output: Any = None
    seconds: float = 0.0


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"draft-{uuid.uuid4().hex[:12]}")
    title: str
    state: State = "draft"
    priority: int = Field(default=3, ge=1, le=5)
    kind: Kind = "func"
    owner: Owner = "agent"
    capability: str | None = None
    scope_sha256: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    evidence: Evidence | None = None
    occurred_at: float | None = None

    @property
    def is_hub(self) -> bool:
        return self.state in HUB_STATES

    def run(self, fn: Callable[[], Any] | None = None) -> Evidence:
        """Локальное исполнение тела задачи агентом. Для note/proposal ничего не делает."""
        if fn is None or self.kind in ("note", "proposal"):
            self.evidence = Evidence(ok=True)
            return self.evidence
        t0 = time.perf_counter()
        try:
            out = fn()
            self.evidence = Evidence(ok=True, output=out, seconds=time.perf_counter() - t0)
            self.state = "done"
        except Exception as exc:  # noqa: BLE001
            self.evidence = Evidence(ok=False, output=str(exc), seconds=time.perf_counter() - t0)
            self.state = "blocked"
        return self.evidence

    def to_proposal(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "intent": self.title,
            "capability": self.capability or f"task.{self.kind}",
            "metadata": {
                "priority": self.priority,
                "owner": self.owner,
                "depends_on": self.depends_on,
                "comments": self.comments,
            },
        }


def from_proposal(p: dict[str, Any]) -> Task:
    meta = p.get("metadata") or {}
    return Task(
        id=str(p.get("proposal_id") or p.get("id") or ""),
        title=str(p.get("title") or p.get("intent") or p.get("capability") or "?"),
        state=p.get("state") if p.get("state") in HUB_STATES else "awaiting",
        kind="proposal",
        capability=p.get("capability"),
        scope_sha256=p.get("scope_sha256"),
        priority=int(meta.get("priority", 3)),
        owner=meta.get("owner", "agent"),
        depends_on=list(meta.get("depends_on", [])),
        comments=list(meta.get("comments", [])),
        occurred_at=p.get("occurred_at"),
    )


def _refusal(resp: Any) -> str | None:
    status = getattr(resp, "status_code", 200)
    if status == 401:
        return NO_IDENTITY
    if status >= 400:
        return f"хаб ответил {status}"
    return None


def list_tasks(http: HttpLike, relay_url: str, headers: dict[str, str]) -> tuple[list[Task], str | None]:
    """Реестр = хаб. Возвращает (задачи, текст отказа или None)."""
    resp = http.get(f"{relay_url}/v1/actions/proposals", headers=headers)
    if err := _refusal(resp):
        return [], err
    items = resp.json().get("items", resp.json() if isinstance(resp.json(), list) else [])
    tasks = [from_proposal(p) for p in items]
    tasks.sort(key=lambda t: (t.priority, t.id))
    return tasks, None


def propose(http: HttpLike, relay_url: str, headers: dict[str, str], task: Task) -> tuple[Task, str | None]:
    """Превратить локальную задачу в proposal хаба (закрывает issue #3/#4 по механике)."""
    resp = http.post(f"{relay_url}/v1/actions/proposals", json=task.to_proposal(), headers=headers)
    if err := _refusal(resp):
        return task, err
    body = resp.json()
    task.id = str(body.get("proposal_id", task.id))
    task.state = body.get("state") if body.get("state") in HUB_STATES else "awaiting"
    task.kind = "proposal"
    return task, None


def rows(tasks: list[Task]) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "title": t.title,
            "state": t.state,
            "priority": t.priority,
            "kind": t.kind,
            "owner": t.owner,
            "depends_on": ", ".join(t.depends_on),
            "comments": len(t.comments),
            "ok": None if t.evidence is None else t.evidence.ok,
        }
        for t in tasks
    ]


def columns(tasks: list[Task]) -> dict[str, list[Task]]:
    order = ("draft", "awaiting", "approved", "consumed", "receipt", "done", "blocked", "rejected")
    out: dict[str, list[Task]] = {s: [] for s in order}
    for t in tasks:
        out.setdefault(t.state, []).append(t)
    return out
