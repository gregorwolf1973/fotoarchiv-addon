"""Dateitypen, Prüfsummen und Vorschaubilder."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
}
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".3gp": "video/3gpp",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".mts": "video/mp2t",
    ".m2ts": "video/mp2t",
    # Ältere Kameras und Windows: spielt kein Browser ab, "Umwandeln" macht daraus H.264-MP4
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
    ".wmv": "video/x-ms-wmv",
}

THUMB_HEIGHT = 400     # Galerie, reicht für Zeilenhöhe 200 px bei doppelter Pixeldichte
THUMB_MAX_WIDTH = 1600
PREVIEW_SIZE = 2048    # Einzelansicht, längste Seite
SMALL_HEIGHT = 160     # rausgezoomte Galerie; wird aus dem normalen Vorschaubild verkleinert

try:
    import pyvips

    # Der Operations-Cache arbeitet mit Dateinamen – nach Drehen oder Bearbeiten lieferte er veraltete Bilder
    pyvips.cache_set_max(0)
except (ImportError, OSError) as exc:  # libvips fehlt
    pyvips = None
    log.error("libvips nicht verfügbar: %s", exc)


def ffprobe_for(ffmpeg: str) -> str:
    """ffprobe liegt neben ffmpeg (Debian-Paket ffmpeg)."""
    found = shutil.which(ffmpeg)
    if found:
        sibling = Path(found).with_name("ffprobe" + Path(found).suffix)
        if sibling.exists():
            return str(sibling)
    return shutil.which("ffprobe") or "ffprobe"


def probe(ffprobe: str, path: Path) -> dict:
    """Aufbau einer Videodatei; RuntimeError, wenn ffprobe sie nicht lesen kann."""
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-300:] or "unbekannter Fehler")
    return json.loads(result.stdout or "{}")


def damage(path: Path, kind: str, ffprobe: str) -> str | None:
    """Warum die Datei unbrauchbar ist, oder None. Fehlt ein Werkzeug, gilt sie als in Ordnung –
    abgelehnt wird nur, was nachweislich kaputt ist (z. B. abgebrochen kopiert oder hochgeladen)."""
    if kind == "image":
        if pyvips is None:
            return None
        try:
            image = pyvips.Image.new_from_file(str(path))  # liest den Kopf, erkennt das Format am Inhalt
        except Exception as exc:
            return f"Bild nicht lesbar ({_first_line(exc)})"
        return None if image.width > 0 and image.height > 0 else "Bild hat keine Größe"
    try:
        info = probe(ffprobe, path)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None  # ffprobe fehlt oder hängt: nicht als beschädigt werten
    except RuntimeError as exc:
        text = str(exc)
        if "moov atom not found" in text:
            return "Video unvollständig – die Datei ist abgeschnitten (abgebrochen kopiert oder hochgeladen)"
        return f"Video nicht lesbar ({_first_line(text)})"
    if not any(s.get("codec_type") == "video" for s in info.get("streams") or []):
        return "Video enthält keine Bildspur"
    return None


def deep_damage(path: Path, kind: str, ffprobe: str) -> str | None:
    """Wie damage(), aber Fotos werden vollständig dekodiert: findet auch abgeschnittene JPEGs,
    deren Kopf noch heil ist (libvips erzeugt daraus sonst still ein halb graues Bild)."""
    if kind != "image" or pyvips is None:
        return damage(path, kind, ffprobe)
    try:
        pyvips.Image.new_from_file(str(path), access="sequential", fail_on="truncated").avg()
    except Exception as exc:
        return f"Bild nicht vollständig lesbar ({_first_line(exc)})"
    return None


def _first_line(error) -> str:
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    return (lines[-1] if lines else "unbekannter Fehler")[:160]


def kind_of(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in IMAGE_TYPES:
        return "image"
    if suffix in VIDEO_TYPES:
        return "video"
    return None


def mime_of(path: Path) -> str:
    suffix = path.suffix.lower()
    return IMAGE_TYPES.get(suffix) or VIDEO_TYPES.get(suffix) or "application/octet-stream"


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _save_webp(image, target: Path, quality: int) -> tuple[int, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Eigene Zwischendatei je Aufruf: Import und Galerie erzeugen dasselbe Vorschaubild manchmal
    # gleichzeitig. Mit einem gemeinsamen Namen benannte der erste die Datei um, der zweite fand seine
    # nicht mehr (No such file or directory) – oder hätte in die schon fertige Datei hineingeschrieben.
    tmp = target.with_name(f".{target.stem}.{uuid.uuid4().hex[:12]}.tmp.webp")
    try:
        image.webpsave(str(tmp), Q=quality, keep="none")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)  # nur noch vorhanden, wenn etwas schiefging
    return image.width, image.height


def _vips_thumbnail(source: Path, width: int, height: int):
    if pyvips is None:
        raise RuntimeError("libvips fehlt")
    # thumbnail dreht nach EXIF-Orientierung und rechnet in sRGB um
    return pyvips.Image.thumbnail(
        str(source), width, height=height, size="down", export_profile="srgb"
    )


def _video_frame(source: Path, ffmpeg: str, target: Path):
    """Ein Standbild aus dem Video; bei sehr kurzen Clips das erste Bild."""
    for position in ("1", "0"):
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", position,
             "-i", str(source), "-frames:v", "1", "-q:v", "2", str(target)],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
            return
    raise RuntimeError(f"ffmpeg: {result.stderr.decode(errors='replace').strip()[-300:]}")


def render(source: Path, kind: str, ffmpeg: str, target: Path, width: int, height: int, quality: int) -> tuple[int, int]:
    """Vorschaubild erzeugen; gibt die Größe des Ergebnisses zurück (zeigt die echte Ausrichtung)."""
    if kind == "video":
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / "frame.jpg"
            _video_frame(source, ffmpeg, frame)
            return _save_webp(_vips_thumbnail(frame, width, height), target, quality)
    return _save_webp(_vips_thumbnail(source, width, height), target, quality)


def thumbnail(source: Path, kind: str, ffmpeg: str, target: Path) -> tuple[int, int]:
    return render(source, kind, ffmpeg, target, THUMB_MAX_WIDTH, THUMB_HEIGHT, 75)


def small(thumb: Path, target: Path) -> tuple[int, int]:
    """Kleines Vorschaubild aus dem vorhandenen – schnell, auch bei HEIC und Videos."""
    return _save_webp(_vips_thumbnail(thumb, THUMB_MAX_WIDTH, SMALL_HEIGHT), target, 70)


def preview(source: Path, kind: str, ffmpeg: str, target: Path) -> tuple[int, int]:
    return render(source, kind, ffmpeg, target, PREVIEW_SIZE, PREVIEW_SIZE, 82)
