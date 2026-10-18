"""Bilderkennung: Entscheidungsregeln, Zerlegung in Token, Ablauf mit Ersatzmodellen, API.

Die echten Modelle (1,6 GB) braucht nur der letzte Test: FOTOARCHIV_VISION_MODELS zeigt auf einen
Ordner mit orientation.onnx, clip-visual.onnx, clip-textual.onnx und clip-tokenizer.json.
"""

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from fotoarchiv import vocab
from fotoarchiv.main import create_app
from fotoarchiv.vision import (DEGREES, VisionService, faces_confirm, orientation_vote, search_hits,
                               suggest_tags)
from fotoarchiv.visionengine import FILES, ModelError, ModelProcess, Tokenizer

REAL_MODELS = Path(os.environ["FOTOARCHIV_VISION_MODELS"]) if os.environ.get("FOTOARCHIV_VISION_MODELS") else None


def one_hot(index: int, sure: float = 0.9) -> np.ndarray:
    p = np.full(4, (1 - sure) / 3)
    p[index] = sure
    return p


def unit(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    return vector / np.linalg.norm(vector)


# ── Entscheidungsregeln ────────────────────────────────────────────
def test_orientation_vote_combines_all_four_turns():
    # Das Foto braucht 90°. Um k gedreht braucht es 90 - k – so urteilt ein gutes Modell
    probs = {k: one_hot(DEGREES.index((90 - k) % 360)) for k in DEGREES}
    assert orientation_vote(probs) == (90, 4)
    probs[180] = one_hot(0)  # ein Ausreißer
    assert orientation_vote(probs) == (90, 3)
    # Unentschlossen: jedes Urteil sagt etwas anderes
    assert orientation_vote({k: one_hot(0, 0.4) for k in DEGREES})[1] == 1


def test_faces_must_confirm_one_clear_orientation():
    assert faces_confirm({0: 0.0, 90: 0.8, 180: 0.0, 270: 0.1}, 90)
    assert not faces_confirm({0: 0.0, 90: 0.55, 180: 0.0, 270: 0.0}, 90)   # zu unsicher
    assert not faces_confirm({0: 0.6, 90: 0.8, 180: 0.0, 270: 0.0}, 90)    # steht schon richtig mit Gesicht
    assert not faces_confirm({0: 0.0, 90: 0.8, 180: 0.0, 270: 0.7}, 90)    # zwei Lagen fast gleich gut
    assert not faces_confirm({0: 0.0, 90: 0.1, 180: 0.0, 270: 0.9}, 90)    # Gesicht spricht für eine andere Lage


def test_suggest_tags_only_for_clear_matches():
    names = ["Hund", "Katze", "Strand"]
    tags = np.eye(3, 8, dtype=np.float32)
    background = np.eye(2, 8, k=5, dtype=np.float32)
    assert suggest_tags(unit([1, 0, 0, 0, 0, 0, 0, 0]), names, tags, background)[0][0] == "Hund"
    both = suggest_tags(unit([1, 0, 1, 0, 0, 0, 0, 0]), names, tags, background)
    assert {name for name, _ in both} == {"Hund", "Strand"}
    assert suggest_tags(unit([0, 0, 0, 1, 0, 0, 0, 0]), names, tags, background) == []      # nichts davon
    assert suggest_tags(unit([0.2, 0, 0, 0, 0, 1, 0, 0]), names, tags, background) == []    # eher Hintergrund


def test_search_hits_need_similarity_and_beat_background():
    query = unit([1, 0, 0, 0])
    background = np.array([unit([0, 1, 0, 0]), unit([1, 0.01, 0, 0])])  # zweiter gleicht der Suche: zählt nicht
    vectors = np.array([unit([1, 0.3, 0, 0]), unit([0.3, 1, 0, 0]), unit([0, 0, 1, 0]), unit([1, 0, 0, 0])],
                       dtype=np.float16)
    assert search_hits(query, vectors, background).tolist() == [3, 0]


# ── Zerlegung in Token ─────────────────────────────────────────────
def test_tokenizer_finds_most_likely_pieces(tmp_path):
    vocab_list = [["<s>", 0.0], ["<pad>", 0.0], ["</s>", 0.0], ["<unk>", 0.0],
                  ["▁", -3.0], ["▁Hund", -5.0], ["▁Hu", -4.0], ["nd", -4.0], ["e", -2.0], ["▁am", -3.0]]
    path = tmp_path / "tokenizer.json"
    path.write_text(json.dumps({
        "added_tokens": [{"content": c} for c in ("<s>", "<pad>", "</s>", "<unk>")],
        "model": {"type": "Unigram", "vocab": vocab_list},
    }))
    tok = Tokenizer(path)
    # "▁Hund" allein (-5) schlägt "▁Hu" + "nd" (-8); unbekannte Zeichen werden zu einem <unk>
    assert tok.encode("Hunde  am", length=8) == [0, 5, 8, 9, 2, 1, 1, 1]
    assert tok.encode("Hund xyz", length=8) == [0, 5, 4, 3, 2, 1, 1, 1]
    assert tok.encode("Hund " * 20, length=6) == [0, 5, 5, 5, 5, 2]


@pytest.mark.skipif(not (REAL_MODELS and (REAL_MODELS / "clip-tokenizer.json").is_file()), reason="Modelle fehlen")
def test_tokenizer_matches_reference_ids():
    tok = Tokenizer(REAL_MODELS / "clip-tokenizer.json")
    # Nummern von der Bibliothek "tokenizers" (0.23.3) für diese tokenizer.json
    assert tok.encode("Hund am Strand", length=7) == [0, 49083, 444, 42233, 2, 1, 1]
    assert tok.encode("Größe Übung ß", length=6) == [0, 66461, 159173, 6, 20036, 2]
    assert tok.encode("Fische unter Wasser 🐟", length=8) == [0, 163721, 13, 3993, 23679, 6, 3, 2]


# ── Ablauf mit Ersatzmodellen ──────────────────────────────────────
def text_vector(text: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
    return unit(np.random.default_rng(seed).normal(size=512))


class FakeText:
    def __init__(self):
        self.calls = 0

    def call(self, operation, texts):
        assert operation == "text"
        self.calls += 1
        return np.stack([text_vector(t) for t in texts])

    def release(self):
        pass

    def close(self):
        pass


class FakeImage:
    """Antwortet je Vorschaubild mit festgelegten Merkmalen und Ausrichtungsurteilen."""

    def __init__(self):
        self.vectors: dict[int, np.ndarray] = {}
        self.default: np.ndarray | None = None  # Merkmale ohne bestimmtes Motiv
        self.needs: dict[int, int] = {}  # asset_id -> nötige Korrektur
        self.calls = []

    def call(self, operation, path, rotations, embed):
        asset_id = int(Path(path).stem)
        self.calls.append((asset_id, tuple(rotations)))
        need = self.needs.get(asset_id, 0)
        orientation = np.stack([one_hot(DEGREES.index((need - k) % 360)) for k in rotations]) if rotations else None
        fallback = self.default if self.default is not None else text_vector(f"Foto {asset_id}")
        vector = self.vectors.get(asset_id, fallback) if embed else None
        return {"orientation": orientation, "embedding": vector}

    def close(self):
        pass


class FakeEngine:
    def __init__(self, scores):
        self.scores = list(scores)

    def detect(self, image):
        score = self.scores.pop(0)
        return [type("Face", (), {"score": score})()] if score else []


class FakeFaces:
    def __init__(self, engine=None):
        self.enabled = engine is not None
        self.engine = engine
        self.state = {"status": "idle"}


def place_models(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for kind in FILES.values():
        for model in kind:
            (folder / model.name).write_bytes(b"")


@pytest.fixture
def service(settings, importer, editor):
    place_models(settings.data / "models" / "vision")
    made = VisionService(settings, importer.db, importer, editor, FakeFaces(), image_models=FakeImage(),
                         text_models=FakeText())
    made.prepare()
    made.image.default = made._vocab[2][0]  # wie „ein Foto“
    return made


def tag_vector(service, name: str) -> np.ndarray:
    names, tags, _ = service._vocab
    return tags[names.index(name)]


def imported(importer, make_jpeg, tmp_path, name: str, **tags) -> int:
    result = importer.import_file(make_jpeg(tmp_path / "quelle" / name, **tags), move=True)
    assert result.status == "imported", result.message
    return result.asset_id


def test_prepare_caches_vocabulary(settings, importer, editor, service):
    assert service.search_ready and service.text.calls == 1
    assert (service.models / f"vocab-{vocab.fingerprint()}.npy").is_file()
    again = VisionService(settings, importer.db, importer, editor, FakeFaces(), image_models=FakeImage(),
                          text_models=FakeText())
    again.prepare()
    assert again.text.calls == 0  # aus der Datei
    assert np.allclose(again._vocab[1], service._vocab[1])


def test_suggestions_dismiss_and_accept(service, importer, editor, make_jpeg, tmp_path):
    dog = imported(importer, make_jpeg, tmp_path, "hund.jpg")
    beach = imported(importer, make_jpeg, tmp_path, "strand.jpg", Keywords="Strand")
    other = imported(importer, make_jpeg, tmp_path, "anderes.jpg")
    service.image.vectors = {dog: tag_vector(service, "Hund"), beach: tag_vector(service, "Strand")}
    assert service.work_once()
    assert not service.work_once()

    assert [s["name"] for s in service.suggestions(dog)] == ["Hund"]
    assert service.suggestions(beach) == []  # hat das Schlagwort schon
    assert service.suggestions(other) == []
    assert service.suggestion_labels() == [{"name": "Hund", "count": 1}]

    assert service.dismiss("Hund", [dog]) == 1
    assert service.suggestions(dog) == []
    importer.db.execute("UPDATE assets SET vision_scanned = 0 WHERE id = ?", (dog,))
    service.work_once()
    assert service.suggestions(dog) == []  # abgelehnt bleibt abgelehnt

    # Übernehmen = Schlagwort von Hand setzen; danach kein Vorschlag mehr, auch nicht nach Entfernen
    service.image.vectors[other] = tag_vector(service, "Katze")
    importer.db.execute("UPDATE assets SET vision_scanned = 0 WHERE id = ?", (other,))
    service.work_once()
    assert [s["name"] for s in service.suggestions(other)] == ["Katze"]
    editor.change_labels(other, "tags", ["Katze"], [])
    editor.change_labels(other, "tags", [], ["Katze"])
    assert service.suggestions(other) == []


def test_orientation_suggested_without_face_confirmation(service, importer, editor, make_jpeg, tmp_path):
    upright = imported(importer, make_jpeg, tmp_path, "gerade.jpg")
    tilted = imported(importer, make_jpeg, tmp_path, "schief.jpg")
    service.image.needs = {tilted: 90}
    service.work_once()

    # Gerade Fotos kosten nur einen Durchlauf, verdächtige vier
    assert sorted(service.image.calls) == sorted([(upright, (0,)), (tilted, (0,)), (tilted, (90, 180, 270))])
    assert service.orientation_of(upright) is None
    assert service.orientation_of(tilted) == {"degrees": 90, "status": "suggested"}
    assert importer.db.one("SELECT width FROM assets WHERE id = ?", (tilted,))["width"] == 320  # nicht gedreht

    service.decide(tilted, accept=True)
    row = importer.db.one("SELECT width, vision_scanned, orient_checked FROM assets WHERE id = ?", (tilted,))
    assert (row["width"], row["vision_scanned"], row["orient_checked"]) == (240, 0, 1)
    assert importer.db.one("SELECT status FROM orientation WHERE asset_id = ?", (tilted,))["status"] == "applied"

    # Nach dem Drehen nur neue Merkmale, keine zweite Prüfung der Ausrichtung
    service.image.calls.clear()
    service.work_once()
    assert service.image.calls == [(tilted, ())]
    assert service.status()["review"] == 0


def test_orientation_automatic_with_face_and_undo(settings, importer, editor, make_jpeg, tmp_path):
    place_models(settings.data / "models" / "vision")
    # Gesichter je Korrektur 0/90/180/270°: nur in der 90°-Lage ein sicheres Gesicht
    faces = FakeFaces(FakeEngine([0.0, 0.85, 0.0, 0.2]))
    service = VisionService(settings, importer.db, importer, editor, faces, image_models=FakeImage(),
                            text_models=FakeText())
    service.prepare()
    asset = imported(importer, make_jpeg, tmp_path, "schief.jpg")
    service.image.needs = {asset: 90}
    service.work_once()

    assert service.orientation_of(asset) == {"degrees": 90, "status": "auto"}
    assert importer.db.one("SELECT width FROM assets WHERE id = ?", (asset,))["width"] == 240
    assert [r["id"] for r in service.review()] == [asset]

    service.decide(asset, accept=False)  # rückgängig
    assert importer.db.one("SELECT width FROM assets WHERE id = ?", (asset,))["width"] == 320
    assert importer.db.one("SELECT status FROM orientation WHERE asset_id = ?", (asset,))["status"] == "undone"
    service.decide(asset, accept=False)  # schon entschieden: nichts mehr drehen
    assert importer.db.one("SELECT width FROM assets WHERE id = ?", (asset,))["width"] == 320


def test_manual_rotation_settles_suggestion(service, importer, editor, make_jpeg, tmp_path):
    asset = imported(importer, make_jpeg, tmp_path, "schief.jpg")
    service.image.needs = {asset: 270}
    service.work_once()
    editor.rotate(asset, 270)
    assert importer.db.one("SELECT status FROM orientation WHERE asset_id = ?", (asset,))["status"] == "manual"
    service.decide(asset, accept=True)
    assert importer.db.one("SELECT width FROM assets WHERE id = ?", (asset,))["width"] == 240  # nur einmal gedreht


def test_search_and_retag_after_vocabulary_change(service, importer, make_jpeg, tmp_path, monkeypatch):
    dog = imported(importer, make_jpeg, tmp_path, "hund.jpg")
    other = imported(importer, make_jpeg, tmp_path, "anderes.jpg")
    service.image.vectors = {dog: text_vector("Hund am Strand")}
    service.work_once()
    assert service.search("  Hund   am Strand ") == [dog]
    assert service.search("Hund am Strand") == [dog] and service.text.calls == 2  # Suchtext aus dem Zwischenspeicher
    assert other not in service.search("etwas ganz anderes")

    # Neue Begriffsliste: Vorschläge aus den gespeicherten Merkmalen, ohne die Fotos neu zu lesen
    service.image.calls.clear()
    monkeypatch.setitem(vocab.VOCAB, "Hund am Strand", ["Hund am Strand"])
    service._load_vocab()
    service._retag_if_changed()
    assert [s["name"] for s in service.suggestions(dog)] == ["Hund am Strand"]
    assert service.image.calls == []


# ── API ────────────────────────────────────────────────────────────
@pytest.fixture
def client(settings, monkeypatch):
    monkeypatch.setattr(VisionService, "start", lambda self: None)  # keine Downloads, kein Hintergrund
    enabled = dataclasses.replace(settings, image_recognition=True)
    place_models(enabled.data / "models" / "vision")
    app = create_app(enabled)
    vision = app.state.ctx.vision
    vision.image, vision.text = FakeImage(), FakeText()
    with TestClient(app) as c:
        yield c


def upload(client, make_jpeg, tmp_path, name) -> int:
    photo = make_jpeg(tmp_path / "quelle" / name)
    return client.put("/api/upload", params={"name": name}, content=photo.read_bytes()).json()["asset_id"]


def test_api_search_suggestions_and_review(client, make_jpeg, tmp_path):
    vision = client.app.state.ctx.vision
    assert client.get("/api/assets", params={"ai": "Hund"}).status_code == 503  # noch nicht bereit
    vision.prepare()
    vision.image.default = vision._vocab[2][0]
    dog = upload(client, make_jpeg, tmp_path, "hund.jpg")
    tilted = upload(client, make_jpeg, tmp_path, "schief.jpg")
    vision.image.vectors = {dog: tag_vector(vision, "Hund") * 0.8 + text_vector("mein Hund") * 0.6}
    vision.image.needs = {tilted: 180}
    vision.work_once()

    ids = lambda **params: [i[0] for i in client.get("/api/assets", params=params).json()["items"]]  # noqa: E731
    assert ids(ai="mein Hund") == [dog]
    assert client.get("/api/geo", params={"ai": "mein Hund"}).json()["items"] == []  # ohne Ort
    assert ids(auto=["Hund"]) == [dog]
    assert client.get("/api/labels").json()["auto"] == [{"name": "Hund", "count": 1}]
    state = client.get("/api/state").json()["vision"]
    assert (state["search"], state["done"], state["total"], state["review"]) == (True, 2, 2, 1)

    detail = client.get(f"/api/assets/{dog}").json()
    assert [s["name"] for s in detail["suggestions"]] == ["Hund"] and detail["orientation"] is None
    assert "vision_scanned" not in detail
    assert client.get(f"/api/assets/{tilted}").json()["orientation"] == {"degrees": 180, "status": "suggested"}

    # Übernehmen über die normale Mehrfachauswahl: Schlagwort in die Datei, Vorschlag erledigt
    client.post("/api/batch", json={"ids": ids(auto=["Hund"]), "action": "tags", "add": ["Hund"]})
    wait_for_tasks(client)
    assert client.get(f"/api/assets/{dog}").json()["tags"] == ["Hund"]
    assert ids(auto=["Hund"]) == []

    review = client.get("/api/vision/review").json()["items"]
    assert [(r["id"], r["degrees"], r["status"]) for r in review] == [(tilted, 180, "suggested")]
    assert client.post("/api/vision/review", json={"ids": [tilted], "accept": False}).json()["total"] == 1
    wait_for_tasks(client)
    assert client.get("/api/vision/review").json()["items"] == []
    assert client.post("/api/vision/suggestions/dismiss", json={"name": "Hund", "ids": []}).status_code == 422


def wait_for_tasks(client):
    import time

    for _ in range(400):
        if not any(t["running"] for t in client.get("/api/tasks").json()):
            return
        time.sleep(0.05)
    raise AssertionError("Aufgabe hängt")


def test_search_disabled(settings):
    with TestClient(create_app(settings)) as c:  # image_recognition=False
        assert c.get("/api/assets", params={"ai": "Hund"}).status_code == 503
        assert c.get("/api/state").json()["vision"]["enabled"] is False
        assert c.get("/api/labels").json()["auto"] == []


# ── Echte Modelle im eigenen Prozess ───────────────────────────────
@pytest.mark.skipif(not (REAL_MODELS and (REAL_MODELS / "clip-visual.onnx").is_file()), reason="Modelle fehlen")
def test_real_models_in_worker_process(tmp_path, make_jpeg):
    photo = make_jpeg(tmp_path / "bild.jpg", width=400, height=300)
    image = ModelProcess("image", REAL_MODELS, 2, idle=60)
    text = ModelProcess("text", REAL_MODELS, 2, idle=60)
    try:
        result = image.call("image", str(photo), [0, 90], True)
        assert result["orientation"].shape == (2, 4) and np.allclose(result["orientation"].sum(axis=1), 1, atol=1e-4)
        assert result["embedding"].shape == (512,) and abs(np.linalg.norm(result["embedding"]) - 1) < 1e-4
        vectors = text.call("text", ["ein Hund", "ein Foto"])
        assert vectors.shape == (2, 512)
        with pytest.raises(ModelError):
            image.call("image", str(tmp_path / "fehlt.jpg"), [0], True)
        assert image.call("ping") == "pong"  # läuft nach dem Fehler weiter
    finally:
        image.close()
        text.close()
    assert not image.running and not text.running
