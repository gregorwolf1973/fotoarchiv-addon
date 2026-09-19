"""Problematische Formate umwandeln: HEIC → JPEG, nicht abspielbare Videos → H.264-MP4.

Der Eintrag behält seine ID (Personen, Schlagworte, Gesichter bleiben dran) und zeigt danach auf
die neue Datei. Das Original kommt als eigener Eintrag in den Papierkorb und wird nach der
Papierkorbfrist gelöscht – bis dahin lässt es sich wiederherstellen.

Vorgemerkt wird über assets.convert: 0 = nichts zu tun, 1 = vorgemerkt, -1 = fehlgeschlagen
(Grund in convert_error). Ein eigener Hintergrund-Thread arbeitet die Vormerkungen ab, weil das
Umwandeln eines Videos auf dem Pi so lange dauert wie das Video selbst.
"""

import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import labels, media
from .config import Settings
from .db import NEXT_ASSET_ID, Database
from .editor import TRASH_DIR, Editor, EditError
from .importer import Importer, move_file, unique_path

log = logging.getLogger(__name__)

IDLE_WAIT = 600  # s, falls ein Aufwecken verloren geht
HEIF_SUFFIXES = {".heic", ".heif"}
MP4_SUFFIXES = {".mp4", ".m4v"}
SKIP_SUFFIXES = {".webm"}  # VP8/VP9/AV1 in WebM spielen die Browser ab
PLAYABLE_CODECS = {"h264"}
PLAYABLE_PIXELS = {"yuv420p", "yuvj420p"}  # 8 Bit 4:2:0; 10 Bit und 4:2:2 können Browser nicht
MP4_AUDIO = {"aac", "mp3"}
JPEG_QUALITY = 92


class Changed(Exception):
    """Der Eintrag hat sich während des Umwandelns geändert; später erneut versuchen."""


@dataclass
class Plan:
    action: str        # heic | remux | transcode
    suffix: str        # Endung der neuen Datei
    copy_audio: bool   # Tonspur übernehmen statt nach AAC umwandeln
    reason: str


def decide(suffix: str, kind: str, info: dict | None) -> Plan | None:
    """Was mit einer Datei zu tun ist. info: Ausgabe von ffprobe (nur bei Videos nötig)."""
    suffix = suffix.lower()
    if kind == "image":
        return Plan("heic", ".jpg", False, "HEIC → JPEG") if suffix in HEIF_SUFFIXES else None
    if suffix in SKIP_SUFFIXES or not info:
        return None
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video" and not _is_cover(s)), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        return None
    playable = video.get("codec_name") in PLAYABLE_CODECS and video.get("pix_fmt") in PLAYABLE_PIXELS
    audio_ok = audio is None or audio.get("codec_name") in MP4_AUDIO
    if playable and audio_ok and suffix in MP4_SUFFIXES:
        return None
    if playable:
        return Plan("remux", ".mp4", audio_ok, f"{suffix.lstrip('.').upper()} → MP4 (verlustfrei umgepackt)")
    codec = video.get("codec_name") or "?"
    pixels = video.get("pix_fmt") or ""
    detail = f"{codec}, {pixels}" if codec in PLAYABLE_CODECS else codec
    return Plan("transcode", ".mp4", audio_ok, f"{detail} → H.264")


def _is_cover(stream: dict) -> bool:
    return bool((stream.get("disposition") or {}).get("attached_pic"))


def video_command(ffmpeg: str, source: Path, target: Path, plan: Plan) -> list[str]:
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "0",
        "-movflags", "+faststart+use_metadata_tags",
    ]
    if plan.action == "remux":
        command += ["-c:v", "copy", "-tag:v", "avc1"]
    else:
        # Drehung wird beim Umwandeln in die Bilder übernommen (autorotate), die neue Datei ist aufrecht
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]
    command += ["-c:a", "copy"] if plan.copy_audio else ["-c:a", "aac", "-b:a", "160k"]
    return command + [str(target)]


def _lower_priority():
    os.nice(10)  # Home Assistant soll flüssig bleiben, während ein Video umgewandelt wird


class ConvertService:
    def __init__(self, settings: Settings, db: Database, importer: Importer, editor: Editor, *, on_import: bool = False):
        self.settings = settings
        self.db = db
        self.importer = importer
        self.editor = editor
        self.on_import = on_import
        self.ffprobe = media.ffprobe_for(settings.ffmpeg)
        self.current: str | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        importer.hooks["imported"].append(self._on_imported)

    # ── Vormerken ──────────────────────────────────────────────────
    def _on_imported(self, asset_id: int):
        if not self.on_import:
            return None
        row = self.db.one("SELECT path, kind FROM assets WHERE id = ?", (asset_id,))
        if row and self.candidate(row["path"], row["kind"]):
            self.db.execute("UPDATE assets SET convert = 1, convert_error = NULL WHERE id = ?", (asset_id,))
            self.wake()
        return None  # kein Hinweis auf ähnliche Fotos

    @staticmethod
    def candidate(path: str, kind: str) -> bool:
        """Grobe Vorauswahl ohne ffprobe: HEIC und alle Videos außer WebM."""
        suffix = Path(path).suffix.lower()
        return suffix in HEIF_SUFFIXES if kind == "image" else suffix not in SKIP_SUFFIXES

    def request(self, asset_id: int):
        """Für die Mehrfachaktion: vormerken, der Hintergrund-Thread erledigt den Rest."""
        row = self.db.one("SELECT path, kind FROM assets WHERE id = ? AND deleted_at IS NULL", (asset_id,))
        if row is None:
            raise EditError("Bild nicht gefunden")
        if self.candidate(row["path"], row["kind"]):
            self.db.execute("UPDATE assets SET convert = 1, convert_error = NULL WHERE id = ?", (asset_id,))
            self.wake()

    def status(self) -> dict:
        row = self.db.one(
            """SELECT COALESCE(SUM(convert = 1), 0) AS pending, COALESCE(SUM(convert = -1), 0) AS failed
               FROM assets WHERE deleted_at IS NULL""")
        # Grund gleich mitliefern: das Add-on-Protokoll ist nach einem Neustart weg
        errors = [{"id": r["id"], "name": Path(r["path"]).name, "reason": r["convert_error"] or ""}
                  for r in self.db.query(
                      """SELECT id, path, convert_error FROM assets WHERE convert = -1 AND deleted_at IS NULL
                         ORDER BY id DESC LIMIT 3""")] if row["failed"] else []
        return {"pending": row["pending"], "failed": row["failed"], "errors": errors, "current": self.current}

    def dismiss_failed(self) -> int:
        """Fehlschläge zur Kenntnis genommen: Hinweis ausblenden. Der Grund bleibt in convert_error,
        und die Datei lässt sich später erneut zum Umwandeln vormerken."""
        count = self.db.execute("UPDATE assets SET convert = 0 WHERE convert = -1").rowcount
        self.db.bump()
        return count

    # ── Hintergrund ────────────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._run, daemon=True, name="convert").start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                if self.work_once():
                    continue
            except Exception:
                log.exception("Konvertieren fehlgeschlagen")
            self._wake.wait(IDLE_WAIT)
            self._wake.clear()

    def work_once(self) -> bool:
        row = self.db.one(
            "SELECT id, path FROM assets WHERE convert = 1 AND deleted_at IS NULL ORDER BY id DESC LIMIT 1")
        if row is None:
            return False
        self.current = Path(row["path"]).name
        try:
            self.convert(row["id"])
            self.db.execute("UPDATE assets SET convert = 0, convert_error = NULL WHERE id = ?", (row["id"],))
        except Changed:
            log.info("%s wurde während des Umwandelns geändert, wird erneut umgewandelt", row["path"])
        except Exception as exc:
            log.warning("Konvertieren von %s fehlgeschlagen: %s", row["path"], exc)
            self.db.execute("UPDATE assets SET convert = -1, convert_error = ? WHERE id = ?", (str(exc)[:500], row["id"]))
        finally:
            self.current = None
            self.db.bump()
        return True

    # ── Umwandeln ──────────────────────────────────────────────────
    def convert(self, asset_id: int) -> str | None:
        """Datei umwandeln und ersetzen. Gibt den neuen Pfad zurück, None wenn nichts zu tun war."""
        row = self.db.one("SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (asset_id,))
        if row is None:
            raise EditError("Bild nicht gefunden")
        source = self.settings.library / row["path"]
        if not source.is_file():
            raise EditError("Datei fehlt auf dem Datenträger")
        info = media.probe(self.ffprobe, source) if row["kind"] == "video" else None
        plan = decide(source.suffix, row["kind"], info)
        if plan is None:
            return None
        log.info("Konvertiere %s: %s", row["path"], plan.reason)
        temp = source.with_name(f".konvert-{asset_id}{plan.suffix}")  # Punkt: beim Einlesen unsichtbar
        try:
            if plan.action == "heic":
                self._heic_to_jpeg(source, temp)
            else:
                self._video(source, temp, plan)
                self._check_video(source, temp)
            stat = source.stat()
            os.utime(temp, (stat.st_atime, stat.st_mtime))  # Dateidatum bleibt, wie beim Bearbeiten
            return self._replace(row, source, temp, plan)
        finally:
            temp.unlink(missing_ok=True)

    def _heic_to_jpeg(self, source: Path, temp: Path):
        pyvips = media.pyvips
        image = pyvips.Image.new_from_file(str(source))  # libheif hat die Drehung (irot) schon angewendet
        if image.hasalpha():
            image = image.flatten(background=[255, 255, 255])
        if image.get_typeof("icc-profile-data"):
            image = image.icc_transform("srgb")  # iPhone-Fotos sind Display P3
        image = image.colourspace("srgb")
        if image.format != "uchar":
            image = image.cast("uchar")
        image.jpegsave(str(temp), Q=JPEG_QUALITY, keep="none")
        # Metadaten übernehmen; die Pixel sind schon aufrecht, also Orientierung zurücksetzen
        self.editor.exiftool.write(temp, "-tagsFromFile", str(source), "-all:all", "--ICC_Profile:all")
        self.editor.exiftool.write(temp, "-IFD0:Orientation#=1", "-XMP-tiff:Orientation=")

    def _video(self, source: Path, temp: Path, plan: Plan):
        command = video_command(self.settings.ffmpeg, source, temp, plan)
        result = subprocess.run(command, capture_output=True, text=True,
                                preexec_fn=_lower_priority if hasattr(os, "nice") else None)
        if result.returncode or not temp.is_file():
            raise RuntimeError(f"ffmpeg: {result.stderr.strip()[-300:] or 'keine Ausgabe'}")
        # Was ffmpeg nicht mitnimmt: Personen, Schlagworte (XMP), Apple-Angaben (Keys), Ort, Aufnahmezeit
        self.editor.exiftool.write(
            temp, "-tagsFromFile", str(source), "-XMP:all", "-Keys:all", "-ItemList:all",
            "-UserData:GPSCoordinates", "-QuickTime:CreateDate", "-QuickTime:ModifyDate")

    def _check_video(self, source: Path, temp: Path):
        """Neue Datei muss ein Video in voller Länge sein, bevor das Original weicht."""
        new = media.probe(self.ffprobe, temp)
        if not any(s.get("codec_type") == "video" for s in new.get("streams") or []):
            raise RuntimeError("Ergebnis enthält kein Video")
        before = float((media.probe(self.ffprobe, source).get("format") or {}).get("duration") or 0)
        after = float((new.get("format") or {}).get("duration") or 0)
        if before and abs(before - after) > max(1.0, before * 0.02):
            raise RuntimeError(f"Länge passt nicht ({after:.1f} s statt {before:.1f} s)")

    def _replace(self, row, source: Path, temp: Path, plan: Plan) -> str:
        library = self.settings.library
        with self.editor._lock:
            # Während des Umwandelns bearbeitet oder gelöscht? Dann stimmt die neue Datei nicht mehr
            now = self.db.one("SELECT path, rev, deleted_at FROM assets WHERE id = ?", (row["id"],))
            if now is None or now["deleted_at"] or now["path"] != row["path"] or now["rev"] != row["rev"]:
                raise Changed("Datei wurde während des Umwandelns geändert")
            target = unique_path(source.with_suffix(plan.suffix))
            trashed = unique_path(library / TRASH_DIR / row["path"])
            move_file(source, trashed)
            try:
                move_file(temp, target)
            except Exception:
                move_file(trashed, source)  # Original zurück, nichts ist passiert
                raise
            new_rel = target.relative_to(library).as_posix()
            with self.db.transaction() as conn:
                # Das Original als eigener Papierkorb-Eintrag; wiederherstellbar bis zum Ablauf der Frist
                columns = [c for c in row.keys() if c != "id"]
                values = {c: row[c] for c in columns}
                values.update(path=trashed.relative_to(library).as_posix(), orig_path=row["path"],
                              deleted_at=datetime.now().isoformat(timespec="seconds"),
                              phash="", faces_scanned=1, persons_dirty=0, convert=0, convert_error=None)
                cur = conn.execute(
                    f"INSERT INTO assets (id, {', '.join(columns)}) "
                    f"VALUES (({NEXT_ASSET_ID}), {', '.join('?' * len(columns))})",
                    [values[c] for c in columns])
                for kind in ("tags", "persons"):
                    _, link, column = labels.TABLES[kind]
                    conn.execute(f"INSERT INTO {link} (asset_id, {column}) SELECT ?, {column} FROM {link} WHERE asset_id = ?",
                                 (cur.lastrowid, row["id"]))
                conn.execute("UPDATE assets SET path = ?, mime = ?, phash = NULL WHERE id = ?",
                             (new_rel, media.mime_of(target), row["id"]))
            self.editor._refresh(row["id"], new_thumbnail=True)  # liest die neue Datei, neue Vorschaubilder
        self.db.bump()
        return new_rel
