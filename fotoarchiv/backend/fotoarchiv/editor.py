"""Bearbeiten und Löschen.

Jede Änderung wird zuerst mit exiftool in die Datei geschrieben. Danach wird die Datei neu
gelesen und die Datenbank daraus aktualisiert – so kann die Datenbank nie etwas anderes
behaupten als die Datei.
"""

import logging
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import labels, media, metadata
from .config import Settings
from .db import Database
from .exiftool import ExifTool, ExifToolError
from .importer import Importer, move_file, unique_path

log = logging.getLogger(__name__)

TRASH_DIR = ".papierkorb"  # beginnt mit Punkt: unsichtbar im HA-Medienbrowser und beim Einlesen
DATED_PATH = re.compile(r"^\d{4}/\d{2}/")

QUICKTIME = {".mp4", ".m4v", ".mov", ".3gp"}
HEIF = {".heic", ".heif", ".avif"}
IPTC = {".jpg", ".jpeg", ".tif", ".tiff"}
WRITABLE = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"} | HEIF | QUICKTIME
ROTATABLE = WRITABLE - HEIF  # libheif ignoriert die EXIF-Orientierung, exiftool kann "irot" nicht schreiben

# EXIF-Orientierung als (gespiegelt, Drehung im Uhrzeigersinn)
ORIENTATIONS = {1: (False, 0), 2: (True, 0), 3: (False, 180), 4: (True, 180),
                5: (True, 270), 6: (False, 90), 7: (True, 90), 8: (False, 270)}
ORIENTATION_OF = {value: key for key, value in ORIENTATIONS.items()}


class EditError(Exception):
    pass


def capabilities(path: str) -> dict:
    suffix = Path(path).suffix.lower()
    return {"editable": suffix in WRITABLE, "rotatable": suffix in ROTATABLE}


def rotated_orientation(orientation: int | None, degrees: int) -> int:
    flip, turn = ORIENTATIONS.get(orientation or 1, (False, 0))
    return ORIENTATION_OF[(flip, (turn + degrees) % 360)]


def _offset_delta(offset: str) -> timedelta:
    sign = -1 if offset.startswith("-") else 1
    hours, minutes = offset[1:].split(":")
    return sign * timedelta(hours=int(hours), minutes=int(minutes))


def _prune_empty_dirs(start: Path, stop: Path):
    """Leere Ordner von start aufwärts entfernen, stop selbst bleibt."""
    current = start
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


class Editor:
    def __init__(self, settings: Settings, db: Database, exiftool: ExifTool, importer: Importer):
        self.settings = settings
        self.db = db
        self.exiftool = exiftool
        self.importer = importer
        self._lock = threading.RLock()  # immer nur eine Änderung gleichzeitig
        # Rückmeldungen an andere Teile (Gesichts- und Bilderkennung): Ereignis -> Funktionen(asset_id)
        self.hooks: dict[str, list] = {"purge": [], "rotate": [], "persons": [], "tags": []}

    def _emit(self, event: str, asset_id: int):
        for hook in self.hooks[event]:
            try:
                hook(asset_id)
            except Exception:
                log.exception("Rückmeldung %s für %s fehlgeschlagen", event, asset_id)

    # ── Hilfen ─────────────────────────────────────────────────────
    def _asset(self, asset_id: int, deleted: bool = False):
        condition = "IS NOT NULL" if deleted else "IS NULL"
        row = self.db.one(f"SELECT * FROM assets WHERE id = ? AND deleted_at {condition}", (asset_id,))
        if row is None:
            raise EditError("Im Papierkorb nicht gefunden" if deleted else "Bild nicht gefunden")
        return row

    def _file(self, row) -> Path:
        path = self.settings.library / row["path"]
        if not path.is_file():
            raise EditError("Datei fehlt auf dem Datenträger")
        return path

    @staticmethod
    def _require(row, allowed: set, action: str):
        suffix = Path(row["path"]).suffix.lower()
        if suffix not in allowed:
            raise EditError(f"{action} ist bei {suffix.lstrip('.').upper()}-Dateien nicht möglich")

    def _write(self, path: Path, *assignments: str):
        try:
            self.exiftool.write(path, *assignments)
        except ExifToolError as exc:
            raise EditError(f"Schreiben fehlgeschlagen: {exc}") from exc

    def _prepare(self, asset_id: int, action: str, allowed: set = WRITABLE):
        """Vor jeder Änderung: Foto und Datei holen, Angaben aus der Begleitdatei in die Datei übernehmen."""
        row = self._asset(asset_id)
        self._require(row, allowed, action)
        path = self._file(row)
        self._absorb(row, path)
        return row, path

    def _absorb(self, row, path: Path) -> list[str]:
        """Was nur in der Begleitdatei steht (Google-JSON, XMP), in die Datei schreiben.

        Nach jeder Änderung wird die Datenbank aus der Datei neu gelesen (_refresh). Stünden Datum, Ort,
        Personen oder Schlagworte dann nur in der Begleitdatei, fielen sie aus der Datenbank. Die Datei
        selbst hat Vorrang: geschrieben wird nur, was ihr fehlt. Die Begleitdatei bleibt liegen."""
        if row["sidecar_absorbed"] or path.suffix.lower() not in WRITABLE:
            return []
        sidecar = metadata.sidecar_for(path)
        if sidecar is None:
            return []
        try:
            raw = self.exiftool.read(path)
            extra = metadata.read_sidecar(sidecar, self.exiftool, self.settings.timezone)
        except Exception as exc:
            log.warning("Begleitdatei %s nicht lesbar: %s", sidecar.name, exc)
            return []
        mtime = path.stat().st_mtime
        own = metadata.extract(raw, path, self.settings.timezone, mtime)
        full = metadata.extract(metadata.merge_sidecar(raw, extra), path, self.settings.timezone, mtime)
        written = []
        if own.date_source != "exif" and full.date_source == "exif":
            self._write_date(path, row, full.taken)
            written.append("Datum")
        if own.lat is None and full.lat is not None:
            self._write_location(path, full.lat, full.lon)
            written.append("Ort")
        for kind, word, mine, theirs in (("tags", "Schlagworte", own.tags, full.tags),
                                         ("persons", "Personen", own.persons, full.persons)):
            known = {name.casefold() for name in mine}
            missing = [name for name in theirs if name.casefold() not in known]
            if missing:
                self._write_labels(path, kind, labels.normalize(list(mine) + missing))
                written.append(word)
        self.db.execute("UPDATE assets SET sidecar_absorbed = 1 WHERE id = ?", (row["id"],))
        return written

    def absorb_sidecar(self, asset_id: int) -> list[str]:
        """Angaben der Begleitdatei in die Datei schreiben (für „Alle Informationen in die Bilder schreiben“)."""
        with self._lock:
            row = self._asset(asset_id)
            written = self._absorb(row, self._file(row))
            if written:
                self._refresh(asset_id)
                self.db.bump()
            return written

    def _refresh(self, asset_id: int, *, new_thumbnail: bool = False):
        """Datenbank aus der Datei neu aufbauen."""
        row = self._asset(asset_id)
        path = self._file(row)
        raw = self.exiftool.read(path)
        stat = path.stat()
        meta = metadata.extract(raw, path, self.settings.timezone, stat.st_mtime)
        checksum = media.md5_file(path)
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE assets SET size = ?, md5 = ?, taken_at = ?, taken_ts = ?, date_source = ?, tz_offset = ?,
                       width = ?, height = ?, duration = ?, lat = ?, lon = ?, camera = ?, rev = rev + 1,
                       thumb_ok = CASE WHEN ? THEN 0 ELSE thumb_ok END
                   WHERE id = ?""",
                (stat.st_size, checksum, meta.taken.isoformat(), meta.taken_ts, meta.date_source, meta.tz_offset,
                 meta.width, meta.height, meta.duration, meta.lat, meta.lon, meta.camera, new_thumbnail, asset_id),
            )
            labels.replace(conn, asset_id, "tags", meta.tags)
            labels.replace(conn, asset_id, "persons", meta.persons)
            labels.remove_unused(conn)
        if new_thumbnail:
            self.importer.drop_cache(asset_id)
            self.importer.ensure_thumbnail(asset_id)
        return meta

    # ── Datum ──────────────────────────────────────────────────────
    def set_date(self, asset_id: int, taken: datetime):
        taken = taken.replace(tzinfo=None, microsecond=0)
        with self._lock:
            row, path = self._prepare(asset_id, "Datum ändern")
            self._write_date(path, row, taken)
            self._refresh(asset_id)
            self._resort(asset_id)
            self.db.bump()

    def _write_date(self, path: Path, row, taken: datetime):
        stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
        suffix = path.suffix.lower()
        if suffix in QUICKTIME:
            # QuickTime speichert UTC; Keys:CreationDate die Ortszeit mit Offset
            offset = row["tz_offset"] or taken.replace(tzinfo=ZoneInfo(self.settings.timezone)).strftime("%z")
            offset = offset if ":" in offset else f"{offset[:3]}:{offset[3:]}"
            utc = (taken - _offset_delta(offset)).strftime("%Y:%m:%d %H:%M:%S")
            self._write(path, f"-QuickTime:CreateDate={utc}", f"-QuickTime:ModifyDate={utc}",
                        f"-Keys:CreationDate={stamp}{offset}")
        else:
            assignments = [f"-AllDates={stamp}"]
            if row["tz_offset"]:
                assignments.append(f"-OffsetTimeOriginal={row['tz_offset']}")
            if suffix not in IPTC:
                assignments.append(f"-XMP-exif:DateTimeOriginal={stamp}")  # PNG/WebP/HEIC: zusätzlich XMP
            self._write(path, *assignments)

    def _resort(self, asset_id: int):
        """Nach Datumsänderung in den passenden JJJJ/MM-Ordner verschieben (nur bei einsortierten Dateien)."""
        row = self._asset(asset_id)
        if not DATED_PATH.match(row["path"]):
            return
        taken = datetime.fromisoformat(row["taken_at"])
        folder = f"{taken:%Y}/{taken:%m}/"
        if row["path"].startswith(folder):
            return
        source = self.settings.library / row["path"]
        target = unique_path(self.settings.library / folder / source.name)
        move_file(source, target)
        self.db.execute("UPDATE assets SET path = ? WHERE id = ?",
                        (target.relative_to(self.settings.library).as_posix(), asset_id))
        _prune_empty_dirs(source.parent, self.settings.library)

    # ── Ort ────────────────────────────────────────────────────────
    def shift_location(self, asset_id: int, dlat: float, dlon: float):
        """Ort um einen Versatz verschieben – eine Gruppe wird auf der Karte gezogen, die Anordnung bleibt.
        Fotos ohne Ort bleiben unberührt."""
        row = self.db.one("SELECT lat, lon FROM assets WHERE id = ?", (asset_id,))
        if row is None or row["lat"] is None:
            raise EditError("Kein Aufnahmeort")
        lat = max(-90.0, min(90.0, row["lat"] + dlat))
        lon = ((row["lon"] + dlon + 180.0) % 360.0) - 180.0  # über die Datumsgrenze hinaus
        self.set_location(asset_id, round(lat, 6), round(lon, 6))

    def set_location(self, asset_id: int, lat: float | None, lon: float | None):
        with self._lock:
            row, path = self._prepare(asset_id, "Ort ändern")
            self._write_location(path, lat, lon)
            self._refresh(asset_id)
            self.db.bump()

    def _write_location(self, path: Path, lat: float | None, lon: float | None):
        if path.suffix.lower() in QUICKTIME:
            if lat is None:
                self._write(path, "-Keys:GPSCoordinates=", "-UserData:GPSCoordinates=")
            else:
                self._write(path, f"-Keys:GPSCoordinates={lat}, {lon}", "-UserData:GPSCoordinates=")
        elif lat is None:
            self._write(path, "-GPS:all=", "-XMP-exif:GPSLatitude=", "-XMP-exif:GPSLongitude=")
        else:
            self._write(path, f"-GPSLatitude*={lat}", f"-GPSLongitude*={lon}")

    # ── Schlagworte und Personen ───────────────────────────────────
    def set_labels(self, asset_id: int, kind: str, names: list[str]):
        names = labels.normalize(names)
        with self._lock:
            row, path = self._prepare(asset_id, "Bearbeiten")
            self._write_labels(path, kind, names)
            meta = self._refresh(asset_id)
            if kind == "persons" and self._leftover(meta, names):
                # Der Name steckt in Gesichtsmarkierungen eines anderen Programms (Picasa, Google Fotos,
                # Lightroom, Windows-Fotogalerie …). Alle gewünschten Namen stehen jetzt in PersonInImage,
                # also gehen beim Entfernen der fremden Markierungen keine Namen verloren – nur deren Rahmen.
                self._write(path, "-XMP-mwg-rs:all=", "-XMP-MP:all=")
                meta = self._refresh(asset_id)
            self.db.bump()
            if kind == "tags":
                self._emit("tags", asset_id)
            if kind == "persons":
                self._emit("persons", asset_id)
                if self._leftover(meta, names):
                    raise EditError("Person ist über eine Gesichtsmarkierung zugeordnet und bleibt erhalten")

    def _write_labels(self, path: Path, kind: str, names: list[str]):
        suffix = path.suffix.lower()
        if kind == "tags":
            tag_lists = ["XMP-dc:Subject"] + (["IPTC:Keywords"] if suffix in IPTC else [])
            assignments = [] if suffix not in IPTC else ["-IPTC:CodedCharacterSet=UTF8"]
            for tag in tag_lists:
                assignments.append(f"-{tag}=")  # erst leeren, dann neu füllen
                assignments += [f"-{tag}={name}" for name in names]
        else:
            assignments = ["-XMP-iptcExt:PersonInImage="] + [f"-XMP-iptcExt:PersonInImage={n}" for n in names]
        self._write(path, *assignments)

    @staticmethod
    def _leftover(meta, names: list[str]) -> bool:
        return bool({p.casefold() for p in meta.persons} - {n.casefold() for n in names})

    def change_labels(self, asset_id: int, kind: str, add: list[str], remove: list[str]):
        with self._lock:
            with self.db.transaction() as conn:
                existing = labels.current(conn, asset_id, kind)
            removed = {name.casefold() for name in remove}
            names = [name for name in existing if name.casefold() not in removed] + list(add)
            if labels.normalize(names) == labels.normalize(existing):
                return  # nichts zu tun, Datei nicht anfassen
            self.set_labels(asset_id, kind, names)

    # ── Drehen ─────────────────────────────────────────────────────
    def rotate(self, asset_id: int, degrees: int):
        if degrees % 90:
            raise EditError("Nur Vierteldrehungen möglich")
        with self._lock:
            row, path = self._prepare(asset_id, "Drehen", ROTATABLE)
            raw = self.exiftool.read(path)
            if path.suffix.lower() in QUICKTIME:
                current = next((v for k, v in raw.items() if k.endswith(":Rotation") and isinstance(v, (int, float))), 0)
                self._write(path, f"-Rotation={(int(current) + degrees) % 360}")
            else:
                self._write(path, f"-Orientation#={rotated_orientation(raw.get('IFD0:Orientation'), degrees)}")
            self._refresh(asset_id, new_thumbnail=True)
            self._emit("rotate", asset_id)
            self.db.bump()

    # ── Papierkorb ─────────────────────────────────────────────────
    def delete(self, asset_id: int):
        with self._lock:
            row = self._asset(asset_id)
            source = self.settings.library / row["path"]
            target = unique_path(self.settings.library / TRASH_DIR / row["path"])
            if source.is_file():
                move_file(source, target)
                _prune_empty_dirs(source.parent, self.settings.library)
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE assets SET path = ?, orig_path = ?, deleted_at = ? WHERE id = ?",
                    (target.relative_to(self.settings.library).as_posix(), row["path"],
                     datetime.now().isoformat(timespec="seconds"), asset_id),
                )
                # Löschvorschläge sind damit erledigt; nach dem Wiederherstellen sollen sie nicht wieder auftauchen
                conn.execute("DELETE FROM delete_requests WHERE asset_id = ?", (asset_id,))
            self.db.bump()

    def restore(self, asset_id: int):
        with self._lock:
            row = self._asset(asset_id, deleted=True)
            source = self.settings.library / row["path"]
            target = unique_path(self.settings.library / (row["orig_path"] or Path(row["path"]).relative_to(TRASH_DIR)))
            if not source.is_file():
                raise EditError("Datei im Papierkorb fehlt")
            move_file(source, target)
            _prune_empty_dirs(source.parent, self.settings.library / TRASH_DIR)
            self.db.execute(
                "UPDATE assets SET path = ?, orig_path = NULL, deleted_at = NULL WHERE id = ?",
                (target.relative_to(self.settings.library).as_posix(), asset_id),
            )
            self.db.bump()

    def purge(self, asset_id: int):
        """Endgültig löschen – nur aus dem Papierkorb heraus."""
        with self._lock:
            row = self._asset(asset_id, deleted=True)
            path = self.settings.library / row["path"]
            sidecar = metadata.sidecar_for(path)
            path.unlink(missing_ok=True)
            if sidecar is not None:
                sidecar.unlink(missing_ok=True)
            _prune_empty_dirs(path.parent, self.settings.library / TRASH_DIR)
            self._emit("purge", asset_id)
            self.importer.drop_cache(asset_id)
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
                labels.remove_unused(conn)
            self.db.bump()

    def forget(self, asset_id: int):
        """Eintrag entfernen, dessen Datei außerhalb des Fotoarchivs gelöscht wurde."""
        with self._lock:
            row = self.db.one("SELECT path FROM assets WHERE id = ?", (asset_id,))
            if row is None:
                return
            if (self.settings.library / row["path"]).exists():
                raise EditError("Die Datei ist wieder vorhanden und bleibt im Archiv")
            self._emit("purge", asset_id)
            self.importer.drop_cache(asset_id)
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
                labels.remove_unused(conn)
            self.db.bump()

    def expired(self, days: int) -> list[int]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        return [r["id"] for r in self.db.query("SELECT id FROM assets WHERE deleted_at < ?", (cutoff,))]

    def purge_expired(self, days: int) -> int:
        ids = self.expired(days)
        for asset_id in ids:
            try:
                self.purge(asset_id)
            except Exception:
                log.exception("Endgültiges Löschen von %s fehlgeschlagen", asset_id)
        if ids:
            log.info("Papierkorb: %d abgelaufene Dateien gelöscht", len(ids))
        return len(ids)
