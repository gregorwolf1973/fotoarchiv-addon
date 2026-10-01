"""Favoritenordner: Sammlungen von Verweisen auf Fotos. Die Dateien selbst bleiben unverändert."""

import sqlite3
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .db import Database


class FolderName(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class FolderItems(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(400, "Der Ordner braucht einen Namen")
    return name


def register(app: FastAPI, db: Database):
    def folder_row(folder_id: int):
        row = db.one("SELECT id, name FROM favorite_folders WHERE id = ?", (folder_id,))
        if row is None:
            raise HTTPException(404, "Ordner nicht gefunden")
        return row

    def save_name(sql: str, params: tuple) -> sqlite3.Cursor:
        try:
            cur = db.execute(sql, params)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Einen Ordner mit diesem Namen gibt es schon") from None
        db.bump()
        return cur

    @app.get("/api/favorites")
    def favorite_list():
        """Ordner mit Anzahl und dem zuletzt hinzugefügten Foto als Titelbild."""
        rows = db.query(
            """SELECT f.id, f.name,
                      (SELECT COUNT(*) FROM favorite_items i JOIN assets a ON a.id = i.asset_id AND a.deleted_at IS NULL
                       WHERE i.folder_id = f.id) AS count,
                      (SELECT a.id || ':' || a.rev FROM favorite_items i JOIN assets a ON a.id = i.asset_id AND a.deleted_at IS NULL
                       WHERE i.folder_id = f.id ORDER BY i.added_at DESC, i.rowid DESC LIMIT 1) AS cover
               FROM favorite_folders f ORDER BY f.name COLLATE NOCASE"""
        )
        result = []
        for r in rows:
            cover = [int(part) for part in r["cover"].split(":")] if r["cover"] else None
            result.append({"id": r["id"], "name": r["name"], "count": r["count"], "cover": cover})
        return result

    @app.post("/api/favorites")
    def favorite_create(body: FolderName):
        name = clean_name(body.name)
        cur = save_name("INSERT INTO favorite_folders (name, created_at) VALUES (?, ?)",
                        (name, datetime.now().isoformat(timespec="seconds")))
        return {"id": cur.lastrowid, "name": name, "count": 0, "cover": None}

    @app.post("/api/favorites/{folder_id}/rename")
    def favorite_rename(folder_id: int, body: FolderName):
        folder_row(folder_id)
        name = clean_name(body.name)
        save_name("UPDATE favorite_folders SET name = ? WHERE id = ?", (name, folder_id))
        return {"id": folder_id, "name": name}

    @app.post("/api/favorites/{folder_id}/delete")
    def favorite_delete(folder_id: int):
        """Nur der Ordner verschwindet, die Fotos bleiben im Archiv."""
        folder_row(folder_id)
        db.execute("DELETE FROM favorite_folders WHERE id = ?", (folder_id,))
        db.bump()
        return {"deleted": True}

    @app.post("/api/favorites/{folder_id}/add")
    def favorite_add(folder_id: int, body: FolderItems):
        folder_row(folder_id)
        ids = sorted(set(body.ids))
        now = datetime.now().isoformat(timespec="seconds")
        with db.transaction() as conn:
            existing = [r["id"] for r in conn.execute(
                f"SELECT id FROM assets WHERE deleted_at IS NULL AND id IN ({','.join('?' * len(ids))})", ids)]
            added = 0
            for asset_id in existing:
                added += conn.execute(
                    "INSERT OR IGNORE INTO favorite_items (folder_id, asset_id, added_at) VALUES (?, ?, ?)",
                    (folder_id, asset_id, now)).rowcount
        db.bump()
        return {"added": added, "already": len(existing) - added}

    @app.post("/api/favorites/{folder_id}/remove")
    def favorite_remove(folder_id: int, body: FolderItems):
        folder_row(folder_id)
        ids = sorted(set(body.ids))
        removed = db.execute(
            f"DELETE FROM favorite_items WHERE folder_id = ? AND asset_id IN ({','.join('?' * len(ids))})",
            (folder_id, *ids)).rowcount
        db.bump()
        return {"removed": removed}
