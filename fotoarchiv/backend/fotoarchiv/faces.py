"""Gesichtserkennung im Hintergrund.

Ablauf je Foto: Gesichter finden → jedem Gesicht die ähnlichste Gruppe geben (oder eine neue) →
ist die Gruppe einer Person zugeordnet, wird deren Name in die Datei geschrieben.
Eine Gruppe ist "Person X" oder unbenannt; unbenannte Gruppen schlägt die Oberfläche zum Benennen vor.
"""

import logging
import threading
from pathlib import Path

import numpy as np

from . import labels
from .config import Settings
from .db import Database
from .editor import WRITABLE, EditError, Editor
from .faceengine import FaceEngine, ensure_models, models_ready

log = logging.getLogger(__name__)

JOIN_THRESHOLD = 0.5    # Kosinus-Ähnlichkeit zur Gruppenmitte, ab der ein Gesicht dazugehört
CARRY_THRESHOLD = 0.6   # erneuter Scan (z. B. nach Drehen): bisherige Zuordnung übernehmen
DECODE_SIZE = 1280      # längste Bildseite für die Erkennung
CROP_SIZE = 160
BATCH = 16
IDLE_WAIT = 300         # Sekunden Pause, wenn nichts zu tun ist
RETRY_WAIT = 3600       # nach Fehler (z. B. Download) erneut versuchen


class NotFound(Exception):
    pass


def _blob(vector: np.ndarray) -> bytes:
    return vector.astype(np.float32).tobytes()


def _vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def load_rgb(path: Path, size: int = DECODE_SIZE) -> np.ndarray:
    import pyvips

    image = pyvips.Image.thumbnail(str(path), size, height=size, size="down")  # dreht nach EXIF
    if image.interpretation not in ("srgb", "b-w"):
        image = image.colourspace("srgb")
    if image.bands in (2, 4):
        image = image[: image.bands - 1]  # Alphakanal weg
    if image.bands == 1:
        image = image.bandjoin([image, image])
    image = image.cast("uchar")
    return np.ndarray(buffer=image.write_to_memory(), dtype=np.uint8, shape=(image.height, image.width, 3))


class CentroidIndex:
    """Normierte Gruppenmitten als Matrix. Einzelne Gruppen ändern sich ohne Neuaufbau der ganzen Matrix."""

    def __init__(self):
        self.ids = np.full(64, -1, dtype=np.int64)
        self.matrix = np.zeros((64, 512), dtype=np.float32)
        self.rows: dict[int, int] = {}
        self.size = 0

    def set(self, group_id: int, vector_sum: np.ndarray):
        row = self.rows.get(group_id)
        if row is None:
            if self.size == len(self.ids):
                self.ids = np.concatenate([self.ids, np.full(len(self.ids), -1, dtype=np.int64)])
                self.matrix = np.vstack([self.matrix, np.zeros_like(self.matrix)])
            row = self.rows[group_id] = self.size
            self.ids[row] = group_id
            self.size += 1
        norm = float(np.linalg.norm(vector_sum))
        self.matrix[row] = vector_sum / norm if norm > 0 else 0

    def remove(self, group_id: int):
        row = self.rows.pop(group_id, None)
        if row is not None:
            self.matrix[row] = 0  # Ähnlichkeit 0: wird nie gewählt
            self.ids[row] = -1

    def best(self, vector: np.ndarray, exclude: int | None = None) -> tuple[int | None, float]:
        if not self.rows:
            return None, -1.0
        similarity = self.matrix[: self.size] @ vector
        if exclude in self.rows:
            similarity[self.rows[exclude]] = -1
        row = int(similarity.argmax())
        return (int(self.ids[row]), float(similarity[row])) if self.ids[row] >= 0 else (None, -1.0)


class FaceService:
    def __init__(self, settings: Settings, db: Database, editor: Editor, *, enabled: bool = True, models: Path | None = None):
        self.settings = settings
        self.db = db
        self.editor = editor
        self.enabled = enabled
        self.models = models or settings.data / "models"
        self.engine: FaceEngine | None = None
        self.state = {"status": "off" if not enabled else "starting", "message": "", "download_done": 0, "download_total": 0}
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._groups: dict[int, dict] = {}   # id -> {sum, count, person_id, hidden}
        self._index = CentroidIndex()
        self._learn = False  # nach Benennen: passende unbenannte Gruppen zuordnen

        editor.hooks["purge"].append(self._before_purge)
        editor.hooks["rotate"].append(self._after_rotate)
        editor.hooks["persons"].append(self._after_persons_changed)

    # ── Start und Hintergrundschleife ──────────────────────────────
    def start(self):
        if self.enabled:
            threading.Thread(target=self._run, daemon=True, name="faces").start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        self._wake.set()

    def load(self):
        """Modelle laden (und beim ersten Mal herunterladen), Gruppen aus der Datenbank aufbauen."""
        self._learn = True  # beim Start einmal abgleichen
        if not models_ready(self.models):
            self.state.update(status="downloading", message="Modelle werden heruntergeladen (ca. 280 MB)")
            ensure_models(self.models, lambda done, total: self.state.update(download_done=done, download_total=total))
        self.state.update(status="loading", message="Modelle werden geladen")
        self.engine = FaceEngine(self.models)
        self.rebuild_groups()
        self.state.update(status="idle", message="")

    def _run(self):
        while not self._stop.is_set():
            try:
                self.load()
                break
            except Exception as exc:
                log.exception("Gesichtserkennung konnte nicht starten")
                self.state.update(status="error", message=str(exc))
                self._stop.wait(RETRY_WAIT)
        while not self._stop.is_set():
            try:
                if self.work_once():
                    continue
                self.state.update(status="idle")
                self._wake.wait(IDLE_WAIT)
                self._wake.clear()
            except Exception:
                log.exception("Fehler in der Gesichtserkennung")
                self._stop.wait(60)

    def work_once(self) -> bool:
        """Ein Stapel Arbeit. True, wenn es etwas zu tun gab."""
        pending = self.db.query(
            "SELECT id FROM assets WHERE faces_scanned = 0 AND deleted_at IS NULL ORDER BY taken_ts DESC LIMIT ?",
            (BATCH,),
        )
        if pending:
            self.state.update(status="scanning")
            for row in pending:
                if self._stop.is_set():
                    break
                self.scan(row["id"])
            self.db.bump()
        learned = self.learn() if self._learn else False
        synced = self.sync_files()
        return bool(pending) or learned or synced

    # ── Gruppen ────────────────────────────────────────────────────
    def rebuild_groups(self):
        """Gruppensummen aus allen Gesichtern neu berechnen (gleicht auch gelöschte Fotos aus)."""
        with self._lock, self.db.transaction() as conn:
            sums: dict[int, np.ndarray] = {}
            counts: dict[int, int] = {}
            for row in conn.execute("SELECT group_id, embedding FROM faces WHERE group_id IS NOT NULL"):
                vector = _vector(row["embedding"])
                sums[row["group_id"]] = sums.get(row["group_id"], 0) + vector
                counts[row["group_id"]] = counts.get(row["group_id"], 0) + 1
            self._groups = {}
            self._index = CentroidIndex()
            for group in conn.execute("SELECT id, person_id, hidden FROM face_groups").fetchall():
                if group["id"] not in counts:
                    conn.execute("DELETE FROM face_groups WHERE id = ?", (group["id"],))
                    continue
                total = sums[group["id"]].astype(np.float32)
                conn.execute("UPDATE face_groups SET vec_sum = ?, count = ? WHERE id = ?",
                             (_blob(total), counts[group["id"]], group["id"]))
                self._groups[group["id"]] = {"sum": total, "count": counts[group["id"]],
                                             "person_id": group["person_id"], "hidden": group["hidden"]}
                self._index.set(group["id"], total)

    def _new_group(self, conn, person_id: int | None = None) -> int:
        group_id = conn.execute("INSERT INTO face_groups (person_id, vec_sum, count) VALUES (?, ?, 0)",
                                (person_id, _blob(np.zeros(512, np.float32)))).lastrowid
        self._groups[group_id] = {"sum": np.zeros(512, np.float32), "count": 0, "person_id": person_id, "hidden": 0}
        self._index.set(group_id, self._groups[group_id]["sum"])
        return group_id

    def _group_add(self, conn, group_id: int, vector: np.ndarray, sign: int = 1):
        group = self._groups.get(group_id)
        if group is None:
            return
        group["sum"] = group["sum"] + sign * vector
        group["count"] += sign
        if group["count"] <= 0:
            conn.execute("DELETE FROM face_groups WHERE id = ?", (group_id,))
            del self._groups[group_id]
            self._index.remove(group_id)
        else:
            conn.execute("UPDATE face_groups SET vec_sum = ?, count = ? WHERE id = ?",
                         (_blob(group["sum"]), group["count"], group_id))
            self._index.set(group_id, group["sum"])

    def _best_group(self, vector: np.ndarray, rejected: int | None) -> int | None:
        group_id, similarity = self._index.best(vector, rejected)
        return group_id if similarity >= JOIN_THRESHOLD else None

    def learn(self) -> bool:
        """Unbenannte Gruppen, die einer benannten Person deutlich ähneln, dieser Person zuordnen."""
        self._learn = False
        merged = False
        with self._lock, self.db.transaction() as conn:
            named = [gid for gid, g in self._groups.items() if g["person_id"]]
            if not named:
                return False
            named_matrix = np.stack([self._groups[g]["sum"] for g in named]).astype(np.float32)
            named_matrix /= np.linalg.norm(named_matrix, axis=1, keepdims=True) + 1e-9
            for group_id in [gid for gid, g in self._groups.items() if not g["person_id"] and not g["hidden"]]:
                group = self._groups[group_id]
                centroid = group["sum"] / (np.linalg.norm(group["sum"]) + 1e-9)
                similarity = named_matrix @ centroid
                best = int(similarity.argmax())
                if similarity[best] < JOIN_THRESHOLD:
                    continue
                target = named[best]
                if target not in self._groups:
                    continue
                refused = conn.execute("SELECT 1 FROM faces WHERE group_id = ? AND rejected_group = ? LIMIT 1",
                                       (group_id, target)).fetchone()
                if refused:
                    continue  # "nicht diese Person" gilt weiter
                self._merge(conn, group_id, target)
                merged = True
        if merged:
            self.db.bump()
        return merged

    def _merge(self, conn, source_id: int, target_id: int):
        conn.execute("UPDATE assets SET persons_dirty = 1 WHERE id IN (SELECT asset_id FROM faces WHERE group_id = ?)",
                     (source_id,))
        conn.execute("UPDATE faces SET group_id = ? WHERE group_id = ?", (target_id, source_id))
        source = self._groups.pop(source_id)
        target = self._groups[target_id]
        target["sum"] = target["sum"] + source["sum"]
        target["count"] += source["count"]
        conn.execute("UPDATE face_groups SET vec_sum = ?, count = ? WHERE id = ?",
                     (_blob(target["sum"]), target["count"], target_id))
        conn.execute("DELETE FROM face_groups WHERE id = ?", (source_id,))
        self._index.remove(source_id)
        self._index.set(target_id, target["sum"])

    # ── Scannen ────────────────────────────────────────────────────
    def crop_file(self, face_id: int) -> Path:
        return self.settings.cache / "faces" / f"{face_id // 1000:04d}" / f"{face_id}.webp"

    def _write_crop(self, image: np.ndarray, face_id: int, x: float, y: float, w: float, h: float):
        cv2 = self.engine.cv2
        height, width = image.shape[:2]
        side = max(w * width, h * height) * 1.6
        cx, cy = (x + w / 2) * width, (y + h / 2) * height
        x1, y1 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        x2, y2 = int(min(width, cx + side / 2)), int(min(height, cy + side / 2))
        crop = cv2.resize(image[y1:y2, x1:x2], (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_AREA)
        ok, data = cv2.imencode(".webp", crop[:, :, ::-1], [cv2.IMWRITE_WEBP_QUALITY, 82])
        if ok:
            target = self.crop_file(face_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data.tobytes())

    def ensure_crop(self, face_id: int) -> Path | None:
        target = self.crop_file(face_id)
        if target.exists():
            return target
        row = self.db.one(
            "SELECT f.x, f.y, f.w, f.h, a.path FROM faces f JOIN assets a ON a.id = f.asset_id WHERE f.id = ?",
            (face_id,),
        )
        if row is None or self.engine is None:
            return None
        try:
            image = load_rgb(self.settings.library / row["path"])
            self._write_crop(image, face_id, row["x"], row["y"], row["w"], row["h"])
        except Exception as exc:
            log.warning("Gesichtsausschnitt %s nicht erzeugbar: %s", face_id, exc)
            return None
        return target if target.exists() else None

    def scan(self, asset_id: int):
        row = self.db.one("SELECT path, kind FROM assets WHERE id = ?", (asset_id,))
        if row is None:
            return
        if row["kind"] != "image":
            self.db.execute("UPDATE assets SET faces_scanned = 1 WHERE id = ?", (asset_id,))
            return
        try:
            image = load_rgb(self.settings.library / row["path"])
            found = self.engine.analyze(image)
        except Exception as exc:
            log.warning("Gesichter in %s nicht erkennbar: %s", row["path"], exc)
            self.db.execute("UPDATE assets SET faces_scanned = -1 WHERE id = ?", (asset_id,))
            return

        height, width = image.shape[:2]
        created = []
        with self._lock, self.db.transaction() as conn:
            old = conn.execute(
                "SELECT id, embedding, group_id, confirmed, rejected_group FROM faces WHERE asset_id = ?", (asset_id,)
            ).fetchall()

            for face in found:
                # Bisherige Zuordnung übernehmen, wenn es dasselbe Gesicht ist (z. B. nach dem Drehen)
                carry = max(old, key=lambda o: float(_vector(o["embedding"]) @ face.embedding), default=None)
                if carry is not None and float(_vector(carry["embedding"]) @ face.embedding) < CARRY_THRESHOLD:
                    carry = None
                rejected = carry["rejected_group"] if carry else None
                confirmed = carry["confirmed"] if carry else 0
                group_id = carry["group_id"] if carry and carry["group_id"] in self._groups else None
                if group_id is None:
                    group_id = self._best_group(face.embedding, rejected) or self._new_group(conn)
                x1, y1, x2, y2 = face.box
                box = (float(max(0.0, x1 / width)), float(max(0.0, y1 / height)),
                       float(min(1.0, (x2 - x1) / width)), float(min(1.0, (y2 - y1) / height)))
                face_id = conn.execute(
                    """INSERT INTO faces (asset_id, x, y, w, h, score, embedding, group_id, confirmed, rejected_group)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (asset_id, *box, face.score, _blob(face.embedding), group_id, confirmed, rejected),
                ).lastrowid
                self._group_add(conn, group_id, face.embedding)
                created.append((face_id, box))

            # Alte Gesichter erst jetzt entfernen: sonst verschwände eine Gruppe mit nur diesem Gesicht,
            # bevor das neue Gesicht ihre Zuordnung übernehmen konnte
            for face in old:
                self._group_add(conn, face["group_id"], _vector(face["embedding"]), -1)
                conn.execute("DELETE FROM faces WHERE id = ?", (face["id"],))

            self._link_known_person(conn, asset_id)
            conn.execute(
                """UPDATE assets SET faces_scanned = 1, persons_dirty = CASE WHEN EXISTS (
                       SELECT 1 FROM faces f JOIN face_groups g ON g.id = f.group_id
                       WHERE f.asset_id = ? AND g.person_id IS NOT NULL) THEN 1 ELSE persons_dirty END
                   WHERE id = ?""",
                (asset_id, asset_id),
            )

        for face in old:
            self.crop_file(face["id"]).unlink(missing_ok=True)
        for face_id, box in created:
            self._write_crop(image, face_id, *box)

    def _link_known_person(self, conn, asset_id: int):
        """Startwert: Ein Gesicht und genau eine Person aus den Metadaten ohne Gesicht → verknüpfen."""
        faces = conn.execute(
            """SELECT f.id, f.embedding, f.group_id FROM faces f LEFT JOIN face_groups g ON g.id = f.group_id
               WHERE f.asset_id = ? AND g.person_id IS NULL""", (asset_id,)).fetchall()
        named = conn.execute(
            """SELECT COUNT(*) FROM faces f JOIN face_groups g ON g.id = f.group_id
               WHERE f.asset_id = ? AND g.person_id IS NOT NULL""", (asset_id,)).fetchone()[0]
        persons = conn.execute(
            """SELECT p.id FROM asset_persons l JOIN persons p ON p.id = l.person_id WHERE l.asset_id = ?
               AND p.id NOT IN (SELECT g.person_id FROM faces f JOIN face_groups g ON g.id = f.group_id
                                WHERE f.asset_id = ? AND g.person_id IS NOT NULL)""", (asset_id, asset_id)).fetchall()
        if len(faces) == 1 and not named and len(persons) == 1:
            self._move_face(conn, faces[0], persons[0]["id"], confirmed=1)

    def _person_group(self, conn, person_id: int) -> int:
        row = conn.execute("SELECT id FROM face_groups WHERE person_id = ? ORDER BY count DESC LIMIT 1",
                           (person_id,)).fetchone()
        return row["id"] if row and row["id"] in self._groups else self._new_group(conn, person_id)

    def _move_face(self, conn, face, person_id: int | None, *, confirmed: int, rejected: int | None = None):
        vector = _vector(face["embedding"])
        self._group_add(conn, face["group_id"], vector, -1)
        target = self._person_group(conn, person_id) if person_id else self._new_group(conn)
        self._group_add(conn, target, vector)
        conn.execute("UPDATE faces SET group_id = ?, confirmed = ?, rejected_group = ? WHERE id = ?",
                     (target, confirmed, rejected, face["id"]))

    # ── Namen in Dateien schreiben ─────────────────────────────────
    def sync_files(self, limit: int = 50) -> bool:
        rows = self.db.query(
            "SELECT id, path FROM assets WHERE persons_dirty = 1 AND deleted_at IS NULL LIMIT ?", (limit,))
        for row in rows:
            try:
                self.relabel(row["id"], self._face_names(row["id"]), [])
            except EditError as exc:
                log.warning("Personen für %s nicht geschrieben: %s", row["path"], exc)
            self.db.execute("UPDATE assets SET persons_dirty = 0 WHERE id = ?", (row["id"],))
        if rows:
            self.db.bump()
        return bool(rows)

    def _face_names(self, asset_id: int) -> list[str]:
        return [r["name"] for r in self.db.query(
            """SELECT DISTINCT p.name FROM faces f JOIN face_groups g ON g.id = f.group_id
               JOIN persons p ON p.id = g.person_id WHERE f.asset_id = ?""", (asset_id,))]

    def relabel(self, asset_id: int, add: list[str], remove: list[str]):
        """Personen eines Fotos ändern: in die Datei, bei Formaten ohne Metadaten nur in die Datenbank."""
        row = self.db.one("SELECT path FROM assets WHERE id = ?", (asset_id,))
        if row is None:
            return
        if Path(row["path"]).suffix.lower() in WRITABLE:
            self.editor.change_labels(asset_id, "persons", add, remove)
            return
        with self.db.transaction() as conn:
            removed = {name.casefold() for name in remove}
            current = [n for n in labels.current(conn, asset_id, "persons") if n.casefold() not in removed]
            labels.replace(conn, asset_id, "persons", current + list(add))
            labels.remove_unused(conn)
        self.db.bump()

    def _remove_label_if_unused(self, asset_id: int, person_id: int):
        """Name aus der Datei nehmen, wenn kein anderes Gesicht dieser Person im Foto ist."""
        still = self.db.one(
            """SELECT 1 FROM faces f JOIN face_groups g ON g.id = f.group_id
               WHERE f.asset_id = ? AND g.person_id = ?""", (asset_id, person_id))
        person = self.db.one("SELECT name FROM persons WHERE id = ?", (person_id,))
        if still or person is None:
            return
        self.relabel(asset_id, [], [person["name"]])

    # ── Aktionen aus der Oberfläche ────────────────────────────────
    def _person_id(self, conn, name: str) -> int:
        clean = labels.normalize([name])
        if not clean:
            raise ValueError("Name fehlt")
        conn.execute("INSERT OR IGNORE INTO persons (name) VALUES (?)", (clean[0],))
        return conn.execute("SELECT id FROM persons WHERE name = ?", (clean[0],)).fetchone()["id"]

    def _face(self, conn, face_id: int):
        face = conn.execute("SELECT f.*, g.person_id FROM faces f LEFT JOIN face_groups g ON g.id = f.group_id "
                            "WHERE f.id = ?", (face_id,)).fetchone()
        if face is None:
            raise NotFound("Gesicht nicht gefunden")
        return face

    def name_group(self, group_id: int, name: str) -> int:
        """Unbenannte Gruppe einer Person geben; gibt es die Person schon mit Gesichtern, werden die Gruppen vereint."""
        with self._lock, self.db.transaction() as conn:
            if group_id not in self._groups:
                raise NotFound("Gruppe nicht gefunden")
            person_id = self._person_id(conn, name)
            conn.execute("UPDATE faces SET confirmed = 1 WHERE group_id = ?", (group_id,))
            target = conn.execute("SELECT id FROM face_groups WHERE person_id = ? AND id != ? ORDER BY count DESC LIMIT 1",
                                  (person_id, group_id)).fetchone()
            if target and target["id"] in self._groups:
                self._merge(conn, group_id, target["id"])
                group_id = target["id"]
            else:
                conn.execute("UPDATE face_groups SET person_id = ?, hidden = 0 WHERE id = ?", (person_id, group_id))
                self._groups[group_id].update(person_id=person_id, hidden=0)
            conn.execute("UPDATE assets SET persons_dirty = 1 WHERE id IN (SELECT asset_id FROM faces WHERE group_id = ?)",
                         (group_id,))
        self._learn = True
        self.wake()
        return person_id

    def hide_group(self, group_id: int):
        with self._lock:
            if group_id not in self._groups:
                raise NotFound("Gruppe nicht gefunden")
            self.db.execute("UPDATE face_groups SET hidden = 1 WHERE id = ?", (group_id,))
            self._groups[group_id]["hidden"] = 1

    def remove_face(self, face_id: int):
        """"Das ist nicht diese Person": Gesicht aus seiner Gruppe lösen und nicht wieder dorthin einsortieren."""
        with self._lock, self.db.transaction() as conn:
            face = self._face(conn, face_id)
            self._move_face(conn, face, None, confirmed=0, rejected=face["group_id"])
        if face["person_id"]:
            self._remove_label_if_unused(face["asset_id"], face["person_id"])
        self.db.bump()

    def assign_face(self, face_id: int, name: str) -> int:
        with self._lock, self.db.transaction() as conn:
            face = self._face(conn, face_id)
            person_id = self._person_id(conn, name)
            if face["person_id"] != person_id:
                self._move_face(conn, face, person_id, confirmed=1)
            else:
                conn.execute("UPDATE faces SET confirmed = 1 WHERE id = ?", (face_id,))
            conn.execute("UPDATE assets SET persons_dirty = 1 WHERE id = ?", (face["asset_id"],))
        if face["person_id"] and face["person_id"] != person_id:
            self._remove_label_if_unused(face["asset_id"], face["person_id"])
        self.sync_asset(face["asset_id"])
        self._learn = True
        self.wake()
        return person_id

    def sync_asset(self, asset_id: int):
        """Einzelnes Foto sofort schreiben (statt auf den Hintergrund zu warten)."""
        row = self.db.one("SELECT persons_dirty FROM assets WHERE id = ?", (asset_id,))
        if row and row["persons_dirty"]:
            self.relabel(asset_id, self._face_names(asset_id), [])
            self.db.execute("UPDATE assets SET persons_dirty = 0 WHERE id = ?", (asset_id,))
            self.db.bump()

    def rename_person(self, person_id: int, name: str) -> tuple[str, str, list[int]]:
        """Person umbenennen oder mit gleichnamiger Person vereinen.

        Gibt (alter Name, neuer Name, betroffene Fotos) zurück; die Dateien schreibt danach eine Hintergrundaufgabe.
        """
        with self._lock, self.db.transaction() as conn:
            old = conn.execute("SELECT name FROM persons WHERE id = ?", (person_id,)).fetchone()
            if old is None:
                raise NotFound("Person nicht gefunden")
            clean = labels.normalize([name])
            if not clean:
                raise ValueError("Name fehlt")
            existing = conn.execute("SELECT id FROM persons WHERE name = ? AND id != ?", (clean[0], person_id)).fetchone()
            if existing is None and old["name"].casefold() == clean[0].casefold():
                target_id = person_id
            else:
                target_id = existing["id"] if existing else conn.execute(
                    "INSERT INTO persons (name) VALUES (?)", (clean[0],)).lastrowid
                conn.execute("UPDATE face_groups SET person_id = ? WHERE person_id = ?", (target_id, person_id))
                for group in self._groups.values():
                    if group["person_id"] == person_id:
                        group["person_id"] = target_id
            conn.execute("UPDATE persons SET name = ? WHERE id = ?", (clean[0], target_id))
            assets = [r["asset_id"] for r in conn.execute(
                """SELECT l.asset_id FROM asset_persons l JOIN assets a ON a.id = l.asset_id
                   WHERE l.person_id = ? AND a.deleted_at IS NULL""", (person_id,))]
        return old["name"], clean[0], assets

    # ── Rückmeldungen vom Editor ───────────────────────────────────
    def _before_purge(self, asset_id: int):
        with self._lock, self.db.transaction() as conn:
            for face in conn.execute("SELECT id, group_id, embedding FROM faces WHERE asset_id = ?", (asset_id,)).fetchall():
                self._group_add(conn, face["group_id"], _vector(face["embedding"]), -1)
                self.crop_file(face["id"]).unlink(missing_ok=True)

    def _after_rotate(self, asset_id: int):
        self.db.execute("UPDATE assets SET faces_scanned = 0 WHERE id = ?", (asset_id,))
        self.wake()

    def _after_persons_changed(self, asset_id: int):
        """Person von Hand aus einem Foto entfernt → zugehörige Gesichter lösen, damit sie nicht zurückkommt."""
        with self._lock, self.db.transaction() as conn:
            present = {name.casefold() for name in labels.current(conn, asset_id, "persons")}
            faces = conn.execute(
                """SELECT f.*, p.name FROM faces f JOIN face_groups g ON g.id = f.group_id
                   JOIN persons p ON p.id = g.person_id WHERE f.asset_id = ?""", (asset_id,)).fetchall()
            for face in faces:
                if face["name"].casefold() not in present:
                    self._move_face(conn, face, None, confirmed=0, rejected=face["group_id"])

    # ── Übersicht ──────────────────────────────────────────────────
    def status(self) -> dict:
        counts = self.db.one(
            """SELECT COALESCE(SUM(kind = 'image'), 0) AS images,
                      COALESCE(SUM(kind = 'image' AND faces_scanned != 0), 0) AS scanned,
                      COALESCE(SUM(persons_dirty), 0) AS pending_files
               FROM assets WHERE deleted_at IS NULL""")
        faces = self.db.one("SELECT COUNT(*) AS n FROM faces")["n"]
        return {**self.state, "enabled": self.enabled, **dict(counts), "faces": faces}
