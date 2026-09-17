"""Hintergrundaufgaben für Mehrfachauswahl (z. B. 500 Bildern ein Schlagwort geben)."""

import itertools
import logging
import queue
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from .editor import EditError

log = logging.getLogger(__name__)

KEEP_FINISHED = 20
PROGRESS_EVERY = 25  # nach so vielen Bildern darf die Oberfläche neu laden


@dataclass
class Task:
    id: int
    label: str
    total: int
    done: int = 0
    failed: list = field(default_factory=list)
    running: bool = True
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    finished_at: str | None = None


class TaskRunner:
    def __init__(self, on_progress: Callable[[], None]):
        self._on_progress = on_progress
        self._queue: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._tasks: deque[Task] = deque(maxlen=KEEP_FINISHED)
        self._lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True, name="tasks").start()

    def submit(self, label: str, asset_ids: list[int], action: Callable[[int], None]) -> Task:
        task = Task(id=next(self._ids), label=label, total=len(asset_ids))
        with self._lock:
            self._tasks.append(task)
        self._queue.put((task, list(dict.fromkeys(asset_ids)), action))
        return task

    def list(self) -> list[Task]:
        with self._lock:
            return list(reversed(self._tasks))

    def _work(self):
        while True:
            task, asset_ids, action = self._queue.get()
            task.total = len(asset_ids)
            for asset_id in asset_ids:
                try:
                    action(asset_id)
                except EditError as exc:
                    task.failed.append({"id": asset_id, "message": str(exc)})
                except Exception as exc:
                    log.exception("Aufgabe %r: Bild %s fehlgeschlagen", task.label, asset_id)
                    task.failed.append({"id": asset_id, "message": f"Interner Fehler: {exc}"})
                task.done += 1
                if task.done % PROGRESS_EVERY == 0:
                    self._on_progress()
            task.running = False
            task.finished_at = datetime.now().isoformat(timespec="seconds")
            self._on_progress()
