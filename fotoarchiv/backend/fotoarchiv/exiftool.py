"""Dauerhaft laufender exiftool-Prozess (-stay_open), damit nicht pro Bild Perl gestartet wird."""

import json
import logging
import queue
import re
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT = 120  # Sekunden pro Aufruf; große Videos brauchen etwas


class ExifToolError(RuntimeError):
    pass


def _pump(stream, lines: queue.Queue):
    for line in stream:
        lines.put(line)
    lines.put(None)


class ExifTool:
    def __init__(self, executable: str):
        self.executable = executable
        self._proc: subprocess.Popen | None = None
        self._out: queue.Queue[bytes | None] = queue.Queue()
        self._err: queue.Queue[bytes | None] = queue.Queue()
        self._lock = threading.Lock()
        self._counter = 0

    def _start(self):
        self._proc = subprocess.Popen(
            [self.executable, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._out, self._err = queue.Queue(), queue.Queue()
        threading.Thread(target=_pump, args=(self._proc.stdout, self._out), daemon=True).start()
        threading.Thread(target=_pump, args=(self._proc.stderr, self._err), daemon=True).start()

    def _kill(self):
        if self._proc:
            self._proc.kill()
            self._proc = None

    def _collect(self, lines: queue.Queue, marker: bytes) -> str:
        collected: list[bytes] = []
        while True:
            try:
                line = lines.get(timeout=TIMEOUT)
            except queue.Empty:
                self._kill()
                raise ExifToolError("exiftool antwortet nicht")
            if line is None:
                self._kill()
                raise ExifToolError("exiftool wurde beendet")
            if line.strip() == marker:
                return b"".join(collected).decode("utf-8", errors="replace")
            collected.append(line)

    def run(self, *args: str) -> tuple[str, str]:
        """Ein Kommando ausführen; liefert (stdout, stderr)."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            self._counter += 1
            marker = f"{{ready{self._counter}}}"
            # -echo4 schreibt die Markierung nach der Verarbeitung auf stderr
            payload = "\n".join(
                ["-charset", "filename=utf8", *args, "-echo4", marker, f"-execute{self._counter}", ""]
            )
            try:
                self._proc.stdin.write(payload.encode("utf-8"))
                self._proc.stdin.flush()
            except OSError as exc:
                self._kill()
                raise ExifToolError(f"exiftool nicht erreichbar: {exc}") from exc
            out = self._collect(self._out, marker.encode())
            err = self._collect(self._err, marker.encode())
            return out, err

    def execute(self, *args: str) -> str:
        return self.run(*args)[0]

    def read(self, path: Path) -> dict:
        """Alle Metadaten mit Gruppennamen (z. B. "ExifIFD:DateTimeOriginal") und Zahlenwerten."""
        text = self.execute("-json", "-n", "-G1", "-a", str(path))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("exiftool lieferte kein JSON für %s", path)
            return {}
        return data[0] if data else {}

    def write(self, path: Path, *assignments: str) -> None:
        """Metadaten in die Datei schreiben; Dateidatum bleibt erhalten. Wirft bei Fehlern."""
        out, err = self.run("-overwrite_original", "-P", *assignments, str(path))
        errors = [line.removeprefix("Error: ").strip() for line in err.splitlines() if line.startswith("Error")]
        if errors or re.search(r"\b[1-9]\d* files? weren't updated", out):
            raise ExifToolError(errors[0] if errors else "Datei wurde nicht geändert")
        if not re.search(r"\b[1-9]\d* image files? (updated|unchanged)", out):
            raise ExifToolError(f"Unerwartete Antwort von exiftool: {out.strip() or err.strip()}")

    def close(self):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.stdin.write(b"-stay_open\nFalse\n")
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    self._proc.kill()
            self._proc = None
