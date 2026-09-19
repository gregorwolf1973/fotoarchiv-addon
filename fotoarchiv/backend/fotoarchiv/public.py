"""Internetzugang: eigener Port mit Anmeldung, Rollen, Sperren und Sicherheits-Headern.

Nach dem Vorbild der Freigabe-Seite von Simple NAS:
- nichts ohne Anmeldung außer der Oberfläche selbst und den Anmelde-Endpunkten
- jeder API-Endpunkt ist ausdrücklich einer Rolle zugeordnet; ein neuer, nicht zugeordneter
  Endpunkt verhindert den Start (lieber gar nicht als versehentlich offen)
- Fehlversuche sperren eskalierend, Scanner werden gesperrt, alles landet im Zugriffsprotokoll
"""

import hmac
import ipaddress
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.routing import Match

from . import api
from .auth import AuthError, LoginFailed, LoginLocked
from .context import Context
from .ratelimit import LOCK_BASE, LOCK_CAP, REQ_ANON_PER_IP, REQ_AUTH_PER_USER, SCAN_PER_IP

log = logging.getLogger(__name__)

COOKIE = "fotoarchiv_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

OPEN = {"auth_session", "auth_login", "auth_logout"}
VIEW = {
    "state", "asset_index", "asset_largest", "asset_geo", "label_list", "asset_detail", "asset_thumb", "asset_preview",
    "asset_original", "task_list", "face_status", "people", "group_faces", "person_faces", "asset_faces",
    "face_crop", "auth_password",  # eigenes Passwort ändern: jede angemeldete Rolle
}
EDIT = {
    "asset_update", "asset_rotate", "asset_delete", "asset_restore", "batch", "upload", "upload_chunk", "upload_known",
    "group_name", "group_hide", "person_rename", "person_merge", "person_delete", "face_assign", "face_remove",
    "duplicate_list", "duplicate_resolve", "duplicate_ignore",
}
# Was eine Rolle über das Ansehen hinaus darf
# Alles, womit Bilder verschwinden: Papierkorb, Wiederherstellen und die Duplikat-Bereinigung
DELETING = {"asset_delete", "asset_restore", "duplicate_list", "duplicate_resolve", "duplicate_ignore"}
# uploader: hochladen und bearbeiten, aber keine Bilder löschen (Mehrfachaktion: siehe api.batch)
ALLOWED = {"viewer": set(), "uploader": EDIT - DELETING, "editor": EDIT}
# Bilder zählen nicht als Scan: ein abgelaufenes Cookie lädt sonst dutzende Vorschaubilder und sperrt sich selbst
IMAGES = {"asset_thumb", "asset_preview", "asset_original", "face_crop"}

CSP = (
    "default-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; "
    "connect-src 'self' https://nominatim.openstreetmap.org; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class PasswordChange(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


def create_public_app(ctx: Context, static_dir: Path | None = None) -> FastAPI:
    settings, auth, limiter, access = ctx.settings, ctx.auth, ctx.limiter, ctx.access
    app = FastAPI(title="Fotoarchiv", docs_url=None, redoc_url=None, openapi_url=None)
    api.install_common(app)

    networks = []
    for entry in settings.public_trusted_proxies:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            log.warning("Ungültiger vertrauenswürdiger Proxy: %s", entry)

    def trusted(address: str) -> bool:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(ip in net for net in networks)

    def client_ip(request: Request) -> str:
        """Adresse für Sperren und Protokoll.

        Nur wenn die Anfrage wirklich von einem vertrauenswürdigen Proxy kommt, zählen dessen Angaben:
        CF-Connecting-IP (Cloudflare) oder X-Forwarded-For von rechts, bis zur ersten fremden Adresse.
        """
        peer = request.client.host if request.client else ""
        if not trusted(peer):
            return peer or "?"
        cloudflare = request.headers.get("cf-connecting-ip", "").strip()
        if cloudflare:
            return cloudflare
        chain = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
        for address in reversed(chain):
            if not trusted(address):
                return address
        return chain[0] if chain else peer

    def scheme(request: Request) -> str:
        peer = request.client.host if request.client else ""
        if trusted(peer):
            return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        return request.url.scheme

    def endpoint_name(request: Request) -> str | None:
        for route in app.router.routes:
            match, _scope = route.matches(request.scope)
            if match == Match.FULL:
                return route.name
        return None

    def reply(status: int, detail: str, **extra) -> JSONResponse:
        return JSONResponse({"detail": detail, **extra}, status_code=status)

    def count_scan(ip: str):
        limiter.record(f"scan:{ip}")
        if limiter.count(f"scan:{ip}", SCAN_PER_IP[1]) >= SCAN_PER_IP[0] and not limiter.banned(f"ban:{ip}"):
            duration = limiter.lock(f"ban:{ip}", LOCK_BASE, LOCK_CAP)
            access.log("rate_limited", ip=ip, detail=f"scanner ban {duration // 60} min")

    @app.middleware("http")
    async def gate(request: Request, call_next):
        ip = client_ip(request)
        request.state.ip = ip
        if limiter.banned(f"ban:{ip}"):
            response = reply(429, "Zu viele Anfragen. Bitte später erneut versuchen.")
            response.headers["Retry-After"] = str(limiter.ban_remaining(f"ban:{ip}"))
            return secure(request, response)

        session = auth.session(request.cookies.get(COOKIE))
        request.state.session = session
        request.state.role = session["role"] if session else None
        name = endpoint_name(request)
        # Getrennte Zähler: Manifest und Symbole lädt der Browser ohne Cookie; sie dürfen nicht an den
        # Vorschaubildern scheitern, die jemand anderes im selben Haushalt gerade lädt
        if session:
            allowed, retry = (True, 0) if name in IMAGES else limiter.hit(f"user:{session['user_id']}", *REQ_AUTH_PER_USER)
        else:
            allowed, retry = limiter.hit(f"ip:{ip}", *REQ_ANON_PER_IP)
        if not allowed:
            access.log("rate_limited", ip=ip, user=session["username"] if session else None,
                       path=request.url.path, detail="requests per minute")
            response = reply(429, "Zu viele Anfragen. Bitte kurz warten.")
            response.headers["Retry-After"] = str(retry)
            return secure(request, response)

        if request.url.path.startswith("/api/"):
            if name in OPEN:
                pass
            elif name in VIEW or name in EDIT:
                if session is None:
                    if name not in IMAGES:
                        count_scan(ip)
                        access.log("unauthorized", ip=ip, path=request.url.path, ua=request.headers.get("user-agent"))
                    return secure(request, reply(401, "Anmeldung erforderlich"))
                if name in EDIT and name not in ALLOWED.get(session["role"], set()):
                    access.log("forbidden", ip=ip, user=session["username"], path=request.url.path)
                    return secure(request, reply(403, "Dafür fehlt die Berechtigung"))
            else:
                count_scan(ip)
                access.log("not_found", ip=ip, path=request.url.path, ua=request.headers.get("user-agent"))
                return secure(request, reply(404, "Nicht gefunden"))
            if request.method not in SAFE_METHODS and session is not None:
                sent = request.headers.get("x-csrf-token", "")
                if not sent or not hmac.compare_digest(sent, session["csrf"]):
                    return secure(request, reply(403, "Sicherheitsprüfung fehlgeschlagen – bitte die Seite neu laden"))

        response = await call_next(request)
        # 202 = weiteres Stück eines Uploads; protokolliert wird die fertige Datei
        if session and name in EDIT and response.status_code < 400 and response.status_code != 202:
            access.log("change", ip=ip, user=session["username"], path=request.url.path, detail=request.method)
        return secure(request, response)

    def secure(request: Request, response):
        headers = response.headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        # OpenStreetMap verlangt einen Referer; gesendet wird nur der Ursprung, nie der Pfad
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Content-Security-Policy"] = CSP
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if scheme(request) == "https":
            headers["Strict-Transport-Security"] = "max-age=15552000"
        if "cache-control" not in headers:
            headers["Cache-Control"] = "private, no-store"
        return response

    # ── Anmeldung ──────────────────────────────────────────────────
    def session_info(request: Request, session: dict | None) -> dict:
        return {
            "authenticated": session is not None,
            "public": True,
            "role": session["role"] if session else None,
            "user": {"username": session["username"], "display_name": session["display_name"]} if session else None,
            "csrf": session["csrf"] if session else None,
            # Sicheres Cookie über http wird vom Browser verworfen: Anmeldung schlüge scheinbar grundlos fehl
            "cookie_blocked": settings.public_cookie_secure and scheme(request) != "https",
        }

    @app.get("/api/auth/session")
    def auth_session(request: Request):
        return session_info(request, request.state.session)

    @app.post("/api/auth/login")
    def auth_login(body: LoginRequest, request: Request):
        ip = request.state.ip
        try:
            token, session = auth.login(body.username, body.password, ip, request.headers.get("user-agent", ""))
        except LoginLocked as exc:
            minutes = max(1, round(exc.retry_after / 60))
            return reply(429, f"Zu viele Fehlversuche. Bitte in {minutes} Minuten erneut versuchen.",
                         retry_after=exc.retry_after)
        except LoginFailed:
            return reply(401, "Benutzername oder Passwort falsch")
        response = JSONResponse(session_info(request, session))
        response.set_cookie(COOKIE, token, max_age=settings.public_session_hours * 3600, httponly=True,
                            secure=settings.public_cookie_secure, samesite="lax", path="/")
        return response

    @app.post("/api/auth/password")
    def auth_password(body: PasswordChange, request: Request):
        try:
            auth.change_password(request.state.session, body.current, body.new, request.state.ip)
        except LoginLocked as exc:
            minutes = max(1, round(exc.retry_after / 60))
            return reply(429, f"Zu viele Fehlversuche. Bitte in {minutes} Minuten erneut versuchen.",
                         retry_after=exc.retry_after)
        except LoginFailed:
            return reply(400, "Das bisherige Passwort stimmt nicht")
        except AuthError as exc:
            return reply(400, str(exc))
        return {"changed": True}

    @app.post("/api/auth/logout")
    def auth_logout(request: Request):
        session = request.state.session
        if session:
            auth.logout(request.cookies.get(COOKIE))
            access.log("logout", ip=request.state.ip, user=session["username"])
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/", secure=settings.public_cookie_secure, httponly=True, samesite="lax")
        return response

    api.register(app, ctx, public=True)

    unknown = sorted(route.name for route in app.routes
                     if isinstance(route, APIRoute) and route.name not in OPEN | VIEW | EDIT)
    if unknown:
        raise RuntimeError(f"Endpunkte ohne Rechtezuordnung im Internetzugang: {', '.join(unknown)}")

    if static_dir and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app
