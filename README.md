# notch (черновик слоя «ячейка = задача»)

Личный черновик для `wforkorg/notch`. Структура повторяет книгу организации, чтобы мерж был
переносом файлов. План: `docs/MERGE-PLAN.md`.

- `book/modules/task_io.py` — модель `Task` поверх proposal хаба, `list_tasks`, `propose`, без marimo.
- `book/modules/board.py` — страница `/book/board`: реактивная доска и форма предложения.
- `docs/marimo-vs-jupyter.md` — зачем реактивный ноутбук.
- `docs/cell-as-task.md` — формат задачи.

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
WFORK_RELAY_URL=http://127.0.0.1:8765 marimo run book/modules/board.py --base-url /book/board
```
