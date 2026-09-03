from notch import Task, registry
from notch.export import to_issues


def setup_function():
    registry.clear()


def test_run_success_sets_done():
    t = Task(id="a", title="A")
    r = t.run(lambda: 42)
    assert r.ok and r.output == 42 and t.status == "done"


def test_run_failure_sets_blocked():
    t = Task(id="b", title="B")
    r = t.run(lambda: 1 / 0)
    assert not r.ok and t.status == "blocked"


def test_note_needs_no_body():
    t = Task(id="n", title="N", kind="note", status="todo")
    assert t.run().ok and t.status == "todo"


def test_registry_orders_by_priority():
    Task(id="low", title="L", priority=5)
    Task(id="high", title="H", priority=1)
    assert [t.id for t in registry.all()] == ["high", "low"]


def test_export_to_issues():
    Task(id="x", title="X", status="done", comments=["c1"])
    issues = to_issues()
    assert issues[0]["state"] == "closed"
    assert "status:done" in issues[0]["labels"]
    assert "- c1" in issues[0]["body"]
