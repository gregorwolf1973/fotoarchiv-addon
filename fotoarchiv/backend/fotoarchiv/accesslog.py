"""Zugriffsprotokoll des Internetzugangs: ein JSON-Objekt pro Zeile (Format wie Simple NAS).

Größe begrenzt durch RotatingFileHandler. Enthält nie Passwörter oder Sitzungskennungen.
Eine zweite Kopie ("Export") kann an einen Ort geschrieben werden, den das CrowdSec-Add-on liest.
"""

import json
import logging
import logging.handlers
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

EVENTS = ("auth_ok", "auth_fail", "logout", "rate_limited", "unauthorized", "forbidden", "not_found", "change")


class AccessLog:
    def __init__(self, path: Path, max_mb: int = 5):
        self.path = Path(path)
        self.max_mb = max_mb
        self._logger = logging.getLogger(f"fotoarchiv.access.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._slots: dict[str, tuple[str, logging.Handler]] = {}
        self._lock = threading.Lock()
        self.set_export(str(self.path), slot="main")

    def set_export(self, export_path: str, slot: str = "export") -> bool:
        """Einen Ausgang auf eine Datei richten; leerer Pfad schließt ihn.

        Zwei rotierende Handler auf dieselbe Datei würden sich gegenseitig die Rotation zerstören,
        deshalb wird ein bereits beschriebener Pfad nicht ein zweites Mal geöffnet.
        """
        with self._lock:
            current = self._slots.get(slot)
            if current and current[0] == export_path:
                return True
            if current:
                self._logger.removeHandler(current[1])
                current[1].close()
                self._slots.pop(slot, None)
            if not export_path:
                return True
            if any(path == export_path for path, _h in self._slots.values()):
                return True
            try:
                os.makedirs(os.path.dirname(export_path), exist_ok=True)
                handler = logging.handlers.RotatingFileHandler(
                    export_path, maxBytes=int(self.max_mb) * 1024 * 1024, backupCount=1, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(message)s"))
                self._logger.addHandler(handler)
                self._slots[slot] = (export_path, handler)
            except OSError as exc:
                log.warning("Zugriffsprotokoll nach %s nicht möglich: %s", export_path, exc)
                return False
        return True

    def writes_to(self, path: str) -> bool:
        return any(p == path for p, _h in self._slots.values())

    def log(self, event: str, **fields):
        now = time.time()
        record = {"ts": round(now, 3), "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "event": event}
        for key, value in fields.items():
            if value is None or value == "":
                continue
            record[key] = str(value)[:160] if key in ("ua", "path", "detail") else value
        try:
            self._logger.info(json.dumps(record, ensure_ascii=False))
        except Exception:
            pass
        if event in ("auth_fail", "rate_limited", "auth_ok"):
            log.info("[Zugang] %s %s", event, " ".join(f"{k}={v}" for k, v in record.items()
                                                       if k not in ("ts", "time", "event", "ua")))

    def tail(self, limit: int = 200, event: str | None = None, max_bytes: int = 256 * 1024) -> list[dict]:
        """Letzte Einträge, neueste zuerst. Liest nur das Ende der Datei."""
        out = []
        for path in (self.path, Path(f"{self.path}.1")):
            if not path.is_file():
                continue
            try:
                with open(path, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - max_bytes))
                    lines = f.read().decode("utf-8", "replace").split("\n")
            except OSError:
                continue
            if size > max_bytes:
                lines = lines[1:]  # erste Zeile ist vermutlich abgeschnitten
            for line in lines:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not event or record.get("event") == event:
                    out.append(record)
        out.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return out[:limit]

    def clear(self):
        with self._lock:
            for path in (self.path, Path(f"{self.path}.1")):
                if path.is_file():
                    try:
                        open(path, "w").close()
                    except OSError:
                        pass
