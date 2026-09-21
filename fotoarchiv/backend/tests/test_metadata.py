from datetime import datetime
from pathlib import Path

from fotoarchiv.metadata import date_from_filename, extract, is_sidecar, merge_sidecar, parse_date, sidecar_for

MTIME = datetime(2024, 1, 2, 3, 4, 5).timestamp()


def test_parse_date_variants():
    assert parse_date("2019:05:12 14:03:22") == (datetime(2019, 5, 12, 14, 3, 22), None)
    assert parse_date("2019:05:12 14:03:22.123+02:00") == (datetime(2019, 5, 12, 14, 3, 22), "+02:00")
    assert parse_date("2019:05:12 14:03:22+0200")[1] == "+02:00"
    assert parse_date("0000:00:00 00:00:00") is None
    assert parse_date("    :  :     :  :  ") is None
    assert parse_date(None) is None


def test_date_from_filename():
    assert date_from_filename("IMG_20190512_140322.jpg") == datetime(2019, 5, 12, 14, 3, 22)
    assert date_from_filename("PXL_20230101_123456789.jpg") == datetime(2023, 1, 1, 12, 34, 56)
    assert date_from_filename("WhatsApp Image 2019-05-12 at 14.03.22.jpeg") == datetime(2019, 5, 12, 14, 3, 22)
    assert date_from_filename("VID-20190512-WA0001.mp4") == datetime(2019, 5, 12)
    assert date_from_filename("2019-05-12 14.03.22.jpg") == datetime(2019, 5, 12, 14, 3, 22)
    assert date_from_filename("DSC01234.JPG") is None
    assert date_from_filename("123420190512999999.jpg") is None


def test_exif_date_beats_filename():
    meta = extract({"ExifIFD:DateTimeOriginal": "2018:07:01 10:00:00"}, Path("IMG_20190512_140322.jpg"), "Europe/Berlin", MTIME)
    assert (meta.taken, meta.date_source) == (datetime(2018, 7, 1, 10), "exif")


def test_quicktime_utc_is_converted_to_local_time():
    meta = extract({"QuickTime:CreateDate": "2019:07:01 10:00:00"}, Path("clip.mp4"), "Europe/Berlin", MTIME)
    assert meta.taken == datetime(2019, 7, 1, 12)  # Sommerzeit
    assert meta.tz_offset == "+02:00"


def test_iphone_video_keeps_local_wallclock():
    raw = {"Keys:CreationDate": "2019:07:01 23:30:00+02:00", "QuickTime:CreateDate": "2019:07:01 21:30:00"}
    meta = extract(raw, Path("IMG_0001.MOV"), "Europe/Berlin", MTIME)
    assert (meta.taken, meta.tz_offset) == (datetime(2019, 7, 1, 23, 30), "+02:00")


def test_filename_beats_modify_date_and_mtime_is_last_resort():
    meta = extract({"IFD0:ModifyDate": "2024:01:01 00:00:00"}, Path("IMG_20190512_140322.jpg"), "Europe/Berlin", MTIME)
    assert meta.date_source == "filename"
    meta = extract({}, Path("scan.jpg"), "Europe/Berlin", MTIME)
    assert (meta.taken, meta.date_source) == (datetime(2024, 1, 2, 3, 4, 5), "mtime")


def test_gps_and_dimensions():
    raw = {
        "Composite:GPSLatitude": 48.137154,
        "Composite:GPSLongitude": 11.576124,
        "Composite:ImageSize": "4032 3024",
        "IFD0:Orientation": 6,
    }
    meta = extract(raw, Path("a.jpg"), "Europe/Berlin", MTIME)
    assert (meta.lat, meta.lon) == (48.137154, 11.576124)
    assert (meta.width, meta.height) == (3024, 4032)

    video = extract({"Keys:GPSCoordinates": "-33.8568 151.2153 12.5", "Track1:Rotation": 90,
                     "Composite:ImageSize": "1920 1080"}, Path("v.mov"), "Europe/Berlin", MTIME)
    assert (video.lat, video.lon, video.width, video.height) == (-33.8568, 151.2153, 1080, 1920)

    nowhere = extract({"Composite:GPSLatitude": 0, "Composite:GPSLongitude": 0}, Path("a.jpg"), "Europe/Berlin", MTIME)
    assert nowhere.lat is None


def test_tags_persons_and_camera():
    raw = {
        "XMP-dc:Subject": ["Urlaub", "Strand"],
        "IPTC:Keywords": ["urlaub", "Italien"],
        "XMP-iptcExt:PersonInImage": "Müller, Hans",
        "XMP-mwg-rs:RegionName": ["Anna", "Müller, Hans"],
        "IFD0:Make": "Apple",
        "IFD0:Model": "iPhone 13",
        "ExifIFD:LensModel": "Irrelevant",
    }
    meta = extract(raw, Path("a.jpg"), "Europe/Berlin", MTIME)
    assert meta.tags == ["Urlaub", "Strand", "Italien"]
    assert meta.persons == ["Müller, Hans", "Anna"]
    assert meta.camera == "Apple iPhone 13"
    assert extract({"IFD0:Make": "Canon", "IFD0:Model": "Canon EOS 5D"}, Path("a.jpg"), "UTC", MTIME).camera == "Canon EOS 5D"


def test_write_video_with_trailer_after_last_atom(exiftool, make_video, tmp_path):
    """Samsung hängt an Videos einen SEF-Anhang an; exiftool verweigert dann das Schreiben ohne -m."""
    video = make_video(tmp_path / "samsung.mp4")
    with open(video, "ab") as f:
        f.write(b"SEFH" + bytes(60) + b"SEFT")
    exiftool.write(video, "-XMP-dc:Subject=Urlaub")
    assert exiftool.read(video).get("XMP-dc:Subject") == "Urlaub"


def test_sidecar_is_found_next_to_its_file(tmp_path):
    video = tmp_path / "20130401_141515.avi"
    video.write_bytes(b"x")
    assert sidecar_for(video) is None
    companion = tmp_path / "20130401_141515.avi.xmp"
    companion.write_text("<x/>")
    assert sidecar_for(video) == companion
    assert is_sidecar(companion) and not is_sidecar(video)


def test_sidecar_fills_gaps_but_the_file_itself_wins():
    raw = {"ExifIFD:DateTimeOriginal": "2018:07:01 10:00:00"}
    companion = {
        "XMP-exif:DateTimeOriginal": "1999:01:01 00:00:00",
        "XMP-dc:Subject": ["Urlaub", "Strand"],
        "XMP-iptcExt:PersonInImage": "Anna",
        "XMP-exif:GPSLatitude": 47.5,
        "XMP-exif:GPSLongitude": 9.75,
    }
    meta = extract(merge_sidecar(raw, companion), Path("20130401_141515.avi"), "Europe/Berlin", MTIME)
    assert (meta.taken, meta.date_source) == (datetime(2018, 7, 1, 10), "exif")  # Datei schlägt Begleitdatei
    assert meta.tags == ["Urlaub", "Strand"] and meta.persons == ["Anna"]
    assert (meta.lat, meta.lon) == (47.5, 9.75)


def test_sidecar_provides_the_date_when_the_file_has_none():
    """Der eigentliche Zweck: AVI kann selbst kein Datum speichern."""
    companion = {"XMP-photoshop:DateCreated": "2013:04:01 14:15:15"}
    meta = extract(merge_sidecar({}, companion), Path("clip.avi"), "Europe/Berlin", MTIME)
    assert (meta.taken, meta.date_source) == (datetime(2013, 4, 1, 14, 15, 15), "exif")


def test_sidecar_never_contributes_its_own_file_properties():
    """Größe, Typ und Maße der XMP-Datei dürfen nicht in den Eintrag geraten."""
    companion = {"File:MIMEType": "application/rdf+xml", "File:FileSize": 1234,
                 "Composite:ImageSize": "10 10", "File:FileName": "clip.avi.xmp"}
    assert merge_sidecar({}, companion) == {}
