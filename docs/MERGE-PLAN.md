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

## Порядок

1. Дождаться решения по PR #12 (рендер `marimo.toml`, `compose.yml` на 143 строки). Доску добавлять поверх его формы.
2. Ветка `feat/cell-as-task` от `main` в `wforkorg/notch`, перенос файлов из таблицы.
3. Подключить `hub_io` в `board.py`, снять `TODO(merge)`.
4. Проверка в своём compose-проекте `-p nb-board`, не трогая `wfork-notch-book*` (AGENTS.md организации).
5. PR; после влития — issue #3 (действия из ленты как proposals) закрывается механикой `propose()`.

## Открытые вопросы к хабу

- Точная форма `POST /v1/actions/proposals` (аудит видел только GET и approve/reject). `to_proposal()` шлёт `title/intent/capability/metadata`; поправить по факту.
- Есть ли в ответе `occurred_at` у proposal или только у событий.
