import shutil

from fotoarchiv.importer import DUPLICATE_DIR, safe_name


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

    assert job.counts == {"imported": 2, "duplicate": 1, "skipped": 1, "error": 0}
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
