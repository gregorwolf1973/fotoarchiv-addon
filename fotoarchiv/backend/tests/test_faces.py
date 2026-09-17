"""Gesichtserkennung mit den echten Modellen.

Benötigt FOTOARCHIV_MODELS (Ordner mit det_10g.onnx und w600k_r50.onnx) und FOTOARCHIV_FACE_PHOTOS
(Porträts: obama_*.jpg mit je einem Gesicht, obama_0.jpg mit Obama und Biden, biden_*.jpg).
Ohne diese Daten werden die Tests übersprungen.
"""

import os
import shutil
from pathlib import Path

import numpy as np
import pyvips
import pytest

from fotoarchiv import labels
from fotoarchiv.faceengine import similarity_transform, ARCFACE_POINTS, _nms
from fotoarchiv.faces import CentroidIndex, FaceService

MODELS = Path(os.environ.get("FOTOARCHIV_MODELS", "")) if os.environ.get("FOTOARCHIV_MODELS") else None
PHOTOS = Path(os.environ.get("FOTOARCHIV_FACE_PHOTOS", "")) if os.environ.get("FOTOARCHIV_FACE_PHOTOS") else None
needs_models = pytest.mark.skipif(
    not (MODELS and (MODELS / "w600k_r50.onnx").is_file() and PHOTOS and PHOTOS.is_dir()),
    reason="Modelle oder Testfotos fehlen",
)


def test_similarity_transform_recovers_rotation_and_scale():
    angle = np.deg2rad(20)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    source = (ARCFACE_POINTS - 56) @ rotation.T * 2.5 + [300, 200]
    matrix = similarity_transform(source.astype(np.float32), ARCFACE_POINTS)
    mapped = source @ matrix[:, :2].T + matrix[:, 2]
    assert np.allclose(mapped, ARCFACE_POINTS, atol=1e-3)


def test_nms_and_centroid_index():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float32)
    assert _nms(boxes, np.array([0.9, 0.8, 0.7]), 0.4) == [0, 2]

    index = CentroidIndex()
    a, b = np.eye(512, dtype=np.float32)[0], np.eye(512, dtype=np.float32)[1]
    for group_id in range(1, 100):  # wächst über die Anfangsgröße hinaus
        index.set(group_id, b * 0.1)
    index.set(500, a * 3)
    assert index.best(a) == (500, pytest.approx(1.0))
    assert index.best(a, exclude=500)[1] == pytest.approx(0.0)
    index.remove(500)
    assert index.best(a)[1] == pytest.approx(0.0)


@pytest.fixture
def service(settings, importer, editor):
    face_service = FaceService(settings, importer.db, editor, enabled=True, models=MODELS)
    face_service.load()
    return face_service


def import_photo(settings, importer, name, *, flip=False, **tags):
    target = settings.import_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if flip:  # gespiegelt = anderer Dateiinhalt, gleiche Person
        pyvips.Image.new_from_file(str(PHOTOS / name)).fliphor().jpegsave(str(target), Q=90)
    else:
        shutil.copy(PHOTOS / name, target)
    if tags:
        importer.exiftool.write(target, *[f"-{k.replace('__', ':')}={v}" for k, v in tags.items()])
    result = importer.import_file(target, name=f"{'gespiegelt-' if flip else ''}{name}")
    assert result.status == "imported", result.message
    return result.asset_id


def persons_of(importer, asset_id):
    with importer.db.transaction() as conn:
        return labels.current(conn, asset_id, "persons")


@needs_models
def test_faces_are_grouped_named_written_and_learned(settings, importer, editor, exiftool, service):
    obama = [import_photo(settings, importer, f"obama_{n}.jpg") for n in (1, 2, 3)]
    both = import_photo(settings, importer, "obama_0.jpg")
    biden = import_photo(settings, importer, "biden_0.jpg")
    while service.work_once():
        pass

    faces = importer.db.query("SELECT asset_id, group_id FROM faces ORDER BY asset_id")
    groups_of = lambda ids: {f["group_id"] for f in faces if f["asset_id"] in ids}  # noqa: E731
    assert len(groups_of(obama)) == 1, "gleiche Person in einer Gruppe"
    obama_group = groups_of(obama).pop()
    assert len([f for f in faces if f["asset_id"] == both]) == 2
    assert groups_of([biden]) < groups_of([both]) and obama_group in groups_of([both])
    assert service.ensure_crop(importer.db.one("SELECT id FROM faces LIMIT 1")["id"]).is_file()

    # Gruppe benennen -> Name landet in allen Dateien
    service.name_group(obama_group, "Barack Obama")
    while service.work_once():
        pass
    for asset_id in obama + [both]:
        assert persons_of(importer, asset_id) == ["Barack Obama"]
    path = settings.library / importer.db.one("SELECT path FROM assets WHERE id = ?", (obama[0],))["path"]
    assert exiftool.read(path)["XMP-iptcExt:PersonInImage"] == "Barack Obama"

    # Neues Foto derselben Person wird automatisch erkannt
    new = import_photo(settings, importer, "obama_4.jpg", flip=True)
    while service.work_once():
        pass
    assert persons_of(importer, new) == ["Barack Obama"]

    # Einzelnes Gesicht benennen
    biden_face = importer.db.one("SELECT id FROM faces WHERE asset_id = ?", (biden,))["id"]
    service.assign_face(biden_face, "Joe Biden")
    assert persons_of(importer, biden) == ["Joe Biden"]
    while service.work_once():
        pass
    assert persons_of(importer, both) == ["Barack Obama", "Joe Biden"], "zweites Gesicht im gemeinsamen Foto gelernt"

    # "Nicht diese Person": Name wird entfernt und kommt nicht zurück
    wrong = importer.db.one("SELECT id FROM faces WHERE asset_id = ?", (obama[2],))["id"]
    service.remove_face(wrong)
    while service.work_once():
        pass
    assert persons_of(importer, obama[2]) == []

    # Person von Hand aus einem Foto entfernt -> Gesicht wird gelöst, Hintergrund schreibt sie nicht zurück
    editor.change_labels(obama[1], "persons", [], ["Barack Obama"])
    importer.db.execute("UPDATE assets SET persons_dirty = 1 WHERE id = ?", (obama[1],))
    while service.work_once():
        pass
    assert persons_of(importer, obama[1]) == []


@needs_models
def test_rotation_keeps_person_and_purge_updates_groups(settings, importer, editor, service):
    asset_id = import_photo(settings, importer, "obama_1.jpg")
    while service.work_once():
        pass
    face = importer.db.one("SELECT id, x, y, group_id FROM faces WHERE asset_id = ?", (asset_id,))
    service.assign_face(face["id"], "Barack Obama")

    editor.rotate(asset_id, 90)
    while service.work_once():
        pass
    rotated = importer.db.one(
        "SELECT f.id, f.x, f.y, p.name FROM faces f JOIN face_groups g ON g.id = f.group_id "
        "JOIN persons p ON p.id = g.person_id WHERE f.asset_id = ?", (asset_id,))
    assert rotated["name"] == "Barack Obama" and rotated["id"] != face["id"]
    assert (round(rotated["x"], 2), round(rotated["y"], 2)) != (round(face["x"], 2), round(face["y"], 2))

    editor.delete(asset_id)
    editor.purge(asset_id)
    assert importer.db.one("SELECT COUNT(*) AS n FROM faces")["n"] == 0
    assert importer.db.one("SELECT COUNT(*) AS n FROM face_groups")["n"] == 0
    # Person bleibt als Name erhalten? Nein: keine Fotos, keine Gesichter -> aufgeräumt
    assert importer.db.one("SELECT COUNT(*) AS n FROM persons")["n"] == 0


@needs_models
def test_rename_person_via_api(settings, make_jpeg):
    from fastapi.testclient import TestClient
    import dataclasses
    from fotoarchiv.main import create_app

    app = create_app(dataclasses.replace(settings, face_recognition=False))
    faces = app.state.faces
    faces.models = MODELS
    faces.enabled = True
    with TestClient(app) as client:
        faces.load()
        importer = app.state.importer
        ids = [import_photo(settings, importer, f"obama_{n}.jpg") for n in (1, 2)]
        while faces.work_once():
            pass
        people = client.get("/api/people").json()
        group = people["groups"][0]
        assert group["count"] == 2 and client.get(f"/api/faces/{group['face_id']}/crop").status_code == 200
        person_id = client.post(f"/api/groups/{group['id']}/name", json={"name": "Obama"}).json()["person_id"]
        while faces.work_once():
            pass
        assert client.get("/api/people").json()["persons"][0]["name"] == "Obama"

        task = client.post(f"/api/persons/{person_id}/rename", json={"name": "Barack Obama"}).json()["task"]
        assert task["total"] == 2
        import time
        for _ in range(200):
            if not any(t["running"] for t in client.get("/api/tasks").json()):
                break
            time.sleep(0.05)
        people = client.get("/api/people").json()
        assert [p["name"] for p in people["persons"]] == ["Barack Obama"]
        assert people["persons"][0]["count"] == 2 and people["persons"][0]["face_id"]
        asset_faces = client.get(f"/api/assets/{ids[0]}/faces").json()
        assert asset_faces[0]["name"] == "Barack Obama"
        assert client.post("/api/faces/999999/remove").status_code == 404
        assert client.get("/api/faces/status").json()["scanned"] == 2
