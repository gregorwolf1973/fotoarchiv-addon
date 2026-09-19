"""Alle Dienste des Add-ons an einer Stelle – geteilt vom Ingress- und vom Internetzugang."""

import logging
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime

from . import config
from .autoimport import AutoImport
from .convert import ConvertService
from .accesslog import AccessLog
from .auth import AuthService
from .db import Database
from .duplicates import DuplicateService
from .editor import Editor
from .exiftool import ExifTool
from .faces import FaceService
from .importer import Importer
from .ratelimit import Limiter
from .tasks import TaskRunner

log = logging.getLogger(__name__)

MAINTENANCE_INTERVAL = 3600


@dataclass
class Context:
    settings: config.Settings
    db: Database
    exiftool: ExifTool
    importer: Importer
    editor: Editor
    tasks: TaskRunner
    faces: FaceService
    duplicates: DuplicateService
    converter: ConvertService
    limiter: Limiter
    access: AccessLog
    auth: AuthService
    auto_import: AutoImport
    _stop: threading.Event = field(default_factory=threading.Event)

    def start(self):
        settings = self.settings
        shutil.rmtree(settings.upload_tmp, ignore_errors=True)  # Reste abgebrochener Uploads
        for folder in (settings.library, settings.import_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.error("Ordner %s nicht anlegbar: %s", folder, exc)
        log.info("Bibliothek: %s | Import: %s%s | Papierkorb: %d Tage | Internetzugang: %s",
                 settings.library, settings.import_dir, " (automatisch)" if settings.auto_import else "",
                 settings.trash_days, f"Port {settings.public_port}" if settings.public_enabled else "aus")
        threading.Thread(target=self._maintenance, daemon=True, name="wartung").start()
        self.tasks.start()  # setzt auch Aufgaben fort, die ein Neustart unterbrochen hat
        self.faces.start()
        self.duplicates.start()
        self.converter.start()
        self.auto_import.start()

    def stop(self):
        self.auto_import.stop()
        self.faces.stop()
        self.duplicates.stop()
        self.converter.stop()
        self._stop.set()
        self.exiftool.close()
        self.db.close()

    def _maintenance(self):
        while not self._stop.is_set():
            try:
                self.editor.purge_expired(self.settings.trash_days)
                self.auth.cleanup()
            except Exception:
                log.exception("Wartung fehlgeschlagen")
            self._stop.wait(MAINTENANCE_INTERVAL)


def register_task_actions(tasks: TaskRunner, editor: Editor, faces: FaceService, duplicates: DuplicateService,
                          converter: ConvertService):
    """Alle Aktionen, die als Hintergrundaufgabe laufen (und nach einem Neustart weiterlaufen) können."""
    tasks.register("labels", lambda p: lambda i: editor.change_labels(i, p["kind"], p["add"], p["remove"]))
    tasks.register("date", lambda p: lambda i: editor.set_date(i, datetime.fromisoformat(p["taken_at"])))
    tasks.register("location", lambda p: lambda i: editor.set_location(i, p["lat"], p["lon"]))
    tasks.register("rotate", lambda p: lambda i: editor.rotate(i, p["degrees"]), repeatable=False)
    # Beim Wiederholen nach Neustart ist das Foto womöglich schon gelöscht/wiederhergestellt – kein Fehler
    tasks.register("delete", lambda p: editor.delete, tolerate_on_resume=True)
    tasks.register("restore", lambda p: editor.restore, tolerate_on_resume=True)
    tasks.register("purge", lambda p: editor.purge, tolerate_on_resume=True)
    tasks.register("forget", lambda p: editor.forget, tolerate_on_resume=True)
    tasks.register("persons_relabel", lambda p: lambda i: faces.relabel(i, p["add"], p["remove"]))
    tasks.register("dedupe", lambda p: lambda i: duplicates.resolve_one(i, p["keep_for"][str(i)], p["transfer"]),
                   tolerate_on_resume=True)
    tasks.register("convert", lambda p: converter.request, tolerate_on_resume=True)


def build(settings: config.Settings) -> Context:
    db = Database(settings.db_path)
    exiftool = ExifTool(settings.exiftool)
    importer = Importer(settings, db, exiftool)
    editor = Editor(settings, db, exiftool, importer)
    tasks = TaskRunner(db, on_progress=db.bump)
    faces = FaceService(settings, db, editor, enabled=settings.face_recognition)
    duplicates = DuplicateService(settings, db, importer, editor, enabled=settings.duplicate_detection)
    converter = ConvertService(settings, db, importer, editor, on_import=settings.convert_on_import)
    register_task_actions(tasks, editor, faces, duplicates, converter)
    limiter = Limiter()
    access = AccessLog(settings.data / "public_access.log", settings.public_log_max_mb)
    if settings.public_log_export_path:
        access.set_export(settings.public_log_export_path, slot="export")
    auth = AuthService(db, limiter, access, settings.public_session_hours)
    auto_import = AutoImport(settings, importer, on_done=faces.wake, enabled=settings.auto_import)
    return Context(settings, db, exiftool, importer, editor, tasks, faces, duplicates, converter, limiter, access, auth,
                   auto_import)
