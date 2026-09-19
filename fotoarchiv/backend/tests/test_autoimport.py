import os
import time
from dataclasses import replace

from fotoarchiv.autoimport import AutoImport
from fotoarchiv.importer import DUPLICATE_DIR


def settle(path, age=3600):
    """Datei als längst fertig kopiert markieren."""
    old = time.time() - age
    os.utime(path, (old, old))
    return path


def wait(importer):
    deadline = time.time() + 30
    while importer.job.running and time.time() < deadline:
        time.sleep(0.05)
    assert not importer.job.running


def test_imports_ready_files_and_deletes_duplicates(settings, importer, make_jpeg):
    done = []
    auto = AutoImport(settings, importer, on_done=lambda: done.append(1), enabled=True)
    photo = settle(make_jpeg(settings.import_dir / "Camera" / "IMG_20240501_101010.jpg"))
    copy = photo.read_bytes()

    assert auto.check()
    wait(importer)
    assert importer.job.auto and importer.job.counts["imported"] == 1 and done == [1]
    assert not photo.exists()
    assert auto.check() is False  # nichts Neues

    # Das Handy lädt dasselbe Foto noch einmal hoch: die Kopie verschwindet, _duplikate bleibt leer
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(copy)
    settle(photo)
    assert auto.check()
    wait(importer)
    assert importer.job.counts["duplicate"] == 1 and "gelöscht" in importer.job.duplicates[0]["message"]
    assert not photo.exists() and not (settings.import_dir / DUPLICATE_DIR).exists()


def test_waits_for_copies_and_does_not_retry_leftovers(settings, importer, make_jpeg):
    settings = importer.settings = replace(settings, import_quiet_seconds=60)  # wie im Betrieb; Tests setzen 0
    auto = AutoImport(settings, importer, enabled=True)
    fresh = make_jpeg(settings.import_dir / "IMG_20240502_101010.jpg")  # wird gerade kopiert
    (settings.import_dir / "notiz.txt").write_text("kein Foto")
    settle(settings.import_dir / "notiz.txt")
    assert auto.check() is False  # Foto zu frisch, Textdatei nicht unterstützt

    settle(fresh)
    assert auto.check()
    wait(importer)
    assert importer.job.counts["imported"] == 1
    assert auto.check() is False  # die Textdatei bleibt liegen, stößt aber keinen Import mehr an


def test_manual_import_still_moves_duplicates(settings, importer, make_jpeg):
    photo = settle(make_jpeg(settings.import_dir / "IMG_20240503_101010.jpg"))
    copy = photo.read_bytes()
    importer.start("import")
    wait(importer)
    photo.write_bytes(copy)
    settle(photo)
    importer.start("import")
    wait(importer)
    assert not importer.job.auto
    assert (settings.import_dir / DUPLICATE_DIR / photo.name).is_file()
