"""
ui/live_recognition_page.py
────────────────────────────
LiveRecognitionPage — live webcam face recognition panel.

Layout:
  Left  : CameraWidget (live feed)
  Right : Real-time recognition log + controls
"""

import logging
from datetime import datetime

import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QListWidget, QListWidgetItem, QSizePolicy,
    QSplitter,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui  import QColor

from ui.camera_widget  import CameraWidget
from ui.alert_dialog   import DangerAlertDialog

logger = logging.getLogger(__name__)


class _LogItem(QListWidgetItem):
    def __init__(self, name: str, confidence: float,
                 flagged: bool = False, already_marked: bool = False):
        ts = datetime.now().strftime("%H:%M:%S")
        if flagged:
            icon, col, suffix = "⚑", "#FF3B3B", ""
        elif already_marked:
            icon, col, suffix = "✓", "#3A8ABF", "  [already marked]"
        else:
            icon, col, suffix = "✓", "#00C853", "  [marked]"
        super().__init__(f"  {icon}  {name}   {confidence:.0%}   {ts}{suffix}")
        self.setForeground(QColor(col))


class LiveRecognitionPage(QWidget):

    def __init__(self, camera_thread, flagged_manager,
                 attendance_manager, parent=None):
        super().__init__(parent)
        self._cam_thread = camera_thread
        self._flagged    = flagged_manager
        self._attendance = attendance_manager
        self._running    = False
        self._last_alert: dict[str, float] = {}

        self._build_ui()
        self._connect_thread()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("LIVE RECOGNITION")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #C8D8E8;"
            "letter-spacing: 3px;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("font-size: 12px; color: #2A4A6A;")
        hdr.addWidget(self._status_dot)

        self._status_lbl = QLabel("CAMERA OFFLINE")
        self._status_lbl.setStyleSheet(
            "font-size: 10px; color: #2A4A6A; letter-spacing: 2px;"
        )
        hdr.addWidget(self._status_lbl)
        lay.addLayout(hdr)

        # Main content: camera | log
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #1E3A5F; width: 1px; }")

        # Left: camera
        left = QWidget()
        left.setStyleSheet("background: transparent;")
        llayout = QVBoxLayout(left)
        llayout.setContentsMargins(0, 0, 0, 0)
        llayout.setSpacing(8)

        self._cam_widget = CameraWidget(show_controls=True)
        llayout.addWidget(self._cam_widget)

        # Control buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._start_btn = QPushButton("▶  START RECOGNITION")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.setFixedHeight(38)
        self._start_btn.clicked.connect(self._toggle_camera)
        btn_row.addWidget(self._start_btn)

        self._clear_btn = QPushButton("⌫  CLEAR LOG")
        self._clear_btn.setObjectName("ghostBtn")
        self._clear_btn.setFixedHeight(38)
        self._clear_btn.clicked.connect(self._clear_log)
        btn_row.addWidget(self._clear_btn)

        llayout.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: recognition log
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        rlayout = QVBoxLayout(right)
        rlayout.setContentsMargins(12, 0, 0, 0)
        rlayout.setSpacing(8)

        log_hdr = QLabel("RECOGNITION LOG")
        log_hdr.setStyleSheet(
            "font-size: 9px; color: #1E4A3A; letter-spacing: 3px;"
        )
        rlayout.addWidget(log_hdr)

        self._log_list = QListWidget()
        self._log_list.setStyleSheet(
            "QListWidget { font-size: 12px; font-family: 'Consolas', monospace; }"
            "QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #0F1A27; }"
        )
        rlayout.addWidget(self._log_list)

        # Stats row
        stats_row = QHBoxLayout()
        self._total_lbl    = QLabel("TOTAL: 0")
        self._flagged_lbl  = QLabel("ALERTS: 0")
        for lbl, col in [
            (self._total_lbl, "#2A5A7A"),
            (self._flagged_lbl, "#FF3B3B"),
        ]:
            lbl.setStyleSheet(
                f"font-size: 9px; color: {col}; letter-spacing: 2px;"
            )
            stats_row.addWidget(lbl)
        stats_row.addStretch()
        rlayout.addLayout(stats_row)

        splitter.addWidget(right)
        splitter.setSizes([700, 300])
        lay.addWidget(splitter, 1)

    # ── Thread wiring ─────────────────────────────────────────────────────────

    def _connect_thread(self):
        self._cam_thread.frame_ready.connect(self._cam_widget.update_frame)
        self._cam_thread.recognized.connect(self._on_recognized)
        self._cam_thread.flagged_detected.connect(self._on_flagged)
        self._cam_thread.status_update.connect(self._on_status)
        self._cam_thread.error.connect(self._on_error)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(str, float, bool)
    def _on_recognized(self, name: str, confidence: float, already_marked: bool):
        item = _LogItem(name, confidence, flagged=False, already_marked=already_marked)
        self._log_list.insertItem(0, item)
        if self._log_list.count() > 200:
            self._log_list.takeItem(self._log_list.count() - 1)
        self._update_stats()

    @pyqtSlot(str, object, object)
    def _on_flagged(self, name: str, record, frame):

        now = datetime.now().timestamp()
        if name in self._last_alert and now - self._last_alert[name] < 10:
            return
        self._last_alert[name] = now

        item = _LogItem(name, 1.0, flagged=True)
        self._log_list.insertItem(0, item)
        self._update_stats()

        snap = frame if frame is not None else getattr(self._cam_widget, "_latest_frame", None)

        dlg = DangerAlertDialog(
            person_name=name,
            record=record,
            snapshot=snap,
            parent=self
        )

        dlg.dismissed.connect(self._on_security_contacted)
        dlg.show()

    @pyqtSlot(str)
    def _on_status(self, msg: str):
        online = "ONLINE" in msg.upper()
        self._status_dot.setStyleSheet(
            f"font-size: 12px; color: {'#00C853' if online else '#2A4A6A'};"
        )
        self._status_lbl.setText(msg)
        if not online:
            self._cam_widget.set_offline(msg)

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self._on_status(f"ERROR: {msg}")
        self._running = False
        self._start_btn.setText("▶  START RECOGNITION")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)

    def _on_security_contacted(self, name: str):
        self._flagged.log_security_call(name)

    # ── Controls ──────────────────────────────────────────────────────────────

    def showEvent(self, event):
        """Auto-start camera when navigating to this page."""
        super().showEvent(event)
        if not self._running:
            self._start_camera()

    def hideEvent(self, event):
        """Pause camera when leaving this page to save resources."""
        super().hideEvent(event)
        if self._running:
            self._stop_camera()

    def _toggle_camera(self):
        if not self._running:
            self._start_camera()
        else:
            self._stop_camera()

    def _start_camera(self):
        if not self._cam_thread.isRunning():
            self._cam_thread.start()
        else:
            self._cam_thread.resume()
        self._running = True
        self._start_btn.setText("⬛  STOP RECOGNITION")
        self._start_btn.setObjectName("dangerBtn")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)

    def _stop_camera(self):
        self._cam_thread.pause()
        # Cancel any in-flight recognition job so it can't fire signals after stop
        if self._cam_thread._pending and not self._cam_thread._pending.done():
            self._cam_thread._pending.cancel()
            self._cam_thread._pending = None
        self._running = False
        self._start_btn.setText("▶  START RECOGNITION")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)
        self._cam_widget.set_offline("PAUSED")

    def _clear_log(self):
        self._log_list.clear()
        self._update_stats()

    def _update_stats(self):
        total   = self._log_list.count()
        alerts  = sum(
            1 for i in range(total)
            if self._log_list.item(i).foreground().color() == QColor("#FF3B3B")
        )
        self._total_lbl.setText(f"TOTAL: {total}")
        self._flagged_lbl.setText(f"ALERTS: {alerts}")