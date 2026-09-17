"""Hintergrundaufgaben überstehen einen Neustart."""

import json

import pytest

from fotoarchiv.db import Database
from fotoarchiv.editor import EditError
from fotoarchiv.tasks import INTERRUPTED, TaskRunner


@pytest.fixture
def db(settings):
    database = Database(settings.db_path)
    yield database
    database.close()


def runner_with(db, calls, *, fail_on=(), **options):
    runner = TaskRunner(db, on_progress=lambda: None)

    def factory(params):
        def act(asset_id):
            calls.append((params["tag"], asset_id))
            if asset_id in fail_on:
                raise EditError(f"geht nicht: {asset_id}")
        return act

    runner.register("demo", factory, **options)
    return runner


def crash_during(db, task_id, finished: int, current: int | None):
    """Zustand nachbauen, als wäre der Container mitten in der Aufgabe beendet worden."""
    db.execute("UPDATE tasks SET done = ?, current = ? WHERE id = ?", (finished, current, task_id))


def test_resumes_after_restart_and_repeats_interrupted_photo(db):
    task = runner_with(db, []).submit("demo", "Test", [5, 6, 7, 6], {"tag": "Urlaub"})
    assert (task["total"], task["running"]) == (3, True)  # doppelte IDs nur einmal
    crash_during(db, task["id"], finished=1, current=6)

    calls = []
    restarted = runner_with(db, calls)
    restarted.run(task["id"])  # das macht start() im Hintergrund
    assert calls == [("Urlaub", 6), ("Urlaub", 7)]
    done = restarted.get(task["id"])
    assert (done["done"], done["running"], done["failed"]) == (3, False, [])
    assert not restarted.any_running()


def test_start_queues_unfinished_tasks(db):
    first = runner_with(db, [])
    open_task = first.submit("demo", "offen", [1], {"tag": "a"})
    calls = []
    restarted = runner_with(db, calls)
    restarted.start()
    for _ in range(200):
        if not restarted.any_running():
            break
        import time
        time.sleep(0.01)
    assert calls == [("a", 1)] and restarted.get(open_task["id"])["done"] == 1


def test_not_repeatable_action_reports_interrupted_photo(db):
    task = runner_with(db, [], repeatable=False).submit("demo", "Drehen", [1, 2, 3], {"tag": "x"})
    crash_during(db, task["id"], finished=1, current=2)

    calls = []
    restarted = runner_with(db, calls, repeatable=False)
    restarted.run(task["id"])
    assert calls == [("x", 3)]  # Foto 2 nicht doppelt gedreht
    assert restarted.get(task["id"])["failed"] == [{"id": 2, "message": INTERRUPTED}]


def test_tolerated_errors_only_for_resumed_photo(db):
    task = runner_with(db, [], tolerate_on_resume=True).submit("demo", "Löschen", [1, 2], {"tag": "x"})
    crash_during(db, task["id"], finished=0, current=1)

    restarted = runner_with(db, [], fail_on={1, 2}, tolerate_on_resume=True)
    restarted.run(task["id"])
    assert [f["id"] for f in restarted.get(task["id"])["failed"]] == [2]


def test_unknown_kind_and_listing(db):
    runner = runner_with(db, [])
    with pytest.raises(ValueError):
        runner.submit("gibtsnicht", "x", [1])
    runner.submit("demo", "eins", [1], {"tag": "a"})
    row = db.one("SELECT params, asset_ids FROM tasks")
    assert json.loads(row["params"]) == {"tag": "a"} and json.loads(row["asset_ids"]) == [1]
    assert [t["label"] for t in runner.list()] == ["eins"]
