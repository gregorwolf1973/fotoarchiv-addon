"""Favoritenordner: anlegen, umbenennen, Fotos verlinken und wieder herausnehmen."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fotoarchiv import favorites_api
from fotoarchiv.api import AssetFilter
from fotoarchiv.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "fotoarchiv.db")
    for asset_id in (1, 2, 3):
        database.execute(
            """INSERT INTO assets (id, path, kind, size, md5, md5_import, taken_ts, date_source, imported_at)
               VALUES (?, ?, 'image', 1, 'x', 'x', ?, 'exif', '2026-01-01')""", (asset_id, f"{asset_id}.jpg", asset_id))
    yield database
    database.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    favorites_api.register(app, db)
    return TestClient(app)


def folder_ids(db, folder_id):
    where, params = AssetFilter(tag=[], person=[], folder=folder_id).clause()
    return [r["id"] for r in db.query(f"SELECT id FROM assets a WHERE {where} ORDER BY id", params)]


def test_create_rename_and_unique_names(client):
    folder = client.post("/api/favorites", json={"name": "  Urlaub   2025 "}).json()
    assert folder["name"] == "Urlaub 2025"
    assert client.post("/api/favorites", json={"name": "urlaub 2025"}).status_code == 409
    other = client.post("/api/favorites", json={"name": "Familie"}).json()
    assert client.post(f"/api/favorites/{other['id']}/rename", json={"name": "URLAUB 2025"}).status_code == 409
    assert client.post(f"/api/favorites/{folder['id']}/rename", json={"name": "Sommer"}).status_code == 200
    assert client.post("/api/favorites", json={"name": "   "}).status_code == 400
    assert [f["name"] for f in client.get("/api/favorites").json()] == ["Familie", "Sommer"]
    assert client.post("/api/favorites/999/rename", json={"name": "x"}).status_code == 404


def test_add_remove_and_filter(client, db):
    folder = client.post("/api/favorites", json={"name": "Best of"}).json()
    assert client.post(f"/api/favorites/{folder['id']}/add", json={"ids": [1, 2, 99]}).json() == {"added": 2, "already": 0}
    assert client.post(f"/api/favorites/{folder['id']}/add", json={"ids": [2, 3]}).json() == {"added": 1, "already": 1}
    assert folder_ids(db, folder["id"]) == [1, 2, 3]

    listed = client.get("/api/favorites").json()[0]
    assert listed["count"] == 3 and listed["cover"][0] in (2, 3)

    assert client.post(f"/api/favorites/{folder['id']}/remove", json={"ids": [2]}).json() == {"removed": 1}
    assert folder_ids(db, folder["id"]) == [1, 3]

    # Fotos im Papierkorb zählen nicht und erscheinen nicht im Ordner, der Verweis bleibt für die Wiederherstellung
    db.execute("UPDATE assets SET deleted_at = '2026-01-02' WHERE id = 3")
    assert client.get("/api/favorites").json()[0]["count"] == 1
    assert folder_ids(db, folder["id"]) == [1]


def test_delete_folder_keeps_photos(client, db):
    folder = client.post("/api/favorites", json={"name": "Weg damit"}).json()
    client.post(f"/api/favorites/{folder['id']}/add", json={"ids": [1]})
    assert client.post(f"/api/favorites/{folder['id']}/delete").json() == {"deleted": True}
    assert client.get("/api/favorites").json() == []
    assert db.one("SELECT COUNT(*) AS n FROM favorite_items")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM assets")["n"] == 3
