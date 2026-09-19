"""Internetzugang: Anmeldung, Rollen, CSRF, Sperren, Proxys, Protokoll."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

from fotoarchiv import admin_api, auth
from fotoarchiv.auth import hash_password, verify_password
from fotoarchiv.main import create_app
from fotoarchiv.public import COOKIE, EDIT, OPEN, VIEW, create_public_app

PROXY = ("172.30.32.9", 40000)   # z. B. Nginx Proxy Manager im Home-Assistant-Netz
STRANGER = ("203.0.113.7", 40000)
PASSWORD = "sehr-geheim-123"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda _seconds: None)


@pytest.fixture
def admin(settings):
    app = create_app(dataclasses.replace(settings, public_enabled=True))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def ctx(admin):
    return admin.app.state.ctx


@pytest.fixture
def public(ctx):
    return create_public_app(ctx)


def visitor(public_app, peer=PROXY, ip=None):
    """Browser hinter dem Proxy; ip landet als X-Forwarded-For im Kopf."""
    client = TestClient(public_app, base_url="https://fotos.example.org", client=peer)
    if ip:
        client.headers["X-Forwarded-For"] = ip
    return client


def login(client, username, password=PASSWORD):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response


def make_user(admin, username, role="viewer", password=PASSWORD):
    response = admin.post("/api/admin/users", json={"username": username, "password": password, "role": role})
    assert response.status_code == 201, response.text
    return response.json()


def test_password_hashing():
    stored = hash_password("richtig-lang")
    assert stored.startswith("scrypt$") and verify_password("richtig-lang", stored)
    assert not verify_password("falsch-lang!", stored)
    assert not verify_password("x", "kaputt")


def test_every_api_endpoint_has_a_role(public):
    from fastapi.routing import APIRoute

    names = {route.name for route in public.routes if isinstance(route, APIRoute)}
    assert names <= OPEN | VIEW | EDIT
    assert not names & {"import_start", "trash_empty", "remove_missing", "admin_users"}


def test_accounts_validation(admin):
    assert admin.post("/api/admin/users", json={"username": "a", "password": PASSWORD}).status_code == 400
    assert admin.post("/api/admin/users", json={"username": "anna", "password": "kurz"}).status_code == 400
    assert admin.post("/api/admin/users", json={"username": "anna", "password": PASSWORD, "role": "gott"}).status_code == 400
    make_user(admin, "anna")
    assert admin.post("/api/admin/users", json={"username": "ANNA", "password": PASSWORD}).status_code == 400
    users = admin.get("/api/admin/users").json()
    assert [(u["username"], u["role"], u["enabled"]) for u in users] == [("anna", "viewer", True)]
    assert "password_hash" not in users[0]


def test_roles_csrf_and_hidden_admin_functions(admin, public, make_jpeg, tmp_path):
    photo = make_jpeg(tmp_path / "IMG_20200101_120000.jpg")
    asset_id = admin.put("/api/upload", params={"name": photo.name}, content=photo.read_bytes()).json()["asset_id"]
    make_user(admin, "leser")
    make_user(admin, "helfer", role="editor")

    anonymous = visitor(public, ip="198.51.100.1")
    assert anonymous.get("/api/state").status_code == 401
    assert anonymous.get(f"/api/assets/{asset_id}/thumb").status_code == 401
    assert anonymous.get("/api/auth/session").json()["authenticated"] is False
    assert login(anonymous, "leser", "falsches-passwort").status_code == 401

    viewer = visitor(public, ip="198.51.100.2")
    response = login(viewer, "leser")
    assert response.status_code == 200 and response.json()["role"] == "viewer"
    cookie = response.headers["set-cookie"]
    assert COOKIE in cookie and "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
    state = viewer.get("/api/state").json()
    assert state["counts"]["total"] == 1 and state["library"] is None
    assert viewer.get(f"/api/assets/{asset_id}/thumb").status_code == 200
    assert viewer.patch(f"/api/assets/{asset_id}", json={"tags": ["x"]}).status_code == 403

    editor = visitor(public, ip="198.51.100.3")
    login(editor, "helfer")
    token = editor.headers.pop("X-CSRF-Token")
    assert editor.patch(f"/api/assets/{asset_id}", json={"tags": ["Urlaub"]}).status_code == 403  # ohne CSRF
    editor.headers["X-CSRF-Token"] = token
    assert editor.patch(f"/api/assets/{asset_id}", json={"tags": ["Urlaub"]}).json()["tags"] == ["Urlaub"]
    assert editor.post("/api/batch", json={"ids": [asset_id], "action": "purge"}).status_code == 403
    for path in ("/api/import", "/api/admin/users", "/api/trash/empty", "/api/library/remove-missing", "/api/gibtsnicht"):
        assert editor.get(path).status_code == 404, path

    assert editor.post("/api/auth/logout").status_code == 200
    assert editor.get("/api/state").status_code == 401


def test_uploader_may_view_and_upload_but_not_edit(admin, public, make_jpeg, tmp_path):
    make_user(admin, "oma", role="uploader")
    uploader = visitor(public, ip="198.51.100.4")
    assert login(uploader, "oma").json()["role"] == "uploader"
    photo = make_jpeg(tmp_path / "IMG_20210101_120000.jpg")
    uploaded = uploader.put("/api/upload", params={"name": photo.name}, content=photo.read_bytes())
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["asset_id"]
    assert uploader.get(f"/api/assets/{asset_id}").status_code == 200
    assert uploader.patch(f"/api/assets/{asset_id}", json={"tags": ["x"]}).status_code == 403
    assert uploader.delete(f"/api/assets/{asset_id}").status_code == 403
    assert uploader.post("/api/batch", json={"ids": [asset_id], "action": "delete"}).status_code == 403
    assert admin.patch(f"/api/admin/users/{make_user(admin, 'opa')['id']}", json={"role": "uploader"}).status_code == 200


def test_escalating_lockout_per_ip(admin, ctx, public):
    clock = Clock()
    ctx.limiter._clock = clock
    make_user(admin, "anna")
    browser = visitor(public, ip="192.0.2.10")

    for _ in range(10):
        assert login(browser, "anna", "falsch-falsch").status_code == 401
    locked = login(browser, "anna")  # selbst das richtige Passwort hilft jetzt nicht
    assert locked.status_code == 429 and locked.json()["retry_after"] == 15 * 60

    clock.now += 15 * 60 + 1
    assert login(browser, "anna").status_code == 200

    other = visitor(public, ip="192.0.2.10")
    for _ in range(10):
        login(other, "niemand", "falsch-falsch")
    assert login(other, "anna").json()["retry_after"] == 30 * 60  # zweite Sperre: doppelt so lang

    snapshot = admin.get("/api/admin/locks").json()
    assert {"kind": "ip", "target": "192.0.2.10"}.items() <= snapshot["locks"][0].items()
    assert admin.post("/api/admin/locks/unlock", json={"key": "authfail:ip:192.0.2.10"}).json() == {"ok": True}
    assert admin.post("/api/admin/locks/unlock", json={"key": "irgendwas"}).status_code == 400
    assert login(other, "anna").status_code == 200


def test_lockout_per_user_across_addresses(admin, public):
    make_user(admin, "anna")
    make_user(admin, "ben")
    for n in range(10):
        login(visitor(public, ip=f"192.0.2.{n + 20}"), "anna", "falsch-falsch")
    fresh = visitor(public, ip="192.0.2.99")
    assert login(fresh, "anna").status_code == 429
    assert login(fresh, "ben").status_code == 200


def test_proxy_headers_only_from_trusted_proxies(admin, ctx, public):
    make_user(admin, "anna")
    spoofed = visitor(public, peer=STRANGER, ip="1.1.1.1")  # direkter Zugriff mit gefälschtem Kopf
    login(spoofed, "anna", "falsch-falsch")
    cloudflare = visitor(public)
    cloudflare.headers["CF-Connecting-IP"] = "198.51.100.77"
    cloudflare.headers["X-Forwarded-For"] = "198.51.100.77, 172.30.32.20"
    login(cloudflare, "anna", "falsch-falsch")
    chain = visitor(public, ip="198.51.100.88, 172.30.32.30")  # Cloudflare-Tunnel -> NPM -> Add-on
    login(chain, "anna", "falsch-falsch")

    failures = [e["ip"] for e in admin.get("/api/admin/log", params={"event": "auth_fail"}).json()]
    assert sorted(failures) == ["198.51.100.77", "198.51.100.88", STRANGER[0]]


def test_scanner_gets_banned(public):
    scanner = visitor(public, ip="192.0.2.200")
    for n in range(30):
        scanner.get(f"/api/wp-admin/{n}")
    response = scanner.get("/api/auth/session")
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    assert visitor(public, ip="192.0.2.201").get("/api/auth/session").status_code == 200


def test_security_headers(public):
    browser = visitor(public, ip="192.0.2.50")
    browser.headers["X-Forwarded-Proto"] = "https"
    headers = browser.get("/api/auth/session").headers
    assert headers["X-Frame-Options"] == "DENY" and headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "https://tile.openstreetmap.org" in headers["Content-Security-Policy"]
    assert headers["Strict-Transport-Security"].startswith("max-age=")
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_cookie_warning_over_plain_http(public):
    plain = TestClient(public, base_url="http://192.168.1.10:8301", client=("192.168.1.50", 5000))
    assert plain.get("/api/auth/session").json()["cookie_blocked"] is True


def test_sessions_end_on_password_change_disable_and_revoke(admin, public):
    user = make_user(admin, "anna")
    first = visitor(public, ip="192.0.2.61")
    login(first, "anna")
    sessions = admin.get("/api/admin/sessions").json()
    assert [(s["username"], s["ip"]) for s in sessions] == [("anna", "192.0.2.61")]
    assert admin.delete(f"/api/admin/sessions/{sessions[0]['id']}").json() == {"revoked": True}
    assert first.get("/api/state").status_code == 401

    login(first, "anna")
    admin.patch(f"/api/admin/users/{user['id']}", json={"password": "ein-neues-passwort"})
    assert first.get("/api/state").status_code == 401
    assert login(first, "anna").status_code == 401 and login(first, "anna", "ein-neues-passwort").status_code == 200

    admin.patch(f"/api/admin/users/{user['id']}", json={"enabled": False})
    assert first.get("/api/state").status_code == 401
    assert login(first, "anna", "ein-neues-passwort").status_code == 401

    events = [e["event"] for e in admin.get("/api/admin/log").json()]
    assert {"auth_ok", "auth_fail", "unauthorized"} <= set(events)
    admin.delete("/api/admin/log")
    assert admin.get("/api/admin/log").json() == []


def test_crowdsec_install(admin, ctx, tmp_path, monkeypatch):
    crowdsec = tmp_path / "crowdsec" / "config"
    export = tmp_path / "config" / ".fotoarchiv" / "public_access.log"
    monkeypatch.setattr(admin_api, "CROWDSEC_DIR", crowdsec)
    monkeypatch.setattr(admin_api, "CROWDSEC_EXPORT", str(export))
    assert admin.post("/api/admin/crowdsec/install").status_code == 404
    crowdsec.mkdir(parents=True)
    assert admin.post("/api/admin/crowdsec/install").json()["restart_needed"] == "CrowdSec"
    status = admin.get("/api/admin/crowdsec").json()
    assert status["all_installed"] and status["export_active"]
    assert str(export) in (crowdsec / "acquis.d" / "fotoarchiv-public.yaml").read_text(encoding="utf-8")
    ctx.access.log("auth_fail", ip="192.0.2.1", user="x")
    assert '"event": "auth_fail"' in export.read_text(encoding="utf-8")


def test_users_change_their_own_password(admin, public):
    make_user(admin, "anna")
    phone = visitor(public, ip="198.51.100.20")
    laptop = visitor(public, ip="198.51.100.21")
    login(phone, "anna")
    login(laptop, "anna")
    new = "ganz-neues-passwort"

    wrong = phone.post("/api/auth/password", json={"current": "falsch-falsch", "new": new})
    assert wrong.status_code == 400 and "stimmt nicht" in wrong.json()["detail"]
    assert phone.post("/api/auth/password", json={"current": PASSWORD, "new": "kurz"}).status_code == 400
    assert phone.post("/api/auth/password", json={"current": PASSWORD, "new": PASSWORD}).status_code == 400
    token = phone.headers.pop("X-CSRF-Token")
    assert phone.post("/api/auth/password", json={"current": PASSWORD, "new": new}).status_code == 403  # ohne CSRF
    phone.headers["X-CSRF-Token"] = token

    assert phone.post("/api/auth/password", json={"current": PASSWORD, "new": new}).json() == {"changed": True}
    assert phone.get("/api/state").status_code == 200    # eigene Sitzung bleibt
    assert laptop.get("/api/state").status_code == 401   # andere Geräte abgemeldet
    assert login(visitor(public, ip="198.51.100.22"), "anna").status_code == 401
    assert login(visitor(public, ip="198.51.100.23"), "anna", new).status_code == 200
    assert visitor(public, ip="198.51.100.24").post(
        "/api/auth/password", json={"current": new, "new": "noch-ein-passwort"}).status_code == 401  # ohne Anmeldung


def test_guessing_the_current_password_locks_like_login(admin, public):
    make_user(admin, "bert")
    browser = visitor(public, ip="198.51.100.30")
    login(browser, "bert")
    for _ in range(10):
        browser.post("/api/auth/password", json={"current": "geraten-geraten", "new": "ganz-neues-passwort"})
    locked = browser.post("/api/auth/password", json={"current": PASSWORD, "new": "ganz-neues-passwort"})
    assert locked.status_code == 429
