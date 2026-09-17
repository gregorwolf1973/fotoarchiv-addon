"""Gesichter finden (SCRFD) und als Merkmalsvektor beschreiben (ArcFace).

Modelle: InsightFace "buffalo_l" (det_10g.onnx, w600k_r50.onnx). Lizenz der Modelle: nur
nicht-kommerzielle Nutzung. Sie werden beim ersten Start von der offiziellen Quelle geladen
und über SHA-256 geprüft.
"""

import hashlib
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

import numpy as np

log = logging.getLogger(__name__)

MODEL_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
MODELS = {
    "det_10g.onnx": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
    "w600k_r50.onnx": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
}

DETECT_SIZE = 640
DETECT_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4
# Zielpunkte (Augen, Nase, Mundwinkel) für das 112×112-Bild, das ArcFace erwartet
ARCFACE_POINTS = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)


@dataclass
class Face:
    box: np.ndarray        # x1, y1, x2, y2 in Pixeln des Eingangsbildes
    score: float
    landmarks: np.ndarray  # 5 × 2
    embedding: np.ndarray | None = None  # 512 Werte, Länge 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def models_ready(folder: Path) -> bool:
    return (folder / ".geprueft").is_file() and all((folder / name).is_file() for name in MODELS)


def ensure_models(folder: Path, progress: Callable[[int, int], None] | None = None):
    """Modelle herunterladen, auspacken und prüfen (nur beim ersten Mal)."""
    if models_ready(folder):
        return
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / "buffalo_l.zip.part"
    request = Request(MODEL_URL, headers={"User-Agent": "Fotoarchiv-HomeAssistant-Addon"})
    with urlopen(request, timeout=60) as response, open(archive, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    try:
        with zipfile.ZipFile(archive) as zf:
            for name, expected in MODELS.items():
                member = next(m for m in zf.namelist() if m.rsplit("/", 1)[-1] == name)
                target = folder / name
                with zf.open(member) as src, open(target, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                if _sha256(target) != expected:
                    target.unlink(missing_ok=True)
                    raise RuntimeError(f"Prüfsumme von {name} stimmt nicht – Download beschädigt oder verändert")
    finally:
        archive.unlink(missing_ok=True)
    (folder / ".geprueft").write_text("ok")


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Ähnlichkeitstransformation (Umeyama) als 2×3-Matrix: Drehung, Skalierung, Verschiebung."""
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_c, dst_c = src - src_mean, dst - dst_mean
    covariance = dst_c.T @ src_c / len(src)
    signs = np.ones(2)
    if np.linalg.det(covariance) < 0:
        signs[1] = -1
    u, s, vt = np.linalg.svd(covariance)
    rotation = u @ np.diag(signs) @ vt
    scale = (s * signs).sum() / (src_c**2).sum() * len(src)
    translation = dst_mean - scale * rotation @ src_mean
    return np.hstack([scale * rotation, translation[:, None]]).astype(np.float32)


def _nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep = []
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[1:][iou <= threshold]
    return keep


class FaceEngine:
    def __init__(self, folder: Path, threads: int = 2):
        import cv2  # erst hier laden: ohne Gesichtserkennung wird OpenCV nicht gebraucht
        import onnxruntime as ort

        self.cv2 = cv2
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads  # Home Assistant soll auf dem Pi flüssig bleiben
        options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
        self.detector = ort.InferenceSession(str(folder / "det_10g.onnx"), options, providers=providers)
        self.recognizer = ort.InferenceSession(str(folder / "w600k_r50.onnx"), options, providers=providers)
        self._det_input = self.detector.get_inputs()[0].name
        self._rec_input = self.recognizer.get_inputs()[0].name

    def detect(self, image: np.ndarray) -> list[Face]:
        """image: RGB, uint8, H × W × 3."""
        cv2 = self.cv2
        height, width = image.shape[:2]
        scale = DETECT_SIZE / max(height, width)
        resized = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))))
        canvas = np.zeros((DETECT_SIZE, DETECT_SIZE, 3), dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1 / 128, (DETECT_SIZE, DETECT_SIZE), (127.5, 127.5, 127.5), swapRB=False)
        outputs = self.detector.run(None, {self._det_input: blob})

        # Ausgaben nach Art sortieren: Wahrscheinlichkeit (1), Rahmen (4), Merkmalspunkte (10) – je 3 Stufen
        by_kind = {1: [], 4: [], 10: []}
        for out in outputs:
            by_kind[out.shape[-1]].append(out.reshape(-1, out.shape[-1]))
        for kind in by_kind:
            by_kind[kind].sort(key=len, reverse=True)  # Schrittweite 8 hat die meisten Anker

        all_boxes, all_scores, all_points = [], [], []
        for level, stride in enumerate((8, 16, 32)):
            scores = by_kind[1][level][:, 0]
            cells = DETECT_SIZE // stride
            anchors_per_cell = len(scores) // (cells * cells)
            centers = np.stack(np.mgrid[:cells, :cells][::-1], axis=-1).reshape(-1, 2).astype(np.float32) * stride
            centers = np.repeat(centers, anchors_per_cell, axis=0)
            hits = np.where(scores >= DETECT_THRESHOLD)[0]
            if not hits.size:
                continue
            distances = by_kind[4][level][hits] * stride
            c = centers[hits]
            all_boxes.append(np.hstack([c - distances[:, :2], c + distances[:, 2:]]))
            points = by_kind[10][level][hits].reshape(-1, 5, 2) * stride
            all_points.append(points + c[:, None, :])
            all_scores.append(scores[hits])
        if not all_boxes:
            return []
        boxes = np.vstack(all_boxes) / scale
        points = np.vstack(all_points) / scale
        scores = np.concatenate(all_scores)
        return [Face(boxes[i], float(scores[i]), points[i]) for i in _nms(boxes, scores, NMS_THRESHOLD)]

    def embed(self, image: np.ndarray, face: Face) -> np.ndarray:
        cv2 = self.cv2
        matrix = similarity_transform(face.landmarks.astype(np.float32), ARCFACE_POINTS)
        aligned = cv2.warpAffine(image, matrix, (112, 112), borderValue=0)
        blob = cv2.dnn.blobFromImage(aligned, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=False)
        vector = self.recognizer.run(None, {self._rec_input: blob})[0][0].astype(np.float32)
        return vector / (np.linalg.norm(vector) + 1e-9)

    def analyze(self, image: np.ndarray, min_size: int = 36, min_score: float = 0.6) -> list[Face]:
        faces = []
        for face in self.detect(image):
            w, h = face.box[2] - face.box[0], face.box[3] - face.box[1]
            if min(w, h) < min_size or face.score < min_score:
                continue  # zu klein oder unsicher: der Merkmalsvektor wäre unzuverlässig
            face.embedding = self.embed(image, face)
            faces.append(face)
        return faces
