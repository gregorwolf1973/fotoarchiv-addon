"""Dateitypen, Prüfsummen und Vorschaubilder."""

import hashlib
import logging
import os
import subprocess
import tempfile
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
    tmp = target.with_name(f".{target.stem}.tmp.webp")
    image.webpsave(str(tmp), Q=quality, keep="none")
    os.replace(tmp, target)
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
