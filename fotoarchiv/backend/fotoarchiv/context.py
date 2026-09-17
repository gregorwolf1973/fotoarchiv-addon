"""Alle Dienste des Add-ons an einer Stelle – geteilt vom Ingress- und vom Internetzugang."""

import logging
import shutil
import threading
from dataclasses import dataclass, field

from . import config
from .accesslog import AccessLog
from .auth import AuthService
from .db import Database
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
    limiter: Limiter
    access: AccessLog
    auth: AuthService
    _stop: threading.Event = field(default_factory=threading.Event)

    def start(self):
        settings = self.settings
        shutil.rmtree(settings.upload_tmp, ignore_errors=True)  # Reste abgebrochener Uploads
        for folder in (settings.library, settings.import_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.error("Ordner %s nicht anlegbar: %s", folder, exc)
        log.info("Bibliothek: %s | Import: %s | Papierkorb: %d Tage | Internetzugang: %s",
                 settings.library, settings.import_dir, settings.trash_days,
                 f"Port {settings.public_port}" if settings.public_enabled else "aus")
        threading.Thread(target=self._maintenance, daemon=True, name="wartung").start()
        self.faces.start()

    def stop(self):
        self.faces.stop()
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


def build(settings: config.Settings) -> Context:
    db = Database(settings.db_path)
    exiftool = ExifTool(settings.exiftool)
    importer = Importer(settings, db, exiftool)
    editor = Editor(settings, db, exiftool, importer)
    tasks = TaskRunner(on_progress=db.bump)
    faces = FaceService(settings, db, editor, enabled=settings.face_recognition)
    limiter = Limiter()
    access = AccessLog(settings.data / "public_access.log", settings.public_log_max_mb)
    if settings.public_log_export_path:
        access.set_export(settings.public_log_export_path, slot="export")
    auth = AuthService(db, limiter, access, settings.public_session_hours)
    return Context(settings, db, exiftool, importer, editor, tasks, faces, limiter, access, auth)
