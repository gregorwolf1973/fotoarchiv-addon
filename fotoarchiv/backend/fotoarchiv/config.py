"""Einstellungen aus /data/options.json (Home Assistant) oder Umgebungsvariablen (Entwicklung)."""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    library: Path      # Archiv, sortiert nach JJJJ/MM
    import_dir: Path   # Samba-Eingangsordner
    data: Path         # Datenbank und Cache (Add-on-Datenordner)
    timezone: str
    exiftool: str
    ffmpeg: str
    trash_days: int = 30
    dev: bool = False  # erlaubt Zugriffe außerhalb von Ingress

    @property
    def db_path(self) -> Path:
        return self.data / "fotoarchiv.db"

    @property
    def cache(self) -> Path:
        return self.data / "cache"

    @property
    def upload_tmp(self) -> Path:
        # Liegt in der Bibliothek, damit das Verschieben nach dem Upload ein Umbenennen bleibt
        return self.library / ".upload"


def load() -> Settings:
    data = Path(os.environ.get("FOTOARCHIV_DATA", "/data"))
    try:
        options = json.loads((data / "options.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        options = {}

    def pick(env: str, option: str, default: str) -> str:
        return os.environ.get(env) or options.get(option) or default

    return Settings(
        library=Path(pick("FOTOARCHIV_LIBRARY", "library_folder", "/media/fotoarchiv")),
        import_dir=Path(pick("FOTOARCHIV_IMPORT", "import_folder", "/share/fotoarchiv-import")),
        data=data,
        timezone=os.environ.get("TZ") or "Europe/Berlin",
        exiftool=os.environ.get("FOTOARCHIV_EXIFTOOL") or shutil.which("exiftool") or "exiftool",
        ffmpeg=os.environ.get("FOTOARCHIV_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg",
        trash_days=int(pick("FOTOARCHIV_TRASH_DAYS", "trash_days", "30")),
        dev=os.environ.get("FOTOARCHIV_DEV") == "1",
    )
