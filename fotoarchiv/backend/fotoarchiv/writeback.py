"""„Alle Informationen in die Bilder schreiben“: was bisher nur in der Datenbank steht, in die Dateien.

Das sind
- Schlagwort-Vorschläge der Bilderkennung, die weder übernommen noch abgelehnt sind,
- Personennamen aus der Gesichtserkennung, die der Hintergrund noch nicht geschrieben hat,
- Angaben aus Begleitdateien (Google-JSON, XMP), die beim Import nur in die Datenbank kamen.

Nicht dazu gehören Drehvorschläge (die prüft man unter „Drehen prüfen“), Favoritenordner und
Gesichtsrahmen. Dateien, die selbst keine Metadaten speichern können (AVI, GIF …), bleiben, wie sie sind.
"""

import os
from pathlib import Path

from . import metadata
from .db import Database
from .editor import WRITABLE, Editor
from .faces import FaceService
from .vision import VISIBLE, VisionService


def _writable(path: str) -> bool:
    return Path(path).suffix.lower() in WRITABLE


def sidecar_assets(library: Path, rows) -> list[int]:
    """Fotos aus rows (id, path), neben denen eine Begleitdatei liegt. Ein Gang durch die Ordner statt
    mehrerer Dateiabfragen je Foto – auf dem Pi wären das sonst Hunderttausende Zugriffe."""
    present: dict[str, set[str]] = {}
    for folder, dirs, files in os.walk(library):
        dirs[:] = [d for d in dirs if not d.startswith(".")]  # Papierkorb, Upload-Reste
        names = {name for name in files if metadata.is_sidecar(Path(name))}
        if names:
            present[Path(folder).relative_to(library).as_posix()] = names
    found = []
    for row in rows:
        rel = Path(row["path"])
        names = present.get(rel.parent.as_posix())
        if names and names.intersection(metadata.sidecar_candidates(rel.name)):
            found.append(row["id"])
    return found


def plan(db: Database, library: Path) -> dict:
    """Was zu schreiben ist, mit den betroffenen Fotos (ids)."""
    suggested = db.query(
        f"""SELECT s.asset_id, a.path, COUNT(*) AS n FROM auto_tags s
            JOIN assets a ON a.id = s.asset_id AND a.deleted_at IS NULL WHERE {VISIBLE} GROUP BY s.asset_id""")
    writable = [r for r in suggested if _writable(r["path"])]
    persons = [r["id"] for r in db.query("SELECT id FROM assets WHERE persons_dirty = 1 AND deleted_at IS NULL")]
    candidates = [r for r in db.query("SELECT id, path FROM assets WHERE sidecar_absorbed = 0 AND deleted_at IS NULL")
                  if _writable(r["path"])]
    sidecars = sidecar_assets(library, candidates)
    ids = sorted({r["asset_id"] for r in writable} | set(persons) | set(sidecars))
    return {
        "files": len(ids),  # Fotos mit mehreren Angaben zählen einmal
        "suggestion_photos": len(writable),
        "suggestion_tags": sum(r["n"] for r in writable),
        "unwritable": len(suggested) - len(writable),  # bleiben Vorschläge
        "persons": len(persons),
        "sidecars": len(sidecars),
        "ids": ids,
    }


def write_one(editor: Editor, faces: FaceService, vision: VisionService, asset_id: int):
    editor.absorb_sidecar(asset_id)  # zuerst: dann stehen auch Personen und Schlagworte der Begleitdatei drin
    faces.sync_asset(asset_id)
    vision.accept_suggestions(asset_id)
