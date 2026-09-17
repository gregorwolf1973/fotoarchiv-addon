"""Testumgebung: echte Dateien, echtes exiftool und libvips, temporäre Ordner.

exiftool muss im PATH liegen oder per FOTOARCHIV_EXIFTOOL angegeben werden.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fotoarchiv.config import Settings  # noqa: E402
from fotoarchiv.db import Database  # noqa: E402
from fotoarchiv.editor import Editor  # noqa: E402
from fotoarchiv.exiftool import ExifTool  # noqa: E402
from fotoarchiv.importer import Importer  # noqa: E402

EXIFTOOL = os.environ.get("FOTOARCHIV_EXIFTOOL") or shutil.which("exiftool") or "exiftool"
FFMPEG = os.environ.get("FOTOARCHIV_FFMPEG") or shutil.which("ffmpeg")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        library=tmp_path / "media" / "fotoarchiv",
        import_dir=tmp_path / "share" / "import",
        data=tmp_path / "data",
        timezone="Europe/Berlin",
        exiftool=EXIFTOOL,
        ffmpeg=FFMPEG or "ffmpeg",
        dev=True,
    )


@pytest.fixture
def exiftool(settings):
    tool = ExifTool(settings.exiftool)
    yield tool
    tool.close()


@pytest.fixture
def importer(settings, exiftool):
    db = Database(settings.db_path)
    yield Importer(settings, db, exiftool)
    db.close()


@pytest.fixture
def editor(settings, importer, exiftool):
    return Editor(settings, importer.db, exiftool, importer)


@pytest.fixture
def make_video():
    """Kurzes Testvideo mit ffmpeg; ohne ffmpeg wird der Test übersprungen."""
    if not FFMPEG:
        pytest.skip("ffmpeg nicht vorhanden")

    def make(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc=size=320x240:rate=10", "-t", "1", "-pix_fmt", "yuv420p", str(path)], check=True)
        return path

    return make


@pytest.fixture
def make_jpeg(exiftool):
    """JPEG mit eindeutigem Inhalt erzeugen und optional Metadaten hineinschreiben."""
    import pyvips

    counter = [0]

    def make(path: Path, width=320, height=240, **tags) -> Path:
        counter[0] += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        image = pyvips.Image.black(width, height, bands=3) + [counter[0] * 7 % 255, 80, 160]
        image.cast("uchar").jpegsave(str(path), Q=90)
        if tags:
            args = ["-overwrite_original"]
            for key, value in tags.items():
                for item in value if isinstance(value, list) else [value]:
                    args.append(f"-{key.replace('__', ':')}={item}")
            exiftool.execute(*args, str(path))
        return path

    return make
