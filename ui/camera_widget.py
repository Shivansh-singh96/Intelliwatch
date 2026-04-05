"""
ui/camera_widget.py
────────────────────
CameraWidget — displays live OpenCV frames in a QLabel.
"""

import logging
import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QColor, QPainter, QFont, QPen

logger = logging.getLogger(__name__)

# Camera resolution
_CAM_W, _CAM_H = 640, 480


class CameraWidget(QWidget):

    snapshot_taken = pyqtSignal(np.ndarray)

    def __init__(self, parent=None, show_controls=True):
        super().__init__(parent)

        self._latest_frame = None
        self._running = False
        self._show_controls = show_controls

        self._setup_ui()

    # ───────────────── UI ───────────────── #

    def _setup_ui(self):

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Camera display
        self._view = QLabel()
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Lock camera display size
        self._view.setFixedSize(_CAM_W, _CAM_H)

        self._view.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )

        self._view.setStyleSheet(
            "background:#060A10;"
            "border:1px solid #1E3A5F;"
        )

        layout.addWidget(self._view, alignment=Qt.AlignmentFlag.AlignCenter)

        self._show_placeholder()

        if self._show_controls:

            bar = QHBoxLayout()
            bar.setContentsMargins(0, 6, 0, 0)

            self._snap_btn = QPushButton("⬡  SNAPSHOT")
            self._snap_btn.setObjectName("ghostBtn")
            self._snap_btn.clicked.connect(self._take_snapshot)

            bar.addWidget(self._snap_btn)
            bar.addStretch()

            self._status_dot = QLabel("●")
            self._status_dot.setStyleSheet("color:#2A4A6A;font-size:10px;")

            self._status_lbl = QLabel("OFFLINE")

            bar.addWidget(self._status_dot)
            bar.addWidget(self._status_lbl)

            layout.addLayout(bar)

    # ───────────────── FRAME UPDATE ───────────────── #

    def update_frame(self, frame: np.ndarray):

        self._latest_frame = frame

        if not self._running:
            self._running = True
            self._set_status(True)

        h, w = frame.shape[:2]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        img = QImage(
            rgb.data,
            w,
            h,
            w * 3,
            QImage.Format.Format_RGB888
        ).copy()

        pix = QPixmap.fromImage(img)

        pix = pix.scaled(
            _CAM_W,
            _CAM_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self._view.setPixmap(pix)

    # ───────────────── OFFLINE ───────────────── #

    def set_offline(self, reason="OFFLINE"):

        self._running = False
        self._set_status(False, reason)
        self._show_placeholder()

    # ───────────────── STATUS ───────────────── #

    def _set_status(self, online, label=None):

        if not self._show_controls:
            return

        color = "#00C853" if online else "#2A4A6A"

        self._status_dot.setStyleSheet(
            f"color:{color};font-size:10px;"
        )

        self._status_lbl.setText(
            label if label else ("LIVE" if online else "OFFLINE")
        )

    # ───────────────── PLACEHOLDER ───────────────── #

    def _show_placeholder(self):

        pix = QPixmap(_CAM_W, _CAM_H)
        pix.fill(QColor("#060A10"))

        painter = QPainter(pix)

        painter.setPen(QPen(QColor("#1E3A5F"), 1))

        cx = pix.width() // 2
        cy = pix.height() // 2

        painter.drawLine(cx - 30, cy, cx + 30, cy)
        painter.drawLine(cx, cy - 30, cx, cy + 30)

        painter.drawEllipse(cx - 20, cy - 20, 40, 40)

        painter.setFont(QFont("Consolas", 9))
        painter.drawText(
            pix.rect(),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            "NO SIGNAL"
        )

        painter.end()

        self._view.setPixmap(pix)

    # ───────────────── SNAPSHOT ───────────────── #

    def _take_snapshot(self):

        if self._latest_frame is None:
            return

        self.snapshot_taken.emit(self._latest_frame.copy())

        self._view.setStyleSheet(
            "background:#060A10;border:1px solid #00C853;"
        )

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(
            200,
            lambda: self._view.setStyleSheet(
                "background:#060A10;border:1px solid #1E3A5F;"
            )
        )

    # ───────────────── UTILITY ───────────────── #

    @staticmethod
    def frame_to_pixmap(frame: np.ndarray, w: int, h: int):

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        fh, fw = rgb.shape[:2]

        img = QImage(
            rgb.data,
            fw,
            fh,
            fw * 3,
            QImage.Format.Format_RGB888
        ).copy()

        pix = QPixmap.fromImage(img)

        return pix.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )