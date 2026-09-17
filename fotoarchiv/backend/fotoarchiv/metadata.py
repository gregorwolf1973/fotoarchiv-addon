"""Aus exiftool-Rohdaten die Felder machen, die das Archiv braucht."""

import calendar
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
        tags=_unique(_as_list(raw.get("XMP-dc:Subject")) + _as_list(raw.get("IPTC:Keywords"))),
        persons=_unique(
            _as_list(raw.get("XMP-iptcExt:PersonInImage"))
            + _as_list(raw.get("XMP-MP:RegionPersonDisplayName"))
            + _as_list(raw.get("XMP-mwg-rs:RegionName"))
        ),
    )
