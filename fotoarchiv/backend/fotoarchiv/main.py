"""HTTP-API und Auslieferung der Oberfläche."""

import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import config, media
from .db import Database
from .exiftool import ExifTool
from .importer import Importer, safe_name

log = logging.getLogger(__name__)

STATIC_DIR = Path(os.environ.get("FOTOARCHIV_STATIC") or Path(__file__).resolve().parent.parent / "static")
# Home Assistant Ingress kommt immer von dieser Adresse
INGRESS_CLIENTS = {"172.30.32.2", "127.0.0.1", "::1"}
LONG_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}


class ImportRequest(BaseModel):
    mode: str = "import"


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    db = Database(settings.db_path)
    exiftool = ExifTool(settings.exiftool)
    importer = Importer(settings, db, exiftool)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        shutil.rmtree(settings.upload_tmp, ignore_errors=True)  # Reste abgebrochener Uploads
        for folder in (settings.library, settings.import_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.error("Ordner %s nicht anlegbar: %s", folder, exc)
        log.info("Bibliothek: %s | Import: %s", settings.library, settings.import_dir)
        yield
        exiftool.close()
        db.close()

    app = FastAPI(title="Fotoarchiv", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Nur Text/JSON komprimieren; Bilder und Videos sind es schon, das kostet auf dem Pi nur Zeit
    binary_types = ("image/webp", *media.IMAGE_TYPES.values(), *media.VIDEO_TYPES.values())
    app.add_middleware(GZipMiddleware, minimum_size=1024, exclude_content_types=tuple(set(binary_types)))
    app.state.settings, app.state.db, app.state.importer = settings, db, importer

    @app.middleware("http")
    async def ingress_only(request: Request, call_next):
        host = request.client.host if request.client else ""
        if not settings.dev and host not in INGRESS_CLIENTS:
            return PlainTextResponse("Nur über Home Assistant erreichbar", status_code=403)
        response = await call_next(request)
        if not request.url.path.startswith("/api/") and not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"  # index.html immer frisch
        return response

    def asset_row(asset_id: int):
        row = db.one("SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (asset_id,))
        if row is None:
            raise HTTPException(404, "Bild nicht gefunden")
        return row

    # ── Übersicht ──────────────────────────────────────────────────
    @app.get("/api/state")
    def state():
        counts = db.one(
            """SELECT COUNT(*) AS total, COALESCE(SUM(kind = 'image'), 0) AS images,
                      COALESCE(SUM(kind = 'video'), 0) AS videos, COALESCE(SUM(size), 0) AS bytes
               FROM assets WHERE deleted_at IS NULL"""
        )
        return {
            "revision": db.revision,
            "counts": dict(counts),
            "library": str(settings.library),
            "import_dir": str(settings.import_dir),
            "importing": importer.job.running,
            "tools": {
                "vips": media.pyvips is not None,
                "exiftool": shutil.which(settings.exiftool) is not None,
                "ffmpeg": shutil.which(settings.ffmpeg) is not None,
            },
        }

    @app.get("/api/assets")
    def asset_index():
        """Kompakte Liste aller Bilder für Galerie und Zeitleiste, neueste zuerst."""
        rows = db.query(
            """SELECT id, taken_ts, width, height, kind, rev FROM assets
               WHERE deleted_at IS NULL ORDER BY taken_ts DESC, id DESC"""
        )
        items = [
            [r["id"], r["taken_ts"], r["width"] or 0, r["height"] or 0, 1 if r["kind"] == "video" else 0, r["rev"]]
            for r in rows
        ]
        return {"revision": db.revision, "fields": ["id", "ts", "w", "h", "video", "rev"], "items": items}

    @app.get("/api/assets/{asset_id}")
    def asset_detail(asset_id: int):
        row = asset_row(asset_id)
        tags = db.query(
            "SELECT t.name FROM tags t JOIN asset_tags a ON a.tag_id = t.id WHERE a.asset_id = ? ORDER BY t.name",
            (asset_id,),
        )
        persons = db.query(
            "SELECT p.name FROM persons p JOIN asset_persons a ON a.person_id = p.id WHERE a.asset_id = ? ORDER BY p.name",
            (asset_id,),
        )
        detail = {key: row[key] for key in row.keys() if key not in ("md5_import", "thumb_ok", "deleted_at")}
        detail["name"] = Path(row["path"]).name
        detail["tags"] = [t["name"] for t in tags]
        detail["persons"] = [p["name"] for p in persons]
        return detail

    @app.get("/api/assets/{asset_id}/thumb")
    def asset_thumb(asset_id: int):
        asset_row(asset_id)
        path = importer.ensure_thumbnail(asset_id)
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

    # ── Import ─────────────────────────────────────────────────────
    @app.get("/api/import")
    def import_status():
        return asdict(importer.job)

    @app.post("/api/import")
    def import_start(body: ImportRequest):
        if body.mode not in ("import", "library"):
            raise HTTPException(400, "Unbekannter Modus")
        if not importer.start(body.mode):
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
        status = 500 if result.status == "error" else 200
        return JSONResponse(result.__dict__, status_code=status)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
