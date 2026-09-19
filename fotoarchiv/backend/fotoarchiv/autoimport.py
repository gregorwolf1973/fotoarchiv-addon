"""Automatischer Import: den Import-Ordner regelmäßig prüfen und neue, fertig kopierte Dateien einlesen.

Gedacht für Handys, die per Sync-App (FolderSync, PhotoSync) im WLAN in den Samba-Ordner hochladen.
Das geht nur in eine Richtung: Das Fotoarchiv schreibt nie aufs Handy zurück, und Löschen auf dem
Handy ändert nichts im Archiv.
"""

import logging
import threading

from .config import Settings
from .importer import Importer

log = logging.getLogger(__name__)

INTERVAL = 60  # s zwischen zwei Blicken in den Import-Ordner


class AutoImport:
    def __init__(self, settings: Settings, importer: Importer, on_done=None, *, enabled: bool = False):
        self.settings = settings
        self.importer = importer
        self.on_done = on_done
        self.enabled = enabled
        # Schon versuchte Dateien mit (Größe, Änderungszeit). Was liegen bleibt (etwa ein Fehler), stößt
        # sonst jede Minute einen neuen Import an; erst eine geänderte Datei wird erneut versucht.
        self._tried: dict[str, tuple[int, float]] = {}
        self._stop = threading.Event()

    def start(self):
        if self.enabled:
            log.info("Automatischer Import aktiv: %s wird jede Minute geprüft", self.settings.import_dir)
            threading.Thread(target=self._run, daemon=True, name="auto-import").start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.check()
            except Exception:
                log.exception("Automatischer Import fehlgeschlagen")
            self._stop.wait(INTERVAL)

    def check(self) -> bool:
        """Import starten, wenn neue Dateien fertig kopiert sind. True, wenn einer gestartet wurde."""
        if self.importer.job.running:
            return False  # läuft schon (auch ein Abgleich); beim nächsten Blick sind die Dateien dran
        ready = self.importer.ready_files()
        new = [rel for rel, signature in ready.items() if self._tried.get(rel) != signature]
        if not new:
            return False
        if not self.importer.start("import", on_done=self.on_done, auto=True):
            return False
        log.info("Automatischer Import: %d neue Datei(en)", len(new))
        self._tried = ready  # verschwundene Dateien vergessen
        return True
