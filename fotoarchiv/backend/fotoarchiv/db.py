"""SQLite-Zugriff mit einfachen, versionierten Migrationen."""

import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

# Jede Migration wird genau einmal ausgeführt; der Stand steht in PRAGMA user_version.
# Bestehende Einträge nie ändern, nur neue anhängen.
MIGRATIONS = [
    """
    CREATE TABLE assets (
        id           INTEGER PRIMARY KEY,
        path         TEXT NOT NULL UNIQUE,   -- relativ zur Bibliothek, mit /
        kind         TEXT NOT NULL,          -- image | video
        mime         TEXT,
        size         INTEGER NOT NULL,
        md5          TEXT NOT NULL,          -- aktueller Datei-Hash
        md5_import   TEXT NOT NULL,          -- Hash beim Import, bleibt nach Bearbeitung erhalten
        taken_at     TEXT,                   -- Ortszeit der Aufnahme, ISO ohne Zone
        taken_ts     INTEGER NOT NULL,       -- taken_at als Sekunden (Sortierung, Gruppierung)
        date_source  TEXT NOT NULL,          -- exif | filename | mtime
        tz_offset    TEXT,
        width        INTEGER,                -- Anzeigegröße, Drehung berücksichtigt
        height       INTEGER,
        duration     REAL,
        lat          REAL,
        lon          REAL,
        camera       TEXT,
        rev          INTEGER NOT NULL DEFAULT 1,  -- erhöht sich bei jeder Änderung (Cache-Busting)
        thumb_ok     INTEGER NOT NULL DEFAULT 0,
        imported_at  TEXT NOT NULL,
        deleted_at   TEXT                    -- gesetzt = im Papierkorb
    );
    CREATE INDEX assets_timeline ON assets (deleted_at, taken_ts DESC, id DESC);
    CREATE INDEX assets_md5 ON assets (md5);
    CREATE INDEX assets_md5_import ON assets (md5_import);

    CREATE TABLE tags (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE
    );
    CREATE TABLE asset_tags (
        asset_id INTEGER NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
        tag_id   INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
        PRIMARY KEY (asset_id, tag_id)
    );
    CREATE INDEX asset_tags_tag ON asset_tags (tag_id);

    CREATE TABLE persons (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE
    );
    CREATE TABLE asset_persons (
        asset_id  INTEGER NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
        person_id INTEGER NOT NULL REFERENCES persons (id) ON DELETE CASCADE,
        PRIMARY KEY (asset_id, person_id)
    );
    CREATE INDEX asset_persons_person ON asset_persons (person_id);
    """,
    """
    ALTER TABLE assets ADD COLUMN orig_path TEXT;  -- Pfad vor dem Verschieben in den Papierkorb
    CREATE INDEX assets_deleted ON assets (deleted_at);
    """,
    """
    ALTER TABLE assets ADD COLUMN faces_scanned INTEGER NOT NULL DEFAULT 0;  -- 0 offen, 1 fertig, -1 Fehler
    ALTER TABLE assets ADD COLUMN persons_dirty INTEGER NOT NULL DEFAULT 0;  -- Namen aus Gesichtern noch in Datei schreiben
    CREATE INDEX assets_faces_pending ON assets (faces_scanned, deleted_at);
    CREATE INDEX assets_persons_dirty ON assets (persons_dirty);

    -- Gruppe ähnlicher Gesichter: entweder einer Person zugeordnet oder (noch) unbenannt
    CREATE TABLE face_groups (
        id        INTEGER PRIMARY KEY,
        person_id INTEGER REFERENCES persons (id) ON DELETE SET NULL,
        vec_sum   BLOB NOT NULL,              -- Summe der Merkmalsvektoren (float32)
        count     INTEGER NOT NULL DEFAULT 0,
        hidden    INTEGER NOT NULL DEFAULT 0  -- "unbekannt, nicht mehr zeigen"
    );
    CREATE INDEX face_groups_person ON face_groups (person_id);

    CREATE TABLE faces (
        id             INTEGER PRIMARY KEY,
        asset_id       INTEGER NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
        x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,  -- 0..1, wie angezeigt
        score          REAL NOT NULL,
        embedding      BLOB NOT NULL,          -- 512 × float32, Länge 1
        group_id       INTEGER REFERENCES face_groups (id) ON DELETE SET NULL,
        confirmed      INTEGER NOT NULL DEFAULT 0,  -- 1 = vom Nutzer bestätigt
        rejected_group INTEGER                 -- "gehört nicht zu dieser Gruppe"
    );
    CREATE INDEX faces_asset ON faces (asset_id);
    CREATE INDEX faces_group ON faces (group_id);
    """,
    """
    -- Konten für den Internetzugang (der Zugang über Home Assistant braucht keins)
    CREATE TABLE users (
        id            INTEGER PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name  TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL DEFAULT 'viewer',  -- viewer | uploader | editor
        enabled       INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL,
        last_login    TEXT
    );
    CREATE TABLE sessions (
        id         TEXT PRIMARY KEY,               -- SHA-256 der Kennung aus dem Cookie, nie die Kennung selbst
        user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        csrf       TEXT NOT NULL,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        last_seen  REAL NOT NULL,
        ip         TEXT,
        user_agent TEXT
    );
    CREATE INDEX sessions_user ON sessions (user_id);
    """,
    """
    -- Hintergrundaufgaben, damit sie einen Neustart überstehen
    CREATE TABLE tasks (
        id          INTEGER PRIMARY KEY,
        kind        TEXT NOT NULL,                 -- angemeldete Aktion, z. B. labels, rotate, persons_relabel
        label       TEXT NOT NULL,
        params      TEXT NOT NULL,                 -- JSON
        asset_ids   TEXT NOT NULL,                 -- JSON-Liste, Reihenfolge der Abarbeitung
        total       INTEGER NOT NULL,
        done        INTEGER NOT NULL DEFAULT 0,
        failed      TEXT NOT NULL DEFAULT '[]',
        current     INTEGER,                       -- Foto in Arbeit
        running     INTEGER NOT NULL DEFAULT 1,
        started_at  TEXT NOT NULL,
        finished_at TEXT
    );
    CREATE INDEX tasks_running ON tasks (running, id);
    """,
    """
    -- Doppelte/ähnliche Fotos: 64-Bit-Wahrnehmungs-Hash als Hex, NULL = noch nicht berechnet, leer = nicht möglich
    ALTER TABLE assets ADD COLUMN phash TEXT;
    CREATE INDEX assets_phash_pending ON assets (phash, kind, deleted_at);
    CREATE TABLE duplicate_ignores (
        a INTEGER NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
        b INTEGER NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
        PRIMARY KEY (a, b)                         -- a < b: "sind keine Duplikate"
    );
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    -- Umwandeln (HEIC → JPEG, Videos → H.264-MP4): 0 = nichts zu tun, 1 = vorgemerkt, -1 = fehlgeschlagen
    ALTER TABLE assets ADD COLUMN convert INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE assets ADD COLUMN convert_error TEXT;
    CREATE INDEX assets_convert ON assets (convert, deleted_at);
    """,
    """
    -- Befund der gründlichen Prüfung: Grund, warum die Datei beschädigt ist (NULL = in Ordnung oder ungeprüft)
    ALTER TABLE assets ADD COLUMN damaged TEXT;
    """,
    """
    -- IDs nie wiederverwenden. SQLite vergibt nach dem Löschen der höchsten ID dieselbe erneut; Bild-URLs
    -- enthalten die ID und werden lange gecacht, ein neues Foto zeigte dann die Vorschau des gelöschten.
    -- Die höchste je vergebene ID steht in meta, neue Einträge bekommen NEXT_ASSET_ID.
    INSERT OR REPLACE INTO meta (key, value) VALUES ('asset_id_high', (SELECT COALESCE(MAX(id), 0) FROM assets));
    CREATE TRIGGER assets_id_high AFTER DELETE ON assets
    WHEN OLD.id > CAST((SELECT value FROM meta WHERE key = 'asset_id_high') AS INTEGER)
    BEGIN
        UPDATE meta SET value = OLD.id WHERE key = 'asset_id_high';
    END;
    -- Einmal neue Kennung für alle Bild-URLs: räumt Vorschauen auf, die schon falsch im Browser-Cache liegen
    DELETE FROM meta WHERE key = 'instance';
    """,
]

# Für INSERT INTO assets (id, …) VALUES ((NEXT_ASSET_ID), …): größer als jede je vergebene ID
NEXT_ASSET_ID = """SELECT MAX(COALESCE((SELECT MAX(id) FROM assets), 0),
                  COALESCE((SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'asset_id_high'), 0)) + 1"""


def _statements(script: str):
    """SQL-Skript in einzelne Anweisungen teilen; Trigger enthalten selbst Semikolons."""
    buffer = ""
    for line in script.splitlines(keepends=True):
        if not buffer and line.strip().startswith("--"):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                yield buffer
            buffer = ""
    if buffer.strip() and buffer.strip() != ";":
        yield buffer


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        # Zufällige Kennung dieser Datenbank: Bild-URLs enthalten sie, damit nach einem Neuaufbau
        # (gleiche IDs, andere Fotos) keine Vorschaubilder aus dem Browser-Cache auftauchen
        self._conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('instance', ?)", (secrets.token_hex(4),))
        self.instance = self._conn.execute("SELECT value FROM meta WHERE key = 'instance'").fetchone()[0]
        # Änderungszähler für die Oberfläche; Startwert Zeit, damit ein Neustart als Änderung gilt
        self.revision = int(time.time() * 1000)

    def _migrate(self):
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self.transaction():
                for statement in _statements(script):
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {number}")

    def bump(self):
        with self._lock:
            self.revision += 1

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def one(self, sql: str, params=()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def close(self):
        with self._lock:
            self._conn.close()
