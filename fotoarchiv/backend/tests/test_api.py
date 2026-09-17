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
    small = client.get(f"/api/assets/{first['asset_id']}/thumb", params={"size": "small"})
    import pyvips
    assert pyvips.Image.new_from_buffer(small.content, "").height == 160
    assert len(small.content) < len(thumb.content)
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
    assert client.post("/api/import", json={"mode": "quatsch"}).status_code == 422


def test_only_ingress_may_connect(settings):
    locked = dataclasses.replace(settings, dev=False)
    with TestClient(create_app(locked)) as c:  # TestClient meldet sich als "testclient"
        assert c.get("/api/state").status_code == 403


def wait_for_tasks(client):
    for _ in range(400):
        if not any(t["running"] for t in client.get("/api/tasks").json()):
            return client.get("/api/tasks").json()[0]
        time.sleep(0.05)
    raise AssertionError("Aufgabe hängt")


def upload(client, make_jpeg, tmp_path, name, **tags):
    photo = make_jpeg(tmp_path / "quelle" / name, **tags)
    return client.put("/api/upload", params={"name": name}, content=photo.read_bytes()).json()["asset_id"]


def test_edit_filter_batch_and_trash(client, make_jpeg, tmp_path):
    a = upload(client, make_jpeg, tmp_path, "a.jpg", DateTimeOriginal="2019:05:12 10:00:00", Keywords=["Urlaub", "Strand"])
    b = upload(client, make_jpeg, tmp_path, "b.jpg", DateTimeOriginal="2019:08:01 10:00:00", Keywords="Urlaub")
    c = upload(client, make_jpeg, tmp_path, "c.jpg", DateTimeOriginal="2021:01:01 10:00:00")

    ids = lambda **params: [item[0] for item in client.get("/api/assets", params=params).json()["items"]]  # noqa: E731
    labels = client.get("/api/labels").json()
    tag = {t["name"]: t for t in labels["tags"]}
    assert tag["Urlaub"]["count"] == 2

    assert ids(tag=[tag["Urlaub"]["id"]]) == [b, a]
    assert ids(tag=[tag["Urlaub"]["id"], tag["Strand"]["id"]]) == [a]
    assert ids(start="2019-05-12", end="2019-05-12") == [a]
    assert ids(q="stra") == [a]
    assert ids(q="c.jpg") == [c]

    # Einzelbearbeitung
    detail = client.patch(f"/api/assets/{c}", json={"persons": ["Anna"], "taken_at": "2018-03-04T05:06:07"}).json()
    assert detail["persons"] == ["Anna"] and detail["taken_at"] == "2018-03-04T05:06:07"
    assert detail["path"] == "2018/03/c.jpg" and detail["editable"] and detail["rotatable"]
    person = client.get("/api/labels").json()["persons"][0]
    assert ids(person=[person["id"]]) == [c]
    assert client.patch(f"/api/assets/{c}", json={"location": {"lat": 47.5, "lon": 11.1}}).json()["lat"] == 47.5
    assert client.patch(f"/api/assets/{c}", json={"location": None}).json()["lat"] is None
    assert client.post(f"/api/assets/{c}/rotate", json={"degrees": 90}).json()["width"] == 240

    # Mehrfachauswahl
    task = client.post("/api/batch", json={"ids": [a, b, c], "action": "tags", "add": ["Familie"], "remove": ["Urlaub"]}).json()
    assert task["total"] == 3
    done = wait_for_tasks(client)
    assert done["done"] == 3 and done["failed"] == []
    names = {t["name"]: t["count"] for t in client.get("/api/labels").json()["tags"]}
    assert names == {"Familie": 3, "Strand": 1}

    # Papierkorb
    assert client.delete(f"/api/assets/{a}").json() == {"deleted": True}
    assert a not in ids() and ids(trash=True) == [a]
    trashed = client.get(f"/api/assets/{a}").json()
    assert trashed["expires_at"] and client.get(f"/api/assets/{a}/thumb").status_code == 200
    assert client.get("/api/state").json()["counts"]["trash"] == 1
    assert client.patch(f"/api/assets/{a}", json={"tags": []}).status_code == 422

    client.post(f"/api/assets/{a}/restore")
    assert ids(trash=True) == []
    client.post("/api/batch", json={"ids": [a, b], "action": "delete"})
    wait_for_tasks(client)
    assert client.post("/api/trash/empty").json()["total"] == 2
    wait_for_tasks(client)
    assert ids(trash=True) == [] and ids() == [c]
    assert client.post("/api/trash/empty").status_code == 400


def test_geo_located_filter_and_batch_location(client, settings, make_jpeg, tmp_path):
    placed = upload(client, make_jpeg, tmp_path, "da.jpg", DateTimeOriginal="2020:01:01 10:00:00",
                    GPSLatitude=47.2692, GPSLatitudeRef="N", GPSLongitude=11.4041, GPSLongitudeRef="E")
    first = upload(client, make_jpeg, tmp_path, "weg1.jpg", DateTimeOriginal="2020:02:01 10:00:00")
    second = upload(client, make_jpeg, tmp_path, "weg2.jpg", DateTimeOriginal="2020:03:01 10:00:00")
    gif = settings.import_dir / "anim.gif"
    gif.parent.mkdir(parents=True, exist_ok=True)
    import pyvips
    (pyvips.Image.black(20, 20, bands=3) + 70).cast("uchar").gifsave(str(gif))
    gif_id = client.app.state.importer.import_file(gif).asset_id

    ids = lambda **params: [item[0] for item in client.get("/api/assets", params=params).json()["items"]]  # noqa: E731
    assert ids(located=True) == [placed]
    assert set(ids(located=False)) == {first, second, gif_id}
    assert ids(located=False, editable=True) == [second, first]
    assert ids(editable=False) == [gif_id]

    geo = client.get("/api/geo").json()
    assert geo["fields"][-2:] == ["lat", "lon"]
    assert [(i[0], round(i[6], 3), round(i[7], 3)) for i in geo["items"]] == [(placed, 47.269, 11.404)]

    assert client.post("/api/batch", json={"ids": [first], "action": "location"}).status_code == 400
    task = client.post("/api/batch", json={"ids": [first, second, gif_id], "action": "location",
                                           "location": {"lat": -33.8568, "lon": 151.2153}}).json()
    assert task["label"] == "Ort bei 3 Dateien setzen"
    done = wait_for_tasks(client)
    assert done["done"] == 3 and len(done["failed"]) == 1 and "GIF" in done["failed"][0]["message"]
    assert {i[0] for i in client.get("/api/geo").json()["items"]} == {placed, first, second}

    client.post("/api/batch", json={"ids": [first], "action": "location", "location": None})
    wait_for_tasks(client)
    assert first in ids(located=False)


def test_remove_missing_entries_with_safety_check(client, settings, make_jpeg, tmp_path):
    keep = upload(client, make_jpeg, tmp_path, "keep.jpg", DateTimeOriginal="2021:01:01 10:00:00")
    gone = upload(client, make_jpeg, tmp_path, "gone.jpg", DateTimeOriginal="2021:01:02 10:00:00")
    assert client.post("/api/library/remove-missing").status_code == 400      # noch fehlt nichts

    (settings.library / "2021/01/gone.jpg").unlink()
    task = client.post("/api/library/remove-missing").json()
    assert task["total"] == 1
    wait_for_tasks(client)
    assert [i[0] for i in client.get("/api/assets").json()["items"]] == [keep]
    assert client.get(f"/api/assets/{gone}").status_code == 404

    # Laufwerk "nicht eingebunden": nichts löschen
    (settings.library / "2021/01/keep.jpg").unlink()
    response = client.post("/api/library/remove-missing")
    assert response.status_code == 409 and "Laufwerk" in response.json()["detail"]
    assert client.get(f"/api/assets/{keep}").status_code == 200


def test_merge_persons(client, make_jpeg, tmp_path):
    a = upload(client, make_jpeg, tmp_path, "a.jpg", **{"XMP-iptcExt__PersonInImage": "Anna"})
    b = upload(client, make_jpeg, tmp_path, "b.jpg", **{"XMP-iptcExt__PersonInImage": "Anna Müller"})
    c = upload(client, make_jpeg, tmp_path, "c.jpg", **{"XMP-iptcExt__PersonInImage": "Anna"})
    persons = {p["name"]: p["id"] for p in client.get("/api/labels").json()["persons"]}

    assert client.post(f"/api/persons/{persons['Anna']}/merge", json={"target_id": persons["Anna"]}).status_code == 400
    assert client.post(f"/api/persons/{persons['Anna']}/merge", json={"target_id": 99999}).status_code == 404
    task = client.post(f"/api/persons/{persons['Anna']}/merge", json={"target_id": persons["Anna Müller"]}).json()["task"]
    assert task["label"] == "„Anna“ mit „Anna Müller“ zusammenführen" and task["total"] == 2
    wait_for_tasks(client)

    for asset_id in (a, b, c):
        assert client.get(f"/api/assets/{asset_id}").json()["persons"] == ["Anna Müller"]
    assert [(p["name"], p["count"]) for p in client.get("/api/labels").json()["persons"]] == [("Anna Müller", 3)]
