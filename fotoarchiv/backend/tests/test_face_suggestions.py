"""Vorschläge "Ist das X?" und "Gesichter vergleichen" – mit künstlichen Merkmalsvektoren, ohne Modelle."""

from collections import defaultdict

import numpy as np

from fotoarchiv.config import Settings
from fotoarchiv.db import Database
from fotoarchiv.faces import FaceService


class FakeEditor:
    hooks = defaultdict(list)


def vector(*parts):
    """Normierter 512er-Vektor aus Anteilen der ersten Achsen, z. B. vector(1, 0.8) ≈ ähnlich zu vector(1)."""
    v = np.zeros(512, np.float32)
    v[:len(parts)] = parts
    return v / np.linalg.norm(v)


def setup(tmp_path, gruppen):
    """gruppen: {group_id: (person_name | None, [vektoren])} -> FaceService mit geladenen Gruppen."""
    settings = Settings(library=tmp_path / "lib", import_dir=tmp_path / "import", data=tmp_path / "data",
                        timezone="Europe/Berlin", exiftool="exiftool", ffmpeg="ffmpeg")
    db = Database(settings.db_path)
    personen = {}
    nummer = 0
    for group_id, (name, vektoren) in gruppen.items():
        person_id = None
        if name:
            person_id = personen.setdefault(name, db.execute("INSERT INTO persons (name) VALUES (?)", (name,)).lastrowid)
        db.execute("INSERT INTO face_groups (id, person_id, vec_sum, count) VALUES (?, ?, ?, 0)",
                   (group_id, person_id, np.zeros(512, np.float32).tobytes()))
        for v in vektoren:
            nummer += 1
            db.execute("INSERT INTO assets (id, path, kind, size, md5, md5_import, taken_ts, date_source, imported_at) "
                       "VALUES (?, ?, 'image', 1, 'x', 'x', 0, 'exif', '2026-10-22')", (nummer, f"a/{nummer}.jpg"))
            db.execute("INSERT INTO faces (asset_id, x, y, w, h, score, embedding, group_id) VALUES (?, 0, 0, 1, 1, 0.9, ?, ?)",
                       (nummer, v.astype(np.float32).tobytes(), group_id))
    service = FaceService(settings, db, FakeEditor(), enabled=False)
    service.rebuild_groups()
    return service, db, personen


def test_vorschlag_zwischen_den_schwellen_und_ablehnen(tmp_path):
    service, db, personen = setup(tmp_path, {
        1: ("Levin Wolf", [vector(1, 0.1), vector(1, -0.1)]),
        2: (None, [vector(1, 1.6)]),          # ~0,53: knapp ähnlich -> Vorschlag
        3: (None, [vector(0, 0, 1)]),         # fremd -> kein Vorschlag
    })
    vorschlaege = service.suggestions()
    assert [(v["group_id"], v["person_id"]) for v in vorschlaege] == [(2, personen["Levin Wolf"])]
    assert 0.35 <= vorschlaege[0]["similarity"] < 1

    service.refuse(2, personen["Levin Wolf"])
    assert service.suggestions() == []
    # auch das automatische Zuordnen hält sich an die Ablehnung
    service.learn()
    assert db.one("SELECT person_id FROM face_groups WHERE id = 2")["person_id"] is None


def test_vergleichen_vereint_aehnliche_unbenannte_gruppen(tmp_path):
    service, db, personen = setup(tmp_path, {
        1: ("Kai Wolf", [vector(0, 0, 0, 1)]),
        2: (None, [vector(1, 0.1), vector(1, 0.2)]),
        3: (None, [vector(1, -0.1)]),        # gleiche Person wie Gruppe 2
        4: (None, [vector(0, 1)]),           # andere Person
        5: (None, [vector(0, 0, 0, 1, 0.1)]),  # sieht aus wie Kai -> lernt dazu
    })
    ergebnis = service.compare()
    assert ergebnis["merged"] == 1 and ergebnis["learned"]
    gruppen = {r["id"]: r for r in db.query("SELECT id, person_id, count FROM face_groups")}
    assert 3 not in gruppen and gruppen[2]["count"] == 3
    assert 4 in gruppen and gruppen[4]["person_id"] is None
    assert db.one("SELECT COUNT(*) AS n FROM faces WHERE group_id = 1")["n"] == 2  # Gruppe 5 kam zu Kai


def test_vergleichen_achtet_auf_nicht_diese_person(tmp_path):
    service, db, _ = setup(tmp_path, {2: (None, [vector(1, 0.1)]), 3: (None, [vector(1, -0.1)])})
    db.execute("UPDATE faces SET rejected_group = 2 WHERE group_id = 3")
    assert service.compare()["merged"] == 0
