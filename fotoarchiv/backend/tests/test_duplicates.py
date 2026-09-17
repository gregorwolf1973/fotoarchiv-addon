import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from fotoarchiv.duplicates import DuplicateService, phash
from fotoarchiv.main import create_app


def pattern(path, seed, width=640, height=480, quality=92):
    """Foto mit grober Struktur (zufällige Kacheln, weich gezeichnet) – gleiche Saat = gleiches Motiv."""
    import pyvips

    rng = np.random.default_rng(seed)
    tiles = rng.integers(0, 256, size=(6, 8, 3), dtype=np.uint8)
    image = pyvips.Image.new_from_array(tiles).resize(width / 8, vscale=height / 6, kernel="linear").gaussblur(8)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.cast("uchar").copy(interpretation="srgb").jpegsave(str(path), Q=quality)
    return path


def distance(a, b):
    return (phash(a) ^ phash(b)).bit_count()


def test_phash_survives_resize_and_recompression(tmp_path):
    original = pattern(tmp_path / "a.jpg", seed=1)
    copy = pattern(tmp_path / "a-klein.jpg", seed=1, width=320, height=240, quality=55)
    other = pattern(tmp_path / "b.jpg", seed=2)
    assert distance(original, copy) <= 4
    assert distance(original, other) > 12


@pytest.fixture
def service(settings, importer, editor):
    return DuplicateService(settings, importer.db, importer, editor)


def add(importer, tmp_path, name, **extra):
    path = pattern(tmp_path / "quelle" / name, seed=sum(map(ord, name)))
    result = importer.import_upload(path, name, None)
    assert result.status == "imported", result
    if extra:
        sets = ", ".join(f"{key} = ?" for key in extra)
        importer.db.execute(f"UPDATE assets SET {sets} WHERE id = ?", (*extra.values(), result.asset_id))
    return result.asset_id


def test_groups_series_and_ignore(service, importer, tmp_path):
    db = importer.db
    base = 0x0123_4567_89AB_CDEF
    a = add(importer, tmp_path, "a.jpg", phash=f"{base:016x}", taken_ts=1000, width=4000, height=3000)
    b = add(importer, tmp_path, "b.jpg", phash=f"{base ^ 0b111:016x}", taken_ts=900_000, width=800, height=600)
    # Serie: 10 Bit Abstand, 5 Sekunden später
    c = add(importer, tmp_path, "c.jpg", phash=f"{base ^ 0x3FF000:016x}", taken_ts=1005, size=999_999_999)
    # gleich weit entfernt, aber eine Stunde später: keine Serie
    add(importer, tmp_path, "d.jpg", phash=f"{base ^ 0x3FF00000000:016x}", taken_ts=4600)
    db.bump()

    result = service.groups()
    assert (result["images"], result["hashed"]) == (4, 4)
    [duplicate] = result["duplicates"]
    assert [i["id"] for i in duplicate["items"]] == [a, b]
    assert duplicate["keep"] == a  # höhere Auflösung
    [series] = result["series"]
    assert [i["id"] for i in series["items"]] == [a, c]  # b liegt zeitlich woanders
    assert series["keep"] == c  # größte Datei

    service.ignore([a, b])
    result = service.groups()
    assert result["duplicates"] == []
    assert {i["id"] for i in result["series"][0]["items"]} == {a, c}


def test_import_hint_for_similar_photo(service, importer, tmp_path):
    first = importer.import_upload(pattern(tmp_path / "q" / "gross.jpg", seed=5), "gross.jpg", None)
    assert first.similar is None
    small = pattern(tmp_path / "q" / "klein.jpg", seed=5, width=320, height=240, quality=50)
    second = importer.import_upload(small, "klein.jpg", None)
    assert second.status == "imported"
    assert second.similar == first.message
    third = importer.import_upload(pattern(tmp_path / "q" / "anders.jpg", seed=6), "anders.jpg", None)
    assert third.similar is None


def test_resolve_transfers_metadata_and_trashes(service, importer, editor, tmp_path):
    keep = importer.import_upload(pattern(tmp_path / "q" / "k.jpg", seed=7), "k.jpg", None).asset_id
    source = pattern(tmp_path / "q" / "IMG_20190512_100000.jpg", seed=7, width=320, height=240)
    removed = importer.import_upload(source, source.name, None).asset_id
    editor.change_labels(removed, "tags", ["Urlaub"], [])
    editor.change_labels(removed, "persons", ["Oma"], [])
    editor.set_location(removed, 47.5, 11.1)

    service.resolve_one(removed, keep, transfer=True)

    row = importer.db.one("SELECT * FROM assets WHERE id = ?", (keep,))
    assert (row["lat"], row["lon"]) == pytest.approx((47.5, 11.1))
    assert row["date_source"] == "exif" and row["taken_at"].startswith("2019-05-12T10:00")
    meta = importer.db.one("SELECT deleted_at FROM assets WHERE id = ?", (removed,))
    assert meta["deleted_at"] is not None
    tags = importer.exiftool.read(importer.settings.library / row["path"])
    assert "Urlaub" in str(tags.get("XMP-dc:Subject")) and "Oma" in str(tags.get("XMP-iptcExt:PersonInImage"))

    with pytest.raises(Exception):
        service.resolve_one(removed, keep, transfer=True)  # schon im Papierkorb


def test_api_resolve_and_permissions(settings, tmp_path):
    with TestClient(create_app(settings)) as client:
        big = pattern(tmp_path / "q" / "gross.jpg", seed=9)
        small = pattern(tmp_path / "q" / "klein.jpg", seed=9, width=300, height=225, quality=50)
        a = client.put("/api/upload", params={"name": big.name}, content=big.read_bytes()).json()
        b = client.put("/api/upload", params={"name": small.name}, content=small.read_bytes()).json()
        assert b["similar"] == a["message"]

        groups = client.get("/api/duplicates").json()
        assert groups["enabled"] is True
        [group] = groups["duplicates"]
        assert group["keep"] == a["asset_id"]

        bad = {"groups": [{"keep": [a["asset_id"]], "remove": [a["asset_id"]]}]}
        assert client.post("/api/duplicates/resolve", json=bad).status_code == 400

        body = {"groups": [{"keep": [a["asset_id"]], "remove": [b["asset_id"]]}], "transfer": True}
        task = client.post("/api/duplicates/resolve", json=body).json()
        assert task["kind"] == "dedupe"
        for _ in range(400):
            done = client.get("/api/tasks").json()[0]
            if not done["running"]:
                break
            time.sleep(0.05)
        assert done["failed"] == [] and done["done"] == 1
        assert client.get("/api/duplicates").json()["duplicates"] == []
        assert client.get("/api/state").json()["counts"]["trash"] == 1

    from fotoarchiv.public import EDIT
    assert {"duplicate_list", "duplicate_resolve", "duplicate_ignore"} <= EDIT
