import json
import os
import time
from dataclasses import replace
from datetime import datetime, timezone

from fotoarchiv.autoimport import AutoImport
from fotoarchiv.importer import DUPLICATE_DIR, changed_at


def settle(path, age=3600):
    """Altes Änderungsdatum setzen, wie es Kopierprogramme am Ende tun. Als fertig gilt die Datei
    damit nur in Tests ohne Wartezeit – sonst erst, wenn die Uhr des Imports weiterläuft (later)."""
    old = time.time() - age
    os.utime(path, (old, old))
    return path


def later(importer, seconds):
    """Die Uhr des Imports vorstellen. Die ctime lässt sich anders als das Änderungsdatum nicht zurücksetzen."""
    importer.now = lambda: time.time() + seconds


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
    deadline = time.time() + 5
    while not done and time.time() < deadline:  # on_done läuft direkt nach dem Ende des Imports
        time.sleep(0.02)
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

    settle(fresh)  # das Kopierprogramm setzt am Ende das alte Datum - fertig ist die Kopie damit nicht
    assert auto.check() is False
    later(importer, 61)
    assert auto.check()
    wait(importer)
    assert importer.job.counts["imported"] == 1
    assert auto.check() is False  # die Textdatei bleibt liegen, stößt aber keinen Import mehr an


def test_waits_until_the_copy_is_done_and_reads_the_json(settings, importer, make_jpeg):
    """Google Takeout per Samba: das Foto ist fertig kopiert und trägt sein altes Datum, die Kopie schreibt
    gerade seine JSON-Begleitdatei. Bisher lief der Import mitten hinein, weil das Foto für sich fertig
    aussah: Fotos kamen ohne ihre JSON ins Archiv, und Kopien brachen ab."""
    settings = importer.settings = replace(settings, import_quiet_seconds=60)
    auto = AutoImport(settings, importer, enabled=True)
    folder = settings.import_dir / "Google Fotos" / "Fotos von 2015"
    photo = settle(make_jpeg(folder / "foto.jpg"))  # ohne Datum im Namen: käme sonst vom Dateidatum
    done = changed_at(photo.stat())
    time.sleep(0.2)  # die ctime ist nur auf wenige Millisekunden genau
    sidecar = folder / "foto.jpg.supplemental-metadata.json"
    taken = datetime(2015, 6, 1, 10, 0, tzinfo=timezone.utc)
    sidecar.write_text(json.dumps({"photoTakenTime": {"timestamp": str(int(taken.timestamp()))}}), encoding="utf-8")

    importer.now = lambda: done + 60.1  # das Foto ist seit einer Minute fertig, die JSON noch nicht
    assert auto.check() is False
    assert photo.is_file() and sidecar.is_file()

    quiet = changed_at(sidecar.stat()) + 61
    importer.now = lambda: quiet  # eine Minute Ruhe im ganzen Ordner
    assert auto.check()
    wait(importer)
    assert importer.job.counts["imported"] == 1
    assert importer.db.one("SELECT taken_at FROM assets")["taken_at"].startswith("2015-06-01")
    assert not (settings.import_dir / "Google Fotos").exists()  # JSON mitgewandert, leere Ordner weg


def test_json_still_being_written_survives_its_duplicate(settings, importer, make_jpeg):
    """Startet eine Kopie, während der Import schon läuft: eine Begleitdatei, die gerade geschrieben wird,
    nicht mit ihrem doppelten Foto löschen. Unter dem Kopierprogramm weggelöscht, bricht die Kopie ab."""
    photo = settle(make_jpeg(settings.import_dir / "foto.jpg"))
    copy = photo.read_bytes()
    importer.start("import", auto=True)
    wait(importer)

    importer.settings = replace(settings, import_quiet_seconds=60)
    photo.write_bytes(copy)  # dieselbe Datei noch einmal ...
    done = changed_at(settle(photo).stat())
    time.sleep(0.2)
    sidecar = settings.import_dir / "foto.jpg.supplemental-metadata.json"
    sidecar.write_text("{}", encoding="utf-8")  # ... und die Kopie schreibt gerade die JSON dazu
    importer.now = lambda: done + 60.1
    importer.start("import", auto=True)
    wait(importer)
    assert importer.job.counts["duplicate"] == 1 and not photo.exists()
    assert sidecar.is_file()


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
