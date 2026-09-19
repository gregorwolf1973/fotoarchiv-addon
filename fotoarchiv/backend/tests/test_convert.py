import subprocess
from pathlib import Path

import pytest

from fotoarchiv.convert import decide, video_command


def streams(video=None, pix="yuv420p", audio="aac", cover=False):
    result = []
    if video:
        result.append({"codec_type": "video", "codec_name": video, "pix_fmt": pix})
    if cover:
        result.insert(0, {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}})
    if audio:
        result.append({"codec_type": "audio", "codec_name": audio})
    return {"streams": result}


def test_images_only_heic():
    assert decide(".HEIC", "image", None).suffix == ".jpg"
    assert decide(".heif", "image", None).action == "heic"
    for suffix in (".jpg", ".png", ".avif", ".webp"):
        assert decide(suffix, "image", None) is None


def test_playable_mp4_stays():
    assert decide(".mp4", "video", streams("h264")) is None
    assert decide(".m4v", "video", streams("h264", audio=None)) is None
    assert decide(".webm", "video", streams("vp9", audio="opus")) is None  # spielt der Browser ab
    assert decide(".mp4", "video", {"streams": []}) is None                # kein Bild, nichts zu tun


def test_remux_when_only_container_or_audio_is_wrong():
    mov = decide(".MOV", "video", streams("h264"))
    assert (mov.action, mov.suffix, mov.copy_audio) == ("remux", ".mp4", True)
    pcm = decide(".mp4", "video", streams("h264", audio="pcm_s16le"))
    assert (pcm.action, pcm.copy_audio) == ("remux", False)
    assert decide(".mp4", "video", streams("h264", cover=True)) is None  # Titelbild ist kein Video


def test_transcode_hevc_10bit_and_others():
    hevc = decide(".mp4", "video", streams("hevc"))
    assert (hevc.action, hevc.copy_audio) == ("transcode", True) and "hevc" in hevc.reason
    assert decide(".mp4", "video", streams("h264", pix="yuv420p10le")).action == "transcode"
    assert decide(".mp4", "video", streams("h264", pix="yuv422p")).action == "transcode"
    assert decide(".avi", "video", streams("mpeg4", audio="mp3")).copy_audio is True


def test_video_command():
    plan = decide(".mov", "video", streams("h264", audio="pcm_s16le"))
    command = video_command("ffmpeg", Path("a.mov"), Path("b.mp4"), plan)
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"
    assert "+faststart" in command[command.index("-movflags") + 1]
    transcode = video_command("ffmpeg", Path("a.mp4"), Path("b.mp4"), decide(".mp4", "video", streams("hevc")))
    assert transcode[transcode.index("-c:v") + 1] == "libx264" and "yuv420p" in transcode
    assert transcode[-1] == "b.mp4"


def test_convert_hevc_video_replaces_file_and_trashes_original(settings, importer, editor, tmp_path):
    """Ganzer Ablauf mit echtem ffmpeg (libx265 zum Erzeugen des Testvideos nötig)."""
    from conftest import FFMPEG
    from fotoarchiv.convert import ConvertService
    from fotoarchiv.editor import TRASH_DIR

    if not FFMPEG:
        pytest.skip("ffmpeg nicht vorhanden")
    source = settings.import_dir / "clip.mov"
    source.parent.mkdir(parents=True, exist_ok=True)
    made = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                           "-i", "testsrc=size=320x240:rate=10", "-t", "2", "-c:v", "libx265", "-tag:v", "hvc1",
                           str(source)], capture_output=True)
    if made.returncode:
        pytest.skip("ffmpeg ohne libx265")
    asset_id = importer.import_file(source).asset_id
    editor.set_labels(asset_id, "tags", ["Urlaub"])
    service = ConvertService(settings, importer.db, importer, editor)

    service.request(asset_id)
    assert service.status()["pending"] == 1
    assert service.work_once()

    row = importer.db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    assert row["path"].endswith("clip.mp4") and row["convert"] == 0 and row["mime"] == "video/mp4"
    assert (settings.library / row["path"]).is_file()
    assert editor.exiftool.read(settings.library / row["path"]).get("XMP-dc:Subject") == "Urlaub"
    trashed = importer.db.one("SELECT * FROM assets WHERE id != ? AND deleted_at IS NOT NULL", (asset_id,))
    assert trashed["path"].startswith(f"{TRASH_DIR}/") and trashed["orig_path"].endswith("clip.mov")
    assert (settings.library / trashed["path"]).is_file()
    assert service.status() == {"pending": 0, "failed": 0, "errors": [], "current": None}

    service.request(asset_id)  # schon abspielbar: nichts mehr zu tun
    assert service.work_once() and importer.db.one("SELECT path FROM assets WHERE id = ?", (asset_id,))["path"] == row["path"]


def test_failed_conversion_shows_reason_and_can_be_dismissed(settings, importer, editor, make_video):
    from fotoarchiv.convert import ConvertService

    asset_id = importer.import_file(make_video(settings.import_dir / "kaputt.avi")).asset_id
    path = importer.db.one("SELECT path FROM assets WHERE id = ?", (asset_id,))["path"]
    service = ConvertService(settings, importer.db, importer, editor)
    service.request(asset_id)
    (settings.library / path).unlink()  # Umwandeln scheitert
    assert service.work_once()

    status = service.status()
    assert status["failed"] == 1
    assert status["errors"] == [{"id": asset_id, "name": "kaputt.avi", "reason": "Datei fehlt auf dem Datenträger"}]

    assert service.dismiss_failed() == 1
    assert service.status()["failed"] == 0 and service.status()["errors"] == []
    row = importer.db.one("SELECT convert, convert_error FROM assets WHERE id = ?", (asset_id,))
    assert row["convert"] == 0 and row["convert_error"] == "Datei fehlt auf dem Datenträger"  # Grund bleibt



def test_old_formats_mpg_and_wmv_become_mp4():
    mpg = decide(".mpg", "video", streams("mpeg2video", audio="mp2"))
    assert (mpg.action, mpg.suffix, mpg.copy_audio) == ("transcode", ".mp4", False)
    wmv = decide(".WMV", "video", streams("wmv3", audio="wmav2"))
    assert (wmv.action, wmv.copy_audio) == ("transcode", False)


@pytest.mark.parametrize("suffix, codecs", [
    (".mpg", ["-c:v", "mpeg1video", "-c:a", "mp2"]),
    (".wmv", ["-c:v", "wmv2", "-c:a", "wmav2"]),
])
def test_import_and_convert_mpg_wmv(settings, importer, editor, suffix, codecs):
    """Echte Dateien: einlesen, Vorschaubild, umwandeln in ein abspielbares MP4."""
    from conftest import FFMPEG
    from fotoarchiv.convert import ConvertService

    if not FFMPEG:
        pytest.skip("ffmpeg nicht vorhanden")
    source = settings.import_dir / f"VID_20090807_101010{suffix}"
    source.parent.mkdir(parents=True, exist_ok=True)
    made = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                           "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                           "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                           "-t", "2", *codecs, str(source)], capture_output=True)
    if made.returncode:
        pytest.skip(f"ffmpeg kann {suffix} nicht erzeugen")
    result = importer.import_file(source)
    assert result.status == "imported", result.message
    assert importer.ensure_thumbnail(result.asset_id) is not None

    service = ConvertService(settings, importer.db, importer, editor)
    service.request(result.asset_id)
    assert service.work_once()
    row = importer.db.one("SELECT path, mime, convert, convert_error FROM assets WHERE id = ?", (result.asset_id,))
    assert row["convert"] == 0, row["convert_error"]
    assert row["path"].endswith(".mp4") and row["mime"] == "video/mp4"
