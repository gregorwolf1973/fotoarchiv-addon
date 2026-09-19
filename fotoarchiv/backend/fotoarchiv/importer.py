"""Import aus dem Samba-Ordner, per Upload oder durch Einlesen der vorhandenen Bibliothek."""

import errno
import json
import logging
import os
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import labels, media, metadata
from .config import Settings
from .db import NEXT_ASSET_ID, Database
from .exiftool import ExifTool

log = logging.getLogger(__name__)

DUPLICATE_DIR = "_duplikate"
DAMAGED_DIR = "_defekt"  # beschädigte Dateien aus dem Import-Ordner
IGNORED_NAMES = {"@eaDir", "#recycle", "Thumbs.db", "desktop.ini"}
REPORT_LIMIT = 500  # Einträge pro Liste im Bericht
DATE_RANK = {"mtime": 0, "filename": 1, "exif": 2}  # wie verlässlich die Datumsquelle ist
RETRY_FAILED = 3600  # s: gescheiterte Vorschaubilder nicht bei jedem Scrollen neu berechnen


@dataclass
class Result:
    status: str                  # imported | relinked | duplicate | damaged | changed | skipped | error
    name: str
    message: str = ""
    asset_id: int | None = None
    existing: str | None = None  # Duplikat: Pfad des vorhandenen Bildes; wieder zugeordnet: bisheriger Pfad
    similar: str | None = None   # neu importiert, aber sehr ähnlich zu diesem vorhandenen Foto


@dataclass
class Job:
    mode: str = ""               # import | library
    deep: bool = False           # Abgleich mit gründlicher Prüfung jeder Datei
    auto: bool = False           # automatischer Import (Handy-Sync): Duplikate werden gelöscht statt verschoben
    cancelled: bool = False
    running: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    total: int = 0
    done: int = 0
    current: str = ""
    counts: dict = field(default_factory=lambda: {
        "imported": 0, "relinked": 0, "duplicate": 0, "damaged": 0, "skipped": 0, "error": 0, "missing": 0,
        "similar": 0, "checked": 0, "changed": 0})
    similar: list = field(default_factory=list)   # neu, aber einem vorhandenen Foto sehr ähnlich
    relinked: list = field(default_factory=list)
    missing: list = field(default_factory=list)   # Einträge, deren Datei fehlt (nur beim Abgleich)
    duplicates: list = field(default_factory=list)
    damaged: list = field(default_factory=list)    # beschädigt (Import: liegen in _defekt)
    changed: list = field(default_factory=list)    # gründliche Prüfung: Inhalt außerhalb geändert
    errors: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name)
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = stem.strip(" .")[:150] or "bild"
    return f"{stem}.{ext.lower()}" if ext else stem


def unique_path(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        n += 1
    return candidate


def move_file(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, target)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        # Anderes Dateisystem (in Home Assistant schon /share → /media): kopieren und löschen.
        # Schreibt noch jemand an der Quelle (Samba-Kopie läuft), wäre die Kopie nur ein halber Stand –
        # und das Löschen danach nähme das Original mit. Darum vorher vergleichen.
        before = source.stat()
        shutil.copy2(source, target)
        after = source.stat()
        changed = (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns)
        if changed or target.stat().st_size != after.st_size:
            target.unlink(missing_ok=True)
            raise OSError(errno.EBUSY, "Datei hat sich während des Kopierens geändert – wird wohl noch geschrieben")
        source.unlink()


def remove_empty_dirs(root: Path):
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if directory.name in (DUPLICATE_DIR, DAMAGED_DIR):
            continue
        try:
            directory.rmdir()  # klappt nur, wenn leer
        except OSError:
            pass


class Importer:
    def __init__(self, settings: Settings, db: Database, exiftool: ExifTool):
        self.settings = settings
        self.db = db
        self.exiftool = exiftool
        self.job = Job()
        # Rückmeldungen: "imported" -> Funktion(asset_id), darf den Pfad eines ähnlichen Fotos liefern
        self.hooks: dict[str, list] = {"imported": []}
        self.ffprobe = media.ffprobe_for(settings.ffmpeg)
        self._file_lock = threading.Lock()  # immer nur eine Datei gleichzeitig (Duplikatprüfung)
        self._job_lock = threading.Lock()
        self._cancel = threading.Event()
        # (Variante, asset_id) -> (rev, Zeitpunkt): gescheiterte Vorschaubilder. Eine neue Revision
        # (Datei bearbeitet oder ersetzt) oder eine Stunde Abstand erlaubt einen neuen Versuch.
        self._failed: dict[tuple[str, int], tuple[int, float]] = {}
        self._report_path = settings.data / "letzter_import.json"
        try:
            self.job = Job(**json.loads(self._report_path.read_text(encoding="utf-8")))
            self.job.running = False
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            pass

    # ── einzelne Datei ─────────────────────────────────────────────
    def import_file(self, source: Path, *, name: str | None = None, move: bool = True, mtime: float | None = None) -> Result:
        """Datei prüfen, einsortieren und eintragen. move=False: Datei liegt schon in der Bibliothek."""
        name = name or source.name
        kind = media.kind_of(Path(name))
        if kind is None:
            return Result("skipped", name, "Dateityp wird nicht unterstützt")

        with self._file_lock:
            try:
                stat = source.stat()
                checksum = media.md5_file(source)
            except OSError as exc:
                return Result("error", name, f"Datei nicht lesbar: {exc}")

            existing = self.db.one(
                """SELECT id, path, deleted_at, taken_at, date_source, tz_offset FROM assets
                   WHERE md5 = ? OR md5_import = ? LIMIT 1""",
                (checksum, checksum),
            )
            if existing and (existing["deleted_at"] or (self.settings.library / existing["path"]).is_file()):
                where = "im Papierkorb" if existing["deleted_at"] else "bereits im Archiv"
                return Result("duplicate", name, where, existing["id"], existing["path"])

            if move:
                # Halbe Dateien (abgebrochen kopiert oder hochgeladen) gar nicht erst ins Archiv lassen.
                # Erst nach der Duplikatprüfung: bei großen Importen mit vielen Duplikaten spart das
                # je Video einen ffprobe-Lauf. Beim Abgleich (move=False) werden sie aufgenommen.
                problem = media.damage(source, kind, self.ffprobe)
                if problem:
                    return Result("damaged", name, problem)

            try:
                raw = self.exiftool.read(source)
            except Exception as exc:  # Metadaten sind nicht zwingend
                log.warning("Metadaten von %s nicht lesbar: %s", name, exc)
                raw = {}
            meta = metadata.extract(raw, Path(name), self.settings.timezone, mtime or stat.st_mtime)

            if move:
                folder = self.settings.library / f"{meta.taken:%Y}" / f"{meta.taken:%m}"
                target = unique_path(folder / safe_name(name))
                try:
                    move_file(source, target)
                    if mtime:
                        os.utime(target, (mtime, mtime))
                except OSError as exc:
                    return Result("error", name, f"Verschieben fehlgeschlagen: {exc}")
            else:
                target = source

            rel = target.relative_to(self.settings.library).as_posix()
            try:
                if existing:
                    # Datei des Eintrags fehlt (von Hand gelöscht oder verschoben): Eintrag übernimmt diese Datei.
                    # Ein umbenanntes Foto ohne EXIF verliert sonst sein Datum aus dem alten Dateinamen.
                    if DATE_RANK.get(meta.date_source, 0) < DATE_RANK.get(existing["date_source"], 0):
                        meta.taken = datetime.fromisoformat(existing["taken_at"])
                        meta.date_source, meta.tz_offset = existing["date_source"], existing["tz_offset"]
                    asset_id = existing["id"]
                    self._relink(asset_id, rel, stat.st_size, checksum, meta)
                else:
                    asset_id = self._insert(rel, kind, stat.st_size, checksum, meta)
            except Exception as exc:
                if move:
                    move_file(target, source)
                log.exception("Eintragen von %s fehlgeschlagen", name)
                return Result("error", name, f"Datenbankfehler: {exc}")

        if existing:
            self.drop_cache(asset_id)
            self.ensure_thumbnail(asset_id)
            self.db.bump()
            return Result("relinked", name, f"Eintrag wieder zugeordnet (vorher {existing['path']})", asset_id, existing["path"])
        self.ensure_thumbnail(asset_id)
        similar = None
        for hook in self.hooks["imported"]:
            try:
                similar = hook(asset_id) or similar
            except Exception:
                log.exception("Rückmeldung nach Import von %s fehlgeschlagen", name)
        self.db.bump()
        return Result("imported", name, rel, asset_id, similar=similar)

    def _relink(self, asset_id: int, rel: str, size: int, checksum: str, meta: metadata.Metadata):
        """Vorhandenen Eintrag auf eine neue Datei zeigen lassen; ID, Import-Prüfsumme und Import-Datum bleiben."""
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE assets SET path = ?, size = ?, md5 = ?, taken_at = ?, taken_ts = ?, date_source = ?,
                       tz_offset = ?, width = ?, height = ?, duration = ?, lat = ?, lon = ?, camera = ?,
                       rev = rev + 1, thumb_ok = 0, phash = NULL, damaged = NULL
                   WHERE id = ?""",
                (rel, size, checksum, meta.taken.isoformat(), meta.taken_ts, meta.date_source, meta.tz_offset,
                 meta.width, meta.height, meta.duration, meta.lat, meta.lon, meta.camera, asset_id),
            )
            labels.replace(conn, asset_id, "tags", meta.tags)
            labels.replace(conn, asset_id, "persons", meta.persons)
            labels.remove_unused(conn)

    def _insert(self, rel: str, kind: str, size: int, checksum: str, meta: metadata.Metadata) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
f"""INSERT INTO assets (id, path, kind, mime, size, md5, md5_import, taken_at, taken_ts,
                       date_source, tz_offset, width, height, duration, lat, lon, camera, imported_at)
                   VALUES (({NEXT_ASSET_ID}), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rel, kind, meta.mime or media.mime_of(Path(rel)), size, checksum, checksum,
                 meta.taken.isoformat(), meta.taken_ts, meta.date_source, meta.tz_offset,
                 meta.width, meta.height, meta.duration, meta.lat, meta.lon, meta.camera,
                 datetime.now().isoformat(timespec="seconds")),
            )
            asset_id = cur.lastrowid
            labels.replace(conn, asset_id, "tags", meta.tags)
            labels.replace(conn, asset_id, "persons", meta.persons)
        return asset_id

    # ── Vorschaubilder ─────────────────────────────────────────────
    def cache_file(self, asset_id: int, variant: str) -> Path:
        return self.settings.cache / variant / f"{asset_id // 1000:04d}" / f"{asset_id}.webp"

    def drop_cache(self, asset_id: int):
        for variant in ("thumb", "small", "preview"):
            self.cache_file(asset_id, variant).unlink(missing_ok=True)

    def _recently_failed(self, variant: str, asset_id: int, rev: int) -> bool:
        entry = self._failed.get((variant, asset_id))
        return entry is not None and entry[0] == rev and time.monotonic() - entry[1] < RETRY_FAILED

    def _set_failed(self, variant: str, asset_id: int, rev: int, failed: bool):
        if failed:
            self._failed[(variant, asset_id)] = (rev, time.monotonic())
        else:
            self._failed.pop((variant, asset_id), None)

    def ensure_thumbnail(self, asset_id: int) -> Path | None:
        row = self.db.one("SELECT path, kind, width, height, thumb_ok, rev FROM assets WHERE id = ?", (asset_id,))
        if row is None:
            return None
        target = self.cache_file(asset_id, "thumb")
        if row["thumb_ok"] and target.exists():
            return target
        if self._recently_failed("thumb", asset_id, row["rev"]):
            return None
        try:
            tw, th = media.thumbnail(self.settings.library / row["path"], row["kind"], self.settings.ffmpeg, target)
        except Exception as exc:
            log.warning("Vorschaubild für %s fehlgeschlagen: %s", row["path"], exc)
            self._set_failed("thumb", asset_id, row["rev"], True)
            self.db.execute("UPDATE assets SET thumb_ok = -1 WHERE id = ?", (asset_id,))
            return None
        self._set_failed("thumb", asset_id, row["rev"], False)
        # Die Ausrichtung des Vorschaubilds ist maßgeblich, auch wenn die Metadaten etwas anderes sagen
        w, h = row["width"] or tw, row["height"] or th
        if (w > h) != (tw > th) and w != h and tw != th:
            w, h = h, w
        self.db.execute("UPDATE assets SET thumb_ok = 1, width = ?, height = ? WHERE id = ?", (w, h, asset_id))
        return target

    def ensure_preview(self, asset_id: int) -> Path | None:
        row = self.db.one("SELECT path, kind, rev FROM assets WHERE id = ?", (asset_id,))
        if row is None:
            return None
        target = self.cache_file(asset_id, "preview")
        if not target.exists():
            if self._recently_failed("preview", asset_id, row["rev"]):
                return None
            try:
                media.preview(self.settings.library / row["path"], row["kind"], self.settings.ffmpeg, target)
            except Exception as exc:
                log.warning("Großansicht für %s fehlgeschlagen: %s", row["path"], exc)
                self._set_failed("preview", asset_id, row["rev"], True)
                return None
            self._set_failed("preview", asset_id, row["rev"], False)
        return target

    def ensure_small(self, asset_id: int) -> Path | None:
        target = self.cache_file(asset_id, "small")
        if target.exists():
            return target
        thumb = self.ensure_thumbnail(asset_id)
        if thumb is None:
            return None
        try:
            media.small(thumb, target)
        except Exception as exc:
            log.warning("Kleines Vorschaubild für %s fehlgeschlagen: %s", asset_id, exc)
            return thumb  # lieber groß als gar nichts
        return target

    # ── Abgleich mit dem Datenträger ───────────────────────────────
    def missing_assets(self) -> list:
        """Einträge (auch im Papierkorb), deren Datei nicht mehr auf dem Datenträger liegt."""
        rows = self.db.query("SELECT id, path, deleted_at FROM assets ORDER BY path")
        return [row for row in rows if not (self.settings.library / row["path"]).is_file()]

    def library_reachable(self) -> bool:
        """Schutz vor einem nicht eingebundenen Laufwerk: leere Bibliothek gilt als nicht erreichbar."""
        root = self.settings.library
        return root.is_dir() and any(p.is_file() for p in root.rglob("*"))

    # ── Upload ─────────────────────────────────────────────────────
    def import_upload(self, temp: Path, name: str, mtime: float | None) -> Result:
        try:
            return self.import_file(temp, name=name, mtime=mtime)
        finally:
            temp.unlink(missing_ok=True)  # Duplikate und Fehler nicht liegen lassen

    # ── Hintergrund-Job ────────────────────────────────────────────
    def start(self, mode: str, on_done=None, *, deep: bool = False, auto: bool = False) -> bool:
        deep = deep and mode == "library"
        auto = auto and mode == "import"
        with self._job_lock:
            if self.job.running:
                return False
            self._cancel.clear()
            self.job = Job(mode=mode, deep=deep, auto=auto, running=True,
                           started_at=datetime.now().isoformat(timespec="seconds"))

        def run():
            self._run(mode, deep=deep, auto=auto)
            if on_done:
                on_done()

        threading.Thread(target=run, daemon=True, name=f"import-{mode}").start()
        return True

    def _scan(self, mode: str, *, progress: bool = True) -> list[Path]:
        root = self.settings.import_dir if mode == "import" else self.settings.library
        if not root.is_dir():
            return []
        known = set()
        if mode == "library":
            known = {row["path"] for row in self.db.query("SELECT path FROM assets")}
        # Ausgeschlossene Ordner gar nicht erst betreten: _duplikate wächst bei großen Importen
        # auf Hunderttausende Dateien, und jeder weitere Import müsste sie sonst erneut durchlaufen
        skip_top = {DUPLICATE_DIR, DAMAGED_DIR} if mode == "import" else set()
        files: list[Path] = []
        stack = [root]
        reported = 0
        while stack:
            folder = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError as exc:
                log.warning("Ordner %s nicht lesbar: %s", folder, exc)
                continue
            for entry in entries:
                if entry.name.startswith(".") or entry.name in IGNORED_NAMES:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not (folder == root and entry.name in skip_top):
                        stack.append(Path(entry.path))
                elif entry.is_file():  # nutzt den Dateityp aus dem Verzeichnis, kein eigener stat
                    path = Path(entry.path)
                    if path.relative_to(root).as_posix() not in known:
                        files.append(path)
            if progress and len(files) - reported >= 1000:
                reported = len(files)
                self.job.current = f"Dateien suchen … {reported:,} gefunden".replace(",", ".")
        files.sort()
        return files

    def ready_files(self) -> dict[str, tuple[int, float]]:
        """Unterstützte, fertig kopierte Dateien im Import-Ordner mit (Größe, Änderungszeit) – für den
        automatischen Import. Dateien, die gerade noch übertragen werden, fehlen hier."""
        root = self.settings.import_dir
        ready = {}
        for path in self._scan("import", progress=False):
            if media.kind_of(path) is None:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue  # inzwischen verschoben oder gelöscht
            if time.time() - stat.st_mtime >= self.settings.import_quiet_seconds:
                ready[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime)
        return ready

    def _recently_written(self, path: Path) -> bool:
        """Beim Kopieren per Samba ändert sich die Datei laufend; Windows setzt das alte Datum erst am Ende."""
        return time.time() - path.stat().st_mtime < self.settings.import_quiet_seconds

    def cancel(self) -> bool:
        """Laufenden Import bzw. Abgleich nach der aktuellen Datei beenden."""
        if not self.job.running:
            return False
        self._cancel.set()
        return True

    def _check_files(self):
        """Gründliche Prüfung: jede Datei ganz lesen und mit der gespeicherten Prüfsumme vergleichen.
        Findet, was beim Import noch nicht auffiel oder später auf dem Datenträger kaputtging."""
        job = self.job
        rows = self.db.query("SELECT id, path, kind, md5 FROM assets WHERE deleted_at IS NULL ORDER BY id")
        job.total += len(rows)
        for row in rows:
            if self._cancel.is_set():
                job.cancelled = True
                return
            path = self.settings.library / row["path"]
            job.current = f"Prüfe {row['path']}"
            if path.is_file():  # fehlende Dateien meldet schon der Abgleich
                try:
                    problem = media.deep_damage(path, row["kind"], self.ffprobe)
                    checksum = media.md5_file(path)
                except OSError as exc:
                    problem, checksum = f"Datei nicht lesbar: {exc}", row["md5"]
                self.db.execute("UPDATE assets SET damaged = ? WHERE id = ?", (problem, row["id"]))
                if problem:
                    self._record(Result("damaged", row["path"], problem, row["id"]), row["path"])
                if checksum != row["md5"]:
                    # Einmal melden und merken, sonst meldet jede Prüfung eine gewollte Bearbeitung erneut
                    self.db.execute("UPDATE assets SET md5 = ?, size = ? WHERE id = ?",
                                    (checksum, path.stat().st_size, row["id"]))
                    self._record(Result("changed", row["path"], "Inhalt wurde außerhalb des Fotoarchivs geändert",
                                        row["id"]), row["path"])
                job.counts["checked"] = job.counts.get("checked", 0) + 1
            job.done += 1

    def _record(self, result: Result, rel: str):
        job = self.job
        job.counts[result.status] = job.counts.get(result.status, 0) + 1
        if result.similar:
            job.counts["similar"] = job.counts.get("similar", 0) + 1
            if len(job.similar) < REPORT_LIMIT:
                job.similar.append({"name": rel, "existing": result.similar})
        bucket = {"duplicate": job.duplicates, "damaged": job.damaged, "changed": job.changed, "error": job.errors,
                  "skipped": job.skipped, "relinked": job.relinked}.get(result.status)
        if bucket is not None and len(bucket) < REPORT_LIMIT:
            entry = {"name": rel, "message": result.message}
            if result.existing:
                entry["existing"] = result.existing
            bucket.append(entry)

    def _run(self, mode: str, *, deep: bool = False, auto: bool = False):
        job = self.job
        try:
            files = self._scan(mode)
            sizes = {path: path.stat().st_size for path in files}
            job.total = len(files)
            root = self.settings.import_dir if mode == "import" else self.settings.library
            for path in files:
                rel = path.relative_to(root).as_posix()
                job.current = rel
                try:
                    if not path.exists():
                        result = Result("skipped", rel, "Datei ist verschwunden")
                    elif path.stat().st_size != sizes[path] or self._recently_written(path):
                        result = Result("skipped", rel, "Datei wird noch kopiert – beim nächsten Import dabei")
                    else:
                        result = self.import_file(path, move=(mode == "import"))
                    if result.status == "duplicate" and mode == "import" and auto:
                        # Byte-gleiche Kopie (MD5) von etwas, das schon im Archiv oder im Papierkorb liegt.
                        # Beim Handy-Sync kommt das ständig vor; in _duplikate würde es sich nur sammeln.
                        path.unlink()
                        result.message += " – Kopie gelöscht"
                    elif result.status == "duplicate" and mode == "import":
                        move_file(path, unique_path(root / DUPLICATE_DIR / rel))
                    elif result.status == "damaged" and mode == "import":
                        move_file(path, unique_path(root / DAMAGED_DIR / rel))
                except Exception as exc:
                    log.exception("Import von %s fehlgeschlagen", rel)
                    result = Result("error", rel, str(exc))
                self._record(result, rel)
                job.done += 1
            if mode == "import":
                remove_empty_dirs(root)
            else:
                job.current = "Fehlende Dateien suchen"
                missing = self.missing_assets()
                job.counts["missing"] = len(missing)
                job.missing = [{"id": r["id"], "name": r["path"]} for r in missing[:REPORT_LIMIT]]
                if deep:
                    self._check_files()
        except Exception as exc:
            log.exception("Import abgebrochen")
            self._record(Result("error", "", f"Import abgebrochen: {exc}"), "")
        finally:
            job.current = ""
            job.running = False
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            self.db.bump()
            try:
                self._report_path.write_text(json.dumps(asdict(job), ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            log.info("Import (%s%s) fertig: %s", mode, ", automatisch" if auto else "", job.counts)
