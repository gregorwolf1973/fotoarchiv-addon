"""Aus exiftool-Rohdaten die Felder machen, die das Archiv braucht."""

import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Reihenfolge = Priorität. Werte sind Ortszeit der Aufnahme (ggf. mit Offset).
LOCAL_DATE_TAGS = [
    "ExifIFD:DateTimeOriginal",
    "XMP-exif:DateTimeOriginal",
    "Keys:CreationDate",            # iPhone-Videos, mit Offset
    "XMP-photoshop:DateCreated",
    "ExifIFD:CreateDate",
    "XMP-xmp:CreateDate",
]
# Bearbeitungsdatum: nur, wenn auch der Dateiname nichts hergibt
MODIFY_DATE_TAGS = ["IFD0:ModifyDate", "XMP-xmp:ModifyDate"]
# QuickTime speichert laut Spezifikation UTC
UTC_DATE_TAGS = ["QuickTime:CreateDate", "Track1:MediaCreateDate"]

OFFSET_TAGS = ["ExifIFD:OffsetTimeOriginal", "ExifIFD:OffsetTime"]

TAG_TAGS = ["XMP-dc:Subject", "IPTC:Keywords"]
PERSON_TAGS = ["XMP-iptcExt:PersonInImage", "XMP-MP:RegionPersonDisplayName", "XMP-mwg-rs:RegionName"]

# ── Begleitdateien ────────────────────────────────────────────────
# Zwei Arten:
# - XMP: AVI, MPG und WMV können selbst keine Metadaten aufnehmen. Programme wie digiKam, darktable
#   oder Lightroom legen sie darum daneben ab: video.avi -> video.avi.xmp
# - JSON: Cloud-Exporte (Google Takeout, Mi Cloud, Samsung Cloud, Amazon Photos) liefern Datum, Ort
#   und Personen als JSON neben dem Bild: bild.jpg.json, bild.jpg.supplemental-metadata.json oder
#   bild.json. Die Angaben stehen dort, weil der Dienst sie nicht ins Bild selbst schreibt.
SIDECAR_SUFFIXES = (".xmp", ".json")
SIDECAR_SUFFIX = SIDECAR_SUFFIXES[0]
# Google Takeout hängt ".supplemental-metadata" an und kürzt lange Namen (ohne .json) auf 46 Zeichen:
# PXL_20230101_123456789.jpg.supplemental-metadata.json -> PXL_20230101_123456789.jpg.supplemental-metada.json
GOOGLE_SUFFIX = ".supplemental-metadata"
GOOGLE_NAME_LIMIT = 46
_GOOGLE_COPY_RE = re.compile(r"^(.*)(\(\d+\))$")  # Google: bild(1).jpg -> bild.jpg(1).json
# Aus der Begleitdatei wird nur übernommen, was sie über die Aufnahme sagt. Größe, MIME-Typ und
# Maße der XMP-Datei selbst dürfen nie in den Eintrag geraten – darum eine feste Liste.
SIDECAR_TAGS = [
    *LOCAL_DATE_TAGS, *UTC_DATE_TAGS, *MODIFY_DATE_TAGS, *OFFSET_TAGS, *TAG_TAGS, *PERSON_TAGS,
    "Composite:GPSLatitude", "Composite:GPSLongitude", "XMP-exif:GPSLatitude", "XMP-exif:GPSLongitude",
    "IFD0:Make", "IFD0:Model", "XMP-tiff:Make", "XMP-tiff:Model",
]
# JSON-Felder, in denen Exporte den Aufnahmezeitpunkt ablegen (Reihenfolge = Priorität).
# Googles "creationTime" fehlt absichtlich: das ist der Zeitpunkt des Hochladens, nicht der Aufnahme.
JSON_TIME_KEYS = [
    "photoTakenTime", "takenTime", "dateTaken", "date_taken", "takenAt", "taken_at", "DateTimeOriginal",
    "dateTimeOriginal", "captureTime", "capture_time", "creationDate", "creation_date", "createDate",
]
JSON_GEO_KEYS = ["geoData", "geoDataExif", "geo", "gps", "location", "coordinates"]
JSON_PERSON_KEYS = ["people", "persons", "personInImage", "PersonInImage"]
JSON_TAG_KEYS = ["tags", "keywords", "labels", "subject", "Subject"]
JSON_CAMERA_KEYS = [("cameraMake", "cameraModel"), ("make", "model"), ("Make", "Model")]

_DATE_RE = re.compile(
    r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?"
)
# IMG_20190512_140322, PXL_20230101_123456789, 2019-05-12 14.03.22, WhatsApp Image 2019-05-12 at 14.03.22
_FILENAME_RE = re.compile(
    r"(?<!\d)((?:19[7-9]|20[0-4])\d)[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
    r"(?:(?:[ _T-]|\sat\s)?([01]\d|2[0-3])[-_.:h]?([0-5]\d)[-_.:m]?([0-5]\d)(?:\d{3})?)?(?!\d)"
)
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass
class Metadata:
    taken: datetime                  # naive Ortszeit
    date_source: str                 # exif | filename | mtime
    tz_offset: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    lat: float | None = None
    lon: float | None = None
    camera: str | None = None
    mime: str | None = None
    tags: list[str] = field(default_factory=list)
    persons: list[str] = field(default_factory=list)

    @property
    def taken_ts(self) -> int:
        return calendar.timegm(self.taken.timetuple())


def parse_date(value) -> tuple[datetime, str | None] | None:
    """exiftool-Datum -> (naive Zeit, Offset). Ungültige Werte wie 0000:00:00 -> None."""
    if not isinstance(value, str):
        return None
    m = _DATE_RE.search(value)
    if not m:
        return None
    y, mo, d, h, mi, s, off = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0))
    except ValueError:
        return None
    if dt.year < 1900:
        return None
    if off and off != "Z" and ":" not in off:
        off = f"{off[:3]}:{off[3:]}"
    return dt, off


def date_from_filename(name: str) -> datetime | None:
    for m in _FILENAME_RE.finditer(name):
        y, mo, d, h, mi, s = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
        except ValueError:
            continue
    return None


def is_sidecar(path: Path) -> bool:
    return path.suffix.lower() in SIDECAR_SUFFIXES


def sidecar_name(name: str, sidecar: Path | None = None) -> str:
    """Wie die Begleitdatei zu dieser Datei heißen muss: video.avi -> video.avi.xmp, bild.jpg -> bild.jpg.json.
    Eine JSON-Datei mit anderem Namensmuster (bild.json, Google-Kürzung) wird dabei vereinheitlicht."""
    suffix = sidecar.suffix.lower() if sidecar is not None else SIDECAR_SUFFIX
    return name + suffix


def sidecar_candidates(name: str) -> list[str]:
    """Mögliche Namen der Begleitdatei zu name, in der Reihenfolge, in der sie zählen."""
    stem = Path(name).stem
    google = name + GOOGLE_SUFFIX
    names = [
        name + ".xmp", name + ".XMP",
        name + ".json", name + ".JSON",                   # Google Takeout (alt), viele andere Exporte
        google + ".json",                                 # Google Takeout (neu)
        google[:GOOGLE_NAME_LIMIT] + ".json",             # … von Google gekürzt
        google[:GOOGLE_NAME_LIMIT + 1] + ".json",
    ]
    copy = _GOOGLE_COPY_RE.match(stem)
    if copy:  # Google: bild(1).jpg gehört zu bild.jpg(1).json
        base = copy.group(1) + Path(name).suffix + copy.group(2)
        names += [base + ".json", (base + GOOGLE_SUFFIX)[:GOOGLE_NAME_LIMIT] + ".json"]
    if stem != name:
        names += [stem + ".json", stem + ".JSON"]          # bild.json: Mi Cloud, Samsung Cloud u. a.
    seen: set[str] = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def sidecar_for(path: Path) -> Path | None:
    """Vorhandene Begleitdatei zu path, sonst None. Auf Linux zählt auch die Endung in Großbuchstaben."""
    for candidate in sidecar_candidates(path.name):
        companion = path.with_name(candidate)
        if companion.is_file():
            return companion
    return None


def merge_sidecar(raw: dict, sidecar: dict) -> dict:
    """Fehlende Angaben aus der Begleitdatei ergänzen – was in der Datei selbst steht, gewinnt."""
    merged = dict(raw)
    for tag in SIDECAR_TAGS:
        if merged.get(tag) in (None, "") and sidecar.get(tag) not in (None, ""):
            merged[tag] = sidecar[tag]
    return merged


def read_sidecar(path: Path, exiftool, tz: str) -> dict:
    """Begleitdatei als exiftool-Rohdaten: XMP liest exiftool, JSON wird in dieselben Tags übersetzt."""
    if path.suffix.lower() == ".json":
        return json_sidecar_tags(json.loads(path.read_text(encoding="utf-8-sig")), tz)
    return exiftool.read(path)


def sidecar_assignments(tags: dict) -> list[str]:
    """exiftool-Zuweisungen, um übersetzte JSON-Angaben in eine Datei zu schreiben."""
    assignments = []
    for tag, value in tags.items():
        if tag.startswith("Composite:"):
            continue  # nicht schreibbar; die XMP-Fassung der Koordinaten ist ebenfalls dabei
        for item in value if isinstance(value, list) else [value]:
            assignments.append(f"-{tag}={item}")
    return assignments


def _json_time(value, tz: str) -> str | None:
    """Zeitangabe aus JSON -> exiftool-Schreibweise mit Offset. Sekunden seit 1970 (Google, als Zahl oder
    Text, auch Millisekunden) werden in die Ortszeit umgerechnet; Textdaten bleiben, wie sie sind."""
    if isinstance(value, dict):
        value = value.get("timestamp") or value.get("epoch") or value.get("value") or value.get("formatted")
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().lstrip("-").isdigit()):
        seconds = float(value)
        if seconds > 1e11:
            seconds /= 1000
        if seconds <= 0:
            return None
        return _local(datetime.fromtimestamp(seconds, timezone.utc), tz)
    if not isinstance(value, str):
        return None
    parsed = parse_date(re.sub(r"^\s*(\d{4})-(\d{2})-(\d{2})", r"\1:\2:\3", value))
    if not parsed:
        return None
    taken, offset = parsed
    if offset == "Z":  # UTC -> Ortszeit, wie bei QuickTime
        return _local(taken.replace(tzinfo=timezone.utc), tz)
    return taken.strftime("%Y:%m:%d %H:%M:%S") + (offset or "")


def _local(aware: datetime, tz: str) -> str:
    local = aware.astimezone(ZoneInfo(tz))
    offset = local.strftime("%z")
    return local.strftime("%Y:%m:%d %H:%M:%S") + f"{offset[:3]}:{offset[3:]}"


def _json_number(obj: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _json_coords(data: dict) -> tuple[float | None, float | None]:
    """Erstes brauchbares Koordinatenpaar: Google geoData/geoDataExif, sonst lat/lon auf oberster Ebene.
    0/0 heißt bei Google „kein Ort“."""
    for obj in [data.get(key) for key in JSON_GEO_KEYS] + [data]:
        if not isinstance(obj, dict):
            continue
        lat = _json_number(obj, ("latitude", "lat"))
        lon = _json_number(obj, ("longitude", "lon", "lng", "long"))
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 7), round(lon, 7)
    return None, None


def _json_names(value) -> list[str]:
    """Liste von Namen: Strings oder Objekte mit "name" (Google: people: [{"name": "Anna"}])."""
    items = value if isinstance(value, list) else [value]
    names = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("name") or item.get("title") or item.get("label")
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
    return names


def json_sidecar_tags(data, tz: str) -> dict:
    """JSON-Begleitdatei -> exiftool-Tags (wie sie SIDECAR_TAGS erwartet). Unbekannte Felder bleiben außen vor."""
    if not isinstance(data, dict):
        return {}
    tags: dict = {}
    for key in JSON_TIME_KEYS:
        taken = _json_time(data.get(key), tz)
        if taken:
            tags["XMP-exif:DateTimeOriginal"] = taken
            break
    lat, lon = _json_coords(data)
    if lat is not None:
        tags["Composite:GPSLatitude"], tags["Composite:GPSLongitude"] = lat, lon
        tags["XMP-exif:GPSLatitude"], tags["XMP-exif:GPSLongitude"] = lat, lon
    persons = _unique([name for key in JSON_PERSON_KEYS for name in _json_names(data.get(key))])
    if persons:
        tags["XMP-iptcExt:PersonInImage"] = persons
    subjects = _unique([name for key in JSON_TAG_KEYS for name in _json_names(data.get(key))])
    if subjects:
        tags["XMP-dc:Subject"] = subjects
    for make_key, model_key in JSON_CAMERA_KEYS:
        make, model = data.get(make_key), data.get(model_key)
        if isinstance(make, str) and make.strip():
            tags["XMP-tiff:Make"] = make.strip()
        if isinstance(model, str) and model.strip():
            tags["XMP-tiff:Model"] = model.strip()
        if "XMP-tiff:Make" in tags or "XMP-tiff:Model" in tags:
            break
    return tags


def _first(raw: dict, keys: list[str]):
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_suffix(raw: dict, suffix: str):
    """Erster Wert, dessen Tag-Name (ohne Gruppe) passt, z. B. ":Model"."""
    for key, value in raw.items():
        if key.endswith(suffix) and value not in (None, ""):
            return value
    return None


def _as_list(value) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in items if str(item).strip()]


def _unique(items: list[str]) -> list[str]:
    seen, result = set(), []
    for item in items:
        if item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result


def _gps(raw: dict) -> tuple[float | None, float | None]:
    lat, lon = raw.get("Composite:GPSLatitude"), raw.get("Composite:GPSLongitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        # Begleitdateien bringen oft nur die XMP-Felder mit, ohne dass exiftool daraus Composite bildet
        lat, lon = _first_suffix(raw, ":GPSLatitude"), _first_suffix(raw, ":GPSLongitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        coords = _first_suffix(raw, ":GPSCoordinates")
        numbers = _NUMBER_RE.findall(str(coords)) if coords is not None else []
        if len(numbers) < 2:
            return None, None
        lat, lon = float(numbers[0]), float(numbers[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None, None
    return round(float(lat), 7), round(float(lon), 7)


def _dimensions(raw: dict) -> tuple[int | None, int | None]:
    size = raw.get("Composite:ImageSize")
    numbers = _NUMBER_RE.findall(str(size)) if size is not None else []
    if len(numbers) < 2:
        return None, None
    w, h = int(float(numbers[0])), int(float(numbers[1]))
    orientation = raw.get("IFD0:Orientation")
    rotation = _first_suffix(raw, ":Rotation")
    if orientation in (5, 6, 7, 8) or rotation in (90, 270):
        w, h = h, w
    return w, h


def extract(raw: dict, path: Path, tz: str, mtime: float) -> Metadata:
    taken, source, offset = None, "exif", None

    parsed = parse_date(_first(raw, LOCAL_DATE_TAGS))
    if parsed:
        taken, offset = parsed
        offset = offset or _first(raw, OFFSET_TAGS)
    else:
        parsed = parse_date(_first(raw, UTC_DATE_TAGS))
        if parsed:
            utc = parsed[0].replace(tzinfo=timezone.utc)
            local = utc.astimezone(ZoneInfo(tz))
            taken = local.replace(tzinfo=None)
            offset = local.strftime("%z")
            offset = f"{offset[:3]}:{offset[3:]}"

    if taken is None:
        taken, source = date_from_filename(path.name), "filename"
    if taken is None and (parsed := parse_date(_first(raw, MODIFY_DATE_TAGS))):
        (taken, offset), source = parsed, "exif"
    if taken is None:
        taken = datetime.fromtimestamp(mtime, ZoneInfo(tz)).replace(tzinfo=None, microsecond=0)
        source = "mtime"

    make = str(_first_suffix(raw, ":Make") or "").strip()
    model = str(_first_suffix(raw, ":Model") or "").strip()
    camera = model if make and model.lower().startswith(make.lower()) else f"{make} {model}".strip()

    duration = _first_suffix(raw, ":Duration")
    lat, lon = _gps(raw)
    width, height = _dimensions(raw)

    return Metadata(
        taken=taken,
        date_source=source,
        tz_offset=offset if isinstance(offset, str) else None,
        width=width,
        height=height,
        duration=float(duration) if isinstance(duration, (int, float)) else None,
        lat=lat,
        lon=lon,
        camera=camera or None,
        mime=raw.get("File:MIMEType"),
        tags=_unique([name for tag in TAG_TAGS for name in _as_list(raw.get(tag))]),
        persons=_unique([name for tag in PERSON_TAGS for name in _as_list(raw.get(tag))]),
    )
