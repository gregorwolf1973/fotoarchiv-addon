"""Hintergrundaufgaben (z. B. 500 Fotos ein Schlagwort geben, Person umbenennen).

Aufgaben stehen in der Datenbank und laufen nach einem Neustart oder Update weiter.
Gespeichert wird keine Funktion, sondern eine benannte Aktion mit Parametern; die Aktionen
meldet context.py beim Start an.

Vor jedem Foto wird es als "in Arbeit" vermerkt. Findet der Neustart so ein Foto, wird es
wiederholt – außer bei Aktionen, die man nicht doppelt ausführen darf (Drehen): Dann steht es
als "bitte prüfen" im Bericht.
"""

import json
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .db import Database
from .editor import EditError

log = logging.getLogger(__name__)

KEEP_FINISHED = 50
PROGRESS_EVERY = 25  # nach so vielen Fotos darf die Oberfläche neu laden
INTERRUPTED = "Durch einen Neustart unterbrochen – bitte prüfen"


@dataclass
class Action:
    factory: Callable[[dict], Callable[[int], None]]  # Parameter -> Funktion(asset_id)
    repeatable: bool = True       # darf ein unterbrochenes Foto erneut ausgeführt werden?
    tolerate_on_resume: bool = False  # Fehler beim Wiederholen ignorieren (z. B. "schon gelöscht")


class TaskRunner:
    def __init__(self, db: Database, on_progress: Callable[[], None]):
        self.db = db
        self._on_progress = on_progress
        self._actions: dict[str, Action] = {}
        self._queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None

    def register(self, kind: str, factory, *, repeatable: bool = True, tolerate_on_resume: bool = False):
        self._actions[kind] = Action(factory, repeatable, tolerate_on_resume)

    def start(self):
        """Arbeiter starten und unterbrochene Aufgaben wieder einreihen."""
        if self._thread:
            return
        for row in self.db.query("SELECT id FROM tasks WHERE running = 1 ORDER BY id"):
            self._queue.put(row["id"])
        self._thread = threading.Thread(target=self._work, daemon=True, name="tasks")
        self._thread.start()

    def submit(self, kind: str, label: str, asset_ids: list[int], params: dict | None = None) -> dict:
        if kind not in self._actions:
            raise ValueError(f"Unbekannte Aufgabe: {kind}")
        ids = list(dict.fromkeys(int(i) for i in asset_ids))
        task_id = self.db.execute(
            """INSERT INTO tasks (kind, label, params, asset_ids, total, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, label, json.dumps(params or {}), json.dumps(ids), len(ids),
             datetime.now().isoformat(timespec="seconds")),
        ).lastrowid
        self._queue.put(task_id)
        return self.get(task_id)

    @staticmethod
    def _public(row) -> dict:
        return {
            "id": row["id"], "kind": row["kind"], "label": row["label"], "total": row["total"],
            "done": row["done"], "failed": json.loads(row["failed"]), "running": bool(row["running"]),
            "started_at": row["started_at"], "finished_at": row["finished_at"],
        }

    def get(self, task_id: int) -> dict | None:
        row = self.db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._public(row) if row else None

    def list(self, limit: int = 20) -> list[dict]:
        rows = self.db.query("SELECT * FROM tasks ORDER BY running DESC, id DESC LIMIT ?", (limit,))
        return [self._public(r) for r in rows]

    def any_running(self) -> bool:
        return self.db.one("SELECT 1 FROM tasks WHERE running = 1 LIMIT 1") is not None

    # ── Arbeiter ───────────────────────────────────────────────────
    def _work(self):
        while True:
            task_id = self._queue.get()
            try:
                self.run(task_id)
            except Exception:
                log.exception("Aufgabe %s abgebrochen", task_id)

    def run(self, task_id: int):
        """Eine Aufgabe ab dem gespeicherten Stand abarbeiten."""
        row = self.db.one("SELECT * FROM tasks WHERE id = ? AND running = 1", (task_id,))
        if row is None:
            return
        action = self._actions.get(row["kind"])
        failed = json.loads(row["failed"])
        if action is None:
            failed.append({"id": None, "message": f"Unbekannte Aufgabe {row['kind']}"})
            self._finish(task_id, row["total"], failed)
            return
        execute = action.factory(json.loads(row["params"]))
        ids = json.loads(row["asset_ids"])
        done = row["done"]
        resumed = row["current"]

        if resumed is not None and not action.repeatable:
            failed.append({"id": resumed, "message": INTERRUPTED})
            done += 1
            self.db.execute("UPDATE tasks SET done = ?, failed = ?, current = NULL WHERE id = ?",
                            (done, json.dumps(failed), task_id))
            resumed = None

        for index in range(done, len(ids)):
            asset_id = ids[index]
            self.db.execute("UPDATE tasks SET current = ? WHERE id = ?", (asset_id, task_id))
            try:
                execute(asset_id)
            except EditError as exc:
                if not (action.tolerate_on_resume and asset_id == resumed):
                    failed.append({"id": asset_id, "message": str(exc)})
            except Exception as exc:
                log.exception("Aufgabe %r: Foto %s fehlgeschlagen", row["label"], asset_id)
                failed.append({"id": asset_id, "message": f"Interner Fehler: {exc}"})
            self.db.execute("UPDATE tasks SET done = ?, failed = ?, current = NULL WHERE id = ?",
                            (index + 1, json.dumps(failed), task_id))
            if (index + 1) % PROGRESS_EVERY == 0:
                self._on_progress()
        self._finish(task_id, len(ids), failed)

    def _finish(self, task_id: int, done: int, failed: list):
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE tasks SET running = 0, done = ?, failed = ?, current = NULL, finished_at = ? WHERE id = ?",
                (done, json.dumps(failed), datetime.now().isoformat(timespec="seconds"), task_id),
            )
            conn.execute(
                """DELETE FROM tasks WHERE running = 0 AND id NOT IN
                   (SELECT id FROM tasks WHERE running = 0 ORDER BY id DESC LIMIT ?)""", (KEEP_FINISHED,))
        self._on_progress()
