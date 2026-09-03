import marimo

__generated_with = "0.10.0"
app = marimo.App(width="medium", app_title="NOTCH · board")


@app.cell
def _():
    import os
    import sys
    from pathlib import Path

    import httpx
    import marimo as mo

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from book.modules import task_io

    relay_url = os.getenv("WFORK_RELAY_URL", "http://host.docker.internal:8765")
    http = httpx.Client(timeout=5.0)
    return http, mo, relay_url, task_io


@app.cell
def _(mo):
    refresh = mo.ui.refresh(options=["10s", "30s"], default_interval="10s")
    refresh
    return (refresh,)


@app.cell
def _(http, refresh, relay_url, task_io):
    refresh.value
    # TODO(merge): headers через hub_io.auth_headers(hub_io.credential()) в wforkorg/notch
    tasks, refusal = task_io.list_tasks(http, relay_url, headers={})
    return refusal, tasks


@app.cell
def _(mo, refusal, task_io, tasks):
    if refusal:
        board = mo.callout(refusal, kind="warn")
    else:
        cols = task_io.columns(tasks)
        board = mo.hstack(
            [
                mo.vstack([mo.md(f"### {state} · {len(items)}"), *[mo.md(f"- **{t.title}** `{t.id}`") for t in items]])
                for state, items in cols.items()
                if items
            ]
        )
    mo.vstack([mo.md("## Доска задач"), board, mo.ui.table(task_io.rows(tasks), selection=None)])
    return (board,)


@app.cell
def _(mo):
    title = mo.ui.text(label="Новая задача")
    kind = mo.ui.dropdown(["func", "file", "shell", "note"], value="note", label="kind")
    submit = mo.ui.run_button(label="Предложить в хаб")
    mo.hstack([title, kind, submit])
    return kind, submit, title


@app.cell
def _(http, kind, mo, relay_url, submit, task_io, title):
    mo.stop(not submit.value or not title.value)
    t = task_io.Task(title=title.value, kind=kind.value, owner="human")
    t, err = task_io.propose(http, relay_url, headers={}, task=t)
    mo.callout(err or f"предложено: {t.id} ({t.state})", kind="warn" if err else "success")
    return


if __name__ == "__main__":
    app.run()
