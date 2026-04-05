"""
ui/register_dialog.py
──────────────────────
RegisterDialog — new user registration with live face capture.

Step 1: Fill in details (name, email, dept, login ID, password)
Step 2: Capture 5 face photos with quality check (blur + brightness)
Step 3: Photos saved to Students/<login_id>/ for encode_students.py
"""

import logging
import os
import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QComboBox, QScrollArea, QWidget,
    QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui  import QImage, QPixmap

from services.auth_service import get_auth, AuthError
import modules.config as cfg

# Lightweight face detector for registration quality check (Haar cascade, no GPU needed)
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

def _detect_face(img_bgr):
    """Return True if at least one face detected. Fast Haar cascade check."""
    gray   = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.equalizeHist(gray)
    faces = _face_cascade.detectMultiScale(
        gray_eq, scaleFactor=1.1, minNeighbors=3, minSize=(50, 50)
    )
    if len(faces) == 0:
        faces = _face_cascade.detectMultiScale(
            gray_eq, scaleFactor=1.2, minNeighbors=2, minSize=(40, 40)
        )
    return len(faces) > 0, faces

logger = logging.getLogger(__name__)

_DEPARTMENTS = [
    "Computer Science", "Electronics & Communication",
    "Mechanical Engineering", "Civil Engineering",
    "Information Technology", "Management", "Administration", "Security", "Other",
]

_REQUIRED_PHOTOS = 15


def _blur_score(img) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _brightness(img) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


class RegisterDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auth = get_auth()
        self.registered_login_id: str | None = None

        # Face capture state
        self._cap             = None
        self._cam_timer       = QTimer(self)
        self._cam_timer.timeout.connect(self._cam_tick)
        self._captured_photos: list[np.ndarray] = []
        self._save_dir        = ""
        self._step            = 1   # 1=details, 2=face capture

        self.setWindowTitle("Request System Access")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(680)
        self.setStyleSheet("QDialog { background-color: #0A0E17; border: 1px solid #1E3A5F; }")
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        # Header
        header = QFrame(); header.setFixedHeight(56)
        header.setStyleSheet("background-color: #060A10; border-bottom: 1px solid #1E3A5F;")
        hlay = QHBoxLayout(header); hlay.setContentsMargins(24, 0, 24, 0)
        self._header_title = QLabel("REQUEST ACCESS — STEP 1 OF 2")
        self._header_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #C8D8E8; letter-spacing: 4px;")
        hlay.addWidget(self._header_title); hlay.addStretch()
        sub = QLabel("PENDING ADMIN APPROVAL")
        sub.setStyleSheet("font-size: 9px; color: #2A6A4A; letter-spacing: 2px;")
        hlay.addWidget(sub)
        self._root.addWidget(header)

        # Step 1: Details form
        self._step1_widget = self._build_step1()
        self._root.addWidget(self._step1_widget, 1)

        # Step 2: Face capture (hidden initially)
        self._step2_widget = self._build_step2()
        self._step2_widget.hide()
        self._root.addWidget(self._step2_widget, 1)

        # Footer
        footer = QFrame()
        footer.setStyleSheet("background-color: #060A10; border-top: 1px solid #0F1A27;")
        flay = QHBoxLayout(footer); flay.setContentsMargins(24, 14, 24, 14); flay.setSpacing(10)

        self._back_btn = QPushButton("← BACK")
        self._back_btn.setObjectName("ghostBtn")
        self._back_btn.setFixedHeight(38)
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.hide()
        flay.addWidget(self._back_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setObjectName("ghostBtn")
        cancel_btn.setFixedHeight(38)
        cancel_btn.clicked.connect(self._on_cancel)
        flay.addWidget(cancel_btn)

        self._next_btn = QPushButton("NEXT: CAPTURE FACE →")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.setFixedHeight(38)
        self._next_btn.clicked.connect(self._go_step2)
        flay.addWidget(self._next_btn, 2)

        self._submit_btn = QPushButton("✓ SUBMIT REQUEST")
        self._submit_btn.setObjectName("primaryBtn")
        self._submit_btn.setFixedHeight(38)
        self._submit_btn.clicked.connect(self._do_register)
        self._submit_btn.hide()
        flay.addWidget(self._submit_btn, 2)

        self._root.addWidget(footer)

    def _build_step1(self) -> QWidget:
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        body_widget = QWidget(); body_widget.setStyleSheet("background: transparent;")
        body = QVBoxLayout(body_widget)
        body.setContentsMargins(28, 24, 28, 24); body.setSpacing(14)

        self._fields: dict = {}

        def _add(key, label, echo=False, combo_items=None):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 9px; color: #2A5A7A; letter-spacing: 2px;")
            body.addWidget(lbl)
            if combo_items:
                w = QComboBox(); w.addItems(combo_items); w.setFixedHeight(38)
            else:
                w = QLineEdit(); w.setFixedHeight(38)
                if echo: w.setEchoMode(QLineEdit.EchoMode.Password)
            self._fields[key] = w
            body.addWidget(w)

        _add("full_name",  "FULL NAME")
        _add("email",      "EMAIL ADDRESS")
        _add("department", "DEPARTMENT", combo_items=_DEPARTMENTS)
        _add("login_id",   "LOGIN ID")
        hint = QLabel("This will also be your profile folder name for face encodings.")
        hint.setStyleSheet("font-size: 9px; color: #1E3A5F; margin-top: -8px;")
        body.addWidget(hint)
        _add("password",   "PASSWORD", echo=True)
        _add("confirm_pw", "CONFIRM PASSWORD", echo=True)

        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet("font-size: 10px; color: #FF3B3B; padding: 4px 0;")
        self._err_lbl.setWordWrap(True)
        body.addWidget(self._err_lbl)

        scroll.setWidget(body_widget)
        return scroll

    def _build_step2(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(16)

        # Instructions
        inst = QLabel("FACE CAPTURE  —  Look straight at the camera")
        inst.setStyleSheet("font-size: 12px; color: #C8D8E8; letter-spacing: 2px;")
        inst.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(inst)

        # Camera feed
        self._cam_lbl = QLabel()
        self._cam_lbl.setFixedSize(400, 300)
        self._cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl.setStyleSheet("background: #060A10; border: 1px solid #1E3A5F; border-radius: 4px;")
        self._cam_lbl.setText("Camera starting...")
        lay.addWidget(self._cam_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # Quality indicators
        q_row = QHBoxLayout(); q_row.setSpacing(20)
        self._blur_lbl = QLabel("BLUR: —")
        self._blur_lbl.setStyleSheet("font-size: 10px; color: #2A5A7A; letter-spacing: 2px;")
        self._bright_lbl = QLabel("BRIGHTNESS: —")
        self._bright_lbl.setStyleSheet("font-size: 10px; color: #2A5A7A; letter-spacing: 2px;")
        self._quality_lbl = QLabel("")
        self._quality_lbl.setStyleSheet("font-size: 10px; font-weight: bold;")
        q_row.addStretch()
        q_row.addWidget(self._blur_lbl)
        q_row.addWidget(self._bright_lbl)
        q_row.addWidget(self._quality_lbl)
        q_row.addStretch()
        lay.addLayout(q_row)

        # Progress
        prog_lbl = QLabel("PHOTOS CAPTURED")
        prog_lbl.setStyleSheet("font-size: 9px; color: #2A5A7A; letter-spacing: 2px;")
        prog_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(prog_lbl)

        self._photo_bar = QProgressBar()
        self._photo_bar.setRange(0, _REQUIRED_PHOTOS)
        self._photo_bar.setValue(0)
        self._photo_bar.setFixedHeight(20)
        self._photo_bar.setFormat(f"%v / {_REQUIRED_PHOTOS}")
        self._photo_bar.setStyleSheet("""
            QProgressBar { background: #0F1520; border: 1px solid #1E3A5F; border-radius: 3px; text-align: center; color: #C8D8E8; font-size: 10px; }
            QProgressBar::chunk { background: #00C853; border-radius: 2px; }
        """)
        lay.addWidget(self._photo_bar)

        self._capture_btn = QPushButton("📷  CAPTURE PHOTO")
        self._capture_btn.setObjectName("primaryBtn")
        self._capture_btn.setFixedHeight(42)
        self._capture_btn.clicked.connect(self._capture_photo)
        lay.addWidget(self._capture_btn)

        self._cap_status = QLabel("Preparing camera...")
        self._cap_status.setStyleSheet("font-size: 10px; color: #2A5A7A; letter-spacing: 1px;")
        self._cap_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._cap_status)

        return w

    # ── Step navigation ───────────────────────────────────────────────────────

    def _go_step2(self):
        """Validate step 1 then move to face capture."""
        self._err_lbl.setText("")
        data = {
            k: (w.currentText() if isinstance(w, QComboBox) else w.text().strip())
            for k, w in self._fields.items()
        }
        pw  = data.get("password", "")
        cpw = data.get("confirm_pw", "")

        if not all([data.get("full_name"), data.get("email"),
                    data.get("login_id"), pw]):
            self._err_lbl.setText("⚠  All fields are required.")
            return
        if pw != cpw:
            self._err_lbl.setText("⚠  Passwords do not match.")
            return
        if len(pw) < 6:
            self._err_lbl.setText("⚠  Password must be at least 6 characters.")
            return
        if "@" not in data.get("email", ""):
            self._err_lbl.setText("⚠  Invalid email address.")
            return

        # Check login ID and email not already taken — fail fast before camera
        try:
            auth = get_auth()
            if auth._find_by_login_id(data["login_id"]) is not None:
                self._err_lbl.setText(
                    f"⚠  Login ID '{data['login_id']}' is already registered.")
                return
            if auth._find_by_email(data["email"].strip().lower()) is not None:
                self._err_lbl.setText(
                    f"⚠  Email '{data['email']}' is already registered.")
                return
        except Exception:
            pass  # if auth fails, let server-side check catch it at submit

        self._form_data = data

        # Switch to step 2
        self._step = 2
        self._step1_widget.hide()
        self._step2_widget.show()
        self._header_title.setText("REQUEST ACCESS — STEP 2 OF 2")
        self._next_btn.hide()
        self._back_btn.show()
        self._submit_btn.show()
        self._submit_btn.setEnabled(False)

        # Prepare student folder
        login_id = data["login_id"]
        self._save_dir = os.path.join(cfg.STUDENTS_DIR, login_id)
        os.makedirs(self._save_dir, exist_ok=True)

        self._captured_photos = []
        self._photo_bar.setValue(0)
        self._start_camera()

    def _go_back(self):
        self._stop_camera()
        self._step = 1
        self._step2_widget.hide()
        self._step1_widget.show()
        self._header_title.setText("REQUEST ACCESS — STEP 1 OF 2")
        self._next_btn.show()
        self._back_btn.hide()
        self._submit_btn.hide()

    # ── Camera ────────────────────────────────────────────────────────────────

    def _start_camera(self):
        self._cap = cv2.VideoCapture(cfg.CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap_status.setText("⚠ Camera not available — you can still submit without photos.")
            self._cap_status.setStyleSheet("font-size: 10px; color: #FF9500;")
            self._submit_btn.setEnabled(True)
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cam_timer.start(33)  # ~30fps display
        self._cap_status.setText("Camera ready — position face in frame, then click CAPTURE")
        self._cap_status.setStyleSheet("font-size: 10px; color: #00C853;")

    def _stop_camera(self):
        self._cam_timer.stop()
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def _cam_tick(self):
        if not self._cap or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret:
            return

        # Compute quality metrics
        blur   = _blur_score(frame)
        bright = _brightness(frame)
        face_ok, faces = _detect_face(frame)

        brightness_ok = cfg.BRIGHTNESS_MIN <= bright <= cfg.BRIGHTNESS_MAX
        blur_ok       = blur >= 20        # realistic webcam threshold
        good          = face_ok and blur_ok and brightness_ok

        self._blur_lbl.setText(f"BLUR: {blur:.0f}")
        self._bright_lbl.setText(f"BRIGHTNESS: {bright:.0f}")

        if good:
            self._quality_lbl.setText("✓ FACE DETECTED")
            self._quality_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #00C853;")
            self._capture_btn.setEnabled(True)
        else:
            reason = []
            if not face_ok:
                reason.append("NO FACE")
            if not blur_ok:
                reason.append("BLURRY")
            if not brightness_ok:
                reason.append("POOR LIGHT")
            self._quality_lbl.setText(f"⚠ {' · '.join(reason)}")
            self._quality_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #FF9500;")
            self._capture_btn.setEnabled(False)

        # Draw overlay — face box + guide ellipse
        h, w = frame.shape[:2]
        display = frame.copy()
        cx, cy = w // 2, h // 2
        ellipse_color = (0, 200, 80) if good else (50, 100, 200)
        cv2.ellipse(display, (cx, cy), (100, 130), 0, 0, 360, ellipse_color, 2)
        # Draw detected face rectangles
        for (fx, fy, fw, fh) in faces:
            cv2.rectangle(display, (fx, fy), (fx+fw, fy+fh), (0, 200, 80), 2)
        cv2.putText(display, f"{len(self._captured_photos)}/{_REQUIRED_PHOTOS}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, ellipse_color, 2)

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            400, 300, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self._cam_lbl.setPixmap(pix)

    def _capture_photo(self):
        if not self._cap or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret:
            return

        blur = _blur_score(frame)
        b    = _brightness(frame)
        face_ok, _ = _detect_face(frame)

        if not face_ok:
            self._cap_status.setText("⚠ No face detected — position your face in the oval")
            self._cap_status.setStyleSheet("font-size: 12px; color: #FF3B3B;")
            return
        if blur < 20:
            self._cap_status.setText("⚠ Image too blurry — hold still and retry")
            self._cap_status.setStyleSheet("font-size: 12px; color: #FF3B3B;")
            return
        if not (cfg.BRIGHTNESS_MIN <= b <= cfg.BRIGHTNESS_MAX):
            self._cap_status.setText("⚠ Poor lighting — move to better light and retry")
            self._cap_status.setStyleSheet("font-size: 12px; color: #FF3B3B;")
            return

        idx = len(self._captured_photos)
        filename = os.path.join(self._save_dir, f"photo_{idx+1:02d}.jpg")
        cv2.imwrite(filename, frame)
        self._captured_photos.append(filename)
        self._photo_bar.setValue(len(self._captured_photos))
        self._cap_status.setText(
            f"✓ Photo {idx+1} saved — {_REQUIRED_PHOTOS - idx - 1} more needed")
        self._cap_status.setStyleSheet("font-size: 10px; color: #00C853;")

        if len(self._captured_photos) >= _REQUIRED_PHOTOS:
            self._stop_camera()
            self._capture_btn.setEnabled(False)
            self._submit_btn.setEnabled(True)
            self._cap_status.setText(
                f"✓ All {_REQUIRED_PHOTOS} photos captured! Click SUBMIT REQUEST.")
            self._cam_lbl.setText(f"✓ {_REQUIRED_PHOTOS} PHOTOS CAPTURED")
            self._cam_lbl.setStyleSheet(
                "background: #0A2A1A; border: 1px solid #00C853; border-radius: 4px;"
                "font-size: 14px; color: #00C853; font-weight: bold;")

    # ── Registration ──────────────────────────────────────────────────────────

    def _do_register(self):
        data = self._form_data
        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("SUBMITTING...")
        try:
            self._auth.register(
                full_name  = data["full_name"],
                email      = data["email"],
                department = data["department"],
                login_id   = data["login_id"],
                password   = data["password"],
            )
            self.registered_login_id = data["login_id"]
            if self._captured_photos:
                QMessageBox.information(
                    self, "Registration Submitted",
                    f"Account created for '{data['login_id']}'.\n\n"
                    f"{len(self._captured_photos)} face photos saved to Profiles/{data['login_id']}/\n\n"
                    "Admin must:\n"
                    "1. Approve your account in Admin Panel\n"
                    "2. Run encode_students.py to register your profile"
                )
            self._stop_camera()
            self.accept()
        except AuthError as e:
            self._err_lbl.setText(f"⚠  {e}")
            self._submit_btn.setEnabled(True)
        finally:
            self._submit_btn.setText("✓ SUBMIT REQUEST")

    def _on_cancel(self):
        self._stop_camera()
        self.reject()

    def closeEvent(self, event):
        self._stop_camera()
        super().closeEvent(event)