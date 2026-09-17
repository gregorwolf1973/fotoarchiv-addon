"""Dauerhaft laufender exiftool-Prozess (-stay_open), damit nicht pro Bild Perl gestartet wird."""

import json
import logging
import queue
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT = 120  # Sekunden pro Aufruf; große Videos brauchen etwas


class ExifToolError(RuntimeError):
    pass


class ExifTool:
    def __init__(self, executable: str):
        self.executable = executable
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        self._lock = threading.Lock()
        self._counter = 0

    def _start(self):
        self._proc = subprocess.Popen(
            [self.executable, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._lines = queue.Queue()
        threading.Thread(target=self._pump, args=(self._proc, self._lines), daemon=True).start()

    @staticmethod
    def _pump(proc: subprocess.Popen, lines: queue.Queue):
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    def _kill(self):
        if self._proc:
            self._proc.kill()
            self._proc = None

    def execute(self, *args: str) -> str:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            self._counter += 1
            marker = f"{{ready{self._counter}}}"
            payload = "\n".join(
                ["-charset", "filename=utf8", *args, f"-execute{self._counter}", ""]
            )
            try:
                self._proc.stdin.write(payload.encode("utf-8"))
                self._proc.stdin.flush()
            except OSError as exc:
                self._kill()
                raise ExifToolError(f"exiftool nicht erreichbar: {exc}") from exc

            out: list[bytes] = []
            while True:
                try:
                    line = self._lines.get(timeout=TIMEOUT)
                except queue.Empty:
                    self._kill()
                    raise ExifToolError("exiftool antwortet nicht")
                if line is None:
                    self._kill()
                    raise ExifToolError("exiftool wurde beendet")
                if line.strip() == marker.encode():
                    return b"".join(out).decode("utf-8", errors="replace")
                out.append(line)

    def read(self, path: Path) -> dict:
        """Alle Metadaten mit Gruppennamen (z. B. "ExifIFD:DateTimeOriginal") und Zahlenwerten."""
        text = self.execute("-json", "-n", "-G1", "-a", str(path))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("exiftool lieferte kein JSON für %s", path)
            return {}
        return data[0] if data else {}

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
