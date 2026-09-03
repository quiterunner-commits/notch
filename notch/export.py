"""Экспорт доски задач в формат, совместимый с GitHub issues."""

from __future__ import annotations

import json
from typing import Any

from .task import TaskRegistry, registry as default_registry

_STATE = {"todo": "open", "doing": "open", "blocked": "open", "done": "closed"}


def to_issues(reg: TaskRegistry = default_registry) -> list[dict[str, Any]]:
    out = []
    for t in reg.all():
        body = "\n".join(
            [
                f"kind: {t.kind}",
                f"owner: {t.owner}",
                f"priority: {t.priority}",
                f"depends_on: {', '.join(t.depends_on) or '-'}",
                "",
                *[f"- {c}" for c in t.comments],
            ]
        )
        out.append(
            {
                "title": t.title,
                "body": body,
                "state": _STATE[t.status],
                "labels": [f"kind:{t.kind}", f"owner:{t.owner}", f"status:{t.status}"],
                "external_id": t.id,
            }
        )
    return out


def dump(path: str, reg: TaskRegistry = default_registry) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_issues(reg), f, ensure_ascii=False, indent=2)
