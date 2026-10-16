"""ZIP-Archiv als Datenstrom: Dateien werden erst beim Senden gelesen, nichts liegt ganz im Speicher
oder auf der Platte. Fotos und Videos sind schon komprimiert, darum ohne Kompression (ZIP_STORED) –
das spart auf dem Pi die Rechenzeit, und das Archiv wird kaum größer."""

import zipfile
from pathlib import Path

CHUNK = 1024 * 1024


class _Sink:
    """Nimmt auf, was zipfile schreibt; der Generator gibt es stückweise weiter. Ohne seek() schreibt
    zipfile Prüfsumme und Größe in einen Datendeskriptor hinter jede Datei, statt zurückzuspringen."""

    def __init__(self):
        self.parts: list[bytes] = []
        self.offset = 0

    def write(self, data) -> int:
        self.parts.append(bytes(data))
        self.offset += len(data)
        return len(data)

    def tell(self) -> int:
        return self.offset

    def flush(self):
        pass

    def take(self) -> bytes:
        data, self.parts = b"".join(self.parts), []
        return data


def unique_names(paths: list[Path]) -> list[str]:
    """Namen im Archiv: flach, ohne Jahr/Monat. Gleichnamige Dateien bekommen (2), (3) … – auch bei
    anderer Groß-/Kleinschreibung, weil sie unter Windows und macOS sonst beim Auspacken kollidieren."""
    used: set[str] = set()
    names = []
    for path in paths:
        name, n = path.name, 1
        while name.lower() in used:
            n += 1
            name = f"{path.stem} ({n}){path.suffix}"
        used.add(name.lower())
        names.append(name)
    return names


def stream(paths: list[Path]):
    """Die Bytes eines ZIP-Archivs mit diesen Dateien, Stück für Stück. Was inzwischen fehlt, fehlt auch im Archiv."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path, name in zip(paths, unique_names(paths)):
            try:
                # strict_timestamps=False: Dateien mit Datum vor 1980 (kaputte Kamerauhr) bekommen 1980
                info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
                source = open(path, "rb")
            except OSError:
                continue
            with source, archive.open(info, "w") as target:
                while chunk := source.read(CHUNK):
                    target.write(chunk)
                    yield sink.take()
            yield sink.take()
    yield sink.take()  # Inhaltsverzeichnis am Ende
