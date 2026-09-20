"""Die HTTP-API. Wird zweimal eingehängt: für Home Assistant (Ingress, volle Rechte) und für den
Internetzugang (angemeldet, Rechte je Rolle, ohne Verwaltungsfunktionen)."""

import calendar
import mimetypes
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import duplicates_api, faces_api, labels, media
from .context import Context
from .editor import WRITABLE, EditError, capabilities
from .importer import safe_name

COUNTER = re.compile(r"_\d+(\.[^.]*)?$")  # "_2" vor der Endung, von unique_path angehängt
UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
UPLOAD_MAX = 50 * 1024**3  # 50 GB je Datei
CHUNK_MAX = 96 * 1024**2  # knapp unter Cloudflares 100 MB je Anfrage


def _truncate(path: Path, size: int):
    """Teildatei auf den Stand vor dem Stück zurücksetzen (bzw. löschen, wenn es das erste war)."""
    try:
        if size:
            with open(path, "r+b") as f:
                f.truncate(size)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


LONG_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}

# Ersatz für ein Vorschaubild, das sich nicht erzeugen lässt. Bewusst mit 200 statt 404: Die Galerie
# lädt Dutzende Vorschaubilder auf einmal, und eine Serie von 404 auf verschiedene Pfade werten
# CrowdSec und ähnliche Wächter als Abtasten (Szenario http-probing) und sperren die Adresse.
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="90" viewBox="0 0 120 90">'
    '<rect width="120" height="90" fill="#9a9a9a" fill-opacity=".35"/>'
    '<g fill="none" stroke="#fff" stroke-opacity=".85" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">'
    '<rect x="42" y="30" width="36" height="30" rx="3"/><path d="M45 56l10-11 8 8 5-5 7 8"/><path d="M36 67l48-44"/>'
    "</g></svg>"
)
# Kurz cachen: Klappt es später (neue Revision oder neuer Versuch nach einer Stunde), soll das echte Bild kommen
PLACEHOLDER_HEADERS = {"Cache-Control": "private, max-age=900", "X-Fotoarchiv-Placeholder": "1"}


def placeholder() -> Response:
    return Response(PLACEHOLDER_SVG, media_type="image/svg+xml", headers=PLACEHOLDER_HEADERS)


def role_of(request: Request) -> str:
    """Vom Zugang gesetzt: admin (Home Assistant), editor, uploader oder viewer (Internet)."""
    return getattr(request.state, "role", "viewer")


class KnownFile(BaseModel):
    name: str = Field(max_length=255)
    size: int = Field(ge=0)


class KnownRequest(BaseModel):
    files: list[KnownFile] = Field(max_length=5000)


def _name_forms(filename: str) -> set[str]:
    """Dateiname im Archiv, auch ohne den Zähler, den unique_path bei Namensgleichheit anhängt (_1, _2 …)."""
    name = filename.lower()
    return {name, COUNTER.sub(r"\1", name)}


class ImportRequest(BaseModel):
    mode: Literal["import", "library"] = "import"
    deep: bool = False  # nur beim Abgleich: jede Datei ganz lesen (dauert Stunden)


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AssetPatch(BaseModel):
    taken_at: datetime | None = None
    location: Location | None = None  # ausdrücklich null = Ort entfernen
    tags: list[str] | None = None
    persons: list[str] | None = None


class DeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)
    reason: str = Field("", max_length=300)


class DeleteRequestIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)


class RotateRequest(BaseModel):
    degrees: Literal[90, 180, 270]


class BatchRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    action: Literal["tags", "persons", "date", "location", "shift", "rotate", "delete", "restore", "purge", "convert"]
    add: list[str] = []
    remove: list[str] = []
    taken_at: datetime | None = None
    degrees: Literal[90, 180, 270] | None = None
    location: Location | None = None  # bei action=location: null entfernt den Ort
    dlat: float | None = Field(None, ge=-180, le=180)  # bei action=shift: Versatz in Grad
    dlon: float | None = Field(None, ge=-360, le=360)


def day_start(day: date) -> int:
    return calendar.timegm(day.timetuple())


@dataclass
class AssetFilter:
    """Suchfilter aus der URL; alle Bedingungen gelten gemeinsam."""

    tag: list[int] = Query([])
    person: list[int] = Query([])
    start: date | None = None
    end: date | None = None
    q: str = ""
    trash: bool = False
    located: bool | None = None   # nur mit / nur ohne Aufnahmeort
    editable: bool | None = None  # nur Formate, die Metadaten speichern können
    proposed: bool = False        # nur Fotos, deren Löschen jemand vorgeschlagen hat

    def clause(self) -> tuple[str, list]:
        where = ["deleted_at IS NOT NULL" if self.trash else "deleted_at IS NULL"]
        params: list = []
        for ids, link, column in ((self.tag, "asset_tags", "tag_id"), (self.person, "asset_persons", "person_id")):
            if ids:
                unique = sorted(set(ids))
                marks = ",".join("?" * len(unique))
                where.append(f"(SELECT COUNT(*) FROM {link} l WHERE l.asset_id = a.id AND l.{column} IN ({marks})) = ?")
                params += [*unique, len(unique)]
        if self.start:
            where.append("taken_ts >= ?")
            params.append(day_start(self.start))
        if self.end:
            where.append("taken_ts < ?")
            params.append(day_start(self.end + timedelta(days=1)))
        for word in self.q.split():
            where.append(
                """(path LIKE ? OR camera LIKE ?
                    OR EXISTS (SELECT 1 FROM asset_tags l JOIN tags t ON t.id = l.tag_id
                               WHERE l.asset_id = a.id AND t.name LIKE ?)
                    OR EXISTS (SELECT 1 FROM asset_persons l JOIN persons p ON p.id = l.person_id
                               WHERE l.asset_id = a.id AND p.name LIKE ?))"""
            )
            params += [f"%{word}%"] * 4
        if self.located is not None:
            where.append("lat IS NOT NULL" if self.located else "lat IS NULL")
        if self.proposed:
            where.append("EXISTS (SELECT 1 FROM delete_requests r WHERE r.asset_id = a.id)")
        if self.editable is not None:
            suffixes = " OR ".join("lower(path) LIKE ?" for _ in WRITABLE)
            where.append(f"({suffixes})" if self.editable else f"NOT ({suffixes})")
            params += [f"%{suffix}" for suffix in sorted(WRITABLE)]
        return " AND ".join(where), params


def install_common(app: FastAPI):
    # Web-App-Manifest; ohne Eintrag liefert StaticFiles es als application/octet-stream aus
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    # Nur Text/JSON komprimieren; Bilder und Videos sind es schon, das kostet auf dem Pi nur Zeit
    binary_types = ("image/webp", *media.IMAGE_TYPES.values(), *media.VIDEO_TYPES.values())
    app.add_middleware(GZipMiddleware, minimum_size=1024, exclude_content_types=tuple(set(binary_types)))


def register(app: FastAPI, ctx: Context, *, public: bool):
    settings, db, importer, editor, tasks, faces = ctx.settings, ctx.db, ctx.importer, ctx.editor, ctx.tasks, ctx.faces

    @app.exception_handler(EditError)
    async def edit_error(_request: Request, exc: EditError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def asset_row(asset_id: int):
        row = db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
        if row is None:
            raise HTTPException(404, "Bild nicht gefunden")
        return row

    # ── Übersicht ──────────────────────────────────────────────────
    @app.get("/api/state")
    def state():
        counts = db.one(
            """SELECT COALESCE(SUM(deleted_at IS NULL), 0) AS total,
                      COALESCE(SUM(deleted_at IS NULL AND kind = 'image'), 0) AS images,
                      COALESCE(SUM(deleted_at IS NULL AND kind = 'video'), 0) AS videos,
                      COALESCE(SUM(CASE WHEN deleted_at IS NULL THEN size END), 0) AS bytes,
                      COALESCE(SUM(deleted_at IS NOT NULL), 0) AS trash
               FROM assets"""
        )
        return {
            "revision": db.revision,
            "instance": db.instance,
            "counts": dict(counts),
            "library": None if public else str(settings.library),
            "map_language": settings.map_language,
            "import_dir": None if public else str(settings.import_dir),
            "trash_days": settings.trash_days,
            "importing": importer.job.running,
            "tasks_running": tasks.any_running(),
            "faces": {"enabled": faces.enabled, "status": faces.state["status"]},
            "converting": ctx.converter.status(),
            # Offene Löschvorschläge – nur für den Admin in Home Assistant, der darüber entscheidet
            "delete_requests": None if public else db.one(
                """SELECT COUNT(DISTINCT r.asset_id) AS n FROM delete_requests r
                   JOIN assets a ON a.id = r.asset_id AND a.deleted_at IS NULL""")["n"],
            "tools": {
                "vips": media.pyvips is not None,
                "exiftool": shutil.which(settings.exiftool) is not None,
                "ffmpeg": shutil.which(settings.ffmpeg) is not None,
            },
        }

    INDEX_FIELDS = ["id", "ts", "w", "h", "video", "rev"]

    def index_rows(filters: AssetFilter, extra: str = "", columns: str = ""):
        where, params = filters.clause()
        return db.query(
            f"""SELECT id, taken_ts, width, height, kind, rev{columns} FROM assets a
                WHERE {where}{extra} ORDER BY taken_ts DESC, id DESC""",
            params,
        )

    def index_item(r) -> list:
        return [r["id"], r["taken_ts"], r["width"] or 0, r["height"] or 0, 1 if r["kind"] == "video" else 0, r["rev"]]

    @app.get("/api/assets")
    def asset_index(filters: AssetFilter = Depends()):
        """Kompakte Liste für Galerie und Zeitleiste, neueste zuerst. Filter werden UND-verknüpft."""
        items = [index_item(r) for r in index_rows(filters)]
        return {"revision": db.revision, "fields": INDEX_FIELDS, "items": items}

    @app.get("/api/largest")
    def asset_largest(
        kind: Literal["all", "image", "video", "damaged"] = "all",
        min_mb: int = Query(0, ge=0),
        limit: int = Query(300, ge=1, le=2000),
        order: Literal["desc", "asc"] = "desc",
    ):
        """Nach Größe sortiert, zum Aufräumen: desc = größte zuerst, asc = kleinste zuerst.

        Einträge wie /api/assets plus Größe, Name und Dauer."""
        where, params = ["deleted_at IS NULL", "size >= ?"], [min_mb * 1024 * 1024]
        if kind == "damaged":
            # Befund der gründlichen Prüfung oder kein Vorschaubild erzeugbar: Datei meist beschädigt
            where.append("(damaged IS NOT NULL OR thumb_ok != 1)")
        elif kind != "all":
            where.append("kind = ?")
            params.append(kind)
        condition = " AND ".join(where)
        direction = "ASC" if order == "asc" else "DESC"
        rows = db.query(
            f"""SELECT id, taken_ts, width, height, kind, rev, size, path, duration, damaged FROM assets
                WHERE {condition} ORDER BY size {direction}, id DESC LIMIT ?""",
            (*params, limit),
        )
        total = db.one(f"SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS bytes FROM assets WHERE {condition}", params)
        return {
            "revision": db.revision,
            "fields": INDEX_FIELDS + ["size", "name", "duration", "damaged"],
            "items": [index_item(r) + [r["size"], Path(r["path"]).name, r["duration"], r["damaged"]] for r in rows],
            "count": total["count"],
            "bytes": total["bytes"],
        }

    @app.get("/api/geo")
    def asset_geo(filters: AssetFilter = Depends()):
        """Wie /api/assets, nur Bilder mit Ort und zusätzlich Breite/Länge."""
        rows = index_rows(filters, " AND lat IS NOT NULL", ", lat, lon")
        items = [index_item(r) + [r["lat"], r["lon"]] for r in rows]
        return {"revision": db.revision, "fields": INDEX_FIELDS + ["lat", "lon"], "items": items}

    @app.get("/api/labels")
    def label_list():
        result = {}
        for kind, (table, link, column) in labels.TABLES.items():
            rows = db.query(
                f"""SELECT t.id, t.name, COUNT(*) AS count FROM {table} t
                    JOIN {link} l ON l.{column} = t.id JOIN assets a ON a.id = l.asset_id AND a.deleted_at IS NULL
                    GROUP BY t.id ORDER BY t.name COLLATE NOCASE"""
            )
            result[kind] = [dict(r) for r in rows]
        return result

    def detail(asset_id: int) -> dict:
        row = asset_row(asset_id)
        with db.transaction() as conn:
            tags = labels.current(conn, asset_id, "tags")
            persons = labels.current(conn, asset_id, "persons")
        result = {key: row[key] for key in row.keys() if key not in ("md5_import", "thumb_ok")}
        result.update(capabilities(row["path"]), name=Path(row["path"]).name, tags=tags, persons=persons)
        result["delete_requests"] = [dict(r) for r in db.query(
            """SELECT r.username, COALESCE(NULLIF(u.display_name, ''), r.username) AS display_name, r.reason, r.created_at
               FROM delete_requests r LEFT JOIN users u ON u.username = r.username
               WHERE r.asset_id = ? ORDER BY r.created_at, r.rowid""", (asset_id,))]
        if row["deleted_at"]:
            expires = datetime.fromisoformat(row["deleted_at"]) + timedelta(days=settings.trash_days)
            result["expires_at"] = expires.isoformat(timespec="seconds")
        return result

    @app.post("/api/delete-requests")
    def delete_request_create(body: DeleteRequest, request: Request):
        """Löschen vorschlagen – für Konten, die selbst nicht löschen dürfen. Der Admin entscheidet."""
        session = getattr(request.state, "session", None)
        username = session["username"] if session else "Home Assistant"
        now = datetime.now().isoformat(timespec="seconds")
        ids = sorted(set(body.ids))
        with db.transaction() as conn:
            existing = {r["id"] for r in conn.execute(
                f"SELECT id FROM assets WHERE deleted_at IS NULL AND id IN ({','.join('?' * len(ids))})", ids)}
            for asset_id in ids:
                if asset_id in existing:
                    conn.execute(
                        """INSERT INTO delete_requests (asset_id, username, reason, created_at) VALUES (?, ?, ?, ?)
                           ON CONFLICT (asset_id, username) DO UPDATE SET reason = excluded.reason, created_at = excluded.created_at""",
                        (asset_id, username, body.reason.strip(), now))
        db.bump()
        return {"requested": len(existing)}

    @app.get("/api/assets/{asset_id}")
    def asset_detail(asset_id: int):
        return detail(asset_id)

    @app.patch("/api/assets/{asset_id}")
    def asset_update(asset_id: int, body: AssetPatch):
        if body.taken_at is not None:
            editor.set_date(asset_id, body.taken_at)
        if "location" in body.model_fields_set:
            loc = body.location
            editor.set_location(asset_id, loc.lat if loc else None, loc.lon if loc else None)
        if body.tags is not None:
            editor.set_labels(asset_id, "tags", body.tags)
        if body.persons is not None:
            editor.set_labels(asset_id, "persons", body.persons)
        return detail(asset_id)

    @app.post("/api/assets/{asset_id}/rotate")
    def asset_rotate(asset_id: int, body: RotateRequest):
        editor.rotate(asset_id, body.degrees)
        return detail(asset_id)

    @app.delete("/api/assets/{asset_id}")
    def asset_delete(asset_id: int):
        editor.delete(asset_id)
        return {"deleted": True}

    @app.post("/api/assets/{asset_id}/restore")
    def asset_restore(asset_id: int):
        editor.restore(asset_id)
        return detail(asset_id)

    @app.get("/api/assets/{asset_id}/thumb")
    def asset_thumb(asset_id: int, size: Literal["normal", "small"] = "normal"):
        asset_row(asset_id)
        path = importer.ensure_small(asset_id) if size == "small" else importer.ensure_thumbnail(asset_id)
        if path is None:
            return placeholder()
        return FileResponse(path, media_type="image/webp", headers=LONG_CACHE)

    @app.get("/api/assets/{asset_id}/preview")
    def asset_preview(asset_id: int):
        asset_row(asset_id)
        path = importer.ensure_preview(asset_id)
        if path is None:
            return placeholder()
        return FileResponse(path, media_type="image/webp", headers=LONG_CACHE)

    @app.get("/api/assets/{asset_id}/original")
    def asset_original(asset_id: int, download: bool = False):
        row = asset_row(asset_id)
        path = settings.library / row["path"]
        if not path.is_file():
            raise HTTPException(404, "Datei fehlt auf dem Datenträger")
        return FileResponse(
            path,
            media_type=media.mime_of(path),
            filename=path.name,
            content_disposition_type="attachment" if download else "inline",
        )

    # ── Mehrfachauswahl ────────────────────────────────────────────
    @app.post("/api/batch")
    def batch(body: BatchRequest, request: Request):
        if body.action == "purge" and role_of(request) != "admin":
            raise HTTPException(403, "Endgültig löschen ist nur über Home Assistant möglich")
        if body.action == "convert" and role_of(request) != "admin":
            raise HTTPException(403, "Umwandeln ist nur über Home Assistant möglich")
        if body.action in ("delete", "restore") and role_of(request) == "uploader":
            raise HTTPException(403, "Löschen ist mit diesem Konto nicht möglich")
        count = len(set(body.ids))
        kind, params = body.action, {}
        if body.action in ("tags", "persons"):
            if not body.add and not body.remove:
                raise HTTPException(400, "Nichts hinzuzufügen oder zu entfernen")
            word = "Schlagworte" if body.action == "tags" else "Personen"
            label = f"{word} bei {count} Dateien ändern"
            kind, params = "labels", {"kind": body.action, "add": body.add, "remove": body.remove}
        elif body.action == "date":
            if body.taken_at is None:
                raise HTTPException(400, "Datum fehlt")
            label, params = f"Datum bei {count} Dateien setzen", {"taken_at": body.taken_at.replace(tzinfo=None).isoformat()}
        elif body.action == "location":
            if "location" not in body.model_fields_set:
                raise HTTPException(400, "Ort fehlt")
            loc = body.location
            label = f"Ort bei {count} Dateien {'setzen' if loc else 'entfernen'}"
            params = {"lat": loc.lat if loc else None, "lon": loc.lon if loc else None}
        elif body.action == "shift":
            if body.dlat is None or body.dlon is None:
                raise HTTPException(400, "Versatz fehlt")
            label, params = f"{count} Dateien auf der Karte verschieben", {"dlat": body.dlat, "dlon": body.dlon}
        elif body.action == "rotate":
            if body.degrees is None:
                raise HTTPException(400, "Drehung fehlt")
            label, params = f"{count} Dateien drehen", {"degrees": body.degrees}
        elif body.action == "delete":
            label = f"{count} Dateien in den Papierkorb"
        elif body.action == "restore":
            label = f"{count} Dateien wiederherstellen"
        elif body.action == "convert":
            label = f"{count} Dateien zum Umwandeln vormerken"
        else:
            label = f"{count} Dateien endgültig löschen"
        return tasks.submit(kind, label, body.ids, params)

    @app.get("/api/tasks")
    def task_list():
        return tasks.list()

    if not public:  # Verwaltung: Papierkorb leeren, Abgleich, Import – nur über Home Assistant
        @app.post("/api/trash/empty")
        def trash_empty():
            ids = [r["id"] for r in db.query("SELECT id FROM assets WHERE deleted_at IS NOT NULL")]
            if not ids:
                raise HTTPException(400, "Der Papierkorb ist leer")
            return tasks.submit("purge", f"Papierkorb leeren ({len(ids)} Dateien)", ids)

        @app.post("/api/convert/dismiss")
        def convert_dismiss():
            return {"dismissed": ctx.converter.dismiss_failed()}

        @app.post("/api/delete-requests/dismiss")
        def delete_request_dismiss(body: DeleteRequestIds):
            """Löschvorschläge ablehnen: die Fotos bleiben, die Vorschläge verschwinden."""
            ids = sorted(set(body.ids))
            count = db.execute(f"DELETE FROM delete_requests WHERE asset_id IN ({','.join('?' * len(ids))})", ids).rowcount
            db.bump()
            return {"dismissed": count}

        @app.post("/api/library/remove-missing")
        def remove_missing():
            """Einträge ohne Datei entfernen – erst nach dem Abgleich und ausdrücklich vom Nutzer ausgelöst."""
            if importer.job.running:
                raise HTTPException(409, "Es läuft gerade ein Import oder Abgleich")
            if not importer.library_reachable():
                raise HTTPException(409, "Die Bibliothek ist leer oder nicht erreichbar – ist das Laufwerk eingebunden?")
            ids = [row["id"] for row in importer.missing_assets()]
            if not ids:
                raise HTTPException(400, "Es fehlen keine Dateien")
            label = "1 fehlenden Eintrag entfernen" if len(ids) == 1 else f"{len(ids)} fehlende Einträge entfernen"
            return tasks.submit("forget", label, ids)

        # ── Import ─────────────────────────────────────────────────────
        @app.get("/api/import")
        def import_status():
            return asdict(importer.job)

        @app.post("/api/import")
        def import_start(body: ImportRequest):
            if not importer.start(body.mode, on_done=faces.wake, deep=body.deep):
                raise HTTPException(409, "Es läuft bereits ein Import")
            return {"started": True}

        @app.post("/api/import/cancel")
        def import_cancel():
            if not importer.cancel():
                raise HTTPException(409, "Es läuft kein Import")
            return {"cancelled": True}

    @app.put("/api/upload")
    async def upload(request: Request, name: str, mtime: float | None = None):
        """Rohe Datei im Body; so gibt es keinen Zwischenpuffer wie bei multipart."""
        if media.kind_of(Path(name)) is None:
            raise HTTPException(415, "Dateityp wird nicht unterstützt")
        settings.upload_tmp.mkdir(parents=True, exist_ok=True)
        temp = settings.upload_tmp / f"{uuid.uuid4().hex}{Path(safe_name(name)).suffix}"
        received = 0
        try:
            with open(temp, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
                    received += len(chunk)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        # Bricht die Verbindung unterwegs ab (Proxy, Funkloch), endet der Datenstrom womöglich ohne Fehler –
        # dann käme eine halbe Datei ins Archiv
        expected = request.headers.get("content-length", "")
        if expected.isdigit() and received != int(expected):
            temp.unlink(missing_ok=True)
            raise HTTPException(400, f"Upload unvollständig ({received} von {expected} Bytes) – bitte erneut hochladen")
        return await finish_upload(temp, name, mtime)

    async def finish_upload(temp: Path, name: str, mtime: float | None) -> JSONResponse:
        # Browser liefern lastModified in Millisekunden
        seconds = mtime / 1000 if mtime and mtime > 1e11 else mtime
        result = await run_in_threadpool(importer.import_upload, temp, name, seconds)
        faces.wake()
        ctx.duplicates.wake()
        status = 500 if result.status == "error" else 422 if result.status == "damaged" else 200
        return JSONResponse(result.__dict__, status_code=status)

    @app.post("/api/upload/known")
    def upload_known(body: KnownRequest):
        """Vorab fragen, bevor ein Handy stundenlang schon Vorhandenes hochlädt: gleicher Name und gleiche
        Größe wie eine Datei im Archiv oder Papierkorb gilt als bekannt und wird gar nicht erst gesendet.
        Die MD5-Prüfung beim Import bleibt die eigentliche Sicherung gegen Duplikate."""
        sizes = sorted({f.size for f in body.files})
        known: dict[int, set[str]] = {}
        for start in range(0, len(sizes), 500):
            part = sizes[start:start + 500]
            rows = db.query(f"SELECT path, size FROM assets WHERE size IN ({','.join('?' * len(part))})", part)
            for row in rows:
                known.setdefault(row["size"], set()).update(_name_forms(Path(row["path"]).name))
        return {"known": [safe_name(f.name).lower() in known.get(f.size, ()) for f in body.files]}

    @app.put("/api/upload/chunk")
    async def upload_chunk(request: Request, upload_id: str, name: str, offset: int, total: int,
                           mtime: float | None = None):
        """Große Dateien in Stücken: Cloudflare lässt im kostenlosen Tarif nur 100 MB je Anfrage durch.
        Die Stücke werden in einer Teildatei aneinandergehängt; mit dem letzten wird sie importiert.
        Passt offset nicht zum bisher Empfangenen, meldet 409 den Stand, und der Browser macht dort weiter."""
        if not UPLOAD_ID.fullmatch(upload_id):
            raise HTTPException(400, "Ungültige Upload-Kennung")
        if media.kind_of(Path(name)) is None:
            raise HTTPException(415, "Dateityp wird nicht unterstützt")
        if not 0 < total <= UPLOAD_MAX or not 0 <= offset < total:
            raise HTTPException(400, "Ungültige Größenangabe")
        session = getattr(request.state, "session", None)
        owner = f"u{session['user_id']}" if session else "ha"  # fremde Uploads lassen sich nicht fortsetzen
        settings.upload_tmp.mkdir(parents=True, exist_ok=True)
        temp = settings.upload_tmp / f"part-{owner}-{upload_id}{Path(safe_name(name)).suffix}"
        have = temp.stat().st_size if temp.exists() else 0
        if offset != 0 and offset != have:
            return JSONResponse({"detail": "Upload an anderer Stelle fortsetzen", "received": have}, status_code=409)
        received = 0
        try:
            with open(temp, "wb" if offset == 0 else "ab") as f:
                async for chunk in request.stream():
                    received += len(chunk)
                    if offset + received > total or received > CHUNK_MAX:
                        raise HTTPException(413, "Stück zu groß")
                    f.write(chunk)
        except Exception:
            _truncate(temp, offset)
            raise
        expected = request.headers.get("content-length", "")
        if expected.isdigit() and received != int(expected):
            _truncate(temp, offset)  # halbes Stück verwerfen, der Browser schickt es noch einmal
            return JSONResponse({"detail": "Stück unvollständig angekommen", "received": offset}, status_code=409)
        if offset + received < total:
            return JSONResponse({"status": "partial", "received": offset + received}, status_code=202)
        return await finish_upload(temp, name, mtime)

    faces_api.register(app, db, faces, tasks)
    duplicates_api.register(app, ctx)
