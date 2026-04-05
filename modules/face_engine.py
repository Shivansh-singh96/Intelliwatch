"""
face_engine.py  —  Centroid-based ArcFace recognition
======================================================
Backend : insightface (ONNX)
Model   : buffalo_l (RetinaFace + ArcFace)
Vectors : 512-dimensional, L2-normalised

KEY FIX: insightface app is initialised INSIDE load() so is_loaded=True
only when the model is fully ready — camera thread no longer races it.
"""

import os
import sys
import logging
import pickle
from collections import defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.config import (
    ENCODE_FILE,
    RECOGNITION_THRESHOLD, GROUP_RECOGNITION_THRESHOLD, KNN_MARGIN,
)

logger = logging.getLogger(__name__)

_EXPECTED_DIM = 512
_MIN_FACE_PX  = 60   # skip faces smaller than this (too blurry for ArcFace)


class MatchResult:
    __slots__ = ("name", "score", "location")

    def __init__(self, name, score, location):
        self.name     = name
        self.score    = score
        self.location = location

    @property
    def is_known(self):
        return self.name != "Unknown"

    def __repr__(self):
        return f"MatchResult({self.name!r}, {self.score:.3f})"


class FaceEngine:
    def __init__(self):
        self._raw_vecs:  list       = []
        self._raw_names: list       = []
        self._centroids: np.ndarray = np.empty((0, _EXPECTED_DIM), dtype=np.float32)
        self._classes:   list       = []
        self._loaded                = False
        self._app                   = None   # insightface FaceAnalysis

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, path: str = ENCODE_FILE) -> bool:
        """
        Load encodefile AND initialise the insightface model.
        is_loaded=True only after BOTH steps succeed.
        """
        # ── Step 1: init insightface app ──────────────────────────────────
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis
                app = FaceAnalysis(
                    name      = "buffalo_l",
                    providers = ["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=0, det_size=(640, 640))
                self._app = app
                print("FaceEngine: insightface buffalo_l ready (ONNX)")
                logger.info("insightface buffalo_l loaded")
            except Exception as exc:
                print(f"FaceEngine ERROR loading model: {exc}")
                logger.error("insightface load failed: %s", exc)
                return False

        # ── Step 2: load encodefile ───────────────────────────────────────
        if not os.path.exists(path):
            print(f"FaceEngine: Encodefile not found: {path}")
            print("  → Run encode_students.py to generate it.")
            self._loaded = True   # app is ready, just no students yet
            return True

        try:
            with open(path, "rb") as fh:
                data = pickle.load(fh)
            if not (isinstance(data, (list, tuple)) and len(data) == 2):
                raise ValueError("Corrupt pickle format")
            vecs, names = data
            arr = np.array(vecs, dtype=np.float32)

            # Dimension check — old dlib/face_recognition files are 128-dim
            if arr.ndim == 2 and arr.shape[1] != _EXPECTED_DIM:
                print(
                    f"\nFaceEngine WARNING: Encodefile has {arr.shape[1]}-dim vectors "
                    f"but ArcFace needs {_EXPECTED_DIM}-dim.\n"
                    f"  → DELETE {path} and re-run encode_students.py\n"
                )
                logger.warning("Stale encodefile — wrong embedding dimension")
                self._loaded = True   # app ready, but no usable students
                return True

            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1
            arr /= norms
            self._raw_vecs  = list(arr)
            self._raw_names = list(names)
            self._build_centroids()
            self._loaded = True

            print(f"FaceEngine: {len(self._classes)} student(s) loaded")
            for i, nm in enumerate(self._classes):
                cnt = self._raw_names.count(nm)
                print(f"  {nm:<30} {cnt} sample(s)  "
                      f"centroid_norm={np.linalg.norm(self._centroids[i]):.4f}")
            return True

        except Exception as exc:
            logger.error("Load failed: %s", exc)
            print(f"FaceEngine load failed: {exc}")
            return False

    def reload(self) -> bool:
        self._loaded = False
        return self.load()

    def save(self, path: str = ENCODE_FILE) -> bool:
        try:
            with open(path, "wb") as fh:
                pickle.dump(
                    (np.array(self._raw_vecs, dtype=np.float32), self._raw_names), fh)
            return True
        except Exception as exc:
            logger.error("Save: %s", exc)
            return False

    @property
    def student_names(self) -> list:
        return list(self._classes)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ── Identification ────────────────────────────────────────────────────────

    def identify_frame(self, frame_bgr: np.ndarray) -> list:
        """
        Use the FULL frame (640×480).  Do NOT pre-downscale — small faces
        lose too much quality for ArcFace alignment.
        """
        if not self._loaded or self._app is None:
            return []
        try:
            faces = self._app.get(frame_bgr)
        except Exception as exc:
            logger.warning("identify_frame error: %s", exc)
            return []

        results = []
        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1

            # Skip tiny faces — ArcFace alignment fails below ~60px
            if w < _MIN_FACE_PX or h < _MIN_FACE_PX:
                continue

            vec = self._norm(face.embedding)
            if vec is None:
                continue

            if not self._classes:
                # App loaded but no students encoded yet
                loc = (y1, x2, y2, x1)
                results.append(MatchResult("Unknown", 0.0, loc))
                continue

            name, score = self._cosine_match(vec, group=False)
            loc = (y1, x2, y2, x1)
            results.append(MatchResult(name, score, loc))
        return results

    def identify_frame_group(self, frame_bgr: np.ndarray) -> list:
        """
        Same as identify_frame but uses GROUP_RECOGNITION_THRESHOLD (lower bar).
        Used for group/class photos where faces may be smaller or at an angle.
        """
        if not self._loaded or self._app is None:
            return []
        try:
            faces = self._app.get(frame_bgr)
        except Exception as exc:
            logger.warning("identify_frame_group error: %s", exc)
            return []

        results = []
        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1
            # Slightly smaller minimum for group photos (faces are farther away)
            if w < 40 or h < 40:
                continue
            vec = self._norm(face.embedding)
            if vec is None:
                continue
            if not self._classes:
                results.append(MatchResult("Unknown", 0.0, (y1, x2, y2, x1)))
                continue
            name, score = self._cosine_match(vec, group=True)   # group=True → lower threshold
            loc = (y1, x2, y2, x1)
            results.append(MatchResult(name, score, loc))
        return results

    def identify_image(self, image_bgr: np.ndarray) -> list:
        return self.identify_frame(image_bgr)

    # ── Registration helpers ──────────────────────────────────────────────────

    def add_encoding(self, name: str, embedding: np.ndarray):
        self._raw_vecs.append(embedding)
        self._raw_names.append(name)
        self._build_centroids()

    def add_encodings_bulk(self, name: str, embeddings: list):
        for vec in embeddings:
            self._raw_vecs.append(vec)
            self._raw_names.append(name)
        self._build_centroids()

    def embed_image(self, img_bgr: np.ndarray):
        """Return L2-normalised 512-dim vector or None."""
        if self._app is None:
            return None
        try:
            faces = self._app.get(img_bgr)
            if not faces:
                return None
            face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
            return self._norm(face.embedding)
        except Exception as exc:
            logger.warning("embed_image: %s", exc)
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_centroids(self):
        groups = defaultdict(list)
        for v, n in zip(self._raw_vecs, self._raw_names):
            groups[n].append(v)
        self._classes = sorted(groups.keys())
        centroids = []
        for nm in self._classes:
            c  = np.mean(groups[nm], axis=0).astype(np.float32)
            c /= max(np.linalg.norm(c), 1e-8)
            centroids.append(c)
        self._centroids = np.array(centroids, dtype=np.float32)

    def _cosine_match(self, vec: np.ndarray, group: bool = False) -> tuple:
        thresh   = GROUP_RECOGNITION_THRESHOLD if group else RECOGNITION_THRESHOLD
        sims     = self._centroids @ vec
        order    = np.argsort(sims)[::-1]
        best     = int(order[0])
        best_s   = float(sims[best])
        second_s = float(sims[order[1]]) if len(order) > 1 else 0.0
        margin   = best_s - second_s

        if best_s >= thresh and margin >= KNN_MARGIN:
            return self._classes[best], round(best_s, 4)
        return "Unknown", round(best_s, 4)

    @staticmethod
    def _norm(vec):
        if vec is None:
            return None
        v = np.array(vec, dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 1e-8 else None