from pathlib import Path

import pytest

from fotoarchiv import media


class FakeImage:
    """Steht für ein pyvips-Bild: webpsave schreibt nur ein paar Bytes."""

    def __init__(self, content: bytes, width: int = 4, height: int = 3, during_save=None):
        self.content, self.width, self.height, self.during_save = content, width, height, during_save

    def webpsave(self, path, **kwargs):
        Path(path).write_bytes(self.content)
        if self.during_save:
            self.during_save()


def test_save_webp_parallel_calls_do_not_collide(tmp_path):
    # Import und Galerie erzeugten dasselbe Vorschaubild gleichzeitig; mit gemeinsamer Zwischendatei
    # benannte der zweite Aufruf sie um, und der erste scheiterte mit "No such file or directory"
    target = tmp_path / "thumb" / "0028" / "28781.webp"
    inner = FakeImage(b"inner", 2, 1)
    outer = FakeImage(b"outer", during_save=lambda: media._save_webp(inner, target, 75))

    assert media._save_webp(outer, target, 75) == (4, 3)
    assert target.read_bytes() == b"outer"
    assert [p.name for p in target.parent.iterdir()] == ["28781.webp"]  # keine Zwischendateien übrig


def test_save_webp_failure_leaves_no_temp_file(tmp_path):
    target = tmp_path / "thumb" / "0001" / "1.webp"

    def fail():
        raise RuntimeError("kaputt")

    with pytest.raises(RuntimeError):
        media._save_webp(FakeImage(b"halb", during_save=fail), target, 75)
    assert list(target.parent.iterdir()) == []
