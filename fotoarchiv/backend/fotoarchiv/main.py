"""Zugang über Home Assistant (Ingress): volle Rechte, keine eigene Anmeldung."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import admin_api, api, config, context

log = logging.getLogger(__name__)

STATIC_DIR = Path(os.environ.get("FOTOARCHIV_STATIC") or Path(__file__).resolve().parent.parent / "static")
# Home Assistant Ingress kommt immer von dieser Adresse
INGRESS_CLIENTS = {"172.30.32.2", "127.0.0.1", "::1"}


def create_app(settings: config.Settings | None = None) -> FastAPI:
    ctx = context.build(settings or config.load())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        ctx.start()
        yield
        ctx.stop()

    app = FastAPI(title="Fotoarchiv", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    api.install_common(app)
    app.state.ctx = ctx
    # Kurzformen für Tests und Werkzeuge
    app.state.settings, app.state.db, app.state.importer = ctx.settings, ctx.db, ctx.importer
    app.state.editor, app.state.tasks, app.state.faces = ctx.editor, ctx.tasks, ctx.faces

    @app.middleware("http")
    async def ingress_only(request: Request, call_next):
        host = request.client.host if request.client else ""
        if not ctx.settings.dev and host not in INGRESS_CLIENTS:
            return PlainTextResponse("Nur über Home Assistant erreichbar", status_code=403)
        request.state.role = "admin"  # Home Assistant hat bereits angemeldet
        response = await call_next(request)
        if not request.url.path.startswith("/api/") and not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"  # index.html immer frisch
        return response

    @app.get("/api/auth/session")
    def auth_session():
        return {"authenticated": True, "public": False, "role": "admin", "user": None, "csrf": None}

    api.register(app, ctx, public=False)
    admin_api.register(app, ctx)
    admin_api.apply_saved_export(ctx)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
