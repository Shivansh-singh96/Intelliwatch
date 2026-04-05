"""
ui/alert_dialog.py
───────────────────
SecurityAlertDialog — full-featured flagged-person alert popup.

Features
--------
• Threat level colour coding  RED=High  ORANGE=Medium  YELLOW=Low
• Snapshot display (live frame captured at detection moment)
• Snapshot auto-saved to Debug/alerts/<timestamp>_<name>.jpg
• [View Details] expander  /  [Dismiss] button
• Flashing border animation
• Alert history persisted to Debug/alert_history.csv
• Auto-dismiss countdown (configurable)
"""

import csv
import logging
import os
from datetime import datetime

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui  import QPixmap, QImage, QColor

import modules.config as cfg

logger = logging.getLogger(__name__)

# ── Threat colour map ─────────────────────────────────────────────────────────
LEVEL_COLORS = {
    "High":   "#FF3B3B",   # RED
    "Medium": "#FF9500",   # ORANGE
    "Low":    "#FFD60A",   # YELLOW
}
LEVEL_BG = {
    "High":   "#2A0000",
    "Medium": "#2A1400",
    "Low":    "#1A1800",
}

# ── Alert history CSV ─────────────────────────────────────────────────────────
ALERT_HISTORY_CSV = os.path.join(cfg.BASE_DIR, "Debug", "alert_history.csv")
ALERT_SNAP_DIR    = os.path.join(cfg.BASE_DIR, "Debug", "alerts")


def _ensure_history_file():
    os.makedirs(os.path.dirname(ALERT_HISTORY_CSV), exist_ok=True)
    if not os.path.exists(ALERT_HISTORY_CSV):
        with open(ALERT_HISTORY_CSV, "w", newline="") as fh:
            csv.writer(fh).writerow(
                ["Timestamp", "Name", "Level", "Reason", "Snapshot", "Action"])


def log_alert_history(name: str, level: str, reason: str,
                      snap_path: str = "", action: str = "Alert Shown"):
    _ensure_history_file()
    try:
        with open(ALERT_HISTORY_CSV, "a", newline="") as fh:
            csv.writer(fh).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                name, level, reason, snap_path, action,
            ])
    except Exception as exc:
        logger.warning("alert_history write failed: %s", exc)


def save_snapshot(frame_bgr: np.ndarray, name: str) -> str:
    """Save snapshot, return file path (empty string on failure)."""
    try:
        os.makedirs(ALERT_SNAP_DIR, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = name.replace("/", "_").replace("\\", "_")
        path = os.path.join(ALERT_SNAP_DIR, f"{ts}_{safe}.jpg")
        cv2.imwrite(path, frame_bgr)
        return path
    except Exception as exc:
        logger.warning("snapshot save failed: %s", exc)
        return ""


def _bgr_to_pixmap(frame_bgr: np.ndarray, w: int, h: int) -> QPixmap:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = QImage(rgb.data, rgb.shape[1], rgb.shape[0],
                 rgb.shape[1] * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img).scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


# ── Main dialog ───────────────────────────────────────────────────────────────

class SecurityAlertDialog(QDialog):
    """
    Replaces DangerAlertDialog.

    Parameters
    ----------
    person_name  : str
    record       : DangerRecord | None
    snapshot     : np.ndarray BGR | None   — live frame at detection
    auto_dismiss : int seconds (0 = no auto-dismiss)
    """

    dismissed = pyqtSignal(str)   # emits person name on any close

    def __init__(self, person_name: str, record=None,
                 snapshot: np.ndarray | None = None,
                 auto_dismiss: int = 60,
                 parent=None):
        super().__init__(parent)

        self._name    = person_name
        self._record  = record
        self._snap    = snapshot
        self._level   = getattr(record, "level",  "High")
        self._reason  = getattr(record, "reason", "Unknown")
        self._color   = LEVEL_COLORS.get(self._level, "#FF3B3B")
        self._bg      = LEVEL_BG.get(self._level, "#2A0000")
        self._snap_path = ""
        self._details_visible = False
        self._countdown = auto_dismiss

        # Save snapshot to disk
        if self._snap is not None:
            self._snap_path = save_snapshot(self._snap, person_name)

        self.setWindowTitle("⚠  SECURITY ALERT")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self._build_ui()
        # Lock to fixed size AFTER building UI — prevents runaway minimum-size growth
        self.setFixedSize(520, self.sizeHint().height())
        self._start_flash()
        if auto_dismiss > 0:
            self._start_countdown(auto_dismiss)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._apply_style(self._color)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Coloured header bar ────────────────────────────────────────────
        self._header_frame = QFrame()
        self._header_frame.setStyleSheet(
            f"background: {self._color}; border-radius: 0px;")
        self._header_frame.setFixedHeight(56)
        hlay = QHBoxLayout(self._header_frame)
        hlay.setContentsMargins(18, 0, 18, 0)

        icon_lbl = QLabel("⚠")
        icon_lbl.setStyleSheet(
            "font-size: 24px; color: #000; background: transparent;")
        hlay.addWidget(icon_lbl)

        title_lbl = QLabel("  SECURITY ALERT")
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #000;"
            "letter-spacing: 4px; background: transparent;")
        hlay.addWidget(title_lbl, 1)

        badge = QLabel(f" {self._level.upper()} THREAT ")
        badge.setStyleSheet(
            "background: rgba(0,0,0,0.35); color: #000;"
            "font-size: 12px; font-weight: bold; border-radius: 4px;"
            "padding: 4px 10px; letter-spacing: 2px;")
        hlay.addWidget(badge)
        root.addWidget(self._header_frame)

        # ── Main body ─────────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(20, 18, 20, 10)
        body.setSpacing(18)

        # Snapshot
        self._snap_lbl = QLabel()
        self._snap_lbl.setFixedSize(160, 120)
        self._snap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_lbl.setStyleSheet(
            f"border: 2px solid {self._color}; border-radius: 4px;"
            "background: #060A10;")
        if self._snap is not None:
            self._snap_lbl.setPixmap(_bgr_to_pixmap(self._snap, 160, 120))
        else:
            self._snap_lbl.setText("No\nSnapshot")
            self._snap_lbl.setStyleSheet(
                self._snap_lbl.styleSheet() +
                "color: #2A4A6A; font-size: 11px;")
        body.addWidget(self._snap_lbl)

        # Info
        info = QVBoxLayout()
        info.setSpacing(8)

        def _field(label: str, value: str, val_color: str = "#C8D8E8"):
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "font-size: 11px; color: #3A6A8A; letter-spacing: 2px;"
                "background: transparent;")
            val = QLabel(value)
            val.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {val_color};"
                "background: transparent; letter-spacing: 1px;")
            val.setWordWrap(True)
            info.addWidget(lbl)
            info.addWidget(val)

        _field("⚠  PERSON",       self._name,   self._color)
        info.addSpacing(2)
        _field("THREAT LEVEL",    self._level.upper(), self._color)
        info.addSpacing(2)
        _field("REASON",          self._reason)
        info.addStretch()
        body.addLayout(info, 1)
        root.addLayout(body)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self._bg};")
        root.addWidget(sep)

        # ── Details panel (hidden by default) ─────────────────────────────
        self._details_panel = QWidget()
        dlay = QVBoxLayout(self._details_panel)
        dlay.setContentsMargins(20, 10, 20, 4)
        dlay.setSpacing(4)

        if self._snap_path:
            path_lbl = QLabel(f"📷  Snapshot: {os.path.basename(self._snap_path)}")
            path_lbl.setStyleSheet("font-size: 11px; color: #2A5A7A;")
            path_lbl.setWordWrap(True)
            dlay.addWidget(path_lbl)

        hist_lbl = QLabel(f"📋  Alert logged to: {os.path.basename(ALERT_HISTORY_CSV)}")
        hist_lbl.setStyleSheet("font-size: 11px; color: #2A5A7A;")
        dlay.addWidget(hist_lbl)

        added = getattr(self._record, "added_date", "")
        if added:
            date_lbl = QLabel(f"🗓  Flagged since: {added}")
            date_lbl.setStyleSheet("font-size: 11px; color: #2A5A7A;")
            dlay.addWidget(date_lbl)

        self._details_panel.hide()
        root.addWidget(self._details_panel)

        # ── Countdown ─────────────────────────────────────────────────────
        self._countdown_lbl = QLabel("")
        self._countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._countdown_lbl.setStyleSheet(
            "font-size: 11px; color: #2A4A6A; letter-spacing: 2px;"
            "background: transparent; padding: 4px 0;")
        root.addWidget(self._countdown_lbl)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 0, 20, 18)
        btn_row.setSpacing(10)

        self._details_btn = QPushButton("🔍  View Details")
        self._details_btn.setFixedHeight(38)
        self._details_btn.setStyleSheet(
            f"QPushButton{{background:#0F1520;color:{self._color};"
            f"border:1px solid {self._color};border-radius:4px;"
            f"font-size:11px;font-weight:bold;padding:0 14px;}}"
            f"QPushButton:hover{{background:{self._bg};}}")
        self._details_btn.clicked.connect(self._toggle_details)
        btn_row.addWidget(self._details_btn)

        dismiss_btn = QPushButton("✕  Dismiss")
        dismiss_btn.setFixedHeight(38)
        dismiss_btn.setStyleSheet(
            "QPushButton{background:#0F1520;color:#C8D8E8;"
            "border:1px solid #1E3A5F;border-radius:4px;"
            "font-size:11px;padding:0 14px;}"
            "QPushButton:hover{background:#1E3A5F;}")
        dismiss_btn.clicked.connect(self._on_dismiss)
        btn_row.addWidget(dismiss_btn)
        root.addLayout(btn_row)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_details(self):
        self._details_visible = not self._details_visible
        self._details_panel.setVisible(self._details_visible)
        self._details_btn.setText(
            "🔼  Hide Details" if self._details_visible else "🔍  View Details")
        self.adjustSize()

    def _on_dismiss(self):
        log_alert_history(self._name, self._level, self._reason,
                          self._snap_path, "Dismissed")
        self.dismissed.emit(self._name)
        self.accept()

    # ── Flash ─────────────────────────────────────────────────────────────────

    def _apply_style(self, border_color: str):
        # Only flash the header background — avoids triggering full relayout
        if hasattr(self, "_header_frame"):
            self._header_frame.setStyleSheet(
                f"background: {border_color}; border-radius: 0px;"
            )

    def _start_flash(self):
        self._flash_on = True
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_tick)
        self._flash_timer.start(500)

    def _flash_tick(self):
        self._flash_on = not self._flash_on
        self._apply_style(self._color if self._flash_on else self._bg)

    # ── Countdown ─────────────────────────────────────────────────────────────

    def _start_countdown(self, secs: int):
        self._countdown = secs
        self._cd_timer = QTimer(self)
        self._cd_timer.timeout.connect(self._cd_tick)
        self._cd_timer.start(1000)
        self._countdown_lbl.setText(f"AUTO-DISMISS IN {secs}s")

    def _cd_tick(self):
        self._countdown -= 1
        self._countdown_lbl.setText(f"AUTO-DISMISS IN {self._countdown}s")
        if self._countdown <= 0:
            self._on_dismiss()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        for attr in ("_flash_timer", "_cd_timer"):
            t = getattr(self, attr, None)
            if t:
                t.stop()
        super().closeEvent(event)


# Keep old name as alias so existing imports don't break
DangerAlertDialog = SecurityAlertDialog