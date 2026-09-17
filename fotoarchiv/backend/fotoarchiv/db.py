"""SQLite-Zugriff mit einfachen, versionierten Migrationen."""

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
]


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
        # Änderungszähler für die Oberfläche; Startwert Zeit, damit ein Neustart als Änderung gilt
        self.revision = int(time.time() * 1000)

    def _migrate(self):
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self.transaction():
                for statement in script.split(";"):
                    if statement.strip():
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
