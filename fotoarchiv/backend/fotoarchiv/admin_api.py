"""Verwaltung des Internetzugangs – nur über Home Assistant (Ingress) erreichbar.

Konten, aktive Sitzungen, Sperren, Zugriffsprotokoll und CrowdSec-Einrichtung.
"""

import json
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .auth import PASSWORD_MIN, AuthError
from .context import Context

log = logging.getLogger(__name__)

# Beide Add-ons sehen das Home-Assistant-Konfigurationsverzeichnis; /share ist im CrowdSec-Add-on nicht eingebunden
CROWDSEC_DIR = Path(os.environ.get("FOTOARCHIV_CROWDSEC_DIR", "/config/.storage/crowdsec/config"))
CROWDSEC_EXPORT = os.environ.get("FOTOARCHIV_CROWDSEC_EXPORT", "/config/.fotoarchiv/public_access.log")
CROWDSEC_FILES = {
    "parsers/s01-parse/fotoarchiv-public.yaml": "fotoarchiv-public-parser.yaml",
    "scenarios/fotoarchiv-public.yaml": "fotoarchiv-public-scenarios.yaml",
    "acquis.d/fotoarchiv-public.yaml": "fotoarchiv-public-acquis.yaml",
}
SOURCE = Path(__file__).resolve().parent / "crowdsec"


class UserCreate(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    display_name: str = Field("", max_length=80)
    role: str = "viewer"


class UserUpdate(BaseModel):
    password: str | None = Field(None, max_length=256)
    display_name: str | None = Field(None, max_length=80)
    role: str | None = None
    enabled: bool | None = None


class UnlockRequest(BaseModel):
    key: str = Field(max_length=200)


def crowdsec_setup_file(ctx: Context) -> Path:
    return ctx.settings.data / "crowdsec_setup.json"


def crowdsec_installed() -> bool:
    return (CROWDSEC_DIR / "acquis.d" / "fotoarchiv-public.yaml").is_file()


def apply_saved_export(ctx: Context):
    """Nach einem Neustart den Export für CrowdSec wieder öffnen, wenn er eingerichtet wurde."""
    if crowdsec_installed() or crowdsec_setup_file(ctx).is_file():
        ctx.access.set_export(CROWDSEC_EXPORT, slot="crowdsec")


def register(app: FastAPI, ctx: Context):
    settings, auth, limiter, access = ctx.settings, ctx.auth, ctx.limiter, ctx.access

    def guard(action, *args, **kwargs):
        try:
            return action(*args, **kwargs)
        except AuthError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/admin/access")
    def admin_access():
        return {
            "enabled": settings.public_enabled,
            "port": settings.public_port,
            "trusted_proxies": list(settings.public_trusted_proxies),
            "cookie_secure": settings.public_cookie_secure,
            "session_hours": settings.public_session_hours,
            "password_min": PASSWORD_MIN,
            "users": len(auth.list_users()),
        }

    # ── Konten ─────────────────────────────────────────────────────
    @app.get("/api/admin/users")
    def admin_users():
        return auth.list_users()

    @app.post("/api/admin/users", status_code=201)
    def admin_user_create(body: UserCreate):
        user = guard(auth.create_user, body.username, body.password, body.display_name, body.role)
        log.info("[Zugang] Konto angelegt: %s (%s)", user["username"], user["role"])
        return user

    @app.patch("/api/admin/users/{user_id}")
    def admin_user_update(user_id: int, body: UserUpdate):
        user = guard(auth.update_user, user_id, password=body.password or None, display_name=body.display_name,
                     role=body.role, enabled=body.enabled)
        log.info("[Zugang] Konto geändert: %s", user["username"])
        return user

    @app.delete("/api/admin/users/{user_id}")
    def admin_user_delete(user_id: int):
        guard(auth.delete_user, user_id)
        return {"deleted": True}

    # ── Sitzungen und Sperren ──────────────────────────────────────
    @app.get("/api/admin/sessions")
    def admin_sessions():
        return auth.list_sessions()

    @app.delete("/api/admin/sessions/{session_id}")
    def admin_session_revoke(session_id: str):
        if not auth.revoke_session(session_id):
            raise HTTPException(404, "Sitzung nicht gefunden")
        return {"revoked": True}

    @app.get("/api/admin/locks")
    def admin_locks():
        return limiter.snapshot()

    @app.post("/api/admin/locks/unlock")
    def admin_unlock(body: UnlockRequest):
        key = body.key.strip()
        if not re.match(r"^(authfail:(ip|user):|ban:|scan:)", key):
            raise HTTPException(400, "Unbekannte Sperre")
        limiter.clear(key=key)
        if key.startswith("ban:"):
            limiter.clear(key=f"scan:{key[4:]}")  # sonst sperrt der alte Zähler sofort wieder
        log.info("[Zugang] Sperre aufgehoben: %s", key)
        return {"ok": True}

    # ── Protokoll ──────────────────────────────────────────────────
    @app.get("/api/admin/log")
    def admin_log(limit: int = 200, event: str | None = None):
        return access.tail(max(1, min(limit, 1000)), event or None)

    @app.delete("/api/admin/log")
    def admin_log_clear():
        access.clear()
        return {"ok": True}

    # ── CrowdSec ───────────────────────────────────────────────────
    @app.get("/api/admin/crowdsec")
    def admin_crowdsec():
        installed = {rel: (CROWDSEC_DIR / rel).is_file() for rel in CROWDSEC_FILES}
        return {
            "config_found": CROWDSEC_DIR.is_dir(),
            "config_dir": str(CROWDSEC_DIR),
            "installed": installed,
            "all_installed": CROWDSEC_DIR.is_dir() and all(installed.values()),
            "export_path": CROWDSEC_EXPORT,
            "export_active": access.writes_to(CROWDSEC_EXPORT),
        }

    @app.post("/api/admin/crowdsec/install")
    def admin_crowdsec_install():
        """Parser, Szenarien und Log-Quelle in die Konfiguration des CrowdSec-Add-ons kopieren."""
        if not CROWDSEC_DIR.is_dir():
            raise HTTPException(404, f"CrowdSec-Konfiguration nicht gefunden ({CROWDSEC_DIR}). Ist das CrowdSec-Add-on installiert?")
        if not access.set_export(CROWDSEC_EXPORT, slot="crowdsec"):
            raise HTTPException(500, f"Protokoll-Export nach {CROWDSEC_EXPORT} nicht möglich")
        written = []
        for rel, source in CROWDSEC_FILES.items():
            content = (SOURCE / source).read_text(encoding="utf-8")
            if rel.startswith("acquis.d/"):
                content = re.sub(r"(?m)^(\s*-\s+)\S+$", lambda m: m.group(1) + CROWDSEC_EXPORT, content, count=1)
            target = CROWDSEC_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel)
        crowdsec_setup_file(ctx).write_text(json.dumps({"export_path": CROWDSEC_EXPORT}), encoding="utf-8")
        log.info("[Zugang] CrowdSec-Dateien installiert: %s", ", ".join(written))
        return {"ok": True, "written": written, "restart_needed": "CrowdSec"}
