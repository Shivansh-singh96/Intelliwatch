"""
encode_students.py
------------------
Run ONCE before main.py, and again whenever you add new student photos.

Backend : insightface (ONNX) — NO TensorFlow, NO face_recognition needed
Model   : buffalo_l (RetinaFace detector + ArcFace embedder)
Vectors : 512-dimensional, L2-normalised

Usage
-----
    cd scis_pyqt6
    python encode_students.py
"""

import os
import sys
import pickle
import logging

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config import (
    STUDENTS_DIR, DEBUG_DIR, ENCODE_FILE, LOG_FILE,
    BLUR_THRESHOLD, BRIGHTNESS_MIN, BRIGHTNESS_MAX,
)

logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
os.makedirs(DEBUG_DIR, exist_ok=True)

MIN_IMAGES = 3


# ── Load insightface once ─────────────────────────────────────────────────────

def load_model():
    print("  Loading insightface buffalo_l (ONNX)...")
    try:
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(
            name      = "buffalo_l",
            providers = ["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        print("  Model ready.\n")
        return app
    except ImportError:
        print("\n  ERROR: insightface not installed.")
        print("  Run:  pip install insightface onnxruntime")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  ERROR loading model: {exc}")
        sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_quality_ok(img_bgr: np.ndarray) -> bool:
    gray       = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur_val   = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = float(np.mean(gray))
    ok = blur_val >= BLUR_THRESHOLD and BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX
    if not ok:
        print(f"      blur={blur_val:.1f}  brightness={brightness:.1f}  -> rejected")
    return ok


def embed(app, img_path: str):
    """
    Detect face and compute ArcFace embedding using insightface.
    Returns L2-normalised float32 vector or None.
    """
    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        return None
    try:
        faces = app.get(img_bgr)
        if not faces:
            return None
        # Use the largest detected face
        face = max(faces, key=lambda f: (
            (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        ))
        vec  = np.array(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-8 else None
    except Exception as exc:
        logger.error("Embed failed %s: %s", img_path, exc)
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  SCIS  --  ARCFACE STUDENT ENCODER  (insightface / ONNX)")
    print(f"  Output : {ENCODE_FILE}")
    print("=" * 62 + "\n")

    if not os.path.exists(STUDENTS_DIR):
        print(f"  ERROR: Students folder not found:\n  {STUDENTS_DIR}")
        print("\n  Create it and add one subfolder per student named by ID.")
        print("  Example:")
        print("    Students/")
        print("      0302CS221101/   <- at least 3 photos inside")
        print("      0302CS221102/")
        return

    folders = sorted([
        f for f in os.listdir(STUDENTS_DIR)
        if os.path.isdir(os.path.join(STUDENTS_DIR, f))
    ])

    if not folders:
        print(f"  ERROR: No student folders found in {STUDENTS_DIR}")
        return

    print(f"  Found {len(folders)} student folder(s)\n" + "-" * 62)

    # Load model once for all students
    app = load_model()

    all_embeddings: list = []
    all_names:      list = []
    summary:        list = []
    skipped:        list = []

    for idx, student in enumerate(folders, 1):
        print(f"\n[{idx}/{len(folders)}]  {student}")
        folder = os.path.join(STUDENTS_DIR, student)

        img_files = sorted([
            f for f in os.listdir(folder)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
        ])

        if not img_files:
            print("    WARNING: No images — skipping")
            skipped.append(f"{student} (no images)")
            continue

        student_embs: list = []
        ok_count   = 0
        skip_count = 0

        for img_file in img_files:
            img_path = os.path.join(folder, img_file)
            img_bgr  = cv2.imread(img_path)

            if img_bgr is None:
                print(f"    SKIP  {img_file}  -- could not read")
                skip_count += 1
                continue

            # Quality check
            if not is_quality_ok(img_bgr):
                print(f"    SKIP  {img_file}  -- poor quality")
                skip_count += 1
                continue

            # ArcFace embedding via insightface
            vec = embed(app, img_path)
            if vec is not None:
                student_embs.append(vec)
                ok_count += 1
                print(f"    OK    {img_file}  (dim={vec.shape[0]})")
            else:
                print(f"    FAIL  {img_file}  -- no face detected")
                skip_count += 1

        # Minimum check
        if len(student_embs) < MIN_IMAGES:
            msg = (f"{len(student_embs)}/{MIN_IMAGES} valid — "
                   f"need at least {MIN_IMAGES} clear photos")
            print(f"\n    SKIPPED  {student}  ({msg})")
            skipped.append(f"{student} ({msg})")
            continue

        all_embeddings.extend(student_embs)
        all_names.extend([student] * len(student_embs))
        summary.append((student, ok_count, skip_count))
        print(f"\n    STORED  {ok_count} embedding(s)  [{skip_count} skipped]")

    if not all_embeddings:
        print("\n  ERROR: No embeddings generated.")
        print("  Ensure each student folder has at least 3 clear, well-lit photos.")
        return

    # Save
    try:
        with open(ENCODE_FILE, "wb") as fh:
            pickle.dump(
                (np.array(all_embeddings, dtype=np.float32), all_names),
                fh,
            )
    except Exception as exc:
        print(f"\n  ERROR: Could not save {ENCODE_FILE}")
        print(f"  {exc}")
        return

    # Report
    print("\n" + "=" * 62)
    print("  ENCODING COMPLETE")
    print("=" * 62)
    print(f"  {'STUDENT':<28} {'STORED':>6}  {'SKIPPED':>7}")
    print("  " + "-" * 48)
    for name, ok, skip in summary:
        bar = "█" * min(ok, 20)
        print(f"  {name:<28} {ok:>6}  {bar:<20}  ({skip} skipped)")
    print("  " + "-" * 48)
    print(f"  Students encoded  : {len(summary)}")
    print(f"  Total vectors     : {len(all_embeddings)}")
    print(f"  Saved to          : {ENCODE_FILE}")

    if skipped:
        print(f"\n  SKIPPED ({len(skipped)}):")
        for s in skipped:
            print(f"    x  {s}")

    print("\n" + "=" * 62)
    print("  Now run:  python app/main.py")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()


# ── Reusable API (called by auth_service on approve/delete) ──────────────────

def encode_single_student(student_id: str) -> tuple[bool, str]:
    """
    Encode (or re-encode) a single student and merge into Encodefile.p.

    Returns (success: bool, message: str).
    Called automatically after admin approves a user.
    """
    folder = os.path.join(STUDENTS_DIR, student_id)
    if not os.path.isdir(folder):
        return False, f"No photo folder found: Students/{student_id}/"

    img_files = sorted([
        f for f in os.listdir(folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
    ])
    if len(img_files) < MIN_IMAGES:
        return False, f"Need at least {MIN_IMAGES} photos, found {len(img_files)}"

    try:
        app = load_model()
    except SystemExit:
        return False, "Could not load insightface model"

    new_vecs = []
    for img_file in img_files:
        vec = embed(app, os.path.join(folder, img_file))
        if vec is not None:
            new_vecs.append(vec)

    if len(new_vecs) < MIN_IMAGES:
        return False, f"Only {len(new_vecs)} valid face(s) detected — need {MIN_IMAGES}"

    # Load existing encodefile (or start fresh)
    all_vecs:  list = []
    all_names: list = []
    if os.path.exists(ENCODE_FILE):
        try:
            with open(ENCODE_FILE, "rb") as fh:
                saved_vecs, saved_names = pickle.load(fh)
            # Drop any previous encodings for this student
            for v, n in zip(saved_vecs, saved_names):
                if n != student_id:
                    all_vecs.append(v)
                    all_names.append(n)
        except Exception:
            pass  # corrupt file — start fresh

    # Append new encodings
    all_vecs.extend(new_vecs)
    all_names.extend([student_id] * len(new_vecs))

    try:
        with open(ENCODE_FILE, "wb") as fh:
            pickle.dump((np.array(all_vecs, dtype=np.float32), all_names), fh)
    except Exception as exc:
        return False, f"Could not save encodefile: {exc}"

    return True, f"Encoded {len(new_vecs)} face(s) for {student_id}"


def remove_student_from_encodefile(student_id: str) -> bool:
    """
    Remove a student's embeddings from Encodefile.p.
    Called automatically when a user is deleted or rejected.
    Returns True if file was updated, False if nothing changed.
    """
    if not os.path.exists(ENCODE_FILE):
        return False
    try:
        with open(ENCODE_FILE, "rb") as fh:
            saved_vecs, saved_names = pickle.load(fh)
        keep = [(v, n) for v, n in zip(saved_vecs, saved_names) if n != student_id]
        if len(keep) == len(saved_names):
            return False  # student wasn't in file
        if keep:
            vecs, names = zip(*keep)
            with open(ENCODE_FILE, "wb") as fh:
                pickle.dump((np.array(vecs, dtype=np.float32), list(names)), fh)
        else:
            os.remove(ENCODE_FILE)   # no students left
        return True
    except Exception as exc:
        logger.error("remove_student_from_encodefile: %s", exc)
        return False
