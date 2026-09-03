"""Модуль книги: /board — доска задач «ячейка = задача».

Реестр задач — хаб: страница читает `GET /v1/actions/proposals` и
раскладывает предложения по колонкам состояния, как /chats раскладывает
ленту. Реактивность та же — `mo.ui.refresh`: ячейка со списком зависит
от `refresh.value` и перечитывает хаб сама.

Форма внизу создаёт черновик `Task` и отдаёт его в хаб (`task_io.propose`).
Это не гейт: создать предложение может сессия, а внешний эффект случится
только после одобрения собой на /book/chats. Логика без marimo — в
task_io.py, здесь только показ.
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(
    width="full",
    app_title="NOTCH · board",
    auto_download=["ipynb", "html"],
)


@app.cell
def _():
    import sys
    from pathlib import Path

    import httpx
    import marimo as mo

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from book.modules import task_io

    env = task_io.environment()
    relay_url = env["relay_url"]
    token = env["token"]
    headers = env["headers"]
    http = httpx.Client(timeout=10.0)
    return env, headers, http, mo, relay_url, task_io, token


@app.cell
def _(mo):
    refresh = mo.ui.refresh(default_interval="10s", label="Обновление")
    refresh
    return (refresh,)


@app.cell
def _(env, headers, http, mo, refresh, relay_url, task_io, token):
    refresh.value
    tasks = []
    if not token:
        listing = {"ok": False, "reason": task_io.NO_IDENTITY, "tasks": []}
        listing_note = mo.callout("Без личности задачи не видны: войдите собой на /book/passkey.", kind="neutral")
    else:
        try:
            listing = task_io.list_tasks(http, relay_url, headers)
        except Exception as error:
            listing = {"ok": False, "reason": f"хаб недоступен: {type(error).__name__}", "tasks": []}
        tasks = listing["tasks"]
        if listing["ok"]:
            who = "сессией" if env["source"] == "session" else "токеном устройства"
            listing_note = mo.md(f"### Доска задач · {len(tasks)} в хабе · личность {who}")
        else:
            listing_note = mo.callout(listing["reason"], kind="warn")
    listing_note
    return listing, tasks


@app.cell
def _(mo, task_io, tasks):
    icons = {
        "awaiting": "🟡", "draft": "⚪", "approved": "🟢", "consumed": "🔵",
        "receipt": "✅", "done": "🟢", "blocked": "🔴", "rejected": "⚫", "expired": "⚫",
    }
    grouped = task_io.columns(tasks)
    board_columns = []
    for state, items in grouped.items():
        cards = [mo.md(f"**{icons.get(state, '·')} {state}** · {len(items)}")]
        for t in items:
            line = f"- **{t.title}**  \n  `{t.id}` · p{t.priority} · {t.kind} · {t.owner}"
            if t.comments:
                line += f" · 💬 {len(t.comments)}"
            cards.append(mo.md(line))
        if not items:
            cards.append(mo.md("_пусто_"))
        board_columns.append(mo.vstack(cards))
    board = mo.hstack(board_columns, widths="equal", align="start", gap=1.5)
    table = mo.ui.table(task_io.rows(tasks), selection=None, page_size=25)
    mo.vstack([board, mo.md("### Таблица"), table])
    return board, table


@app.cell
def _(mo):
    title = mo.ui.text(label="Задача", placeholder="что сделать", full_width=True)
    kind = mo.ui.dropdown(["note", "func", "file", "shell"], value="note", label="kind")
    priority = mo.ui.number(start=1, stop=5, value=3, label="приоритет")
    comment = mo.ui.text(label="комментарий", placeholder="необязательно", full_width=True)
    submit = mo.ui.run_button(label="Предложить в хаб")
    mo.vstack([
        mo.md("### Предложить в хаб"),
        mo.hstack([title, kind, priority], widths=[4, 1, 1]),
        mo.hstack([comment, submit], widths=[5, 1]),
    ])
    return comment, kind, priority, submit, title


@app.cell
def _(comment, headers, http, kind, mo, priority, relay_url, submit, task_io, title, token):
    mo.stop(not submit.value)
    if not title.value.strip():
        proposed_note = mo.callout("У задачи нет заголовка.", kind="warn")
    elif not token:
        proposed_note = mo.callout(task_io.NO_IDENTITY, kind="warn")
    else:
        draft = task_io.Task(
            title=title.value.strip(),
            kind=kind.value,
            owner="human",
            priority=int(priority.value or 3),
            comments=[comment.value.strip()] if comment.value.strip() else [],
        )
        try:
            proposed = task_io.propose(http, relay_url, headers, draft)
        except Exception as error:
            proposed = {"ok": False, "reason": f"хаб недоступен: {type(error).__name__}", "task": draft}
        proposed_note = mo.callout(
            mo.md(task_io.format_proposed(proposed)),
            kind="success" if proposed["ok"] else "danger",
        )
    proposed_note
    return


if __name__ == "__main__":
    app.run()
