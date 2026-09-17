import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from fotoarchiv.main import create_app


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_upload_index_detail_and_files(client, settings, make_jpeg, tmp_path):
    photo = make_jpeg(tmp_path / "IMG_20220815_120000.jpg", width=400, height=300, Keywords="Sommer")
    body = photo.read_bytes()

    r = client.put("/api/upload", params={"name": photo.name, "mtime": 1660557600000}, content=body)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["status"] == "imported"
    assert (settings.library / "2022" / "08" / photo.name).is_file()
    assert not any(settings.upload_tmp.iterdir())

    again = client.put("/api/upload", params={"name": "anders.jpg"}, content=body).json()
    assert (again["status"], again["existing"]) == ("duplicate", f"2022/08/{photo.name}")
    assert not any(settings.upload_tmp.iterdir())

    index = client.get("/api/assets").json()
    assert index["items"] == [[first["asset_id"], index["items"][0][1], 400, 300, 0, 1]]

    detail = client.get(f"/api/assets/{first['asset_id']}").json()
    assert detail["tags"] == ["Sommer"]
    assert detail["date_source"] == "filename"
    assert detail["name"] == photo.name

    thumb = client.get(f"/api/assets/{first['asset_id']}/thumb")
    assert thumb.headers["content-type"] == "image/webp"
    assert "content-encoding" not in thumb.headers
    assert client.get(f"/api/assets/{first['asset_id']}/preview").status_code == 200

    original = client.get(f"/api/assets/{first['asset_id']}/original", headers={"Range": "bytes=0-9"})
    assert original.status_code == 206 and original.content == body[:10]

    state = client.get("/api/state").json()
    assert state["counts"]["total"] == 1


def test_upload_rejects_unsupported_type(client):
    assert client.put("/api/upload", params={"name": "virus.exe"}, content=b"x").status_code == 415


def test_import_endpoint(client, settings, make_jpeg):
    make_jpeg(settings.import_dir / "a.jpg")
    assert client.post("/api/import", json={"mode": "import"}).status_code == 200
    importer = client.app.state.importer
    for _ in range(200):
        if not importer.job.running:
            break
        time.sleep(0.05)
    status = client.get("/api/import").json()
    assert status["counts"]["imported"] == 1
    assert client.post("/api/import", json={"mode": "quatsch"}).status_code == 400


def test_only_ingress_may_connect(settings):
    locked = dataclasses.replace(settings, dev=False)
    with TestClient(create_app(locked)) as c:  # TestClient meldet sich als "testclient"
        assert c.get("/api/state").status_code == 403
