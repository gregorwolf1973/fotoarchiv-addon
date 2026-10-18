"""HTTP-Schnittstelle der Bilderkennung: Stand, Drehen prüfen, Schlagwort-Vorschläge ablehnen.

Die Suche in normaler Sprache läuft über den Filter ai= von /api/assets und /api/geo (api.py),
Vorschläge übernehmen über die normalen Schlagwort-Wege (Einzelansicht, Mehrfachauswahl).
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .context import Context


class ReviewDecision(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)
    accept: bool


class SuggestionDismiss(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    ids: list[int] = Field(min_length=1, max_length=20000)


def register(app: FastAPI, ctx: Context):
    vision, tasks = ctx.vision, ctx.tasks

    @app.get("/api/vision/status")
    def vision_status():
        return vision.status()

    @app.get("/api/vision/review")
    def orientation_review():
        """Automatisch gedrehte und vielleicht falsch gedrehte Fotos, neueste zuerst."""
        return {"revision": ctx.db.revision, "items": vision.review()}

    @app.post("/api/vision/review")
    def orientation_decide(body: ReviewDecision):
        count = len(set(body.ids))
        label = (f"Drehung bei {count} Fotos übernehmen" if body.accept
                 else f"Drehung bei {count} Fotos verwerfen bzw. rückgängig machen")
        return tasks.submit("orient", label, body.ids, {"accept": body.accept})

    @app.post("/api/vision/suggestions/dismiss")
    def suggestion_dismiss(body: SuggestionDismiss):
        return {"dismissed": vision.dismiss(body.name.strip(), sorted(set(body.ids)))}
