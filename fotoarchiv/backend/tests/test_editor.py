from datetime import datetime, timedelta

import pyvips
import pytest

from fotoarchiv.editor import TRASH_DIR, EditError, rotated_orientation
from fotoarchiv.media import md5_file


def imported(settings, importer, make_jpeg, name="bild.jpg", **tags):
    source = make_jpeg(settings.import_dir / name, **tags)
    result = importer.import_file(source)
    assert result.status == "imported", result.message
    return result.asset_id


def row(importer, asset_id):
    return importer.db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))


def test_orientation_composition():
    assert rotated_orientation(1, 90) == 6
    assert rotated_orientation(6, 90) == 3
    assert rotated_orientation(3, 90) == 8
    assert rotated_orientation(8, 90) == 1
    assert rotated_orientation(None, 270) == 8
    assert rotated_orientation(2, 90) == 7   # gespiegelt bleibt gespiegelt
    for start in range(1, 9):
        assert rotated_orientation(rotated_orientation(start, 90), 270) == start


def test_set_date_writes_file_moves_and_keeps_import_hash(settings, importer, editor, exiftool, make_jpeg):
    asset_id = imported(settings, importer, make_jpeg, DateTimeOriginal="2019:05:12 14:03:22")
    before = row(importer, asset_id)

    editor.set_date(asset_id, datetime(2003, 8, 9, 7, 6, 5))

    after = row(importer, asset_id)
    path = settings.library / after["path"]
    assert after["path"] == "2003/08/bild.jpg"
    assert not (settings.library / "2019").exists()          # leerer Ordner aufgeräumt
    assert exiftool.read(path)["ExifIFD:DateTimeOriginal"] == "2003:08:09 07:06:05"
    assert (after["taken_at"], after["date_source"]) == ("2003-08-09T07:06:05", "exif")
    assert after["md5"] == md5_file(path) != before["md5"]
    assert after["md5_import"] == before["md5_import"]
    assert after["rev"] == before["rev"] + 1


def test_set_date_on_png_and_video(settings, importer, editor, exiftool, make_video):
    png = settings.import_dir / "grafik.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    (pyvips.Image.black(40, 30, bands=3) + 99).cast("uchar").pngsave(str(png))
    png_id = importer.import_file(png).asset_id
    editor.set_date(png_id, datetime(2010, 1, 2, 3, 4, 5))
    assert row(importer, png_id)["taken_at"] == "2010-01-02T03:04:05"

    video_id = importer.import_file(make_video(settings.import_dir / "clip.mp4")).asset_id
    editor.set_date(video_id, datetime(2019, 7, 1, 12, 0, 0))
    video = row(importer, video_id)
    raw = exiftool.read(settings.library / video["path"])
    assert raw["QuickTime:CreateDate"] == "2019:07:01 10:00:00"  # UTC, Sommerzeit
    assert (video["taken_at"], video["tz_offset"], video["path"]) == ("2019-07-01T12:00:00", "+02:00", "2019/07/clip.mp4")


def test_location_set_and_clear(settings, importer, editor, make_jpeg, make_video):
    asset_id = imported(settings, importer, make_jpeg)
    editor.set_location(asset_id, -33.8568, 151.2153)
    assert (round(row(importer, asset_id)["lat"], 4), round(row(importer, asset_id)["lon"], 4)) == (-33.8568, 151.2153)
    editor.set_location(asset_id, None, None)
    assert row(importer, asset_id)["lat"] is None

    video_id = importer.import_file(make_video(settings.import_dir / "v.mov")).asset_id
    editor.set_location(video_id, 48.1372, 11.5761)
    assert round(row(importer, video_id)["lat"], 4) == 48.1372
    editor.set_location(video_id, None, None)
    assert row(importer, video_id)["lon"] is None


def test_labels_replace_add_remove(settings, importer, editor, exiftool, make_jpeg):
    asset_id = imported(settings, importer, make_jpeg, Keywords=["Alt"])
    editor.set_labels(asset_id, "tags", ["Urlaub", " Straße  am Meer ", "urlaub"])
    path = settings.library / row(importer, asset_id)["path"]
    raw = exiftool.read(path)
    assert raw["XMP-dc:Subject"] == ["Urlaub", "Straße am Meer"]
    assert raw["IPTC:Keywords"] == ["Urlaub", "Straße am Meer"]

    editor.change_labels(asset_id, "tags", add=["Italien"], remove=["urlaub"])
    tags = importer.db.query(
        "SELECT name FROM tags JOIN asset_tags ON tag_id = id WHERE asset_id = ? ORDER BY name", (asset_id,))
    assert [t["name"] for t in tags] == ["Italien", "Straße am Meer"]
    assert importer.db.one("SELECT COUNT(*) AS n FROM tags WHERE name IN ('Alt', 'Urlaub')")["n"] == 0

    md5 = row(importer, asset_id)["md5"]
    editor.change_labels(asset_id, "tags", add=["italien"], remove=[])  # schon vorhanden
    assert row(importer, asset_id)["md5"] == md5                      # Datei unverändert

    editor.set_labels(asset_id, "persons", ["Anna", "Ben"])
    assert exiftool.read(path)["XMP-iptcExt:PersonInImage"] == ["Anna", "Ben"]
    editor.set_labels(asset_id, "tags", [])
    assert "XMP-dc:Subject" not in exiftool.read(path)


def test_person_from_foreign_face_region_can_be_removed_and_renamed(settings, importer, editor, exiftool, make_jpeg):
    # Namen aus Gesichtsmarkierungen anderer Programme (hier MWG, z. B. Picasa/Lightroom)
    asset_id = imported(settings, importer, make_jpeg, **{"XMP-mwg-rs__RegionName": ["Oma", "Kai"]})
    path = settings.library / row(importer, asset_id)["path"]

    editor.change_labels(asset_id, "persons", add=["Kai Müller"], remove=["Kai"])
    raw = exiftool.read(path)
    assert not any(key.startswith("XMP-mwg-rs:") for key in raw)          # fremde Markierungen entfernt
    assert raw["XMP-iptcExt:PersonInImage"] == ["Oma", "Kai Müller"]     # kein Name verloren

    editor.set_labels(asset_id, "persons", [])
    assert "XMP-iptcExt:PersonInImage" not in exiftool.read(path)


def test_rotate_jpeg_updates_orientation_size_and_thumbnail(settings, importer, editor, exiftool, make_jpeg):
    asset_id = imported(settings, importer, make_jpeg)  # 320 × 240
    before = row(importer, asset_id)
    thumb = importer.cache_file(asset_id, "thumb")
    importer.ensure_preview(asset_id)
    importer.ensure_small(asset_id)

    editor.rotate(asset_id, 90)
    after = row(importer, asset_id)
    assert exiftool.read(settings.library / after["path"])["IFD0:Orientation"] == 6
    assert (after["width"], after["height"]) == (240, 320)
    assert pyvips.Image.new_from_file(str(thumb)).height > pyvips.Image.new_from_file(str(thumb)).width
    assert not importer.cache_file(asset_id, "preview").exists()
    assert not importer.cache_file(asset_id, "small").exists()  # wird gedreht neu erzeugt
    assert after["rev"] > before["rev"]

    editor.rotate(asset_id, 270)
    assert exiftool.read(settings.library / after["path"])["IFD0:Orientation"] == 1


def test_rotate_video_and_refuse_heif(settings, importer, editor, exiftool, make_video):
    video_id = importer.import_file(make_video(settings.import_dir / "v.mp4")).asset_id
    editor.rotate(video_id, 90)
    video = row(importer, video_id)
    assert exiftool.read(settings.library / video["path"])["Composite:Rotation"] == 90
    assert (video["width"], video["height"]) == (240, 320)

    avif = settings.import_dir / "bild.avif"
    (pyvips.Image.black(40, 30, bands=3) + 50).cast("uchar").heifsave(str(avif), compression="av1")
    avif_id = importer.import_file(avif).asset_id
    with pytest.raises(EditError, match="AVIF"):
        editor.rotate(avif_id, 90)


def test_trash_restore_purge(settings, importer, editor, make_jpeg):
    asset_id = imported(settings, importer, make_jpeg, DateTimeOriginal="2020:02:02 02:02:02")
    original = settings.library / "2020/02/bild.jpg"

    editor.delete(asset_id)
    trashed = row(importer, asset_id)
    assert trashed["path"] == f"{TRASH_DIR}/2020/02/bild.jpg" and trashed["deleted_at"]
    assert (settings.library / trashed["path"]).is_file() and not original.exists()
    with pytest.raises(EditError):
        editor.set_date(asset_id, datetime(2000, 1, 1))  # gelöschte Bilder nicht bearbeiten

    # Duplikat eines Bildes im Papierkorb wird erkannt
    copy = settings.import_dir / "kopie.jpg"
    copy.write_bytes((settings.library / trashed["path"]).read_bytes())
    assert importer.import_file(copy).message == "im Papierkorb"

    editor.restore(asset_id)
    restored = row(importer, asset_id)
    assert (restored["path"], restored["deleted_at"], restored["orig_path"]) == ("2020/02/bild.jpg", None, None)
    assert original.is_file()
    assert not (settings.library / TRASH_DIR / "2020").exists()

    editor.delete(asset_id)
    importer.ensure_thumbnail(asset_id)
    editor.purge(asset_id)
    assert row(importer, asset_id) is None
    assert not importer.cache_file(asset_id, "thumb").exists()
    assert not any((settings.library / TRASH_DIR).rglob("*.jpg"))


def test_purge_expired_only_old_items(settings, importer, editor, make_jpeg):
    old = imported(settings, importer, make_jpeg, name="alt.jpg")
    new = imported(settings, importer, make_jpeg, name="neu.jpg")
    editor.delete(old)
    editor.delete(new)
    long_ago = (datetime.now() - timedelta(days=31)).isoformat(timespec="seconds")
    importer.db.execute("UPDATE assets SET deleted_at = ? WHERE id = ?", (long_ago, old))

    assert editor.purge_expired(30) == 1
    assert row(importer, old) is None and row(importer, new) is not None


def test_ids_are_never_reused_after_purge(settings, importer, editor, make_jpeg, tmp_path):
    """Bild-URLs enthalten die ID und werden lange gecacht: ein neues Foto darf nie die ID eines gelöschten erben."""
    first = importer.import_file(make_jpeg(tmp_path / "a.jpg")).asset_id
    doomed = importer.import_file(make_jpeg(tmp_path / "b.jpg")).asset_id
    editor.delete(doomed)
    editor.purge(doomed)  # war die höchste ID
    fresh = importer.import_file(make_jpeg(tmp_path / "c.jpg")).asset_id
    assert fresh > doomed > first
