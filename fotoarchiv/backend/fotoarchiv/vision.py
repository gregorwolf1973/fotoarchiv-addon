"""Bilderkennung im Hintergrund: falsch gedrehte Fotos, Schlagwort-Vorschläge, Suche in normaler Sprache.

Je Foto (Videos über ihr Vorschaubild) einmal:
- Bildmerkmale (CLIP) berechnen und speichern. Daraus kommen die Suche („Hund am Strand“) und die
  Schlagwort-Vorschläge. Die Vorschläge stehen nur in der Datenbank; in die Datei kommt ein
  Schlagwort erst, wenn es jemand übernimmt.
- Ausrichtung prüfen (nur Fotos, nur beim ersten Mal). Das Modell beurteilt das Foto zuerst, wie es ist;
  nur wenn es eine Drehung verlangt, auch in den drei anderen Lagen. Stimmen mindestens drei der vier
  Urteile überein und bestätigt ein Gesicht die neue Lage eindeutig, wird das Foto gedreht (rückgängig
  machbar). Ohne diese Bestätigung kommt es nur in die Liste „Drehen prüfen“, und nur wenn alle vier
  Urteile übereinstimmen.
  Kalibriert an 400 Fotos der Bibliothek: Mit Gesichtsbestätigung wurde keines falsch gedreht, ohne sie lag
  das Modell bei etwa jedem dritten Verdacht daneben.
"""

import logging
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import numpy as np

from . import vocab
from .config import Settings
from .db import Database
from .editor import ROTATABLE, EditError, Editor
from .faces import FaceService, load_rgb
from .importer import Importer
from .visionengine import DEGREES, ModelCrash, ModelError, ModelProcess, ensure_models, missing

log = logging.getLogger(__name__)

BATCH = 32
IDLE_WAIT = 300          # Sekunden Pause, wenn nichts zu tun ist
YIELD_WAIT = 30          # die Gesichtserkennung arbeitet gerade: ihr den Vortritt lassen
RETRY_WAIT = 3600        # nach Fehler beim Herunterladen
IMAGE_IDLE = 300         # Bildmodelle nach 5 Minuten ohne Arbeit beenden
TEXT_IDLE = 600          # Textmodell (1,1 GB) nach 10 Minuten ohne Suche beenden

MIN_AGREE_AUTO = 3       # so viele der vier Urteile müssen dieselbe Drehung ergeben (plus Gesicht)
MIN_AGREE_SUGGEST = 4    # ohne Gesicht nur Vorschlag, und nur bei Einigkeit (3 von 4: deutlich mehr Fehlalarme)
FACE_STRONG = 0.6        # Gesicht in der neuen Lage mindestens so sicher erkannt …
FACE_WEAK = 0.5          # … in der jetzigen Lage höchstens so sicher
FACE_MARGIN = 0.2        # … und deutlich sicherer als in jeder anderen Lage

SCALE = 100.0            # CLIP-Temperatur: Ähnlichkeit → Wahrscheinlichkeit
TAG_FIRST = 0.5          # bestes Schlagwort ab dieser Wahrscheinlichkeit
TAG_SECOND = 0.3         # ein zweites ab dieser
SEARCH_MIN_SIMILARITY = 0.15
SEARCH_MIN_SHARE = 0.5   # Suchtext muss gegen „ein Foto“, „Menschen in einem Raum“ … gewinnen
SEARCH_SAME_AS_QUERY = 0.9  # Hintergrund-Sätze, die dem Suchtext fast gleichen, zählen nicht
SEARCH_LIMIT = 2000
CHUNK = 4096
QUERY_CACHE = 256

REVIEW = ("auto", "suggested")
# Sichtbarer Vorschlag: weder abgelehnt noch übernommen, und das Foto hat das Schlagwort nicht schon
VISIBLE = """s.state = 0 AND NOT EXISTS (SELECT 1 FROM asset_tags l JOIN tags t ON t.id = l.tag_id
             WHERE l.asset_id = s.asset_id AND t.name = s.name)"""


class NotReady(Exception):
    pass


# ── Entscheidungen (ohne Modelle prüfbar) ──────────────────────────
def orientation_vote(probs: dict[int, np.ndarray]) -> tuple[int, int]:
    """probs[k]: Modellurteil für das um k° (Uhrzeigersinn) gedrehte Foto, Klasse i = Korrektur DEGREES[i].

    Braucht das gedrehte Foto die Korrektur c, braucht das Original c + k. Gibt die Korrektur mit der
    höchsten Summe zurück und wie viele Einzelurteile genau sie ergeben."""
    votes = np.zeros(4)
    agree = []
    for turn, p in probs.items():
        for index, correction in enumerate(DEGREES):
            votes[DEGREES.index((correction + turn) % 360)] += p[index]
        agree.append((DEGREES[int(np.argmax(p))] + turn) % 360)
    best = DEGREES[int(votes.argmax())]
    return best, sum(a == best for a in agree)


def faces_confirm(scores: dict[int, float], correction: int) -> bool:
    """scores[d]: sicherstes Gesicht im um d° korrigierten Foto. Nur eine eindeutige Lage zählt."""
    top = max(scores, key=scores.get)
    others = max(v for d, v in scores.items() if d != correction)
    return (top == correction and scores[correction] >= FACE_STRONG and scores[0] < FACE_WEAK
            and scores[correction] - others >= FACE_MARGIN)


def _share(similarities: np.ndarray) -> np.ndarray:
    """Erste Spalte gegen alle: Wahrscheinlichkeit nach CLIP-Art (Softmax über skalierte Ähnlichkeit)."""
    logits = SCALE * similarities
    logits -= logits.max(axis=-1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=-1, keepdims=True)


def suggest_tags(vector: np.ndarray, names: list[str], tags: np.ndarray, background: np.ndarray) -> list[tuple[str, float]]:
    """Höchstens zwei Schlagworte, nur wenn das Foto klar zu ihnen passt (siehe vocab.py)."""
    probs = _share(np.concatenate([tags @ vector, background @ vector]))[: len(names)]
    order = np.argsort(-probs)
    if probs[order[0]] < TAG_FIRST:
        return []
    result = [(names[order[0]], float(probs[order[0]]))]
    if probs[order[1]] >= TAG_SECOND:
        result.append((names[order[1]], float(probs[order[1]])))
    return result


def search_hits(query: np.ndarray, vectors: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Indizes der Treffer in vectors, beste zuerst. vectors darf float16 sein."""
    competitors = background[background @ query < SEARCH_SAME_AS_QUERY]
    probes = np.vstack([query[None], competitors]).astype(np.float32)
    hits, scores = [], []
    for start in range(0, len(vectors), CHUNK):
        similarities = vectors[start:start + CHUNK].astype(np.float32) @ probes.T
        share = _share(similarities)[:, 0]
        found = np.where((similarities[:, 0] >= SEARCH_MIN_SIMILARITY) & (share >= SEARCH_MIN_SHARE))[0]
        hits.append(found + start)
        scores.append(similarities[found, 0])
    if not hits:
        return np.array([], dtype=np.int64)
    hits, scores = np.concatenate(hits), np.concatenate(scores)
    return hits[np.argsort(-scores)][:SEARCH_LIMIT]


class VisionService:
    def __init__(self, settings: Settings, db: Database, importer: Importer, editor: Editor, faces: FaceService, *,
                 enabled: bool = True, auto_rotate: bool = True, models: Path | None = None,
                 image_models=None, text_models=None):
        self.settings = settings
        self.db = db
        self.importer = importer
        self.editor = editor
        self.faces = faces
        self.enabled = enabled
        self.auto_rotate = auto_rotate
        self.models = models or settings.data / "models" / "vision"
        threads = settings.face_threads
        self.image = image_models or ModelProcess("image", self.models, threads, idle=IMAGE_IDLE)
        self.text = text_models or ModelProcess("text", self.models, threads, idle=TEXT_IDLE)
        self.state = {"status": "starting" if enabled else "off", "message": "", "download_done": 0, "download_total": 0}
        self._vocab: tuple[list[str], np.ndarray, np.ndarray] | None = None  # Namen, Schlagworte, Hintergrund
        self._queries: OrderedDict[str, np.ndarray] = OrderedDict()
        self._query_lock = threading.Lock()
        self._vectors_version = 0
        self._vectors: tuple[int, np.ndarray, np.ndarray] | None = None  # Stand, IDs, Merkmale (float16)
        self._vectors_lock = threading.Lock()
        self._rotating: set[int] = set()  # eigene Drehungen: der Haken soll sie nicht als "von Hand" werten
        self._wake = threading.Event()
        self._stop = threading.Event()

        editor.hooks["rotate"].append(self._after_rotate)
        editor.hooks["tags"].append(self._after_tags)
        importer.hooks["imported"].append(self._after_import)

    # ── Start und Hintergrundschleife ──────────────────────────────
    def start(self):
        if self.enabled:
            threading.Thread(target=self._run, daemon=True, name="vision").start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self.image.close()
        self.text.close()

    def wake(self):
        self._wake.set()

    def prepare(self):
        """Modelle herunterladen (nur beim ersten Mal), Schlagwort-Merkmale berechnen."""
        if missing(self.models):
            self.state.update(status="downloading", message="Modelle für die Bilderkennung werden heruntergeladen (ca. 1,6 GB)")
            ensure_models(self.models, progress=lambda done, total: self.state.update(download_done=done, download_total=total))
        self.state.update(status="loading", message="Schlagworte werden vorbereitet")
        self._load_vocab()
        self._retag_if_changed()
        self.state.update(status="idle", message="")

    def _run(self):
        while not self._stop.is_set():
            try:
                self.prepare()
                break
            except Exception as exc:
                log.exception("Bilderkennung konnte nicht starten")
                self.state.update(status="error", message=str(exc))
                self._stop.wait(RETRY_WAIT)
        while not self._stop.is_set():
            try:
                if self._faces_busy():
                    self._stop.wait(YIELD_WAIT)
                    continue
                if self.work_once():
                    continue
                self.state.update(status="idle")
                self._wake.wait(IDLE_WAIT)
                self._wake.clear()
            except ModelCrash as exc:
                log.warning("Bilderkennung unterbrochen: %s", exc)
                self.state.update(status="error", message=str(exc))
                self._stop.wait(60)
            except Exception:
                log.exception("Fehler in der Bilderkennung")
                self._stop.wait(60)

    def _faces_busy(self) -> bool:
        """Beide zugleich brächten den Pi an den Anschlag; die Gesichtserkennung war zuerst da."""
        return self.faces.enabled and self.faces.state.get("status") in ("starting", "downloading", "loading", "scanning")

    def work_once(self) -> bool:
        rows = self.db.query(
            "SELECT id FROM assets WHERE vision_scanned = 0 AND deleted_at IS NULL ORDER BY taken_ts DESC LIMIT ?",
            (BATCH,))
        if rows:
            self.state.update(status="scanning", message="")
        for row in rows:
            if self._stop.is_set():
                break
            self.analyze(row["id"])
        if rows:
            self.db.bump()
        return bool(rows)

    # ── Ein Foto ───────────────────────────────────────────────────
    def analyze(self, asset_id: int):
        row = self.db.one("SELECT path, kind, orient_checked, deleted_at FROM assets WHERE id = ?", (asset_id,))
        if row is None or row["deleted_at"]:
            return
        thumb = self.importer.ensure_thumbnail(asset_id)
        if thumb is None:
            self.db.execute("UPDATE assets SET vision_scanned = -1 WHERE id = ?", (asset_id,))
            return
        check = row["kind"] == "image" and not row["orient_checked"] and Path(row["path"]).suffix.lower() in ROTATABLE
        try:
            result = self.image.call("image", str(thumb), [0] if check else [], True)
            correction = self._check_orientation(thumb, result["orientation"][0]) if check else None
        except ModelCrash:
            raise
        except ModelError as exc:
            log.warning("Bilderkennung für %s nicht möglich: %s", row["path"], exc)
            self.db.execute("UPDATE assets SET vision_scanned = -1 WHERE id = ?", (asset_id,))
            return

        vector = result["embedding"]
        names, tags, background = self._vocab
        suggestions = suggest_tags(vector, names, tags, background)
        automatic = correction is not None and correction[1]
        with self.db.transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO clip_vectors (asset_id, vector) VALUES (?, ?)",
                         (asset_id, vector.astype(np.float16).tobytes()))
            self._store_suggestions(conn, asset_id, suggestions)
            conn.execute("UPDATE assets SET vision_scanned = 1, orient_checked = CASE WHEN ? THEN 1 ELSE orient_checked END "
                         "WHERE id = ?", (check, asset_id))
            if correction is not None:
                conn.execute("INSERT OR REPLACE INTO orientation (asset_id, degrees, status, created_at) VALUES (?, ?, ?, ?)",
                             (asset_id, correction[0], "auto" if automatic else "suggested",
                              datetime.now().isoformat(timespec="seconds")))
        self._vectors_version += 1
        if automatic:
            # Erst jetzt: der Haken nach dem Drehen setzt vision_scanned zurück, die Merkmale werden neu berechnet
            try:
                self._rotate(asset_id, correction[0])
                log.info("%s automatisch um %d° gedreht", row["path"], correction[0])
            except EditError as exc:
                log.warning("%s nicht drehbar: %s", row["path"], exc)
                self.db.execute("UPDATE orientation SET status = 'suggested' WHERE asset_id = ?", (asset_id,))

    def _check_orientation(self, thumb: Path, plain: np.ndarray) -> tuple[int, bool] | None:
        """(Korrektur, automatisch drehen?) oder None, wenn das Foto richtig steht."""
        if int(np.argmax(plain)) == 0:
            return None  # der weitaus häufigste Fall: drei weitere Durchläufe sparen
        others = self.image.call("image", str(thumb), [90, 180, 270], False)["orientation"]
        correction, agree = orientation_vote({0: plain, 90: others[0], 180: others[1], 270: others[2]})
        if correction == 0 or agree < MIN_AGREE_AUTO:
            return None
        engine = self.faces.engine if self.faces.enabled else None
        if self.auto_rotate and engine is not None:
            image = load_rgb(thumb)
            scores = {}
            for degrees in DEGREES:
                turned = np.ascontiguousarray(np.rot90(image, -(degrees // 90)))  # im Uhrzeigersinn
                scores[degrees] = max((face.score for face in engine.detect(turned)), default=0.0)
            if faces_confirm(scores, correction):
                return correction, True
        return (correction, False) if agree >= MIN_AGREE_SUGGEST else None

    def _rotate(self, asset_id: int, degrees: int):
        self._rotating.add(asset_id)
        try:
            self.editor.rotate(asset_id, degrees)
        finally:
            self._rotating.discard(asset_id)

    @staticmethod
    def _store_suggestions(conn, asset_id: int, suggestions: list[tuple[str, float]]):
        conn.execute("DELETE FROM auto_tags WHERE asset_id = ? AND state = 0", (asset_id,))
        for name, score in suggestions:  # abgelehnte und übernommene bleiben, wie sie sind
            conn.execute("INSERT OR IGNORE INTO auto_tags (asset_id, name, score) VALUES (?, ?, ?)",
                         (asset_id, name, round(score, 3)))

    # ── Schlagwort-Merkmale ────────────────────────────────────────
    def _load_vocab(self):
        path = self.models / f"vocab-{vocab.fingerprint()}.npy"
        names = list(vocab.VOCAB)
        if path.is_file():
            matrix = np.load(path)
        else:
            prompts = [p for name in names for p in vocab.VOCAB[name]]
            vectors = self.text.call("text", prompts + vocab.BACKGROUND)
            rows, start = [], 0
            for name in names:
                count = len(vocab.VOCAB[name])
                mean = vectors[start:start + count].mean(axis=0)
                rows.append(mean / np.linalg.norm(mean))
                start += count
            matrix = np.vstack([np.stack(rows), vectors[start:]]).astype(np.float32)
            for old in self.models.glob("vocab-*.npy"):
                old.unlink(missing_ok=True)
            np.save(path, matrix)
            self.text.release()  # 1,1 GB: nicht neben den Bildmodellen liegen lassen, bis jemand sucht
        self._vocab = (names, matrix[: len(names)], matrix[len(names):])

    def _retag_if_changed(self):
        """Begriffsliste geändert: Vorschläge aus den gespeicherten Merkmalen neu berechnen."""
        current = vocab.fingerprint()
        stored = self.db.one("SELECT value FROM meta WHERE key = 'vision_vocab'")
        if stored and stored["value"] == current:
            return
        names, tags, background = self._vocab
        last = 0
        while True:
            rows = self.db.query("SELECT asset_id, vector FROM clip_vectors WHERE asset_id > ? ORDER BY asset_id LIMIT 1000",
                                 (last,))
            if not rows:
                break
            with self.db.transaction() as conn:
                for row in rows:
                    vector = np.frombuffer(row["vector"], dtype=np.float16).astype(np.float32)
                    self._store_suggestions(conn, row["asset_id"], suggest_tags(vector, names, tags, background))
            last = rows[-1]["asset_id"]
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('vision_vocab', ?)", (current,))
        self.db.bump()

    # ── Suche ──────────────────────────────────────────────────────
    @property
    def search_ready(self) -> bool:
        return self.enabled and self._vocab is not None

    def _query_vector(self, text: str) -> np.ndarray:
        with self._query_lock:
            if text in self._queries:
                self._queries.move_to_end(text)
                return self._queries[text]
        vector = self.text.call("text", [text])[0]
        with self._query_lock:
            self._queries[text] = vector
            while len(self._queries) > QUERY_CACHE:
                self._queries.popitem(last=False)
        return vector

    def _all_vectors(self) -> tuple[np.ndarray, np.ndarray]:
        with self._vectors_lock:
            version = self._vectors_version
            if self._vectors is None or self._vectors[0] != version:
                rows = self.db.query("SELECT asset_id, vector FROM clip_vectors ORDER BY asset_id")
                ids = np.array([r["asset_id"] for r in rows], dtype=np.int64)
                matrix = (np.frombuffer(b"".join(r["vector"] for r in rows), dtype=np.float16).reshape(-1, 512)
                          if rows else np.zeros((0, 512), dtype=np.float16))
                self._vectors = (version, ids, matrix)
            return self._vectors[1], self._vectors[2]

    def search(self, text: str) -> list[int]:
        """Fotos, deren Inhalt zum Text passt; beste zuerst. Gelöschte filtert die Abfrage danach heraus."""
        text = " ".join(text.split())[:200]
        if not self.enabled:
            raise NotReady("Die Bilderkennung ist in den Add-on-Optionen ausgeschaltet")
        if not self.search_ready:
            raise NotReady("Die Bildsuche ist noch nicht bereit – die Modelle werden gerade geladen")
        if not text:
            return []
        try:
            query = self._query_vector(text)
        except ModelError as exc:
            raise NotReady(f"Die Bildsuche ist gerade nicht verfügbar: {exc}") from exc
        ids, matrix = self._all_vectors()
        return ids[search_hits(query, matrix, self._vocab[2])].tolist()

    # ── Schlagwort-Vorschläge ──────────────────────────────────────
    def suggestions(self, asset_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            f"SELECT s.name, s.score FROM auto_tags s WHERE s.asset_id = ? AND {VISIBLE} ORDER BY s.score DESC",
            (asset_id,))]

    def suggestion_labels(self) -> list[dict]:
        """Wie /api/labels: Name und Zahl der Fotos, bei denen das Schlagwort noch vorgeschlagen ist."""
        return [dict(r) for r in self.db.query(
            f"""SELECT s.name, COUNT(*) AS count FROM auto_tags s JOIN assets a ON a.id = s.asset_id AND a.deleted_at IS NULL
                WHERE {VISIBLE} GROUP BY s.name ORDER BY s.name COLLATE NOCASE""")]

    def dismiss(self, name: str, asset_ids: list[int]) -> int:
        """Vorschlag ablehnen; er kommt auch bei einer Neuberechnung nicht wieder."""
        marks = ",".join("?" * len(asset_ids))
        count = self.db.execute(
            f"UPDATE auto_tags SET state = -1 WHERE name = ? AND state = 0 AND asset_id IN ({marks})",
            (name, *asset_ids)).rowcount
        self.db.bump()
        return count

    # ── Drehen prüfen ──────────────────────────────────────────────
    def orientation_of(self, asset_id: int) -> dict | None:
        row = self.db.one("SELECT degrees, status FROM orientation WHERE asset_id = ? AND status IN ('auto', 'suggested')",
                          (asset_id,))
        return dict(row) if row else None

    def review(self) -> list[dict]:
        rows = self.db.query(
            """SELECT o.asset_id AS id, o.degrees, o.status, a.taken_ts AS ts, a.width AS w, a.height AS h, a.rev
               FROM orientation o JOIN assets a ON a.id = o.asset_id AND a.deleted_at IS NULL
               WHERE o.status IN ('auto', 'suggested') ORDER BY a.taken_ts DESC, a.id DESC""")
        return [dict(r) for r in rows]

    def decide(self, asset_id: int, accept: bool):
        """accept: Vorschlag stimmt (drehen) bzw. die automatische Drehung stimmt (lassen).
        Sonst: Vorschlag verwerfen bzw. automatische Drehung rückgängig machen."""
        row = self.db.one("SELECT degrees, status FROM orientation WHERE asset_id = ?", (asset_id,))
        if row is None or row["status"] not in REVIEW:
            return  # schon entschieden oder inzwischen von Hand gedreht
        if row["status"] == "suggested":
            if accept:
                self._rotate(asset_id, row["degrees"])
            status = "applied" if accept else "dismissed"
        else:
            if not accept:
                self._rotate(asset_id, (360 - row["degrees"]) % 360)
            status = "accepted" if accept else "undone"
        self.db.execute("UPDATE orientation SET status = ? WHERE asset_id = ?", (status, asset_id))
        self.db.bump()

    # ── Rückmeldungen ──────────────────────────────────────────────
    def _after_rotate(self, asset_id: int):
        self.db.execute("UPDATE assets SET vision_scanned = 0 WHERE id = ?", (asset_id,))  # Merkmale der neuen Lage
        if asset_id not in self._rotating:
            # Von Hand gedreht: Vorschlag oder automatische Drehung sind damit erledigt
            self.db.execute("UPDATE orientation SET status = 'manual' WHERE asset_id = ? AND status IN ('auto', 'suggested')",
                            (asset_id,))
        self.wake()

    def _after_tags(self, asset_id: int):
        """Schlagwort von Hand gesetzt: passender Vorschlag gilt als übernommen und kommt nicht wieder."""
        self.db.execute(
            """UPDATE auto_tags SET state = 1 WHERE asset_id = ? AND state = 0 AND name IN (
                   SELECT t.name FROM asset_tags l JOIN tags t ON t.id = l.tag_id WHERE l.asset_id = ?)""",
            (asset_id, asset_id))

    def _after_import(self, _asset_id: int):
        self.wake()

    # ── Übersicht ──────────────────────────────────────────────────
    def status(self) -> dict:
        counts = self.db.one(
            """SELECT COUNT(*) AS total, COALESCE(SUM(vision_scanned != 0), 0) AS done
               FROM assets WHERE deleted_at IS NULL""")
        review = self.db.one(
            """SELECT COUNT(*) AS n FROM orientation o JOIN assets a ON a.id = o.asset_id AND a.deleted_at IS NULL
               WHERE o.status IN ('auto', 'suggested')""")["n"]
        return {**self.state, "enabled": self.enabled, "auto_rotate": self.auto_rotate, "search": self.search_ready,
                "total": counts["total"], "done": counts["done"], "review": review}
