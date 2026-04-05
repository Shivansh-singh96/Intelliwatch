"""
ui/admin_panel.py
──────────────────
AdminPanel — full admin toolkit (admin-only).

Tabs:
  1. Pending Approvals   — approve/reject new users
  2. All Users           — promote/delete users
  3. Register Student    — live face capture to add new student
  4. Register via Photo  — import photos from folder
  5. Upload Group Photo  — recognise everyone in a single image
  6. All Attendance      — full attendance table
  7. Analytics           — launch Dash dashboard
  8. Flag / Watchlist    — add/remove flagged persons
"""

import logging
import os
import csv
import shutil
import subprocess
import webbrowser

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QTabWidget, QMessageBox, QFileDialog,
    QFormLayout, QLineEdit, QComboBox, QProgressBar,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QScrollArea, QSplitter,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui  import QColor, QImage, QPixmap

from services.auth_service    import get_auth
from modules.attendance_manager import AttendanceManager
from modules.flagged_manager  import FlaggedManager
from modules.face_engine      import FaceEngine
import modules.config as cfg
from ui.alert_dialog import ALERT_HISTORY_CSV, ALERT_SNAP_DIR, LEVEL_COLORS, _bgr_to_pixmap

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "pending":  "#FFD60A",
    "approved": "#00C853",
    "rejected": "#FF3B3B",
}
_LEVEL_COLORS = {"High": "#FF3B3B", "Medium": "#FF9500", "Low": "#FFD60A"}

_REQUIRED_PHOTOS = 15
_DEPTS = [
    "Computer Science", "Electronics & Communication",
    "Mechanical Engineering", "Civil Engineering",
    "Information Technology", "Management", "Administration", "Security", "Other",
]


# ── helpers ────────────────────────────────────────────────────────────────────

def _blur_score(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def _brightness(img):
    return float(np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)))

# Lightweight Haar cascade for registration face check
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

def _detect_face(img_bgr):
    """Returns (face_found: bool, faces array). Fast Haar cascade."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # Equalise histogram to improve detection in dark/bright conditions
    gray_eq = cv2.equalizeHist(gray)
    faces = _face_cascade.detectMultiScale(
        gray_eq, scaleFactor=1.1, minNeighbors=3, minSize=(50, 50)
    )
    if len(faces) == 0:
        # Second attempt — more permissive
        faces = _face_cascade.detectMultiScale(
            gray_eq, scaleFactor=1.2, minNeighbors=2, minSize=(40, 40)
        )
    return len(faces) > 0, faces

def _table_widget(headers):
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().hide()
    t.setShowGrid(False)
    t.horizontalHeader().setStretchLastSection(True)
    return t


# ── Admin Panel ────────────────────────────────────────────────────────────────

class AdminPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auth       = get_auth()
        self._attendance = AttendanceManager()
        self._flagged    = FlaggedManager()
        self._engine     = FaceEngine()
        self._flagged.load()
        self._engine.load()

        # Auto-create accounts for pre-existing students
        n = self._auth.sync_students_from_encodefile()
        if n: print(f"AdminPanel: auto-created {n} student account(s)")

        # Camera state for register tab
        self._cap          = None
        self._cam_timer    = QTimer(self)
        self._cam_timer.timeout.connect(self._cam_tick)
        self._reg_photos: list = []
        self._reg_save_dir = ""

        self._build_ui()
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    # ── Master UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("ADMIN PANEL")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #C8D8E8; letter-spacing: 3px;")
        hdr.addWidget(title); hdr.addStretch()

        self._badge = QLabel("0 PENDING")
        self._badge.setStyleSheet(
            "font-size: 12px; color: #FFD60A; letter-spacing: 2px;"
            "background: #1A1500; border: 1px solid #3A3000; border-radius: 3px; padding: 4px 10px;")
        hdr.addWidget(self._badge)

        ref_btn = QPushButton("⟳  REFRESH")
        ref_btn.setObjectName("ghostBtn"); ref_btn.setFixedHeight(32)
        ref_btn.clicked.connect(self.refresh)
        hdr.addWidget(ref_btn)
        lay.addLayout(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1E3A5F; background-color: #0A0E17; }
            QTabBar::tab { background: #0F1520; color: #2A5A7A; border: 1px solid #1E3A5F;
                           padding: 8px 14px; font-size: 11px; letter-spacing: 2px; }
            QTabBar::tab:selected { background: #0A2A1A; color: #00C853; border-bottom: 2px solid #00C853; }
        """)

        self._tabs.addTab(self._build_tab_pending(),       "⏳ PENDING")
        self._tabs.addTab(self._build_tab_all_users(),     "👥 ALL USERS")
        self._tabs.addTab(self._build_tab_reg_live(),      "📷 REGISTER LIVE")
        self._tabs.addTab(self._build_tab_reg_photo(),     "🖼 REGISTER PHOTO")
        self._tabs.addTab(self._build_tab_group(),         "👥 GROUP PHOTO")
        self._tabs.addTab(self._build_tab_attendance(),    "≡ ATTENDANCE")
        self._tabs.addTab(self._build_tab_analytics(),     "📊 ANALYTICS")
        self._tabs.addTab(self._build_tab_flagged(),       "⚑ FLAGGED")
        self._tabs.addTab(self._build_tab_alert_history(), "📸 ALERTS")

        self._tabs.currentChanged.connect(self._on_tab_changed)
        lay.addWidget(self._tabs, 1)

    # ── Tab: Pending ───────────────────────────────────────────────────────────

    def _build_tab_pending(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(12, 12, 12, 12)
        self._pending_tbl = _table_widget(
            ["FULL NAME", "EMAIL", "DEPARTMENT", "LOGIN ID", "CREATED", "ACTIONS"])
        lay.addWidget(self._pending_tbl)
        return w

    def _load_pending(self):
        users = self._auth.get_pending_users()
        t = self._pending_tbl; t.setRowCount(0)
        self._badge.setText(f"{len(users)} PENDING")

        for i, u in enumerate(users):
            t.insertRow(i)
            t.setItem(i, 0, QTableWidgetItem(u.full_name))
            t.setItem(i, 1, QTableWidgetItem(u.email))
            t.setItem(i, 2, QTableWidgetItem(u.department))
            t.setItem(i, 3, QTableWidgetItem(u.login_id))
            import time; created = getattr(u, "created_at", None)
            t.setItem(i, 4, QTableWidgetItem(
                __import__("datetime").datetime.fromtimestamp(
                    created).strftime("%Y-%m-%d") if created else "—"))

            cell = QWidget(); cl = QHBoxLayout(cell)
            cl.setContentsMargins(4, 2, 4, 2); cl.setSpacing(6)

            appr = QPushButton("✓ APPROVE")
            appr.setStyleSheet("QPushButton{background:#0A2A1A;color:#00C853;border:1px solid #1A4A2A;border-radius:3px;padding:4px 8px;font-size: 12px;}QPushButton:hover{background:#00C853;color:#000;}")
            appr.clicked.connect(lambda _, uid=u.uid: self._approve(uid))
            cl.addWidget(appr)

            rej = QPushButton("✖ REJECT")
            rej.setStyleSheet("QPushButton{background:#1A0808;color:#FF3B3B;border:1px solid #3A1010;border-radius:3px;padding:4px 8px;font-size: 12px;}QPushButton:hover{background:#FF3B3B;color:#000;}")
            rej.clicked.connect(lambda _, uid=u.uid: self._reject(uid))
            cl.addWidget(rej)

            t.setCellWidget(i, 5, cell); t.setRowHeight(i, 48)

    # ── Tab: All Users ─────────────────────────────────────────────────────────

    def _build_tab_all_users(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(12, 12, 12, 12)
        self._all_tbl = _table_widget(
            ["FULL NAME", "EMAIL", "ROLE", "STATUS", "LOGIN ID", "ACTIONS"])
        lay.addWidget(self._all_tbl)
        return w

    def _load_all_users(self):
        users = self._auth.get_all_users()
        t = self._all_tbl; t.setRowCount(0)

        for i, u in enumerate(users):
            t.insertRow(i)
            t.setItem(i, 0, QTableWidgetItem(u.full_name))
            t.setItem(i, 1, QTableWidgetItem(u.email))

            ri = QTableWidgetItem(u.role.upper())
            ri.setForeground(QColor("#00C853" if u.role == "admin" else "#3A6A8A"))
            t.setItem(i, 2, ri)

            si = QTableWidgetItem(u.status.upper())
            si.setForeground(QColor(_STATUS_COLORS.get(u.status, "#C8D8E8")))
            t.setItem(i, 3, si)
            t.setItem(i, 4, QTableWidgetItem(u.login_id))

            cell = QWidget(); cl = QHBoxLayout(cell)
            cl.setContentsMargins(4, 2, 4, 2); cl.setSpacing(4)

            # Edit button — always shown
            eb = QPushButton("✎")
            eb.setToolTip("Edit details")
            eb.setStyleSheet("QPushButton{background:#0A1A2A;color:#C8D8E8;border:1px solid #1E3A5F;border-radius:3px;padding:4px 6px;font-size: 12px;}QPushButton:hover{background:#1E3A5F;color:#fff;}")
            eb.clicked.connect(lambda _, uu=u: self._edit_user(uu))
            cl.addWidget(eb)

            if u.role != "admin":
                pb = QPushButton("⬆")
                pb.setToolTip("Promote to Admin")
                pb.setStyleSheet("QPushButton{background:#0A1A2A;color:#3A8ABF;border:1px solid #1E3A5F;border-radius:3px;padding:4px 6px;font-size: 12px;}QPushButton:hover{background:#3A8ABF;color:#000;}")
                pb.clicked.connect(lambda _, uid=u.uid: self._promote(uid))
                cl.addWidget(pb)

            if u.login_id != "admin":
                db = QPushButton("⊗")
                db.setToolTip("Delete user")
                db.setStyleSheet("QPushButton{background:#1A0808;color:#FF3B3B;border:1px solid #3A1010;border-radius:3px;padding:4px 6px;font-size: 12px;}QPushButton:hover{background:#FF3B3B;color:#000;}")
                db.clicked.connect(lambda _, uid=u.uid: self._delete_user(uid))
                cl.addWidget(db)

            t.setCellWidget(i, 5, cell); t.setRowHeight(i, 44)

    # ── Tab: Register Live ─────────────────────────────────────────────────────

    def _build_tab_reg_live(self):
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(16)

        # Left: form
        form_w = QWidget(); form_w.setFixedWidth(260)
        fl = QVBoxLayout(form_w); fl.setSpacing(10)

        fl.addWidget(self._sec_label("PROFILE DETAILS"))
        self._reg_fields = {}
        for key, label in [("sid", "PROFILE ID / LOGIN ID"), ("name", "FULL NAME"),
                            ("dept", "DEPARTMENT")]:
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; color: #2A5A7A; letter-spacing: 2px;")
            fl.addWidget(lbl)
            if key == "dept":
                w2 = QComboBox(); w2.addItems(_DEPTS); w2.setFixedHeight(34)
            else:
                w2 = QLineEdit(); w2.setFixedHeight(34)
            self._reg_fields[key] = w2; fl.addWidget(w2)

        self._reg_prog = QProgressBar()
        self._reg_prog.setRange(0, _REQUIRED_PHOTOS); self._reg_prog.setValue(0)
        self._reg_prog.setFixedHeight(18)
        self._reg_prog.setFormat(f"%v/{_REQUIRED_PHOTOS} photos")
        self._reg_prog.setStyleSheet("QProgressBar{background:#0F1520;border:1px solid #1E3A5F;border-radius:3px;text-align:center;color:#C8D8E8;font-size: 11px;}QProgressBar::chunk{background:#00C853;border-radius:2px;}")
        fl.addWidget(self._reg_prog)

        self._reg_capture_btn = QPushButton("📷  CAPTURE PHOTO")
        self._reg_capture_btn.setObjectName("primaryBtn"); self._reg_capture_btn.setFixedHeight(38)
        self._reg_capture_btn.clicked.connect(self._reg_capture)
        self._reg_capture_btn.setEnabled(False)
        fl.addWidget(self._reg_capture_btn)

        self._reg_start_btn = QPushButton("▶  START CAMERA")
        self._reg_start_btn.setObjectName("ghostBtn"); self._reg_start_btn.setFixedHeight(38)
        self._reg_start_btn.clicked.connect(self._reg_start_cam)
        fl.addWidget(self._reg_start_btn)

        self._reg_save_btn = QPushButton("✓  SAVE PROFILE")
        self._reg_save_btn.setObjectName("primaryBtn"); self._reg_save_btn.setFixedHeight(38)
        self._reg_save_btn.clicked.connect(self._reg_save)
        self._reg_save_btn.setEnabled(False)
        fl.addWidget(self._reg_save_btn)

        self._reg_status = QLabel("Fill in details then start camera.")
        self._reg_status.setStyleSheet("font-size: 11px; color: #2A5A7A;")
        self._reg_status.setWordWrap(True)
        fl.addWidget(self._reg_status)
        fl.addStretch()
        lay.addWidget(form_w)

        # Right: camera preview
        self._reg_cam_lbl = QLabel("Camera preview")
        self._reg_cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reg_cam_lbl.setStyleSheet("background:#060A10;border:1px solid #1E3A5F;border-radius:4px;font-size:12px;color:#1E3A5F;")
        self._reg_cam_lbl.setMinimumSize(400, 300)
        self._reg_cam_lbl.setMaximumSize(800, 600)
        lay.addWidget(self._reg_cam_lbl, 1)

        return w

    def _reg_start_cam(self):
        sid = self._reg_fields["sid"].text().strip()
        if not sid:
            QMessageBox.warning(self, "Validation", "Enter Profile ID first.")
            return
        self._reg_save_dir = os.path.join(cfg.STUDENTS_DIR, sid)
        os.makedirs(self._reg_save_dir, exist_ok=True)
        self._reg_photos = []
        self._reg_prog.setValue(0)

        self._cap = cv2.VideoCapture(cfg.CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._reg_status.setText("⚠ Camera not available.")
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cam_timer.start(33)
        self._reg_capture_btn.setEnabled(True)
        self._reg_status.setText("Camera ready — click CAPTURE PHOTO")

    def _cam_tick(self):
        """Single cam timer drives all camera uses."""
        if not self._cap or not self._cap.isOpened(): return
        ret, frame = self._cap.read()
        if not ret: return

        # Brighten dark frames before quality check and display
        frame = cv2.convertScaleAbs(frame, alpha=1.3, beta=15)

        self._latest_frame = frame

        # Quality check — require face detected + reasonable blur + brightness
        blur      = _blur_score(frame)
        bright    = _brightness(frame)
        face_ok, faces = _detect_face(frame)
        good = face_ok and blur >= 10 and cfg.BRIGHTNESS_MIN <= bright <= cfg.BRIGHTNESS_MAX

        display = frame.copy()
        h, w   = display.shape[:2]
        cx, cy = w // 2, h // 2
        color  = (0, 200, 80) if good else (50, 100, 200)
        cv2.ellipse(display, (cx, cy), (100, 130), 0, 0, 360, color, 2)
        for (fx, fy, fw, fh) in faces:
            cv2.rectangle(display, (fx, fy), (fx+fw, fy+fh), (0, 200, 80), 2)
        if not face_ok:
            cv2.putText(display, "NO FACE", (cx-55, cy+160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 100, 200), 2)
        elif not good:
            cv2.putText(display, "POOR QUALITY", (cx-80, cy+160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 200), 2)

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self._reg_cam_lbl.width() or 400, self._reg_cam_lbl.height() or 300,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        self._reg_cam_lbl.setPixmap(pix)
        self._reg_capture_btn.setEnabled(good)

    def _reg_capture(self):
        frame = getattr(self, "_latest_frame", None)
        if frame is None: return
        face_ok, _ = _detect_face(frame)
        if not face_ok:
            self._reg_status.setText("⚠ No face detected — look at the camera"); return
        if _blur_score(frame) < 10:
            self._reg_status.setText("⚠ Too blurry — hold still"); return
        b = _brightness(frame)
        if not (cfg.BRIGHTNESS_MIN <= b <= cfg.BRIGHTNESS_MAX):
            self._reg_status.setText("⚠ Poor lighting"); return

        idx  = len(self._reg_photos)
        path = os.path.join(self._reg_save_dir, f"photo_{idx+1:02d}.jpg")
        cv2.imwrite(path, frame)
        self._reg_photos.append(path)
        self._reg_prog.setValue(len(self._reg_photos))
        self._reg_status.setText(f"✓ Photo {idx+1}/{_REQUIRED_PHOTOS} captured")

        if len(self._reg_photos) >= _REQUIRED_PHOTOS:
            self._stop_cam()
            self._reg_save_btn.setEnabled(True)
            self._reg_capture_btn.setEnabled(False)
            self._reg_status.setText("✓ All photos done — click SAVE STUDENT")

    def _reg_save(self):
        sid  = self._reg_fields["sid"].text().strip()
        name = self._reg_fields["name"].text().strip()
        if not sid:
            QMessageBox.warning(self, "Validation", "Profile ID is required."); return
        if not self._reg_photos:
            QMessageBox.warning(self, "Validation", "No photos captured yet."); return

        # ── Duplicate check ───────────────────────────────────────────────────
        student_folder = os.path.join(cfg.STUDENTS_DIR, sid)
        if os.path.isdir(student_folder) and os.listdir(student_folder):
            reply = QMessageBox.question(
                self, "Profile Already Exists",
                f"Profile ID '{sid}' already has photos registered.\n"
                f"Overwrite and re-encode?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        # ── Check if user account exists in auth DB ───────────────────────────
        existing = self._auth._find_by_login_id(sid)
        if existing:
            reply2 = QMessageBox.question(
                self, "Account Exists",
                f"A user account with login ID '{sid}' already exists.\n"
                f"Update their photos and re-encode?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply2 != QMessageBox.StandardButton.Yes:
                return

        self._stop_cam()

        # ── Auto-encode in background ─────────────────────────────────────────
        self._reg_status.setText("⟳ Encoding face data…")
        import threading
        from encode_students import encode_single_student

        def _encode():
            ok, msg = encode_single_student(sid)
            status = f"✓ Encoded: {msg}" if ok else f"⚠ Encode failed: {msg}"
            self._reg_status.setText(status)

        threading.Thread(target=_encode, daemon=True).start()

        QMessageBox.information(
            self, "Profile Registered",
            f"Profile '{sid}' saved with {len(self._reg_photos)} photo(s).\n\n"
            f"Face encoding is running in background — "
            f"recognition will be active within a few seconds.")
        self._reg_prog.setValue(0)
        self._reg_photos = []
        self._reg_save_btn.setEnabled(False)
        for f in self._reg_fields.values():
            if isinstance(f, QLineEdit): f.clear()

    def _stop_cam(self):
        self._cam_timer.stop()
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    # ── Tab: Register via Photo ────────────────────────────────────────────────

    def _build_tab_reg_photo(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(12)

        lay.addWidget(self._sec_label("REGISTER NEW STUDENT — UPLOAD PHOTOS"))

        # ── Form ──────────────────────────────────────────────────────────────
        form = QFormLayout(); form.setSpacing(10); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._rp_sid   = QLineEdit(); self._rp_sid.setFixedHeight(36)
        self._rp_sid.setPlaceholderText("e.g. 0302CS221101")
        form.addRow("STUDENT ID *", self._rp_sid)

        self._rp_name  = QLineEdit(); self._rp_name.setFixedHeight(36)
        form.addRow("FULL NAME *", self._rp_name)

        self._rp_email = QLineEdit(); self._rp_email.setFixedHeight(36)
        self._rp_email.setPlaceholderText("profile@example.com")
        form.addRow("EMAIL *", self._rp_email)

        self._rp_dept  = QComboBox(); self._rp_dept.addItems(_DEPTS)
        self._rp_dept.setFixedHeight(36)
        form.addRow("DEPARTMENT", self._rp_dept)

        self._rp_pwd   = QLineEdit(); self._rp_pwd.setFixedHeight(36)
        self._rp_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._rp_pwd.setPlaceholderText("Min 6 characters")
        form.addRow("PASSWORD *", self._rp_pwd)

        lay.addLayout(form)

        # ── Photo picker ───────────────────────────────────────────────────────
        lay.addWidget(self._sec_label("FACE PHOTOS  (select 3–10 clear face images)"))

        row = QHBoxLayout()
        self._rp_path_lbl = QLabel("No files selected")
        self._rp_path_lbl.setStyleSheet("font-size: 12px; color: #2A5A7A;")
        row.addWidget(self._rp_path_lbl, 1)
        browse_files = QPushButton("📂  SELECT PHOTOS")
        browse_files.setObjectName("ghostBtn"); browse_files.setFixedHeight(34)
        browse_files.clicked.connect(self._rp_browse_files)
        row.addWidget(browse_files)
        browse_folder = QPushButton("📁  SELECT FOLDER")
        browse_folder.setObjectName("ghostBtn"); browse_folder.setFixedHeight(34)
        browse_folder.clicked.connect(self._rp_browse_folder)
        row.addWidget(browse_folder)
        lay.addLayout(row)

        self._rp_count = QLabel("")
        self._rp_count.setStyleSheet("font-size: 12px; color: #2A5A7A;")
        lay.addWidget(self._rp_count)

        self._rp_selected_files: list[str] = []

        # ── Submit ──────────────────────────────────────────────────────────
        btn = QPushButton("✓  CREATE STUDENT ACCOUNT & IMPORT PHOTOS")
        btn.setObjectName("primaryBtn"); btn.setFixedHeight(42)
        btn.clicked.connect(self._rp_register)
        lay.addWidget(btn)

        self._rp_status = QLabel("")
        self._rp_status.setStyleSheet("font-size: 11px; color: #00C853;")
        self._rp_status.setWordWrap(True)
        lay.addWidget(self._rp_status)
        lay.addStretch()
        return w

    def _rp_browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Face Photos", "",
            "Images (*.jpg *.jpeg *.png *.bmp)")
        if not files: return
        self._rp_selected_files = files
        self._rp_path_lbl.setText(f"{len(files)} file(s) selected")
        self._rp_count.setText(", ".join(os.path.basename(f) for f in files[:5])
                               + ("..." if len(files) > 5 else ""))

    def _rp_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Photo Folder")
        if not folder: return
        imgs = [os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))]
        if not imgs:
            QMessageBox.warning(self, "No images", "No image files found in that folder.")
            return
        self._rp_selected_files = sorted(imgs)
        self._rp_path_lbl.setText(f"{len(imgs)} file(s) from folder")
        self._rp_count.setText(os.path.basename(folder))

    def _rp_register(self):
        sid   = self._rp_sid.text().strip()
        name  = self._rp_name.text().strip()
        email = self._rp_email.text().strip()
        dept  = self._rp_dept.currentText()
        pwd   = self._rp_pwd.text()
        files = self._rp_selected_files

        # Validation
        errors = []
        if not sid:   errors.append("Profile ID is required.")
        if not name:  errors.append("Full name is required.")
        if not email: errors.append("Email is required.")
        if not pwd:   errors.append("Password is required.")
        if len(files) < 3: errors.append("Select at least 3 photos.")
        if errors:
            self._rp_status.setStyleSheet("font-size: 11px; color: #FF3B3B;")
            self._rp_status.setText("⚠  " + "  |  ".join(errors))
            return

        # Create auth account
        try:
            self._auth.register_approved(
                full_name=name, email=email, department=dept,
                login_id=sid, password=pwd, role="user")
        except Exception as e:
            self._rp_status.setStyleSheet("font-size: 11px; color: #FF3B3B;")
            self._rp_status.setText(f"⚠  {e}")
            return

        # Copy photos
        dest = os.path.join(cfg.STUDENTS_DIR, sid)
        os.makedirs(dest, exist_ok=True)
        for i, src in enumerate(files):
            ext = os.path.splitext(src)[1]
            shutil.copy2(src, os.path.join(dest, f"photo_{i+1:02d}{ext}"))

        self._rp_status.setStyleSheet("font-size: 11px; color: #00C853;")
        self._rp_status.setText(
            f"✓ Account created for '{sid}' with {len(files)} photos.\n"
            "  Run encode_students.py to activate recognition.")

        # Clear form
        for w in [self._rp_sid, self._rp_name, self._rp_email, self._rp_pwd]:
            w.clear()
        self._rp_selected_files = []
        self._rp_path_lbl.setText("No files selected")
        self._rp_count.setText("")
        self.refresh()

    # ── Tab: Group Photo ───────────────────────────────────────────────────────

    def _build_tab_group(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(14)

        lay.addWidget(self._sec_label("GROUP PHOTO RECOGNITION"))

        info = QLabel("Upload a group photo. The system will identify all known profiles "
                      "and optionally mark their attendance.")
        info.setStyleSheet("font-size: 11px; color: #C8D8E8;"); info.setWordWrap(True)
        lay.addWidget(info)

        row = QHBoxLayout()
        self._grp_path = QLineEdit(); self._grp_path.setFixedHeight(36)
        self._grp_path.setPlaceholderText("No image selected...")
        self._grp_path.setReadOnly(True); row.addWidget(self._grp_path, 1)
        browse = QPushButton("BROWSE")
        browse.setObjectName("ghostBtn"); browse.setFixedHeight(36)
        browse.clicked.connect(self._grp_browse); row.addWidget(browse)
        lay.addLayout(row)

        self._grp_preview = QLabel("No image selected")
        self._grp_preview.setFixedHeight(200)
        self._grp_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grp_preview.setStyleSheet(
            "background:#060A10;border:1px solid #1E3A5F;border-radius:4px;color:#1E3A5F;")
        lay.addWidget(self._grp_preview)

        btn_row = QHBoxLayout()
        recog_btn = QPushButton("🔍  IDENTIFY PERSONS")
        recog_btn.setObjectName("primaryBtn"); recog_btn.setFixedHeight(40)
        recog_btn.clicked.connect(self._grp_identify)
        btn_row.addWidget(recog_btn)
        att_btn = QPushButton("≡  MARK ATTENDANCE FOR ALL")
        att_btn.setObjectName("ghostBtn"); att_btn.setFixedHeight(40)
        att_btn.clicked.connect(self._grp_mark_all)
        btn_row.addWidget(att_btn)
        lay.addLayout(btn_row)

        self._grp_results = QListWidget()
        self._grp_results.setFixedHeight(120)
        self._grp_results.setStyleSheet(
            "QListWidget{font-size:11px;font-family:Consolas,monospace;}"
            "QListWidget::item{padding:4px 8px;border-bottom:1px solid #0F1A27;}")
        lay.addWidget(self._grp_results)
        self._grp_identified: list[tuple[str, float]] = []
        lay.addStretch()
        return w

    def _grp_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Group Photo", "",
            "Images (*.jpg *.jpeg *.png *.bmp)")
        if not path: return
        self._grp_path.setText(path)
        pix = QPixmap(path).scaled(
            self._grp_preview.width(), 200,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self._grp_preview.setPixmap(pix)
        self._grp_identified = []
        self._grp_results.clear()

    def _grp_identify(self):
        path = self._grp_path.text().strip()
        if not path: QMessageBox.warning(self, "No image", "Select an image first."); return
        if not self._engine.is_loaded:
            QMessageBox.warning(self, "Not loaded", "Run encode_students.py first."); return
        img = cv2.imread(path)
        if img is None: QMessageBox.warning(self, "Error", "Cannot read image."); return

        # Scale up small images so faces meet the minimum face size threshold
        h, w = img.shape[:2]
        if max(h, w) < 1280:
            scale = 1280 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_CUBIC)

        results = self._engine.identify_frame_group(img)
        self._grp_results.clear()
        self._grp_identified = []
        for r in results:
            if r.is_known:
                self._grp_identified.append((r.name, r.score))
                item = QListWidgetItem(f"  ✓  {r.name}   {r.score:.0%}")
                item.setForeground(QColor("#00C853"))
                self._grp_results.addItem(item)
        if not self._grp_identified:
            self._grp_results.addItem("No known persons identified.")

    def _grp_mark_all(self):
        if not self._grp_identified:
            QMessageBox.information(self, "Nothing to mark", "Run identification first."); return
        count = 0
        for name, score in self._grp_identified:
            ok, _ = self._attendance.mark(name, score)
            if ok: count += 1
        QMessageBox.information(self, "Done", f"Marked attendance for {count} profile(s).")

    # ── Tab: Attendance ────────────────────────────────────────────────────────

    def _build_tab_attendance(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(8)

        toolbar = QHBoxLayout()
        self._att_search = QLineEdit(); self._att_search.setPlaceholderText("Search...")
        self._att_search.setFixedHeight(34); self._att_search.textChanged.connect(self._att_filter)
        toolbar.addWidget(self._att_search, 1)
        ref = QPushButton("⟳"); ref.setObjectName("ghostBtn"); ref.setFixedSize(34, 34)
        ref.clicked.connect(self._load_attendance); toolbar.addWidget(ref)
        lay.addLayout(toolbar)

        self._att_tbl = _table_widget(["NAME", "TIME", "STATUS"])
        lay.addWidget(self._att_tbl, 1)
        return w

    def _load_attendance(self):
        records = self._attendance.get_all()
        self._att_all = records
        self._att_filter()

    def _att_filter(self):
        q = self._att_search.text().strip().lower() if hasattr(self, "_att_search") else ""
        records = getattr(self, "_att_all", [])
        t = self._att_tbl; t.setRowCount(0)
        for i, r in enumerate(records):
            if q and q not in r["Name"].lower(): continue
            t.insertRow(t.rowCount())
            row = t.rowCount() - 1
            t.setItem(row, 0, QTableWidgetItem(r["Name"]))
            t.setItem(row, 1, QTableWidgetItem(r["Time"]))
            si = QTableWidgetItem("Present"); si.setForeground(QColor("#00C853"))
            t.setItem(row, 2, si)

    # ── Tab: Analytics ─────────────────────────────────────────────────────────

    def _build_tab_analytics(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(16)
        lay.addStretch()

        icon = QLabel("📊"); icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(icon)

        info = QLabel("Launch Dash Analytics Dashboard\n\n"
                      "Opens an interactive web dashboard with attendance charts,\n"
                      "threat level metrics, and detection history.")
        info.setStyleSheet("font-size: 12px; color: #C8D8E8; line-height: 1.6;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(info)

        btn = QPushButton("🚀  LAUNCH ANALYTICS DASHBOARD")
        btn.setObjectName("primaryBtn"); btn.setFixedHeight(46)
        btn.clicked.connect(self._launch_analytics)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._analytics_status = QLabel("")
        self._analytics_status.setStyleSheet("font-size: 12px; color: #2A5A7A;")
        self._analytics_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._analytics_status)
        lay.addStretch()
        return w

    def _launch_analytics(self):
        import sys, socket, threading, time, subprocess as sp

        def _is_running():
            try:
                s = socket.create_connection(("127.0.0.1", 8050), timeout=1)
                s.close(); return True
            except OSError:
                return False

        def _kill_existing():
            try:
                result = sp.run(["netstat", "-ano"], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if ":8050" in line and "LISTENING" in line:
                        pid = line.strip().split()[-1]
                        sp.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                        time.sleep(0.6)
                        break
            except Exception:
                pass

        def _launch():
            try:
                self._analytics_status.setText("⟳  Starting analytics server...")

                # Kill any stale process on port 8050
                _kill_existing()
                for _ in range(8):
                    if not _is_running(): break
                    time.sleep(0.3)

                # Launch using same Python/venv as this app
                proc = sp.Popen(
                    [sys.executable, cfg.DASHBOARD_SCRIPT],
                    stdout=sp.DEVNULL,
                    stderr=sp.PIPE,
                    creationflags=sp.CREATE_NO_WINDOW
                    if hasattr(sp, "CREATE_NO_WINDOW") else 0,
                )

                # Poll up to 15 seconds
                ready = False
                for _ in range(30):
                    time.sleep(0.5)
                    if _is_running():
                        ready = True
                        break

                if ready:
                    from PyQt6.QtCore import QMetaObject, Qt as _Qt
                    QMetaObject.invokeMethod(
                        self, "_on_analytics_ready",
                        _Qt.ConnectionType.QueuedConnection,
                    )
                else:
                    err = proc.stderr.read(800).decode(errors="ignore")
                    self._analytics_error = err
                    from PyQt6.QtCore import QMetaObject, Qt as _Qt
                    QMetaObject.invokeMethod(
                        self, "_on_analytics_error",
                        _Qt.ConnectionType.QueuedConnection,
                    )

            except Exception as exc:
                self._analytics_error = str(exc)
                from PyQt6.QtCore import QMetaObject, Qt as _Qt
                QMetaObject.invokeMethod(
                    self, "_on_analytics_error",
                    _Qt.ConnectionType.QueuedConnection,
                )

        threading.Thread(target=_launch, daemon=True).start()

    from PyQt6.QtCore import pyqtSlot

    @pyqtSlot()
    def _on_analytics_ready(self):
        self._analytics_status.setText("✓  Dashboard running at http://127.0.0.1:8050")
        webbrowser.open("http://127.0.0.1:8050")

    @pyqtSlot()
    def _on_analytics_error(self):
        err = getattr(self, "_analytics_error", "")
        hint = ""
        if "No module named" in err:
            pkg = err.split("No module named")[-1].strip().strip("'\"")
            hint = f"\n\nMissing package: '{pkg}'\nRun:  pip install dash plotly dash-bootstrap-components pandas"
        elif err:
            hint = f"\n\nDetails:\n{err[:400]}"
        self._analytics_status.setText("⚠  Failed to start analytics server")
        QMessageBox.critical(
            self, "Analytics Dashboard Error",
            f"Could not start the analytics server at 127.0.0.1:8050.{hint}\n\n"
            f"Make sure all required packages are installed:\n"
            f"pip install dash plotly dash-bootstrap-components pandas"
        )

    # ── Tab: Flagged ───────────────────────────────────────────────────────────

    def _build_tab_flagged(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(10)

        # Add form
        add_frame = QFrame()
        add_frame.setStyleSheet("QFrame{background:#0F1520;border:1px solid #1E3A5F;border-radius:4px;}")
        af = QHBoxLayout(add_frame); af.setContentsMargins(12, 10, 12, 10); af.setSpacing(8)

        self._fl_name = QComboBox(); self._fl_name.setEditable(True)
        self._fl_name.setFixedHeight(34); self._fl_name.setMinimumWidth(160)
        af.addWidget(QLabel("ID:")); af.addWidget(self._fl_name)

        self._fl_reason = QLineEdit(); self._fl_reason.setFixedHeight(34)
        self._fl_reason.setPlaceholderText("Reason...")
        af.addWidget(self._fl_reason, 1)

        self._fl_level = QComboBox()
        self._fl_level.addItems(["High", "Medium", "Low"]); self._fl_level.setFixedHeight(34)
        af.addWidget(self._fl_level)

        add_btn = QPushButton("⊕  FLAG")
        add_btn.setStyleSheet("QPushButton{background:#1A0808;color:#FF3B3B;border:1px solid #3A1010;border-radius:3px;padding:6px 12px;font-size: 12px;}QPushButton:hover{background:#FF3B3B;color:#000;}")
        add_btn.clicked.connect(self._fl_add); af.addWidget(add_btn)
        lay.addWidget(add_frame)

        # Table
        self._fl_tbl = _table_widget(["NAME / ID", "REASON", "LEVEL", "DATE", "ACTIONS"])
        lay.addWidget(self._fl_tbl, 1)
        return w

    def _load_flagged(self):
        known = self._engine.student_names if self._engine.is_loaded else []
        self._fl_name.clear(); self._fl_name.addItems(known)

        records = self._flagged.all_records()
        t = self._fl_tbl; t.setRowCount(0)
        for i, r in enumerate(records):
            t.insertRow(i)
            col = _LEVEL_COLORS.get(r.level, "#C8D8E8")
            ni = QTableWidgetItem(r.name); ni.setForeground(QColor(col)); t.setItem(i, 0, ni)
            t.setItem(i, 1, QTableWidgetItem(r.reason))
            li = QTableWidgetItem(r.level.upper()); li.setForeground(QColor(col)); t.setItem(i, 2, li)
            t.setItem(i, 3, QTableWidgetItem(r.added_date))

            rem = QPushButton("✖ REMOVE")
            rem.setStyleSheet("QPushButton{background:#1A0808;color:#FF3B3B;border:1px solid #3A1010;border-radius:3px;padding:4px 8px;font-size: 12px;}QPushButton:hover{background:#FF3B3B;color:#000;}")
            rem.clicked.connect(lambda _, n=r.name: self._fl_remove(n))
            t.setCellWidget(i, 4, rem); t.setRowHeight(i, 44)

    def _fl_add(self):
        name   = self._fl_name.currentText().strip()
        reason = self._fl_reason.text().strip()
        level  = self._fl_level.currentText()
        if not name or not reason:
            QMessageBox.warning(self, "Validation", "Name and reason are required."); return
        ok = self._flagged.add(name, reason, level)
        if ok: self._load_flagged(); self._fl_reason.clear()
        else: QMessageBox.information(self, "Already Flagged", f"'{name}' is already on watchlist.")

    def _fl_remove(self, name: str):
        r = QMessageBox.question(self, "Remove Flag",
            f"Remove '{name}' from watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._flagged.remove(name); self._load_flagged()

    # ── Shared actions ─────────────────────────────────────────────────────────

    def _edit_user(self, user):
        """Open an inline edit dialog for a user's details."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit — {user.login_id}")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet("QDialog{background:#0A0E17;} QLabel{color:#C8D8E8;}")
        lay = QVBoxLayout(dlg); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(12)

        lay.addWidget(self._sec_label(f"EDITING: {user.login_id}"))

        form = QFormLayout(); form.setSpacing(10)
        fields = {}

        for key, label, val in [
            ("full_name",  "FULL NAME",   user.full_name),
            ("email",      "EMAIL",       user.email),
            ("login_id",   "LOGIN ID",    user.login_id),
            ("department", "DEPARTMENT",  user.department),
        ]:
            w = QLineEdit(val); w.setFixedHeight(36)
            if key == "login_id" and user.login_id == "admin":
                w.setReadOnly(True)
                w.setStyleSheet("background:#0F1520;color:#3A6A8A;")
            form.addRow(label, w)
            fields[key] = w

        # Role selector
        role_cb = QComboBox(); role_cb.addItems(["user", "admin"])
        role_cb.setCurrentText(user.role); role_cb.setFixedHeight(36)
        form.addRow("ROLE", role_cb)
        lay.addLayout(form)

        err_lbl = QLabel(""); err_lbl.setStyleSheet("color:#FF3B3B; font-size: 12px;")
        lay.addWidget(err_lbl)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        def _save():
            try:
                self._auth.update_user(
                    uid        = user.uid,
                    full_name  = fields["full_name"].text(),
                    email      = fields["email"].text(),
                    department = fields["department"].text(),
                    login_id   = fields["login_id"].text(),
                    role       = role_cb.currentText(),
                )
                dlg.accept()
                self.refresh()
            except Exception as e:
                err_lbl.setText(f"⚠  {e}")

        btns.accepted.connect(_save)
        dlg.exec()

    def _approve(self, uid):
        self._auth.approve_user(uid); self.refresh()

    def _reject(self, uid):
        r = QMessageBox.question(self, "Reject", "Reject this registration?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._auth.reject_user(uid); self.refresh()

    def _promote(self, uid):
        r = QMessageBox.question(self, "Promote", "Promote to Admin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._auth.promote_user(uid); self.refresh()

    def _delete_user(self, uid):
        r = QMessageBox.question(self, "Delete", "Permanently delete this user?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._auth.delete_user(uid); self.refresh()

    def _on_tab_changed(self, idx):
        if idx == 5: self._load_attendance()
        elif idx == 7: self._load_flagged()
        elif idx == 8: self._load_alert_history()

    # ── Tab: Alert History ────────────────────────────────────────────────────

    def _build_tab_alert_history(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(self._sec_label("ALERT HISTORY & SNAPSHOTS"))
        hdr.addStretch()
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setObjectName("ghostBtn"); refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self._load_alert_history)
        hdr.addWidget(refresh_btn)
        clear_btn = QPushButton("🗑  Clear All")
        clear_btn.setObjectName("ghostBtn"); clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet("QPushButton{color:#FF3B3B;border:1px solid #3A1010;background:#0A0E17;border-radius:3px;padding:0 8px;}QPushButton:hover{background:#3A1010;}")
        clear_btn.clicked.connect(self._clear_alert_history)
        hdr.addWidget(clear_btn)
        open_btn = QPushButton("📂  Open Folder")
        open_btn.setObjectName("ghostBtn"); open_btn.setFixedHeight(30)
        open_btn.clicked.connect(lambda: os.startfile(ALERT_SNAP_DIR) if os.path.isdir(ALERT_SNAP_DIR) else None)
        hdr.addWidget(open_btn)
        lay.addLayout(hdr)

        # Split: table left, snapshot right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # History table
        self._alert_hist_tbl = _table_widget(
            ["TIME", "PERSON", "LEVEL", "REASON", "ACTION", "⊗"])
        self._alert_hist_tbl.setMinimumWidth(380)
        # Use cellClicked to handle both snapshot preview AND delete column
        self._alert_hist_tbl.cellClicked.connect(self._on_alert_cell_clicked)
        splitter.addWidget(self._alert_hist_tbl)

        # Snapshot viewer
        snap_panel = QWidget()
        snap_lay = QVBoxLayout(snap_panel); snap_lay.setContentsMargins(8,4,4,4)
        snap_lbl_hdr = QLabel("SNAPSHOT")
        snap_lbl_hdr.setStyleSheet("font-size: 11px;color:#3A6A8A;letter-spacing:2px;")
        snap_lay.addWidget(snap_lbl_hdr)
        self._alert_snap_lbl = QLabel("Select a row\nto view snapshot")
        self._alert_snap_lbl.setFixedSize(320, 240)
        self._alert_snap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._alert_snap_lbl.setStyleSheet(
            "background:#060A10;border:1px solid #1E3A5F;border-radius:4px;"
            "color:#2A4A6A;font-size:11px;")
        snap_lay.addWidget(self._alert_snap_lbl)
        self._alert_snap_path_lbl = QLabel("")
        self._alert_snap_path_lbl.setStyleSheet("font-size: 11px;color:#2A5A7A;")
        self._alert_snap_path_lbl.setWordWrap(True)
        snap_lay.addWidget(self._alert_snap_path_lbl)
        snap_lay.addStretch()
        splitter.addWidget(snap_panel)
        splitter.setSizes([420, 340])

        lay.addWidget(splitter, 1)

        # Store snap paths per row
        self._alert_snap_paths: list[str] = []
        return w

    def _load_alert_history(self):
        self._alert_snap_paths = []
        t = self._alert_hist_tbl; t.setRowCount(0)
        if not os.path.exists(ALERT_HISTORY_CSV):
            return
        try:
            with open(ALERT_HISTORY_CSV, newline="") as fh:
                rows = list(csv.DictReader(fh))
        except Exception:
            return

        for i, row in enumerate(reversed(rows)):  # newest first
            t.insertRow(i)
            level  = row.get("Level", "")
            color  = LEVEL_COLORS.get(level, "#C8D8E8")

            t.setItem(i, 0, QTableWidgetItem(row.get("Timestamp", "")))
            t.setItem(i, 1, QTableWidgetItem(row.get("Name", "")))

            li = QTableWidgetItem(level.upper())
            li.setForeground(QColor(color))
            t.setItem(i, 2, li)

            t.setItem(i, 3, QTableWidgetItem(row.get("Reason", "")))
            t.setItem(i, 4, QTableWidgetItem(row.get("Action", "")))

            # Delete column — plain item, handled by cellClicked (column 5)
            del_item = QTableWidgetItem("  ⊗  DELETE")
            del_item.setForeground(QColor("#FF3B3B"))
            del_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(i, 5, del_item)
            t.setRowHeight(i, 36)
            self._alert_snap_paths.append(row.get("Snapshot", ""))

        # Store raw rows for quick lookup by row index (newest-first order)
        self._alert_rows_data = list(reversed(rows))

    def _delete_alert_row(self, timestamp: str, name: str):
        """Remove a single row from alert_history.csv."""
        if not os.path.exists(ALERT_HISTORY_CSV):
            return
        try:
            with open(ALERT_HISTORY_CSV, newline="") as fh:
                rows = list(csv.DictReader(fh))
            rows = [r for r in rows
                    if not (r.get("Timestamp") == timestamp and r.get("Name") == name)]
            with open(ALERT_HISTORY_CSV, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["Timestamp","Name","Level","Reason","Snapshot","Action"])
                w.writeheader(); w.writerows(rows)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        self._load_alert_history()

    def _clear_alert_history(self):
        reply = QMessageBox.question(self, "Clear All",
            "Delete all alert history records?\nSnapshot images will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with open(ALERT_HISTORY_CSV, "w", newline="") as fh:
                csv.writer(fh).writerow(["Timestamp","Name","Level","Reason","Snapshot","Action"])
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        self._load_alert_history()

    def _on_alert_cell_clicked(self, row: int, col: int):
        """Handle snapshot preview and delete button."""

    # DELETE column
        if col == 5:
            if not hasattr(self, "_alert_rows_data") or row >= len(self._alert_rows_data):
                return

            record = self._alert_rows_data[row]
            self._delete_alert_row(
                record.get("Timestamp", ""),
                record.get("Name", "")
            )
            return

    # SHOW SNAPSHOT
        if row < 0 or row >= len(self._alert_snap_paths):
            return

        snap_path = self._alert_snap_paths[row]

        if snap_path and os.path.exists(snap_path):
            frame = cv2.imread(snap_path)

            if frame is not None:
                pix = _bgr_to_pixmap(frame, 320, 240)

                self._alert_snap_lbl.setPixmap(pix)
                self._alert_snap_path_lbl.setText(os.path.basename(snap_path))
                return

    # fallback
        self._alert_snap_lbl.setText("No snapshot\navailable")
        self._alert_snap_path_lbl.setText("")
        rows = self._alert_hist_tbl.selectedItems()
        if not rows:
            return
        idx = self._alert_hist_tbl.currentRow()
        if idx < 0 or idx >= len(self._alert_snap_paths):
            return
        snap_path = self._alert_snap_paths[idx]
        if snap_path and os.path.exists(snap_path):
            
            frame = cv2.imread(snap_path)
            if frame is not None:
                pix = _bgr_to_pixmap(frame, 320, 240)
                self._alert_snap_lbl.setPixmap(pix)
                self._alert_snap_path_lbl.setText(os.path.basename(snap_path))
                return
        self._alert_snap_lbl.setText("No snapshot\navailable")
        self._alert_snap_path_lbl.setText("")

    def refresh(self):
        self._auth.sync_students_from_encodefile()
        self._load_pending()
        self._load_all_users()
        self._load_flagged()

    def _sec_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 11px; color: #2A6A5A; letter-spacing: 3px;"
                          "border-bottom: 1px solid #1E3A5F; padding-bottom: 6px;")
        return lbl