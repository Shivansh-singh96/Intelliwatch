"""
ui/settings_page.py
────────────────────
SettingsPage — admin-only runtime configuration.
Non-admin users see read-only system info only.
"""

import logging
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QMessageBox,
)
from PyQt6.QtCore import Qt

import modules.config as cfg

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self._profile  = profile
        self._is_admin = (profile.role == "admin")
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(20)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("SYSTEM SETTINGS")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #D8E8F4;"
            "letter-spacing: 3px;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        if not self._is_admin:
            lock_badge = QLabel("⊘  READ ONLY — ADMIN ACCESS REQUIRED")
            lock_badge.setStyleSheet(
                "font-size: 12px; color: #FF9500; letter-spacing: 2px;"
                "background: #1A0E00; border: 1px solid #3A2000;"
                "border-radius: 3px; padding: 4px 10px;"
            )
            hdr.addWidget(lock_badge)
        lay.addLayout(hdr)

        if not self._is_admin:
            # Non-admin: show only their own profile info
            self._build_user_info(lay)
            lay.addStretch()
            return

        # Admin: full settings
        # Recognition
        recog = self._make_group("RECOGNITION THRESHOLDS")
        form  = QFormLayout(recog)
        form.setSpacing(12)

        self._thresh = QDoubleSpinBox()
        self._thresh.setRange(0.1, 1.0); self._thresh.setSingleStep(0.05)
        self._thresh.setValue(cfg.RECOGNITION_THRESHOLD); self._thresh.setFixedHeight(36)
        form.addRow("Live threshold", self._thresh)

        self._group_thresh = QDoubleSpinBox()
        self._group_thresh.setRange(0.1, 1.0); self._group_thresh.setSingleStep(0.05)
        self._group_thresh.setValue(cfg.GROUP_RECOGNITION_THRESHOLD); self._group_thresh.setFixedHeight(36)
        form.addRow("Group photo threshold", self._group_thresh)

        self._margin = QDoubleSpinBox()
        self._margin.setRange(0.0, 0.2); self._margin.setSingleStep(0.01)
        self._margin.setDecimals(3); self._margin.setValue(cfg.KNN_MARGIN)
        self._margin.setFixedHeight(36)
        form.addRow("Match margin", self._margin)
        lay.addWidget(recog)

        # Attendance
        att = self._make_group("ATTENDANCE")
        form2 = QFormLayout(att); form2.setSpacing(12)
        self._cooldown = QSpinBox()
        self._cooldown.setRange(1, 480); self._cooldown.setValue(cfg.ATTENDANCE_COOLDOWN)
        self._cooldown.setSuffix(" min"); self._cooldown.setFixedHeight(36)
        form2.addRow("Re-mark cooldown", self._cooldown)
        lay.addWidget(att)

        # Camera
        cam = self._make_group("CAMERA")
        form3 = QFormLayout(cam); form3.setSpacing(12)
        self._frame_skip = QSpinBox()
        self._frame_skip.setRange(1, 30); self._frame_skip.setValue(cfg.FRAME_SKIP)
        self._frame_skip.setFixedHeight(36)
        form3.addRow("Recognition frame skip", self._frame_skip)
        self._fps_cap = QSpinBox()
        self._fps_cap.setRange(1, 30); self._fps_cap.setValue(cfg.RECOGNITION_FPS_CAP)
        self._fps_cap.setSuffix(" fps"); self._fps_cap.setFixedHeight(36)
        form3.addRow("Max recognition fps", self._fps_cap)
        lay.addWidget(cam)

        # Apply
        btn_row = QHBoxLayout()
        apply_btn = QPushButton("✓  APPLY SETTINGS")
        apply_btn.setObjectName("primaryBtn")
        apply_btn.setFixedHeight(40); apply_btn.setFixedWidth(200)
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(apply_btn); btn_row.addStretch()
        lay.addLayout(btn_row)

        # System info
        self._build_system_info(lay)
        lay.addStretch()

    def _build_user_info(self, lay):
        """For regular users: show only their own profile."""
        info = self._make_group("YOUR PROFILE")
        ilay = QVBoxLayout(info)
        ilay.setSpacing(6)
        for label, value in [
            ("Full Name",   self._profile.full_name),
            ("Email",       self._profile.email),
            ("Department",  self._profile.department),
            ("Login ID",    self._profile.login_id),
            ("Role",        self._profile.role.upper()),
            ("Status",      self._profile.status.upper()),
        ]:
            row = QHBoxLayout()
            k = QLabel(label.upper())
            k.setStyleSheet("font-size: 12px; color: #3A7A9A; letter-spacing: 2px;")
            k.setFixedWidth(160)
            row.addWidget(k)
            v = QLabel(str(value))
            v.setStyleSheet("font-size: 13px; color: #D8E8F4;")
            row.addWidget(v, 1)
            ilay.addLayout(row)
        lay.addWidget(info)

        info2 = self._make_group("SYSTEM INFORMATION")
        ilay2 = QVBoxLayout(info2); ilay2.setSpacing(6)
        for label, value in [
            ("Application", "IntelliWatch v2.0"),
            ("GUI Framework", "PyQt6"),
            ("Recognition", "ArcFace (insightface / ONNX)"),
        ]:
            row = QHBoxLayout()
            k = QLabel(label.upper())
            k.setStyleSheet("font-size: 12px; color: #3A7A9A; letter-spacing: 2px;")
            k.setFixedWidth(160); row.addWidget(k)
            v = QLabel(value)
            v.setStyleSheet("font-size: 13px; color: #D8E8F4;")
            row.addWidget(v, 1); ilay2.addLayout(row)
        lay.addWidget(info2)

    def _build_system_info(self, lay):
        info = self._make_group("SYSTEM INFORMATION")
        ilay = QVBoxLayout(info); ilay.setSpacing(6)
        for label, value in [
            ("Application",    "IntelliWatch v2.0"),
            ("GUI Framework",  "PyQt6"),
            ("Recognition",    "ArcFace (insightface / ONNX)"),
            ("Encode file",    cfg.ENCODE_FILE),
            ("Attendance CSV", cfg.ATTENDANCE_CSV),
            ("Logged in as",   f"{self._profile.login_id}  [{self._profile.role}]"),
        ]:
            row = QHBoxLayout()
            k = QLabel(label.upper())
            k.setStyleSheet("font-size: 12px; color: #3A7A9A; letter-spacing: 2px;")
            k.setFixedWidth(160); row.addWidget(k)
            v = QLabel(value)
            v.setStyleSheet("font-size: 13px; color: #D8E8F4;")
            v.setWordWrap(True); row.addWidget(v, 1); ilay.addLayout(row)
        lay.addWidget(info)

    def _make_group(self, title: str) -> QGroupBox:
        g = QGroupBox(title)
        g.setStyleSheet("""
            QGroupBox {
                border: 1px solid #1E3A5F; border-radius: 4px;
                margin-top: 14px; padding: 12px;
                font-size: 11px; color: #2A6A5A; letter-spacing: 3px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 8px;
            }
        """)
        return g

    def _apply(self):
        cfg.RECOGNITION_THRESHOLD       = self._thresh.value()
        cfg.GROUP_RECOGNITION_THRESHOLD = self._group_thresh.value()
        cfg.KNN_MARGIN                  = self._margin.value()
        cfg.ATTENDANCE_COOLDOWN         = self._cooldown.value()
        cfg.FRAME_SKIP                  = self._frame_skip.value()
        cfg.RECOGNITION_FPS_CAP         = self._fps_cap.value()
        QMessageBox.information(self, "Settings", "Settings applied successfully.")
        logger.info("Settings updated by admin %s", self._profile.login_id)