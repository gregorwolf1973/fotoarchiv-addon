"""Doppelte und sehr ähnliche Fotos finden (Wahrnehmungs-Hash).

Jedes Foto bekommt einen 64-Bit-pHash aus seinem Vorschaubild: verkleinert, neu komprimiert, als
anderes Format gespeichert oder anders beschriftet bleibt er (fast) gleich.
- doppelt: Abstand ≤ duplicate_bits (Standard 6), egal wann aufgenommen (gemessen: WhatsApp-Kopie 0,
  aufgehellt 2, andere Fotos derselben Person ≥ 14, andere Motive 18–38)
- Serie: Abstand ≤ series_bits (Standard 12) und höchstens 30 Sekunden auseinander

Beide Schwellen stehen in den Add-on-Optionen. Sie gelten paarweise: sind A und B sowie B und C
ähnlich genug, landen alle drei in einer Gruppe, auch wenn A und C weiter auseinanderliegen.
"""

import logging
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from . import labels
from .config import Settings
from .db import Database
from .editor import EditError, Editor
from .importer import Importer

log = logging.getLogger(__name__)

SERIES_SECONDS = 30
BATCH = 200
IDLE_WAIT = 600
DATE_RANK = {"mtime": 0, "filename": 1, "exif": 2}

_N = 32
_DCT = np.cos(np.pi * (2 * np.arange(_N)[None, :] + 1) * np.arange(_N)[:, None] / (2 * _N)).astype(np.float32)


def phash(path: Path) -> int:
    import pyvips

    small = pyvips.Image.thumbnail(str(path), _N, height=_N, size="force").colourspace("b-w")[0]
    pixels = np.ndarray(buffer=small.write_to_memory(), dtype=np.uint8, shape=(_N, _N)).astype(np.float32)
    coefficients = (_DCT @ pixels @ _DCT.T)[:8, :8].flatten()  # niedrige Frequenzen = grobe Bildstruktur
    median = np.median(coefficients[1:])
    value = 0
    for coefficient in coefficients:
        value = (value << 1) | int(coefficient > median)
    return value


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int):
        self.parent[self.find(a)] = self.find(b)

    def groups(self) -> list[list[int]]:
        result: dict[int, list[int]] = {}
        for x in self.parent:
            result.setdefault(self.find(x), []).append(x)
        return [sorted(members) for members in result.values() if len(members) > 1]


class DuplicateService:
    def __init__(self, settings: Settings, db: Database, importer: Importer, editor: Editor, *, enabled: bool = True):
        self.settings = settings
        self.db = db
        self.importer = importer
        self.editor = editor
        self.enabled = enabled
        self.duplicate_bits = settings.duplicate_bits
        self.series_bits = settings.series_bits
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._cache: tuple[tuple, dict] | None = None
        self._ignore_version = 0
        # Import-Hinweis: je Byte-Position ein Verzeichnis Bytewert -> Fotos (erst bei Bedarf aufgebaut)
        self._hashes: dict[int, int] | None = None
        self._buckets: list[dict[int, set[int]]] = []
        self._index_lock = threading.Lock()
        editor.hooks["rotate"].append(self._invalidate)
        importer.hooks["imported"].append(self._on_imported)

    # ── Hintergrund ────────────────────────────────────────────────
    def start(self):
        if self.enabled:
            threading.Thread(target=self._run, daemon=True, name="duplicates").start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                if self.hash_pending():
                    continue
            except Exception:
                log.exception("Ähnlichkeits-Hash fehlgeschlagen")
            self._wake.wait(IDLE_WAIT)
            self._wake.clear()

    def hash_pending(self, limit: int = BATCH) -> int:
        rows = self.db.query(
            "SELECT id FROM assets WHERE phash IS NULL AND kind = 'image' AND deleted_at IS NULL LIMIT ?", (limit,))
        for row in rows:
            if self._stop.is_set():
                break
            self.hash_asset(row["id"])
        if rows:
            self.db.bump()
        return len(rows)

    def hash_asset(self, asset_id: int) -> int | None:
        thumb = self.importer.ensure_thumbnail(asset_id)
        try:
            value = phash(thumb) if thumb else None
        except Exception as exc:
            log.warning("Hash für Foto %s nicht berechenbar: %s", asset_id, exc)
            value = None
        # Leerer Text = nicht berechenbar, damit es nicht bei jedem Durchlauf erneut versucht wird
        self.db.execute("UPDATE assets SET phash = ? WHERE id = ?",
                        (f"{value:016x}" if value is not None else "", asset_id))
        self._index_update(asset_id, value)
        return value

    def _invalidate(self, asset_id: int):
        self.db.execute("UPDATE assets SET phash = NULL WHERE id = ?", (asset_id,))
        self._index_update(asset_id, None)
        self.wake()

    def _index_update(self, asset_id: int, value: int | None):
        with self._index_lock:
            if self._hashes is None:
                return
            old = self._hashes.pop(asset_id, None)
            if old is not None:
                for band in range(8):
                    self._buckets[band].get((old >> (8 * band)) & 0xFF, set()).discard(asset_id)
            if value is not None:
                self._hashes[asset_id] = value
                for band in range(8):
                    self._buckets[band].setdefault((value >> (8 * band)) & 0xFF, set()).add(asset_id)

    def similar_to(self, asset_id: int, value: int) -> int | None:
        """Ein vorhandenes Foto innerhalb der Schwelle – geprüft werden nur Fotos mit einem gleichen Byte."""
        with self._index_lock:
            if self._hashes is None:
                self._hashes, self._buckets = {}, [{} for _ in range(8)]
                rows = self.db.query("SELECT id, phash FROM assets WHERE phash IS NOT NULL AND phash != ''")
                for row in rows:
                    number = int(row["phash"], 16)
                    self._hashes[row["id"]] = number
                    for band in range(8):
                        self._buckets[band].setdefault((number >> (8 * band)) & 0xFF, set()).add(row["id"])
            candidates = set()
            for band in range(8):
                candidates |= self._buckets[band].get((value >> (8 * band)) & 0xFF, set())
            matches = sorted(c for c in candidates
                             if c != asset_id and (self._hashes[c] ^ value).bit_count() <= self.duplicate_bits)
        for match in matches:
            if self.db.one("SELECT 1 FROM assets WHERE id = ? AND deleted_at IS NULL", (match,)):
                return match
        return None

    def _on_imported(self, asset_id: int) -> str | None:
        """Beim Import sofort hashen und auf ein sehr ähnliches vorhandenes Foto hinweisen."""
        if not self.enabled:
            return None
        value = self.hash_asset(asset_id)
        match = self.similar_to(asset_id, value) if value is not None else None
        if match is None:
            return None
        return self.db.one("SELECT path FROM assets WHERE id = ?", (match,))["path"]

    # ── Gruppen ────────────────────────────────────────────────────
    def status(self) -> dict:
        row = self.db.one(
            """SELECT COALESCE(SUM(kind = 'image'), 0) AS images,
                      COALESCE(SUM(kind = 'image' AND phash IS NOT NULL), 0) AS hashed
               FROM assets WHERE deleted_at IS NULL""")
        return {"enabled": self.enabled, **dict(row)}

    def ignore(self, asset_ids: list[int]):
        ids = sorted(set(asset_ids))
        with self.db.transaction() as conn:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    conn.execute("INSERT OR IGNORE INTO duplicate_ignores (a, b) VALUES (?, ?)", (a, b))
        self._ignore_version += 1

    def groups(self) -> dict:
        key = (self.db.revision, self._ignore_version)
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        found = self._compute() if self.enabled else {"duplicates": [], "series": []}
        result = {**self.status(), **found}
        self._cache = (key, result)
        return result

    def _compute(self) -> dict:
        rows = self.db.query(
            """SELECT id, phash, taken_ts FROM assets
               WHERE deleted_at IS NULL AND kind = 'image' AND phash IS NOT NULL AND phash != ''
               ORDER BY taken_ts, id""")
        if len(rows) < 2:
            return {"duplicates": [], "series": []}
        ids = np.array([r["id"] for r in rows], dtype=np.int64)
        hashes = np.array([int(r["phash"], 16) for r in rows], dtype=np.uint64)
        times = np.array([r["taken_ts"] for r in rows], dtype=np.int64)
        ignored = {(r["a"], r["b"]) for r in self.db.query("SELECT a, b FROM duplicate_ignores")}

        def allowed(a: int, b: int) -> bool:
            return (min(a, b), max(a, b)) not in ignored

        # Doppelte: bei Abstand ≤ 7 ist mindestens eines der 8 Bytes identisch (Schubfachprinzip),
        # darum ist duplicate_bits auf 7 begrenzt – sonst würden Paare durch diese Vorauswahl fallen
        same = _UnionFind()
        for band in range(8):
            keys = ((hashes >> np.uint64(8 * band)) & np.uint64(0xFF)).astype(np.int64)
            order = np.argsort(keys, kind="stable")
            bounds = np.flatnonzero(np.diff(keys[order])) + 1
            for bucket in np.split(order, bounds):
                if len(bucket) < 2:
                    continue
                for start in range(0, len(bucket), 512):
                    part = bucket[start:start + 512]
                    distance = np.bitwise_count(hashes[part][:, None] ^ hashes[bucket][None, :])
                    for row, col in zip(*np.nonzero(distance <= self.duplicate_bits)):
                        a, b = int(ids[part[row]]), int(ids[bucket[col]])
                        if a < b and allowed(a, b):
                            same.union(a, b)

        # Serien: zeitlich benachbart und ähnlich (Fotos sind nach Zeit sortiert)
        series = _UnionFind()
        for i in range(len(ids)):
            j = i + 1
            while j < len(ids) and times[j] - times[i] <= SERIES_SECONDS:
                a, b = int(ids[i]), int(ids[j])
                if (int(hashes[i]) ^ int(hashes[j])).bit_count() <= self.series_bits and allowed(a, b) \
                        and same.find(a) != same.find(b):
                    series.union(a, b)
                j += 1

        duplicate_groups = same.groups()
        series_groups = [g for g in series.groups() if len({same.find(x) for x in g}) > 1]
        details = self._details({x for g in duplicate_groups + series_groups for x in g})
        return {
            "duplicates": self._describe(duplicate_groups, details, "duplicate"),
            "series": self._describe(series_groups, details, "series"),
        }

    def _details(self, asset_ids: set[int]) -> dict[int, dict]:
        if not asset_ids:
            return {}
        marks = ",".join("?" * len(asset_ids))
        rows = self.db.query(
            f"""SELECT a.id, a.taken_ts, a.width, a.height, a.rev, a.size, a.path, a.date_source, a.camera,
                       a.lat IS NOT NULL AS has_location,
                       (SELECT COUNT(*) FROM asset_tags WHERE asset_id = a.id) AS tags,
                       (SELECT COUNT(*) FROM asset_persons WHERE asset_id = a.id) AS persons
                FROM assets a WHERE a.id IN ({marks})""", tuple(asset_ids))
        result = {}
        for r in rows:
            item = dict(r)
            item["name"] = Path(r["path"]).name
            item["format"] = Path(r["path"]).suffix.lstrip(".").upper()
            item["has_location"] = bool(r["has_location"])
            result[r["id"]] = item
        return result

    @staticmethod
    def _best(items: list[dict], kind: str) -> int:
        if kind == "series":
            # In einer Serie ist die größte Datei meist die schärfste (mehr Details, schlechter komprimierbar)
            return max(items, key=lambda i: (i["size"], -i["id"]))["id"]
        return max(items, key=lambda i: (
            (i["width"] or 0) * (i["height"] or 0),
            DATE_RANK.get(i["date_source"], 0),
            i["tags"] + i["persons"] + int(i["has_location"]),
            i["size"],
            -i["id"],
        ))["id"]

    def _describe(self, groups: list[list[int]], details: dict, kind: str) -> list[dict]:
        described = []
        for members in groups:
            items = sorted((details[x] for x in members if x in details), key=lambda i: (i["taken_ts"], i["id"]))
            if len(items) < 2:
                continue
            described.append({
                "key": f"{kind}-{items[0]['id']}",
                "kind": kind,
                "keep": self._best(items, kind),
                "span": items[-1]["taken_ts"] - items[0]["taken_ts"],
                "items": items,
            })
        described.sort(key=lambda g: -g["items"][-1]["taken_ts"])
        return described

    # ── Aufräumen ──────────────────────────────────────────────────
    def resolve_one(self, remove_id: int, keep_id: int, transfer: bool):
        """Foto in den Papierkorb legen; vorher auf Wunsch Metadaten aufs behaltene Foto übertragen."""
        removed = self.db.one("SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (remove_id,))
        keep = self.db.one("SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (keep_id,))
        if removed is None:
            raise EditError("Foto ist schon gelöscht")
        if keep is None:
            raise EditError("Das zu behaltende Foto fehlt – nichts gelöscht")
        if transfer:
            with self.db.transaction() as conn:
                tags = labels.current(conn, remove_id, "tags")
                persons = labels.current(conn, remove_id, "persons")
            if tags:
                self.editor.change_labels(keep_id, "tags", tags, [])
            if persons:
                self.editor.change_labels(keep_id, "persons", persons, [])
            if keep["lat"] is None and removed["lat"] is not None:
                self.editor.set_location(keep_id, removed["lat"], removed["lon"])
            if DATE_RANK.get(keep["date_source"], 0) < DATE_RANK.get(removed["date_source"], 0):
                self.editor.set_date(keep_id, datetime.fromisoformat(removed["taken_at"]))
        self.editor.delete(remove_id)
