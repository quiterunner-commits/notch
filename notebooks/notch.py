import marimo

__generated_with = "0.10.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from notch import Task, registry, run_shell
    registry.clear()
    return Task, mo, registry, run_shell


@app.cell
def _(Task):
    config = Task(
        id="config",
        title="Конфигурация окружения",
        status="done",
        priority=1,
        kind="func",
        owner="human",
        comments=["пока только имя хоста; секреты не в ноутбуке"],
    )
    config.run(lambda: {"host": "vps.local"})
    return (config,)


@app.cell
def _(Task, config):
    compare = Task(
        id="compare-notebooks",
        title="Сравнить marimo и Jupyter (docs/marimo-vs-jupyter.md)",
        status="done",
        priority=1,
        kind="file",
        owner="agent",
        depends_on=["config"],
        comments=["вывод: marimo DAG = бесплатные зависимости между задачами"],
    )
    compare.run()
    return (compare,)


@app.cell
def _(Task, config, run_shell):
    hello = Task(
        id="hello-shell",
        title="Проверить запуск shell-задачи",
        priority=2,
        kind="shell",
        owner="agent",
        depends_on=["config"],
    )
    hello.run(lambda: run_shell(f"echo hello from {config.result.output['host']}"))
    return (hello,)


@app.cell
def _(Task):
    deploy = Task(
        id="deploy",
        title="Ноутбук как источник деплоя",
        status="todo",
        priority=3,
        kind="note",
        owner="human",
        comments=["после того как формат задачи устоится"],
    )
    deploy.run()
    return (deploy,)


@app.cell
def _(mo, registry, compare, config, deploy, hello):
    board = mo.ui.table(registry.rows(), selection=None)
    mo.vstack([mo.md("## Доска задач"), board])
    return (board,)


if __name__ == "__main__":
    app.run()
