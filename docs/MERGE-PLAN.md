# План слияния `quiterunner-commits/notch` → `wforkorg/notch`

Основание: `docs/AUDIT.md` соседней сессии (срез `main` @ `8c18517`, 2026-09-03).

## Принципы, взятые из аудита

1. **Реестр задач = хаб.** `Task` накрывает proposal `local-event-hub`, локальный файл-реестр не заводим (код в `book/` монтируется `:ro`).
2. **Код без marimo отдельно от ячеек** — по образцу `hub_io.py`: `task_io.py` тестируется без браузера.
3. **Гейт на внешний эффект — approve собой**, не форма. Создание proposal не требует controller, одобрение — требует.
4. **Не дублировать шестую копию окружения хаба.** В `board.py` есть `TODO(merge)`: заменить `headers={}` на `hub_io.auth_headers(hub_io.credential())`.

## Что переносится (файл → место в wforkorg/notch)

| Здесь | Туда | Примечание |
| --- | --- | --- |
| `book/modules/task_io.py` | `book/modules/task_io.py` | новый файл, конфликтов нет |
| `book/modules/board.py` | `book/modules/board.py` | новая страница `/book/board` |
| `tests/test_task_io.py` | `tests/test_task_io.py` | FakeHttp заменить на подмену `httpx` из их `conftest.py` |
| `tests/test_board.py` | `tests/test_board.py` | как `test_chats_proposals.py` |
| `docs/marimo-vs-jupyter.md` | `docs/marimo-vs-jupyter.md` | справочный документ |
| `docs/cell-as-task.md` | `docs/cell-as-task.md` | обновить под hub-состояния |
| `requirements.txt` (`pydantic>=2`) | одна строка в их `requirements.txt` | явный пин, сейчас приходит транзитивно |

Не переносится: `tests/conftest.py` (у них свой), `README.md`.

## Что добавить на стороне wforkorg (руками, поверх формы PR #12)

- `deploy/compose.yml`: сервис `notch-book-board`, `127.0.0.1:2730`, `--base-url /book/board`, `session-cache:ro`.
- Оглавление в `book/notch_book.py`: ссылка на `/book/board`.
- `book/notch_mcp_server.py`: инструменты `list_tasks` / `propose_task` рядом с `run_tests`.
- `book/modules/widgets.py`: вынести `ProposalApproval` и JS-хелперы WebAuthn из `chats.py`, использовать в `board.py` для одобрения.

## Порядок: две независимые части, выбор не сужается

Работа делится по признаку «трогает ли она `deploy/compose.yml`». Части не зависят друг от
друга, порядок между ними любой, ждать одну ради другой не нужно.

### Часть A — переносится когда угодно, конфликтов с PR #12 нет

Только новые файлы, ни одного изменения в существующих (кроме одной строки в
`requirements.txt`):

- `book/modules/task_io.py`, `book/modules/board.py`
- `tests/test_task_io.py`, `tests/test_board.py`
- `docs/cell-as-task.md`, `docs/marimo-vs-jupyter.md`, `docs/MERGE-PLAN.md`
- `pydantic>=2` в `requirements.txt`

Доска после этого запускается вручную (`marimo run book/modules/board.py`) и полностью
тестируется. Как отдельный сервис в контейнере — ещё нет, это часть B.

### Часть B — трогает `deploy/compose.yml`, форма зависит от PR #12

- сервис `notch-book-board`, `127.0.0.1:2730`, `--base-url /book/board`, `session-cache:ro`
- ссылка на `/book/board` в оглавлении `book/notch_book.py`
- инструменты `list_tasks` / `propose_task` в `book/notch_mcp_server.py`
- вынос `ProposalApproval` и WebAuthn-хелперов в `book/modules/widgets.py`

Если PR #12 к этому моменту влит — пишем поверх его формы. Если нет — пишем поверх текущего
`main`, а при влитии #12 правим один сервис в компоузе. Оба варианта рабочие, разница в
несколько строк.

## Что должна выяснить сессия с доступом к коду (не оператор)

Эти два пункта проверяются чтением кода `local-event-hub`, спрашивать оператора не нужно.

1. **Форма `POST /v1/actions/proposals`.** Аудит видел только `GET` и `approve/reject`.
   Сейчас `to_proposal()` шлёт `title`, `intent`, `capability`, `metadata` — это догадка
   по форме ответа `GET`. Найти обработчик создания предложения в хабе, привести
   `to_proposal()` к его схеме, тест `test_propose_turns_draft_into_hub_task` поправить следом.
2. **Есть ли `occurred_at` у proposal** или только у событий `/v1/events`. Если нет —
   убрать поле из `from_proposal()` либо брать время из связанного события.

Пока это не проверено, `propose()` работает как черновик: `list_tasks()` (только чтение)
от него не зависит и доску показывает корректно.
