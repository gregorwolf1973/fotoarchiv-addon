"""Einstellungen aus /data/options.json (Home Assistant) oder Umgebungsvariablen (Entwicklung)."""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TRUSTED_PROXIES = ("127.0.0.1", "::1", "172.30.32.0/23")


@dataclass(frozen=True)
class Settings:
    library: Path      # Archiv, sortiert nach JJJJ/MM
    import_dir: Path   # Samba-Eingangsordner
    data: Path         # Datenbank und Cache (Add-on-Datenordner)
    timezone: str
    exiftool: str
    ffmpeg: str
    trash_days: int = 30
    import_quiet_seconds: int = 60  # so lange unverändert, bevor eine Datei als fertig kopiert gilt
    face_recognition: bool = True
    face_threads: int = 2  # Kerne für die Gesichtserkennung (1–8)
    duplicate_detection: bool = True
    convert_on_import: bool = False  # HEIC und nicht abspielbare Videos beim Import umwandeln
    auto_import: bool = False  # Import-Ordner jede Minute prüfen und neue Dateien selbst einlesen (Handy-Sync)
    map_language: str = "de"  # Kartenbeschriftung: de (deutscher Stil) | local (Landessprache, openstreetmap.org)
    # Internetzugang (eigener Port, nur hinter Reverse Proxy mit TLS veröffentlichen)
    public_enabled: bool = False
    public_port: int = 8301
    public_trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES
    public_cookie_secure: bool = True
    public_session_hours: int = 12
    public_log_max_mb: int = 5
    public_log_export_path: str = ""
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


def _bool(value, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() not in ("false", "0", "no", "off")


def load() -> Settings:
    data = Path(os.environ.get("FOTOARCHIV_DATA", "/data"))
    try:
        options = json.loads((data / "options.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        options = {}

    def pick(env: str, option: str, default):
        return os.environ.get(env) or options.get(option) or default

    proxies = options.get("public_trusted_proxies") or DEFAULT_TRUSTED_PROXIES
    return Settings(
        library=Path(pick("FOTOARCHIV_LIBRARY", "library_folder", "/media/fotoarchiv")),
        import_dir=Path(pick("FOTOARCHIV_IMPORT", "import_folder", "/share/fotoarchiv-import")),
        data=data,
        timezone=os.environ.get("TZ") or "Europe/Berlin",
        exiftool=os.environ.get("FOTOARCHIV_EXIFTOOL") or shutil.which("exiftool") or "exiftool",
        ffmpeg=os.environ.get("FOTOARCHIV_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg",
        trash_days=int(pick("FOTOARCHIV_TRASH_DAYS", "trash_days", 30)),
        face_recognition=_bool(os.environ.get("FOTOARCHIV_FACES", options.get("face_recognition")), True),
        # 0 wäre bei pick() nicht unterscheidbar vom fehlenden Wert, darum erst ab 1
        face_threads=min(8, max(1, int(pick("FOTOARCHIV_FACE_THREADS", "face_threads", 2)))),
        duplicate_detection=_bool(os.environ.get("FOTOARCHIV_DUPLICATES", options.get("duplicate_detection")), True),
        convert_on_import=_bool(os.environ.get("FOTOARCHIV_CONVERT", options.get("convert_on_import")), False),
        auto_import=_bool(os.environ.get("FOTOARCHIV_AUTO_IMPORT", options.get("auto_import")), False),
        map_language="local" if str(options.get("map_language") or "de") == "local" else "de",
        public_enabled=_bool(os.environ.get("FOTOARCHIV_PUBLIC", options.get("public_enabled")), False),
        public_port=int(pick("FOTOARCHIV_PUBLIC_PORT", "public_port", 8301)),
        public_trusted_proxies=tuple(str(p).strip() for p in proxies if str(p).strip()),
        public_cookie_secure=_bool(os.environ.get("FOTOARCHIV_COOKIE_SECURE", options.get("public_cookie_secure")), True),
        public_session_hours=int(options.get("public_session_hours") or 12),
        public_log_max_mb=int(options.get("public_log_max_mb") or 5),
        public_log_export_path=str(options.get("public_log_export_path") or "").strip(),
        dev=os.environ.get("FOTOARCHIV_DEV") == "1",
    )
