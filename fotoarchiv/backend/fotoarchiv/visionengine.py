"""Bilderkennung: Ausrichtung (EfficientNetV2) und Bildinhalt (CLIP, mehrsprachig).

Modelle, beim ersten Start von Hugging Face geladen (Stand fest über den Commit, Prüfung per SHA-256):
- Ausrichtung: DuarteBarbosa/deep-image-orientation-detection (MIT). Sagt, um wie viel Grad ein Foto
  im Uhrzeigersinn gedreht werden muss: Klasse 0/1/2/3 = 0/90/180/270°.
- CLIP: immich-app/XLM-Roberta-Base-ViT-B-32__laion5b_s13b_b90k (OpenCLIP, MIT). Bild und Text landen
  im selben Raum – damit Suche in normaler Sprache (auch Deutsch) und Schlagwort-Vorschläge.

Die Modelle laufen in einem eigenen Prozess (python -m fotoarchiv.visionengine). Nur so bekommt der Pi
den Speicher zurück, wenn nichts zu tun ist: onnxruntime gibt ihn im laufenden Prozess nicht frei
(gemessen: das Textmodell belegt 1,1 GB und nach dem Freigeben noch genauso viel).
"""

import hashlib
import json
import logging
import os
import pickle
import select
import struct
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

import numpy as np

log = logging.getLogger(__name__)

HF = "https://huggingface.co"
ORIENT = f"{HF}/DuarteBarbosa/deep-image-orientation-detection/resolve/9bc7687b9fd5152e220084ca23e13e7fa1daec38"
CLIP = f"{HF}/immich-app/XLM-Roberta-Base-ViT-B-32__laion5b_s13b_b90k/resolve/111f6ddca817bb6cd8343c3e3dc5ce39d9ba54b0"


@dataclass(frozen=True)
class ModelFile:
    name: str    # Dateiname im Modellordner
    url: str
    sha256: str
    size: int    # für die Fortschrittsanzeige, falls der Server keine Länge nennt


FILES = {
    "image": [
        ModelFile("orientation.onnx", f"{ORIENT}/orientation_model_v2_0.9882.onnx",
                  "cffe911c1dff47fbfbbd90110aaab9c07134645c460d35b3ae8832079bea91ba", 80_578_424),
        ModelFile("clip-visual.onnx", f"{CLIP}/visual/model.onnx",
                  "07a431b489757821d9e7460d5e98ecc03aa682f47ffb364b99879e1d6613a54b", 351_613_724),
    ],
    "text": [
        ModelFile("clip-textual.onnx", f"{CLIP}/textual/model.onnx",
                  "ca4a815f14666700479ced66ee21cf7ab8878715ba71d144f18bc9571ef152cd", 1_113_269_728),
        ModelFile("clip-tokenizer.json", f"{CLIP}/textual/tokenizer.json",
                  "3a56def25aa40facc030ea8b0b87f3688e4b3c39eb8b45d5702b3a1300fe2a20", 17_082_734),
    ],
}

DEGREES = (0, 90, 180, 270)
ORIENT_RESIZE, ORIENT_CROP = 416, 384
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], np.float32)
CLIP_SIZE = 224
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)
TEXT_LENGTH = 77


class ModelError(Exception):
    """Die Anfrage ging schief (z. B. Bild nicht lesbar); der Arbeitsprozess läuft weiter."""


class ModelCrash(ModelError):
    """Der Arbeitsprozess ist abgestürzt, hängt oder startet nicht – später noch einmal versuchen."""


# ── Herunterladen ──────────────────────────────────────────────────
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def missing(folder: Path, kinds=("image", "text")) -> list[ModelFile]:
    """Fehlende Dateien. Eine Datei liegt erst unter ihrem Namen, wenn die Prüfsumme gestimmt hat."""
    return [f for kind in kinds for f in FILES[kind] if not (folder / f.name).is_file()]


def ensure_models(folder: Path, kinds=("image", "text"), progress: Callable[[int, int], None] | None = None):
    todo = missing(folder, kinds)
    if not todo:
        return
    folder.mkdir(parents=True, exist_ok=True)
    total = sum(f.size for f in todo)
    done = 0
    for model in todo:
        part = folder / f"{model.name}.part"
        request = Request(model.url, headers={"User-Agent": "Fotoarchiv-HomeAssistant-Addon"})
        try:
            with urlopen(request, timeout=60) as response, open(part, "wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, max(total, done))
            if _sha256(part) != model.sha256:
                raise RuntimeError(f"Prüfsumme von {model.name} stimmt nicht – Download beschädigt oder verändert")
            part.rename(folder / model.name)
        finally:
            part.unlink(missing_ok=True)


# ── Text in Token-Nummern (XLM-RoBERTa, SentencePiece-Unigram) ────
class Tokenizer:
    """Liest tokenizer.json und zerlegt Text wie die Bibliothek "tokenizers" (dieselben Nummern,
    geprüft in den Tests) – ohne deren Abhängigkeiten. Normalisierung: NFKC statt der
    vorkompilierten SentencePiece-Tabelle; für normale Suchtexte ist das gleichwertig."""

    BOS, PAD, EOS, UNK = 0, 1, 2, 3
    UNK_PENALTY = 10.0

    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        special = {t["content"] for t in data.get("added_tokens", [])}
        vocab = data["model"]["vocab"]
        self.pieces = {piece: (index, score) for index, (piece, score) in enumerate(vocab) if piece not in special}
        self.max_length = max(len(piece) for piece in self.pieces)
        self.unk_score = min(score for _, score in self.pieces.values()) - self.UNK_PENALTY

    def _segment(self, word: str) -> list[int]:
        """Zerlegung mit der höchsten Gesamtwahrscheinlichkeit (Viterbi)."""
        size = len(word)
        best = [(-np.inf, 0, self.UNK)] * (size + 1)
        best[0] = (0.0, 0, self.UNK)
        for end in range(1, size + 1):
            for start in range(max(0, end - self.max_length), end):
                if best[start][0] == -np.inf:
                    continue
                entry = self.pieces.get(word[start:end])
                if entry is None and end - start > 1:
                    continue
                piece_id, score = entry if entry else (self.UNK, self.unk_score)
                total = best[start][0] + score
                if total > best[end][0]:
                    best[end] = (total, start, piece_id)
        ids, end = [], size
        while end > 0:
            _, start, piece_id = best[end]
            if not (piece_id == self.UNK and ids and ids[-1] == self.UNK):  # unbekannte Zeichen zusammenfassen
                ids.append(piece_id)
            end = start
        return ids[::-1]

    def encode(self, text: str, length: int = TEXT_LENGTH) -> list[int]:
        ids = []
        for word in unicodedata.normalize("NFKC", text).split():
            ids += self._segment("▁" + word)
        ids = [self.BOS] + ids[: length - 2] + [self.EOS]
        return ids + [self.PAD] * (length - len(ids))


# ── Bilder vorbereiten ─────────────────────────────────────────────
def load_image(path: Path):
    """Vorschaubild (schon nach EXIF gedreht) als 8-Bit-RGB."""
    import pyvips

    image = pyvips.Image.new_from_file(str(path))
    if image.interpretation not in ("srgb", "b-w"):
        image = image.colourspace("srgb")
    if image.bands in (2, 4):
        image = image[: image.bands - 1]
    if image.bands == 1:
        image = image.bandjoin([image, image])
    return image.cast("uchar")


def rotated(image, degrees: int):
    """Im Uhrzeigersinn drehen."""
    return {0: image, 90: image.rot90(), 180: image.rot180(), 270: image.rot270()}[degrees % 360]


def _array(image, size: int) -> np.ndarray:
    return np.ndarray(buffer=image.write_to_memory(), dtype=np.uint8, shape=(size, size, 3)).astype(np.float32) / 255


def orientation_input(image) -> np.ndarray:
    """Wie beim Training (torchvision): auf 416 × 416 stauchen, Mitte 384 × 384, ImageNet-Normierung."""
    image = image.resize(ORIENT_RESIZE / image.width, vscale=ORIENT_RESIZE / image.height, kernel="linear")
    margin = (ORIENT_RESIZE - ORIENT_CROP) // 2
    pixels = _array(image.crop(margin, margin, ORIENT_CROP, ORIENT_CROP), ORIENT_CROP)
    return ((pixels - IMAGENET_MEAN) / IMAGENET_STD).transpose(2, 0, 1)


def clip_input(image) -> np.ndarray:
    """Wie OpenCLIP: kürzere Seite auf 224 (bikubisch), Mitte 224 × 224, CLIP-Normierung."""
    image = image.resize(CLIP_SIZE / min(image.width, image.height), kernel="cubic")
    left, top = (image.width - CLIP_SIZE) // 2, (image.height - CLIP_SIZE) // 2
    pixels = _array(image.crop(left, top, CLIP_SIZE, CLIP_SIZE), CLIP_SIZE)
    return ((pixels - CLIP_MEAN) / CLIP_STD).transpose(2, 0, 1)


def _normalize(vector: np.ndarray) -> np.ndarray:
    return (vector / (np.linalg.norm(vector, axis=-1, keepdims=True) + 1e-9)).astype(np.float32)


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - logits.max(axis=-1, keepdims=True))
    return exp / exp.sum(axis=-1, keepdims=True)


# ── Im Arbeitsprozess ──────────────────────────────────────────────
class Models:
    """kind "image": Ausrichtung und Bildmerkmale; kind "text": Textmerkmale."""

    def __init__(self, folder: Path, kind: str, threads: int):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]

        def session(name):
            return ort.InferenceSession(str(folder / name), options, providers=providers)

        if kind == "image":
            self.orientation = session("orientation.onnx")
            self.visual = session("clip-visual.onnx")
        elif kind == "text":
            self.textual = session("clip-textual.onnx")
            self.tokenizer = Tokenizer(folder / "clip-tokenizer.json")
        else:
            raise ValueError(kind)

    def handle(self, request: tuple):
        operation = request[0]
        if operation == "image":
            _, path, rotations, embed = request
            image = load_image(Path(path))
            result = {"orientation": None, "embedding": None}
            if rotations:
                batch = np.stack([orientation_input(rotated(image, degrees)) for degrees in rotations])
                logits = self.orientation.run(None, {"input": batch})[0]
                result["orientation"] = _softmax(logits.astype(np.float32))
            if embed:
                vector = self.visual.run(None, {"image": clip_input(image)[None]})[0][0]
                result["embedding"] = _normalize(vector)
            return result
        if operation == "text":
            vectors = [self.textual.run(None, {"text": np.array([self.tokenizer.encode(t)], dtype=np.int32)})[0][0]
                       for t in request[1]]
            return _normalize(np.stack(vectors))
        if operation == "ping":
            return "pong"
        raise ValueError(f"Unbekannte Anfrage: {operation}")


def _write_frame(stream, value):
    data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack(">Q", len(data)) + data)
    stream.flush()


def _read_exact(stream, size: int, deadline: float | None) -> bytes:
    data = bytearray()
    while len(data) < size:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([stream], [], [], remaining)[0]:
                raise TimeoutError("Bilderkennung antwortet nicht")
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError("Bilderkennung beendet")
        data += chunk
    return bytes(data)


def _read_frame(stream, timeout: float | None = None):
    deadline = time.monotonic() + timeout if timeout else None
    (size,) = struct.unpack(">Q", _read_exact(stream, 8, deadline))
    return pickle.loads(_read_exact(stream, size, deadline))


def serve(kind: str, folder: Path, threads: int):
    """Hauptschleife des Arbeitsprozesses: Anfragen über stdin, Antworten über stdout."""
    answers = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)  # was sonst auf stdout landete, darf das Protokoll nicht stören
    try:
        os.nice(10)  # Home Assistant geht vor
    except OSError:
        pass
    requests = sys.stdin.buffer
    try:
        models = Models(folder, kind, threads)
    except Exception as exc:
        _write_frame(answers, ("error", f"Modelle nicht ladbar: {exc}"))
        return
    _write_frame(answers, ("ok", "ready"))
    while True:
        try:
            request = _read_frame(requests)
        except EOFError:
            return
        try:
            _write_frame(answers, ("ok", models.handle(request)))
        except Exception as exc:
            log.exception("Anfrage %s fehlgeschlagen", request[0])
            _write_frame(answers, ("error", f"{type(exc).__name__}: {exc}"))


# ── Im Hauptprozess ────────────────────────────────────────────────
class ModelProcess:
    """Startet den Arbeitsprozess bei Bedarf und beendet ihn nach `idle` Sekunden ohne Anfrage."""

    def __init__(self, kind: str, folder: Path, threads: int, *, idle: float = 300, timeout: float = 300):
        self.kind = kind
        self.folder = folder
        self.threads = threads
        self.idle = idle
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._last = 0.0
        self._closed = threading.Event()
        self._reaper: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def call(self, *request):
        with self._lock:
            if self._closed.is_set():
                raise ModelCrash("Bilderkennung wird beendet")
            if not self.running:
                self._start()
            try:
                _write_frame(self._proc.stdin, request)
                status, value = _read_frame(self._proc.stdout, self.timeout)
            except (OSError, EOFError, TimeoutError, pickle.UnpicklingError) as exc:
                self._kill()
                raise ModelCrash(str(exc)) from exc
            finally:
                self._last = time.monotonic()
        if status != "ok":
            raise ModelError(value)
        return value

    def _start(self):
        package_root = str(Path(__file__).resolve().parent.parent)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (package_root, env.get("PYTHONPATH")) if p)
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "fotoarchiv.visionengine", self.kind, str(self.folder), str(self.threads)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0, cwd=package_root, env=env,
        )
        try:
            status, value = _read_frame(self._proc.stdout, self.timeout)
        except (OSError, EOFError, TimeoutError) as exc:
            self._kill()
            raise ModelCrash(f"Bilderkennung startet nicht: {exc}") from exc
        if status != "ok":
            self._kill()
            raise ModelCrash(value)
        log.info("Bilderkennung (%s) gestartet", "Text" if self.kind == "text" else "Bilder")
        if self._reaper is None:
            self._reaper = threading.Thread(target=self._reap, daemon=True, name=f"modelle-{self.kind}")
            self._reaper.start()

    def _reap(self):
        while not self._closed.wait(min(30.0, self.idle / 2)):
            if self.running and time.monotonic() - self._last > self.idle and self._lock.acquire(blocking=False):
                try:
                    self._stop_process()
                    log.info("Bilderkennung (%s) beendet – Speicher freigegeben",
                             "Text" if self.kind == "text" else "Bilder")
                finally:
                    self._lock.release()

    def _stop_process(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()  # Ende der Eingabe: der Prozess beendet sich selbst
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()
        if proc.stdout:
            proc.stdout.close()

    def _kill(self):
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.kill()
            proc.wait()
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    stream.close()

    def release(self):
        """Prozess jetzt beenden (Speicher frei); die nächste Anfrage startet ihn neu."""
        with self._lock:
            self._stop_process()

    def close(self):
        self._closed.set()
        with self._lock:
            self._stop_process()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pyvips").setLevel(logging.WARNING)
    serve(sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]))
