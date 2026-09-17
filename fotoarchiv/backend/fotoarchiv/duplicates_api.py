"""HTTP-Schnittstelle der Doppelten-Erkennung."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .context import Context


class ResolveGroup(BaseModel):
    keep: list[int] = Field(min_length=1)
    remove: list[int] = Field(min_length=1)


class ResolveRequest(BaseModel):
    groups: list[ResolveGroup] = Field(min_length=1)
    transfer: bool = True  # Schlagworte, Personen, Ort und besseres Datum aufs behaltene Foto übertragen


class IgnoreRequest(BaseModel):
    ids: list[int] = Field(min_length=2)


def register(app: FastAPI, ctx: Context):
    duplicates, tasks = ctx.duplicates, ctx.tasks

    @app.get("/api/duplicates")
    async def duplicate_list():
        return await run_in_threadpool(duplicates.groups)  # kann bei vielen Fotos eine Sekunde dauern

    @app.post("/api/duplicates/resolve")
    def duplicate_resolve(body: ResolveRequest):
        keep_for: dict[str, int] = {}
        for group in body.groups:
            overlap = set(group.keep) & set(group.remove)
            if overlap:
                raise HTTPException(400, f"Foto {min(overlap)} kann nicht zugleich behalten und gelöscht werden")
            for remove_id in group.remove:
                keep_for[str(remove_id)] = group.keep[0]
        count = len(keep_for)
        label = f"{count} {'doppeltes Foto' if count == 1 else 'doppelte Fotos'} in den Papierkorb"
        return tasks.submit("dedupe", label, [int(i) for i in keep_for], {"keep_for": keep_for, "transfer": body.transfer})

    @app.post("/api/duplicates/ignore")
    def duplicate_ignore(body: IgnoreRequest):
        duplicates.ignore(body.ids)
        return {"ignored": True}
