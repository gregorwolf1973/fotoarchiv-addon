"""HTTP-API und Auslieferung der Oberfläche."""

import calendar
import logging
import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import config, faces_api, labels, media
from .db import Database
from .editor import WRITABLE, EditError, Editor, capabilities
from .exiftool import ExifTool
from .faces import FaceService
from .importer import Importer, safe_name
from .tasks import TaskRunner

log = logging.getLogger(__name__)

STATIC_DIR = Path(os.environ.get("FOTOARCHIV_STATIC") or Path(__file__).resolve().parent.parent / "static")
# Home Assistant Ingress kommt immer von dieser Adresse
INGRESS_CLIENTS = {"172.30.32.2", "127.0.0.1", "::1"}
LONG_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}
PURGE_INTERVAL = 3600


class ImportRequest(BaseModel):
    mode: Literal["import", "library"] = "import"


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AssetPatch(BaseModel):
    taken_at: datetime | None = None
    location: Location | None = None  # ausdrücklich null = Ort entfernen
    tags: list[str] | None = None
    persons: list[str] | None = None


class RotateRequest(BaseModel):
    degrees: Literal[90, 180, 270]


class BatchRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    action: Literal["tags", "persons", "date", "location", "rotate", "delete", "restore", "purge"]
    add: list[str] = []
    remove: list[str] = []
    taken_at: datetime | None = None
    degrees: Literal[90, 180, 270] | None = None
    location: Location | None = None  # bei action=location: null entfernt den Ort


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
        if self.editable is not None:
            suffixes = " OR ".join("lower(path) LIKE ?" for _ in WRITABLE)
            where.append(f"({suffixes})" if self.editable else f"NOT ({suffixes})")
            params += [f"%{suffix}" for suffix in sorted(WRITABLE)]
        return " AND ".join(where), params


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    db = Database(settings.db_path)
    exiftool = ExifTool(settings.exiftool)
    importer = Importer(settings, db, exiftool)
    editor = Editor(settings, db, exiftool, importer)
    tasks = TaskRunner(on_progress=db.bump)
    faces = FaceService(settings, db, editor, enabled=settings.face_recognition)
    stop = threading.Event()

    def purge_loop():
        while not stop.is_set():
            try:
                editor.purge_expired(settings.trash_days)
            except Exception:
                log.exception("Papierkorb-Bereinigung fehlgeschlagen")
            stop.wait(PURGE_INTERVAL)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        shutil.rmtree(settings.upload_tmp, ignore_errors=True)  # Reste abgebrochener Uploads
        for folder in (settings.library, settings.import_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.error("Ordner %s nicht anlegbar: %s", folder, exc)
        log.info("Bibliothek: %s | Import: %s | Papierkorb: %d Tage",
                 settings.library, settings.import_dir, settings.trash_days)
        threading.Thread(target=purge_loop, daemon=True, name="purge").start()
        faces.start()
        yield
        faces.stop()
        stop.set()
        exiftool.close()
        db.close()

    app = FastAPI(title="Fotoarchiv", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Nur Text/JSON komprimieren; Bilder und Videos sind es schon, das kostet auf dem Pi nur Zeit
    binary_types = ("image/webp", *media.IMAGE_TYPES.values(), *media.VIDEO_TYPES.values())
    app.add_middleware(GZipMiddleware, minimum_size=1024, exclude_content_types=tuple(set(binary_types)))
    app.state.settings, app.state.db, app.state.importer = settings, db, importer
    app.state.editor, app.state.tasks, app.state.faces = editor, tasks, faces

    @app.middleware("http")
    async def ingress_only(request: Request, call_next):
        host = request.client.host if request.client else ""
        if not settings.dev and host not in INGRESS_CLIENTS:
            return PlainTextResponse("Nur über Home Assistant erreichbar", status_code=403)
        response = await call_next(request)
        if not request.url.path.startswith("/api/") and not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"  # index.html immer frisch
        return response

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
            "counts": dict(counts),
            "library": str(settings.library),
            "import_dir": str(settings.import_dir),
            "trash_days": settings.trash_days,
            "importing": importer.job.running,
            "tasks_running": any(task.running for task in tasks.list()),
            "faces": {"enabled": faces.enabled, "status": faces.state["status"]},
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
        if row["deleted_at"]:
            expires = datetime.fromisoformat(row["deleted_at"]) + timedelta(days=settings.trash_days)
            result["expires_at"] = expires.isoformat(timespec="seconds")
        return result

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
            raise HTTPException(404, "Kein Vorschaubild")
        return FileResponse(path, media_type="image/webp", headers=LONG_CACHE)

    @app.get("/api/assets/{asset_id}/preview")
    def asset_preview(asset_id: int):
        asset_row(asset_id)
        path = importer.ensure_preview(asset_id)
        if path is None:
            raise HTTPException(404, "Keine Großansicht")
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
    def batch(body: BatchRequest):
        count = len(set(body.ids))
        if body.action in ("tags", "persons"):
            if not body.add and not body.remove:
                raise HTTPException(400, "Nichts hinzuzufügen oder zu entfernen")
            word = "Schlagworte" if body.action == "tags" else "Personen"
            label = f"{word} bei {count} Dateien ändern"
            action = lambda i: editor.change_labels(i, body.action, body.add, body.remove)  # noqa: E731
        elif body.action == "date":
            if body.taken_at is None:
                raise HTTPException(400, "Datum fehlt")
            label, action = f"Datum bei {count} Dateien setzen", lambda i: editor.set_date(i, body.taken_at)
        elif body.action == "location":
            if "location" not in body.model_fields_set:
                raise HTTPException(400, "Ort fehlt")
            loc = body.location
            label = f"Ort bei {count} Dateien {'setzen' if loc else 'entfernen'}"
            action = lambda i: editor.set_location(i, loc.lat if loc else None, loc.lon if loc else None)  # noqa: E731
        elif body.action == "rotate":
            if body.degrees is None:
                raise HTTPException(400, "Drehung fehlt")
            label, action = f"{count} Dateien drehen", lambda i: editor.rotate(i, body.degrees)
        elif body.action == "delete":
            label, action = f"{count} Dateien in den Papierkorb", editor.delete
        elif body.action == "restore":
            label, action = f"{count} Dateien wiederherstellen", editor.restore
        else:
            label, action = f"{count} Dateien endgültig löschen", editor.purge
        return asdict(tasks.submit(label, body.ids, action))

    @app.get("/api/tasks")
    def task_list():
        return [asdict(task) for task in tasks.list()]

    @app.post("/api/trash/empty")
    def trash_empty():
        ids = [r["id"] for r in db.query("SELECT id FROM assets WHERE deleted_at IS NOT NULL")]
        if not ids:
            raise HTTPException(400, "Der Papierkorb ist leer")
        return asdict(tasks.submit(f"Papierkorb leeren ({len(ids)} Dateien)", ids, editor.purge))

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
        return asdict(tasks.submit(label, ids, editor.forget))

    # ── Import ─────────────────────────────────────────────────────
    @app.get("/api/import")
    def import_status():
        return asdict(importer.job)

    @app.post("/api/import")
    def import_start(body: ImportRequest):
        if not importer.start(body.mode, on_done=faces.wake):
            raise HTTPException(409, "Es läuft bereits ein Import")
        return {"started": True}

    @app.put("/api/upload")
    async def upload(request: Request, name: str, mtime: float | None = None):
        """Rohe Datei im Body; so gibt es keinen Zwischenpuffer wie bei multipart."""
        if media.kind_of(Path(name)) is None:
            raise HTTPException(415, "Dateityp wird nicht unterstützt")
        settings.upload_tmp.mkdir(parents=True, exist_ok=True)
        temp = settings.upload_tmp / f"{uuid.uuid4().hex}{Path(safe_name(name)).suffix}"
        try:
            with open(temp, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        # Browser liefern lastModified in Millisekunden
        seconds = mtime / 1000 if mtime and mtime > 1e11 else mtime
        result = await run_in_threadpool(importer.import_upload, temp, name, seconds)
        faces.wake()
        status = 500 if result.status == "error" else 200
        return JSONResponse(result.__dict__, status_code=status)

    faces_api.register(app, db, faces, tasks)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
