# Ячейка как задача

Задача — объект `Task` из `book/modules/task_io.py`. Ячейка marimo создаёт его, исполняет
локально (`run`) или отдаёт в хаб (`propose`). Реестр задач — хаб `local-event-hub`.

## Жизненный цикл

```
draft ──run()──▶ done | blocked          (локально, агент как функция/файл/shell)
draft ──propose()──▶ awaiting ──approve собой──▶ approved ──▶ consumed ──▶ receipt
                                └──▶ rejected
```

Локальные состояния: `draft`, `done`, `blocked`. Состояния хаба: `awaiting`, `approved`,
`rejected`, `consumed`, `receipt`. Хаб-состояния меняет только хаб.

## Поля

| Поле | Смысл |
| --- | --- |
| `id` | `draft-…` пока локальная; `proposal_id` после `propose()` |
| `title` | заголовок задачи = `intent` proposal |
| `state` | см. цикл выше |
| `kind` | `func` / `file` / `shell` / `note` / `proposal` |
| `owner` | `agent` или `human` |
| `capability` | capability хаба, по умолчанию `task.<kind>` |
| `scope_sha256` | от хаба |
| `depends_on` | явные зависимости (marimo выводит их сам по переменным) |
| `comments` | лог обсуждения, уезжает в `metadata.comments` proposal |
| `evidence` | результат локального `run()` |

## Пример ячейки

```python
@app.cell
def _(task_io, http, relay_url, headers):
    t = task_io.Task(
        title="Поднять Postgres на VPS",
        kind="shell", priority=2, owner="agent",
        comments=["порт 5432 только через туннель"],
    )
    t, err = task_io.propose(http, relay_url, headers, t)   # → awaiting в хабе
    return (t,)
```

## Доска

`book/modules/board.py`: колонки по `state`, таблица, форма «предложить в хаб».
Реактивность — через `mo.ui.refresh`, как в `chats.py`.
