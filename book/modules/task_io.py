"""Слой «ячейка = задача» — без marimo, по образцу hub_io.py.

`Task` накрывает proposal хаба local-event-hub, а не конкурирует с ним.
Реестр задач — сам хаб (`/v1/actions/proposals`); в книге живёт только
кэш в памяти ячейки, потому что `book/` смонтирован `:ro`, а второй
путь к данным мимо хаба здесь отвергли ещё для вложений (см. material.py).

Два круга жизни задачи:

    draft ──run()──▶ done | blocked            локально, агент как функция
    draft ──propose()──▶ awaiting ──approve собой──▶ approved ──▶ consumed ──▶ receipt
                                  └──▶ rejected        (истёкшее хаб зовёт expired)

Локальные состояния меняет книга, состояния хаба — только хаб: `propose()`
берёт `state` из его ответа, а не назначает сама.

Форма `POST /v1/actions/proposals` взята не из формы ответа `GET`, а из
единственного в нашем коде клиента, который её реально шлёт и был написан
по коду хаба, — `apps/macos/agent-bridge/gated_bridge.py` (PR #11):
`capability`, `title`, `actor{kind, ref}` (kind из словаря хаба:
system/rule/user/device/agent), `external_effect`, `reversible`,
`intent` — объект до 16 полей. `descriptor` не трогаем: у хаба он описывает
вложенный файл, а не действие. Ответ — конверт `{"proposal": {...}}`.
Сам код хаба в этот репозиторий не входит; если его схема разойдётся с
этой, править надо `to_proposal()` и тест `test_propose_*`, а не ячейки.

Окружение и личность — из hub_io: сессия входа собой раньше env-токена,
401 хаба → NO_IDENTITY, тот же текст, что на остальных страницах.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field

from book.modules import hub_io

NO_IDENTITY = hub_io.NO_IDENTITY

# Состояния хаба — в порядке цикла propose → approve → consume → receipt.
# `expired` в цикле не рисуют, но хаб его отдаёт (gated_bridge опрашивает
# и его), и задача с ним — не «awaiting».
HUB_STATES = ("awaiting", "approved", "rejected", "consumed", "receipt", "expired")
LOCAL_STATES = ("draft", "done", "blocked")
# Порядок колонок доски: сначала то, что ждёт человека.
BOARD_ORDER = ("awaiting", "draft", "approved", "consumed", "receipt", "done", "blocked", "rejected", "expired")

State = Literal[
    "draft", "done", "blocked",
    "awaiting", "approved", "rejected", "consumed", "receipt", "expired",
]
Kind = Literal["func", "file", "shell", "note", "proposal"]
Owner = Literal["agent", "human"]

# Актор хаба: книгу представляет человек (сессия passkey) или агент.
ACTOR_KIND = {"human": "user", "agent": "agent"}
ACTOR_REF = "notch-book-board"
DRAFT_PREFIX = "draft-"


class Evidence(BaseModel):
    """Что осталось от локального run(): результат или текст ошибки."""

    ok: bool
    output: Any = None
    seconds: float = 0.0


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"{DRAFT_PREFIX}{uuid.uuid4().hex[:12]}")
    title: str = Field(min_length=1, max_length=200)
    state: State = "draft"
    kind: Kind = "func"
    owner: Owner = "agent"
    priority: int = Field(default=3, ge=1, le=5)
    capability: Optional[str] = None
    # Внешний необратимый эффект — правда о задаче, а не флаг «поважнее»:
    # shell и file меняют мир за пределами книги, note и func — нет.
    external_effect: Optional[bool] = None
    reversible: Optional[bool] = None
    scope_sha256: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list)
    evidence: Optional[Evidence] = None
    occurred_at: Optional[str] = None

    @property
    def is_hub(self) -> bool:
        return self.state in HUB_STATES

    @property
    def is_draft(self) -> bool:
        return self.state == "draft"

    def effective_capability(self) -> str:
        return self.capability or f"task.{self.kind}"

    def effective_external_effect(self) -> bool:
        if self.external_effect is not None:
            return self.external_effect
        return self.kind in ("shell", "file")

    def effective_reversible(self) -> bool:
        if self.reversible is not None:
            return self.reversible
        return not self.effective_external_effect()

    def run(self, fn: Optional[Callable[[], Any]] = None) -> Evidence:
        """Локальное исполнение тела задачи агентом — без хаба и без гейта.

        Гейт здесь не нужен по замыслу: внешний эффект идёт только через
        `propose()`. Поэтому run() честно отказывается от shell/file —
        для них тело задачи и есть внешний эффект.
        """
        if self.state in HUB_STATES:
            self.evidence = Evidence(ok=False, output="задача уже в хабе: её решает approve, а не run()")
            return self.evidence
        if self.effective_external_effect():
            self.evidence = Evidence(ok=False, output="внешний эффект: только через propose() и approve собой")
            self.state = "blocked"
            return self.evidence
        if fn is None:
            self.evidence = Evidence(ok=True)
            return self.evidence
        started = time.perf_counter()
        try:
            output = fn()
        except Exception as error:  # тело задачи — чужой код, любая ошибка = blocked
            self.evidence = Evidence(ok=False, output=f"{type(error).__name__}: {error}", seconds=time.perf_counter() - started)
            self.state = "blocked"
            return self.evidence
        self.evidence = Evidence(ok=True, output=output, seconds=time.perf_counter() - started)
        self.state = "done"
        return self.evidence

    def to_proposal(self) -> Dict[str, Any]:
        """Тело `POST /v1/actions/proposals` в форме хаба (см. докстринг модуля)."""
        intent: Dict[str, Any] = {
            "kind": self.kind,
            "priority": self.priority,
            "owner": self.owner,
            "draft_id": self.id if self.id.startswith(DRAFT_PREFIX) else "",
            "depends_on": list(self.depends_on),
            "comments": list(self.comments)[-10:],
        }
        if self.evidence is not None:
            intent["evidence"] = self.evidence.model_dump()
        return {
            "capability": self.effective_capability(),
            "title": self.title[:200],
            "actor": {"kind": ACTOR_KIND[self.owner], "ref": ACTOR_REF},
            "external_effect": self.effective_external_effect(),
            "reversible": self.effective_reversible(),
            "intent": intent,
        }


def from_proposal(proposal: Dict[str, Any]) -> Optional[Task]:
    """Proposal хаба → Task. Без идентификатора это не задача, а мусор в ответе."""
    proposal_id = proposal.get("proposal_id") or proposal.get("id")
    if not proposal_id:
        return None
    intent = proposal.get("intent")
    intent = intent if isinstance(intent, dict) else {}
    title = proposal.get("title") or intent.get("detail") or proposal.get("capability") or str(proposal_id)
    if isinstance(proposal.get("intent"), str) and not proposal.get("title"):
        title = proposal["intent"]
    state = proposal.get("state") if proposal.get("state") in HUB_STATES else "awaiting"
    kind = intent.get("kind") if intent.get("kind") in ("func", "file", "shell", "note") else "proposal"
    owner = intent.get("owner") if intent.get("owner") in ("agent", "human") else "agent"
    try:
        priority = max(1, min(5, int(intent.get("priority", 3))))
    except (TypeError, ValueError):
        priority = 3
    return Task(
        id=str(proposal_id),
        title=str(title)[:200] or str(proposal_id),
        state=state,
        kind=kind,
        owner=owner,
        priority=priority,
        capability=proposal.get("capability"),
        external_effect=proposal.get("external_effect"),
        reversible=proposal.get("reversible"),
        scope_sha256=proposal.get("scope_sha256"),
        depends_on=[str(d) for d in intent.get("depends_on", []) if d],
        comments=[str(c) for c in intent.get("comments", [])],
        occurred_at=_when(proposal),
    )


def _when(proposal: Dict[str, Any]) -> Optional[str]:
    """У proposal нет `occurred_at` событий; берём любую метку времени, что есть."""
    for key in ("occurred_at", "created_at", "updated_at", "ts"):
        value = proposal.get(key)
        if value:
            return str(value)
    return None


def environment() -> Dict[str, Any]:
    """Окружение страницы — одно на всю книгу, а не шестая копия в ячейке.

    Личность выбирает hub_io.credential(): сессия входа собой раньше
    env-токена; заголовок — hub_io.auth_headers(), пустой без токена.
    """
    token, source = hub_io.credential(
        os.getenv("WFORK_SESSION_PATH", ""),
        os.getenv("WFORK_RELAY_TOKEN", ""),
    )
    return {
        "relay_url": os.getenv("WFORK_RELAY_URL", "http://host.docker.internal:8765").rstrip("/"),
        "relay_browser_url": os.getenv("WFORK_RELAY_BROWSER_URL", "/relay").rstrip("/"),
        "token": token,
        "source": source,
        "headers": hub_io.auth_headers(token),
    }


def list_tasks(
    http: Any,
    relay_url: str,
    headers: Dict[str, str],
    states: Iterable[str] = HUB_STATES,
) -> Dict[str, Any]:
    """Реестр = хаб: `GET /v1/actions/proposals?state=…` по каждому состоянию.

    По одному запросу на состояние, как gated_bridge: хаб отдаёт список
    по фильтру, а не «всё сразу». Первый отказ — отказ всего чтения:
    половина доски хуже честного «хаб не ответил».
    """
    tasks: List[Task] = []
    seen = set()
    for state in states:
        response = http.get(f"{relay_url}/v1/actions/proposals", params={"state": state}, headers=headers)
        if not response.is_success:
            return {"ok": False, "reason": hub_io._refusal(response), "tasks": []}
        body = response.json()
        items = body if isinstance(body, list) else body.get("proposals") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            task = from_proposal(item)
            if task is None or task.id in seen:
                continue
            seen.add(task.id)
            tasks.append(task)
    tasks.sort(key=lambda t: (BOARD_ORDER.index(t.state) if t.state in BOARD_ORDER else 99, t.priority, t.id))
    return {"ok": True, "reason": "", "tasks": tasks}


def propose(http: Any, relay_url: str, headers: Dict[str, str], task: Task) -> Dict[str, Any]:
    """Черновик → предложение хаба. Гейт — approve собой на /book/chats,
    не эта функция: создать proposal может и сессия, одобрить — только подпись.
    """
    if task.state in HUB_STATES:
        return {"ok": False, "reason": f"задача уже в хабе: {task.id} ({task.state})", "task": task}
    response = http.post(f"{relay_url}/v1/actions/proposals", headers=headers, json=task.to_proposal())
    if not response.is_success:
        return {"ok": False, "reason": hub_io._refusal(response), "task": task}
    body = response.json()
    stored = body.get("proposal") if isinstance(body.get("proposal"), dict) else body
    proposal_id = stored.get("proposal_id") or stored.get("id")
    if not proposal_id:
        return {"ok": False, "reason": "хаб не вернул идентификатор предложения", "task": task}
    accepted = task.model_copy(
        update={
            "id": str(proposal_id),
            "state": stored.get("state") if stored.get("state") in HUB_STATES else "awaiting",
            "capability": stored.get("capability") or task.effective_capability(),
            "scope_sha256": stored.get("scope_sha256") or task.scope_sha256,
            "occurred_at": _when(stored) or task.occurred_at,
        }
    )
    return {"ok": True, "reason": "", "task": accepted}


def columns(tasks: Iterable[Task]) -> Dict[str, List[Task]]:
    """Колонки доски по состоянию; пустые остаются — доска без колонки
    «awaiting» читалась бы как «ждать нечего», а не «пока пусто»."""
    grouped: Dict[str, List[Task]] = {state: [] for state in BOARD_ORDER}
    for task in tasks:
        grouped.setdefault(task.state, []).append(task)
    return grouped


def rows(tasks: Iterable[Task]) -> List[Dict[str, Any]]:
    """Плоские строки для mo.ui.table — без вложенных моделей."""
    return [
        {
            "id": t.id,
            "title": t.title,
            "state": t.state,
            "kind": t.kind,
            "owner": t.owner,
            "priority": t.priority,
            "capability": t.effective_capability(),
            "effect": "внешний" if t.effective_external_effect() else "локальный",
            "scope": (t.scope_sha256 or "")[:12],
            "comments": len(t.comments),
            "when": (t.occurred_at or "")[:19].replace("T", " "),
        }
        for t in tasks
    ]


def format_proposed(result: Dict[str, Any]) -> str:
    """Одна строка отчёта о propose() — формат отдельно от отправки."""
    task = result.get("task")
    if not result.get("ok"):
        return f"🔴 {result.get('reason', 'причина неизвестна')}"
    return f"🟢 `{task.id}` — {task.title} · {task.state}; одобрить собой можно на /book/chats"
