"""HTTP-Schnittstelle der Gesichtserkennung: Personen, Gesichtergruppen, einzelne Gesichter."""

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .db import Database
from .faces import FaceService, NotFound
from .tasks import TaskRunner

LONG_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}
# Bestätigte Gesichter bevorzugt, dann groß und gut erkannt
BEST_FACE = "ORDER BY f.confirmed DESC, f.score * f.w * f.h DESC LIMIT 1"


class NameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def register(app: FastAPI, db: Database, faces: FaceService, tasks: TaskRunner):
    def guard(action, *args):
        try:
            return action(*args)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def face_rows(where: str, params) -> list[dict]:
        rows = db.query(
            f"""SELECT f.id, f.asset_id, f.confirmed, a.taken_ts FROM faces f
                JOIN assets a ON a.id = f.asset_id AND a.deleted_at IS NULL
                LEFT JOIN face_groups g ON g.id = f.group_id
                WHERE {where} ORDER BY a.taken_ts DESC LIMIT 2000""",
            params,
        )
        return [dict(r) for r in rows]

    @app.get("/api/faces/status")
    def face_status():
        return faces.status()

    @app.get("/api/people")
    def people():
        persons = db.query(
            f"""SELECT p.id, p.name,
                   (SELECT COUNT(*) FROM asset_persons l JOIN assets a ON a.id = l.asset_id AND a.deleted_at IS NULL
                    WHERE l.person_id = p.id) AS count,
                   (SELECT f.id FROM faces f JOIN face_groups g ON g.id = f.group_id
                    JOIN assets a ON a.id = f.asset_id AND a.deleted_at IS NULL
                    WHERE g.person_id = p.id {BEST_FACE}) AS face_id
                FROM persons p ORDER BY count DESC, p.name COLLATE NOCASE"""
        )
        groups = db.query(
            f"""SELECT g.id, COUNT(f.id) AS count,
                   (SELECT f.id FROM faces f JOIN assets a ON a.id = f.asset_id AND a.deleted_at IS NULL
                    WHERE f.group_id = g.id {BEST_FACE}) AS face_id
                FROM face_groups g JOIN faces f ON f.group_id = g.id
                JOIN assets a ON a.id = f.asset_id AND a.deleted_at IS NULL
                WHERE g.person_id IS NULL AND g.hidden = 0
                GROUP BY g.id HAVING COUNT(f.id) >= 2 ORDER BY count DESC LIMIT 300"""
        )
        return {
            "persons": [dict(r) for r in persons if r["count"] or r["face_id"]],
            "groups": [dict(r) for r in groups],
        }

    @app.get("/api/groups/{group_id}/faces")
    def group_faces(group_id: int):
        return face_rows("f.group_id = ?", (group_id,))

    @app.post("/api/groups/{group_id}/name")
    def group_name(group_id: int, body: NameRequest):
        return {"person_id": guard(faces.name_group, group_id, body.name)}

    @app.post("/api/groups/{group_id}/hide")
    def group_hide(group_id: int):
        guard(faces.hide_group, group_id)
        return {"hidden": True}

    @app.get("/api/persons/{person_id}/faces")
    def person_faces(person_id: int):
        return face_rows("g.person_id = ?", (person_id,))

    @app.post("/api/persons/{person_id}/rename")
    def person_rename(person_id: int, body: NameRequest):
        old, new, assets = guard(faces.rename_person, person_id, body.name)
        if not assets:
            db.bump()
            return {"task": None}
        label = f"Person „{old}“ in „{new}“ umbenennen"
        task = tasks.submit(label, assets, lambda asset_id: faces.relabel(asset_id, [new], [old]))
        return {"task": asdict(task)}

    @app.get("/api/assets/{asset_id}/faces")
    def asset_faces(asset_id: int):
        rows = db.query(
            """SELECT f.id, f.x, f.y, f.w, f.h, f.confirmed, f.group_id, p.id AS person_id, p.name
               FROM faces f LEFT JOIN face_groups g ON g.id = f.group_id LEFT JOIN persons p ON p.id = g.person_id
               WHERE f.asset_id = ? ORDER BY f.x""",
            (asset_id,),
        )
        return [dict(r) for r in rows]

    @app.post("/api/faces/{face_id}/assign")
    def face_assign(face_id: int, body: NameRequest):
        return {"person_id": guard(faces.assign_face, face_id, body.name)}

    @app.post("/api/faces/{face_id}/remove")
    def face_remove(face_id: int):
        guard(faces.remove_face, face_id)
        return {"removed": True}

    @app.get("/api/faces/{face_id}/crop")
    def face_crop(face_id: int):
        path = faces.ensure_crop(face_id)
        if path is None:
            raise HTTPException(404, "Kein Ausschnitt")
        return FileResponse(path, media_type="image/webp", headers=LONG_CACHE)
