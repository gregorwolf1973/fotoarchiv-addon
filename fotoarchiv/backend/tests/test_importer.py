import shutil

from fotoarchiv.editor import TRASH_DIR
from fotoarchiv.importer import DUPLICATE_DIR, safe_name

# Begleitdatei, wie digiKam und darktable sie neben Videos legen, die selbst nichts speichern können
SIDECAR = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:exif="http://ns.adobe.com/exif/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
    exif:DateTimeOriginal="2013-04-01T14:15:15"
    exif:GPSLatitude="47,30.000000N"
    exif:GPSLongitude="9,45.000000E">
   <dc:subject><rdf:Bag><rdf:li>Urlaub</rdf:li><rdf:li>Strand</rdf:li></rdf:Bag></dc:subject>
   <Iptc4xmpExt:PersonInImage><rdf:Bag><rdf:li>Anna</rdf:li></rdf:Bag></Iptc4xmpExt:PersonInImage>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def test_import_folder_sorts_deduplicates_and_cleans_up(settings, importer, make_jpeg):
    inbox = settings.import_dir
    make_jpeg(
        inbox / "Urlaub" / "strand.jpg",
        DateTimeOriginal="2019:05:12 14:03:22",
        GPSLatitude=48.137154, GPSLatitudeRef="N", GPSLongitude=11.576124, GPSLongitudeRef="E",
        Keywords=["Urlaub", "Strand"], **{"XMP-iptcExt__PersonInImage": "Anna"},
    )
    make_jpeg(inbox / "IMG_20200101_101010.jpg")
    shutil.copy(inbox / "Urlaub" / "strand.jpg", inbox / "Urlaub" / "strand_kopie.jpg")
    (inbox / "notiz.txt").write_text("kein Bild")

    importer._run("import")
    job = importer.job

    assert job.counts == {"imported": 2, "relinked": 0, "duplicate": 1, "damaged": 0, "skipped": 1, "error": 0,
                          "missing": 0, "similar": 0}
    assert (settings.library / "2019" / "05" / "strand.jpg").is_file()
    assert (settings.library / "2020" / "01" / "IMG_20200101_101010.jpg").is_file()
    assert (inbox / DUPLICATE_DIR / "Urlaub" / "strand_kopie.jpg").is_file()
    assert job.duplicates[0]["existing"] == "2019/05/strand.jpg"
    assert (inbox / "notiz.txt").is_file()            # nicht unterstützt: bleibt liegen
    assert not (inbox / "Urlaub").exists()             # leerer Unterordner entfernt

    row = importer.db.one("SELECT * FROM assets WHERE path = '2019/05/strand.jpg'")
    assert row["taken_at"] == "2019-05-12T14:03:22"
    assert row["date_source"] == "exif"
    assert (round(row["lat"], 4), round(row["lon"], 4)) == (48.1372, 11.5761)
    assert (row["width"], row["height"], row["thumb_ok"]) == (320, 240, 1)
    assert importer.cache_file(row["id"], "thumb").is_file()
    tags = [r["name"] for r in importer.db.query(
        "SELECT name FROM tags JOIN asset_tags ON tag_id = id WHERE asset_id = ? ORDER BY name", (row["id"],))]
    assert tags == ["Strand", "Urlaub"]
    assert importer.db.one("SELECT name FROM persons")["name"] == "Anna"

    other = importer.db.one("SELECT * FROM assets WHERE path LIKE '2020/%'")
    assert (other["taken_at"], other["date_source"]) == ("2020-01-01T10:10:10", "filename")

    report = importer.__class__(settings, importer.db, importer.exiftool).job  # nach Neustart noch da
    assert report.counts["imported"] == 2 and not report.running


def test_duplicate_found_after_file_was_edited(settings, importer, make_jpeg):
    original = make_jpeg(settings.import_dir / "a.jpg")
    backup = settings.data / "a.jpg"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(original, backup)

    assert importer.import_file(original).status == "imported"
    importer.db.execute("UPDATE assets SET md5 = 'nach-bearbeitung'")  # Datei wurde verändert

    result = importer.import_file(backup, move=False)
    assert (result.status, result.existing) == ("duplicate", importer.db.one("SELECT path FROM assets")["path"])


def test_same_name_gets_suffix(settings, importer, make_jpeg):
    for folder in ("x", "y"):
        make_jpeg(settings.import_dir / folder / "bild.jpg", DateTimeOriginal="2021:03:04 05:06:07")
        assert importer.import_file(settings.import_dir / folder / "bild.jpg").status == "imported"
    names = sorted(p.name for p in (settings.library / "2021" / "03").iterdir())
    assert names == ["bild.jpg", "bild_1.jpg"]


def test_library_scan_indexes_in_place(settings, importer, make_jpeg):
    make_jpeg(settings.library / "Alt" / "foto.jpg")
    make_jpeg(settings.library / ".upload" / "halb.jpg")  # versteckte Ordner ignorieren

    importer._run("library")
    assert importer.job.counts["imported"] == 1
    assert importer.db.one("SELECT path FROM assets")["path"] == "Alt/foto.jpg"
    assert (settings.library / "Alt" / "foto.jpg").is_file()

    importer._run("library")  # zweiter Lauf findet nichts Neues
    assert importer.job.total == 0


def test_safe_name():
    assert safe_name("..\\..\\böse:name?.JPG") == "böse_name_.jpg"
    assert safe_name("../.jpg") == "bild.jpg"


def test_reimport_after_manual_delete_relinks_entry(settings, importer, make_jpeg):
    source = make_jpeg(settings.import_dir / "urlaub.jpg", DateTimeOriginal="2019:05:12 14:03:22", Keywords="Strand")
    backup = settings.data / "sicherung.jpg"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, backup)
    first = importer.import_file(source)
    importer.ensure_preview(first.asset_id)
    (settings.library / "2019/05/urlaub.jpg").unlink()            # von Hand gelöscht

    again = settings.import_dir / "urlaub-wieder.jpg"
    shutil.copy(backup, again)
    result = importer.import_file(again)

    assert (result.status, result.asset_id, result.existing) == ("relinked", first.asset_id, "2019/05/urlaub.jpg")
    row = importer.db.one("SELECT * FROM assets WHERE id = ?", (first.asset_id,))
    assert row["path"] == "2019/05/urlaub-wieder.jpg" and row["rev"] == 2
    assert importer.cache_file(first.asset_id, "thumb").is_file()
    assert not importer.cache_file(first.asset_id, "preview").exists()   # alte Großansicht verworfen
    assert importer.db.one("SELECT COUNT(*) AS n FROM assets")["n"] == 1


def test_library_sync_relinks_moved_and_reports_missing(settings, importer, make_jpeg):
    for name in ("bleibt.jpg", "verschoben.jpg", "geloescht.jpg"):
        importer.import_file(make_jpeg(settings.import_dir / name, DateTimeOriginal="2020:06:01 12:00:00", Keywords=name))
    # ohne EXIF: Datum kommt nur aus dem Dateinamen
    importer.import_file(make_jpeg(settings.import_dir / "IMG_20110304_050607.jpg"))
    shutil.move(settings.library / "2011/03/IMG_20110304_050607.jpg", settings.library / "Ferien.jpg")
    folder = settings.library / "2020" / "06"
    (settings.library / "Sortiert").mkdir()
    shutil.move(folder / "verschoben.jpg", settings.library / "Sortiert" / "neu.jpg")
    (folder / "geloescht.jpg").unlink()

    importer._run("library")
    job = importer.job

    assert job.counts["relinked"] == 2 and job.counts["imported"] == 0 and job.counts["duplicate"] == 0
    assert sorted(e["existing"] for e in job.relinked) == ["2011/03/IMG_20110304_050607.jpg", "2020/06/verschoben.jpg"]
    renamed = importer.db.one("SELECT taken_at, date_source FROM assets WHERE path = 'Ferien.jpg'")
    assert (renamed["taken_at"], renamed["date_source"]) == ("2011-03-04T05:06:07", "filename")
    assert job.counts["missing"] == 1 and job.missing[0]["name"] == "2020/06/geloescht.jpg"
    moved = importer.db.one("SELECT path FROM assets a JOIN asset_tags l ON l.asset_id = a.id "
                            "JOIN tags t ON t.id = l.tag_id WHERE t.name = 'verschoben.jpg'")
    assert moved["path"] == "Sortiert/neu.jpg"                         # Schlagwort blieb erhalten


def test_damaged_files_go_to_defekt_folder(settings, importer, make_jpeg):
    from fotoarchiv.importer import DAMAGED_DIR

    inbox = settings.import_dir / "urlaub"
    inbox.mkdir(parents=True)
    (inbox / "abgebrochen.jpg").write_bytes(b"\x00" * 8192)
    make_jpeg(inbox / "heil.jpg")
    importer._run("import")
    job = importer.job
    assert job.counts["damaged"] == 1 and job.counts["imported"] == 1
    assert job.damaged[0]["name"] == "urlaub/abgebrochen.jpg" and "nicht lesbar" in job.damaged[0]["message"]
    assert (settings.import_dir / DAMAGED_DIR / "urlaub" / "abgebrochen.jpg").is_file()
    importer._run("import")  # zweiter Lauf fasst _defekt nicht an
    assert importer.job.total == 0


def test_files_still_being_copied_wait_for_next_import(settings, importer, make_jpeg):
    import dataclasses
    import os

    from fotoarchiv.importer import Importer

    patient = Importer(dataclasses.replace(settings, import_quiet_seconds=60), importer.db, importer.exiftool)
    photo = make_jpeg(settings.import_dir / "frisch.jpg")
    patient._run("import")
    assert patient.job.counts["skipped"] == 1 and "noch kopiert" in patient.job.skipped[0]["message"]
    assert photo.is_file()

    old = photo.stat().st_mtime - 3600  # Windows setzt am Ende des Kopierens das alte Datum
    os.utime(photo, (old, old))
    patient._run("import")
    assert patient.job.counts["imported"] == 1 and not photo.exists()


def test_move_across_filesystems_keeps_source_if_it_changes(tmp_path, monkeypatch):
    import errno
    import os
    import shutil

    import pytest
    from fotoarchiv import importer as module

    def cross_device(*args):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "replace", cross_device)
    source, target = tmp_path / "share" / "clip.mp4", tmp_path / "media" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"a" * 1000)

    real_copy = shutil.copy2

    def copy_while_samba_writes(src, dst):
        real_copy(src, dst)
        with open(src, "ab") as f:  # Samba schreibt weiter
            f.write(b"b" * 1000)

    monkeypatch.setattr(module.shutil, "copy2", copy_while_samba_writes)
    with pytest.raises(OSError, match="während des Kopierens"):
        module.move_file(source, target)
    assert source.stat().st_size == 2000 and not target.exists()  # nichts verloren, nichts halb

    monkeypatch.setattr(module.shutil, "copy2", real_copy)
    module.move_file(source, target)  # fertig geschrieben: klappt
    assert target.stat().st_size == 2000 and not source.exists()


def deep_check(importer):
    """Wie ein Klick auf „Bibliothek abgleichen“ mit gründlicher Prüfung: frischer Bericht je Lauf."""
    from fotoarchiv.importer import Job

    importer.job = Job(mode="library", deep=True, running=True)
    importer._run("library", deep=True)
    return importer.job


def test_deep_check_finds_truncated_and_changed_files(settings, importer, make_jpeg):
    folder = settings.library / "2019" / "05"
    good = make_jpeg(folder / "heil.jpg", width=800, height=600)
    half = make_jpeg(folder / "halb.jpg", width=800, height=600)
    data = half.read_bytes()
    half.write_bytes(data[: len(data) // 2])  # Kopf heil, Rest fehlt: fällt erst beim Dekodieren auf

    importer._run("library")  # normaler Abgleich merkt nichts
    assert importer.job.counts["damaged"] == 0

    job = deep_check(importer)
    assert job.counts["checked"] == 2 and job.counts["damaged"] == 1 and job.counts["changed"] == 0
    assert job.damaged[0]["name"] == "2019/05/halb.jpg" and "nicht vollständig" in job.damaged[0]["message"]
    rows = {r["path"]: r["damaged"] for r in importer.db.query("SELECT path, damaged FROM assets")}
    assert rows["2019/05/heil.jpg"] is None and rows["2019/05/halb.jpg"]

    with open(good, "ab") as f:  # außerhalb verändert (hier: angehängte Bytes, Bild bleibt lesbar)
        f.write(b"\x00" * 16)
    job = deep_check(importer)
    assert job.counts["changed"] == 1 and job.changed[0]["name"] == "2019/05/heil.jpg"
    assert deep_check(importer).counts["changed"] == 0  # nur einmal melden


def test_deep_check_can_be_cancelled(settings, importer, make_jpeg):
    make_jpeg(settings.library / "2020" / "01" / "a.jpg")
    importer._run("library")
    importer._cancel.set()
    importer._check_files()
    assert importer.job.cancelled and importer.job.counts["checked"] == 0


def test_sidecar_is_read_and_travels_with_the_video(settings, importer, make_video):
    """AVI kann selbst keine Metadaten aufnehmen – sie stehen in der Begleitdatei daneben."""
    video = make_video(settings.import_dir / "urlaub.avi")  # Dateiname ohne Datum: alles kommt aus der XMP
    (settings.import_dir / "urlaub.avi.xmp").write_text(SIDECAR, encoding="utf-8")

    result = importer.import_file(video)
    assert result.status == "imported"

    row = importer.db.one("SELECT * FROM assets WHERE id = ?", (result.asset_id,))
    assert (row["taken_at"], row["date_source"]) == ("2013-04-01T14:15:15", "exif")
    assert (round(row["lat"], 4), round(row["lon"], 4)) == (47.5, 9.75)
    tags = [r["name"] for r in importer.db.query(
        "SELECT name FROM tags JOIN asset_tags ON tag_id = id WHERE asset_id = ? ORDER BY name", (row["id"],))]
    assert tags == ["Strand", "Urlaub"]
    assert importer.db.one("SELECT name FROM persons")["name"] == "Anna"

    moved = settings.library / row["path"]
    assert moved.parent == settings.library / "2013" / "04"       # nach dem Datum aus der Begleitdatei einsortiert
    assert moved.with_name(moved.name + ".xmp").is_file()          # mitgewandert
    assert not (settings.import_dir / "urlaub.avi.xmp").exists()


def test_sidecar_is_not_reported_as_unsupported(settings, importer, make_jpeg):
    make_jpeg(settings.import_dir / "a.jpg")
    (settings.import_dir / "a.jpg.xmp").write_text(SIDECAR, encoding="utf-8")

    importer._run("import")

    assert (importer.job.counts["imported"], importer.job.counts["skipped"]) == (1, 0)
    assert (settings.library / "2013" / "04" / "a.jpg.xmp").is_file()


def test_sidecar_follows_the_file_into_the_trash_and_is_purged_with_it(settings, importer, editor, make_jpeg):
    source = make_jpeg(settings.import_dir / "a.jpg")
    (settings.import_dir / "a.jpg.xmp").write_text(SIDECAR, encoding="utf-8")
    asset_id = importer.import_file(source).asset_id

    def companion() -> bool:
        path = settings.library / importer.db.one("SELECT path FROM assets WHERE id = ?", (asset_id,))["path"]
        return path.with_name(path.name + ".xmp").is_file()

    editor.delete(asset_id)
    assert companion()
    editor.restore(asset_id)
    assert companion()

    editor.delete(asset_id)
    editor.purge(asset_id)
    assert not list((settings.library / TRASH_DIR).rglob("*.xmp"))
