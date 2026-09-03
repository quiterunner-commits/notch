# Ячейка как задача

Задача — объект `Task` из `book/modules/task_io.py`. Ячейка marimo создаёт его, исполняет
локально (`run`) или отдаёт в хаб (`propose`). Реестр задач — хаб `local-event-hub`.

## Жизненный цикл

```
draft ──run()──▶ done | blocked          (локально, агент как функция; shell/file — только через хаб)
draft ──propose()──▶ awaiting ──approve собой──▶ approved ──▶ consumed ──▶ receipt
                                └──▶ rejected        (истёкшее хаб зовёт expired)
```

Локальные состояния: `draft`, `done`, `blocked`. Состояния хаба: `awaiting`, `approved`,
`rejected`, `consumed`, `receipt` (+ `expired`, его хаб тоже отдаёт). Хаб-состояния меняет
только хаб: `propose()` берёт `state` из ответа.

## Поля

| Поле | Смысл |
| --- | --- |
| `id` | `draft-…` пока локальная; `proposal_id` после `propose()` |
| `title` | заголовок задачи = `intent` proposal |
| `state` | см. цикл выше |
| `kind` | `func` / `file` / `shell` / `note` / `proposal` |
| `owner` | `agent` или `human` |
| `capability` | capability хаба, по умолчанию `task.<kind>` |
| `external_effect`, `reversible` | правда о задаче для хаба; по умолчанию shell/file — внешний и необратимый |
| `scope_sha256` | от хаба |
| `depends_on` | явные зависимости (marimo выводит их сам по переменным) |
| `comments` | лог обсуждения, уезжает в `intent.comments` proposal |
| `evidence` | результат локального `run()` |

## Пример ячейки

```python
@app.cell
def _(task_io, http, relay_url, headers):
    draft = task_io.Task(
        title="Поднять Postgres на VPS",
        kind="shell", priority=2, owner="human",
        comments=["порт 5432 только через туннель"],
    )
    result = task_io.propose(http, relay_url, headers, draft)   # {"ok", "reason", "task"}
    t = result["task"]                                          # → awaiting в хабе, id = proposal_id
    return (t,)
```

## Форма `POST /v1/actions/proposals`

Взята из `gated_bridge.py` (PR #11 в `wforkorg/notch`) — единственного клиента, написанного
по коду хаба: `capability`, `title`, `actor{kind ∈ system/rule/user/device/agent, ref}`,
`external_effect`, `reversible`, `intent` (объект до 16 полей). Ответ — `{"proposal": {...}}`.
Чтение — `GET /v1/actions/proposals?state=<state>` по каждому состоянию, ответ `{"proposals": [...]}`.

## Доска

`book/modules/board.py`: колонки по `state`, таблица, форма «предложить в хаб».
Реактивность — через `mo.ui.refresh`, как в `chats.py`.
