"""Konten, Passwörter und Sitzungen für den Internetzugang."""

import base64
import hashlib
import hmac
import random
import re
import secrets
import time
from datetime import datetime

from .accesslog import AccessLog
from .db import Database
from .ratelimit import AUTHFAIL_IP, AUTHFAIL_USER, LOCK_BASE, LOCK_CAP, Limiter

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._@-]{2,64}$")
PASSWORD_MIN = 10
ROLES = ("viewer", "editor")
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
LAST_SEEN_EVERY = 300  # Sekunden: "zuletzt aktiv" nicht bei jedem Vorschaubild schreiben


class AuthError(ValueError):
    pass


class LoginFailed(Exception):
    pass


class LoginLocked(Exception):
    def __init__(self, retry_after: int):
        super().__init__("gesperrt")
        self.retry_after = retry_after


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=64, **SCRYPT)
    encode = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), dklen=len(expected),
                                n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Für unbekannte Benutzer trotzdem rechnen, damit die Antwortzeit nichts verrät
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: Database, limiter: Limiter, access: AccessLog, session_hours: int = 12, clock=time.time):
        self.db = db
        self.limiter = limiter
        self.access = access
        self.session_hours = session_hours
        self._clock = clock

    # ── Konten ─────────────────────────────────────────────────────
    def list_users(self) -> list[dict]:
        now = self._clock()
        rows = self.db.query(
            """SELECT u.id, u.username, u.display_name, u.role, u.enabled, u.created_at, u.last_login,
                      (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id AND s.expires_at > ?) AS sessions
               FROM users u ORDER BY u.username COLLATE NOCASE""", (now,))
        return [dict(r) | {"enabled": bool(r["enabled"])} for r in rows]

    def _user(self, user_id: int):
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
        if row is None:
            raise AuthError("Konto nicht gefunden")
        return row

    @staticmethod
    def _check_password(password: str):
        if not password or len(password) < PASSWORD_MIN:
            raise AuthError(f"Passwort: mindestens {PASSWORD_MIN} Zeichen")

    def create_user(self, username: str, password: str, display_name: str = "", role: str = "viewer") -> dict:
        username = (username or "").strip()
        if not USERNAME_RE.match(username):
            raise AuthError("Benutzername: 2–64 Zeichen, Buchstaben, Ziffern, . _ @ -")
        self._check_password(password)
        if role not in ROLES:
            raise AuthError("Unbekannte Rolle")
        if self.db.one("SELECT 1 FROM users WHERE username = ?", (username,)):
            raise AuthError("Konto existiert bereits")
        user_id = self.db.execute(
            "INSERT INTO users (username, display_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, (display_name or "").strip()[:80], hash_password(password), role,
             datetime.now().isoformat(timespec="seconds")),
        ).lastrowid
        return next(u for u in self.list_users() if u["id"] == user_id)

    def update_user(self, user_id: int, *, password: str | None = None, display_name: str | None = None,
                    role: str | None = None, enabled: bool | None = None) -> dict:
        user = self._user(user_id)
        revoke = False
        with self.db.transaction() as conn:
            if password:
                self._check_password(password)
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
                revoke = True  # neues Passwort: überall abmelden
            if display_name is not None:
                conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name.strip()[:80], user_id))
            if role is not None:
                if role not in ROLES:
                    raise AuthError("Unbekannte Rolle")
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            if enabled is not None:
                conn.execute("UPDATE users SET enabled = ? WHERE id = ?", (int(enabled), user_id))
                revoke = revoke or (bool(user["enabled"]) and not enabled)
            if revoke:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if password:
            self.limiter.clear(key=f"authfail:user:{user['username'].lower()}")
        return next(u for u in self.list_users() if u["id"] == user_id)

    def delete_user(self, user_id: int):
        self._user(user_id)
        self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))  # Sitzungen per CASCADE

    # ── Anmeldung ──────────────────────────────────────────────────
    def _fail(self, key: str, limit_window: tuple[int, int], ip: str):
        """Fehlversuch zählen; ist das Fenster voll, eskalierend sperren."""
        self.limiter.record(key)
        limit, window = limit_window
        if self.limiter.count(key, window) >= limit:
            duration = self.limiter.lock(key, LOCK_BASE, LOCK_CAP)
            kind, target = key.split(":", 2)[1:]
            self.access.log("rate_limited", ip=ip, detail=f"lock {kind}:{target} {duration // 60} min")

    def _retry_after(self, key: str, window: int) -> int:
        return self.limiter.ban_remaining(key) or window

    def login(self, username: str, password: str, ip: str, user_agent: str = "") -> tuple[str, dict]:
        """Gibt (Sitzungskennung fürs Cookie, Sitzung) zurück oder wirft LoginFailed/LoginLocked."""
        username = (username or "").strip()[:64]
        ip_key = f"authfail:ip:{ip}"
        user_key = f"authfail:user:{username.lower()}"
        if self.limiter.locked(ip_key, *AUTHFAIL_IP):
            self.access.log("rate_limited", ip=ip, user=username, detail="login locked (ip)")
            raise LoginLocked(self._retry_after(ip_key, AUTHFAIL_IP[1]))
        if username and self.limiter.locked(user_key, *AUTHFAIL_USER):
            self.access.log("rate_limited", ip=ip, user=username, detail="login locked (user)")
            raise LoginLocked(self._retry_after(user_key, AUTHFAIL_USER[1]))

        user = self.db.one("SELECT * FROM users WHERE username = ?", (username,)) if username else None
        valid = verify_password(password or "", user["password_hash"] if user else _DUMMY_HASH)
        if not (user and valid and user["enabled"]):
            time.sleep(random.uniform(0.15, 0.35))
            self._fail(ip_key, AUTHFAIL_IP, ip)
            if username:
                self._fail(user_key, AUTHFAIL_USER, ip)
            self.access.log("auth_fail", ip=ip, user=username, ua=user_agent)
            raise LoginFailed()

        token = secrets.token_urlsafe(32)
        now = self._clock()
        csrf = secrets.token_urlsafe(24)
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO sessions (id, user_id, csrf, created_at, expires_at, last_seen, ip, user_agent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_token_id(token), user["id"], csrf, now, now + self.session_hours * 3600, now, ip, user_agent[:160]),
            )
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?",
                         (datetime.now().isoformat(timespec="seconds"), user["id"]))
        self.access.log("auth_ok", ip=ip, user=user["username"])
        return token, self.session(token)

    def session(self, token: str | None) -> dict | None:
        if not token or len(token) > 128:
            return None
        row = self.db.one(
            """SELECT s.id AS session_id, s.csrf, s.expires_at, s.last_seen, u.id AS user_id, u.username,
                      u.display_name, u.role, u.enabled
               FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?""", (_token_id(token),))
        now = self._clock()
        if row is None or row["expires_at"] <= now or not row["enabled"]:
            return None
        if now - row["last_seen"] > LAST_SEEN_EVERY:
            self.db.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (now, row["session_id"]))
        return {key: row[key] for key in ("session_id", "csrf", "user_id", "username", "display_name", "role")}

    def logout(self, token: str | None):
        if token:
            self.db.execute("DELETE FROM sessions WHERE id = ?", (_token_id(token),))

    def list_sessions(self) -> list[dict]:
        rows = self.db.query(
            """SELECT s.id, u.username, s.created_at, s.last_seen, s.expires_at, s.ip, s.user_agent
               FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.expires_at > ? ORDER BY s.last_seen DESC""",
            (self._clock(),))
        # Die gespeicherte Kennung ist nur ein Hash; gekürzt reicht sie zum Beenden
        return [dict(r) | {"id": r["id"][:16]} for r in rows]

    def revoke_session(self, short_id: str) -> bool:
        if not re.fullmatch(r"[0-9a-f]{16}", short_id or ""):
            return False
        return self.db.execute("DELETE FROM sessions WHERE substr(id, 1, 16) = ?", (short_id,)).rowcount > 0

    def cleanup(self):
        self.db.execute("DELETE FROM sessions WHERE expires_at <= ?", (self._clock(),))
