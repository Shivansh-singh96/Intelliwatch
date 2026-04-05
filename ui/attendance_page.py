"""
ui/attendance_page.py
──────────────────────
AttendancePage — view, search, and export attendance records.

Admin : sees ALL records, can mark manually for any student.
User  : sees ONLY their own records.
"""

import csv
import logging
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QLineEdit,
    QHeaderView, QFileDialog, QAbstractItemView,
    QComboBox, QInputDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui  import QColor
from modules.flagged_manager import FlaggedManager

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "Present": "#00C853",
    "Late":    "#FF9500",
    "Unknown": "#2A4A6A",
}


class AttendancePage(QWidget):

    def __init__(self, attendance_manager, profile, parent=None):
        super().__init__(parent)
        self._manager  = attendance_manager
        self._flagged  = FlaggedManager()
        self._flagged.load()
        self._profile  = profile
        self._is_admin = (profile.role == "admin")
        self._all_records: list = []
        self._build_ui()
        self.load_records()

        self._auto_refresh = QTimer(self)
        self._auto_refresh.timeout.connect(self.load_records)
        self._auto_refresh.start(30_000)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("ATTENDANCE LOG")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #D8E8F4;"
            "letter-spacing: 3px;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        if not self._is_admin:
            badge = QLabel(f"VIEWING: {self._profile.login_id.upper()}")
            badge.setStyleSheet(
                "font-size: 12px; color: #00C853; letter-spacing: 2px;"
                "background: #0A1A0A; border: 1px solid #1A3A1A;"
                "border-radius: 3px; padding: 4px 10px;"
            )
            hdr.addWidget(badge)

        self._count_lbl = QLabel("0 RECORDS")
        self._count_lbl.setStyleSheet(
            "font-size: 12px; color: #3A7A9A; letter-spacing: 2px;"
        )
        hdr.addWidget(self._count_lbl)
        lay.addLayout(hdr)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        if self._is_admin:
            self._search = QLineEdit()
            self._search.setPlaceholderText("Search by name or ID...")
            self._search.setFixedHeight(36)
            self._search.textChanged.connect(self._apply_filter)
            toolbar.addWidget(self._search, 2)

        self._date_filter = QComboBox()
        self._date_filter.setFixedHeight(36)
        self._date_filter.setFixedWidth(140)
        self._date_filter.addItems(["Today", "All Records"])
        self._date_filter.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self._date_filter)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setObjectName("ghostBtn")
        refresh_btn.setFixedSize(36, 36)
        refresh_btn.clicked.connect(self.load_records)
        toolbar.addWidget(refresh_btn)

        if self._is_admin:
            manual_btn = QPushButton("✚  MARK MANUAL")
            manual_btn.setObjectName("primaryBtn")
            manual_btn.setFixedHeight(36)
            manual_btn.clicked.connect(self._manual_mark)
            toolbar.addWidget(manual_btn)

        export_btn = QPushButton("⬇  EXPORT CSV")
        export_btn.setObjectName("ghostBtn")
        export_btn.setFixedHeight(36)
        export_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_btn)

        lay.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["PROFILE NAME", "PROFILE ID", "TIME", "STATUS"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setShowGrid(False)
        lay.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setStyleSheet(
            "font-size: 11px; color: #2A4A6A; letter-spacing: 2px;"
        )
        lay.addWidget(self._summary)

    def load_records(self):
        self._all_records = self._manager.get_all()
        # Non-admin: filter to own records only
        if not self._is_admin:
            uid = self._profile.login_id.lower()
            self._all_records = [
                r for r in self._all_records
                if r["Name"].lower() == uid
            ]
        self._apply_filter()

    def _apply_filter(self):
        query     = self._search.text().strip().lower() if self._is_admin and hasattr(self, "_search") else ""
        today_only = self._date_filter.currentIndex() == 0
        today_str  = datetime.now().strftime("%Y-%m-%d")

        filtered = []
        for rec in self._all_records:
            name     = rec["Name"]
            time_str = rec["Time"]
            if today_only and not time_str.startswith(today_str):
                continue
            if query and query not in name.lower():
                continue
            filtered.append(rec)

        self._populate_table(filtered)

    def _populate_table(self, records: list):
        self._table.setRowCount(0)
        for row_idx, rec in enumerate(records):
            self._table.insertRow(row_idx)
            name     = rec["Name"]
            time_str = rec["Time"]
            try:
                dt     = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                status = "Present"
            except ValueError:
                status = "Unknown"
            col = _STATUS_COLORS.get(status, _STATUS_COLORS["Unknown"])
            items = [
                QTableWidgetItem(name),
                QTableWidgetItem(name),
                QTableWidgetItem(time_str),
                QTableWidgetItem(status),
            ]
            for ci, item in enumerate(items):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if ci == 3:
                    item.setForeground(QColor(col))
                self._table.setItem(row_idx, ci, item)

        n = len(records)
        self._count_lbl.setText(f"{n} RECORDS")
        self._summary.setText(
            f"SHOWING {n} OF {len(self._all_records)} RECORDS  ·  AUTO-REFRESH EVERY 30s"
        )

    def _manual_mark(self):
        known = sorted({r["Name"] for r in self._manager.get_all()})
        name, ok = QInputDialog.getItem(
            self, "Manual Attendance", "Enter or select profile name / ID:",
            known, editable=True,
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # Block flagged persons
        if self._flagged.is_flagged(name):
            record = self._flagged.get(name)
            QMessageBox.critical(self, "⚑ SECURITY ALERT",
                f"FLAGGED PERSON — ATTENDANCE BLOCKED\n\n"
                f"Name   : {name}\n"
                f"Reason : {record.reason if record else 'Unknown'}\n"
                f"Level  : {record.level if record else 'Unknown'}\n\n"
                f"Attendance cannot be marked for a flagged person.\n"
                f"Notify security immediately.")
            self._flagged.log_detection(name, 1.0, action="Manual Mark Attempted")
            return

        if self._manager.already_marked(name):
            msg = f"'{name}' was already marked recently. Force mark again?"
            reply = QMessageBox.question(self, "Already Marked", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._manager.mark_force(name)
            else:
                return
        else:
            self._manager.mark(name)
        self.load_records()
        QMessageBox.information(self, "Attendance Marked",
            f"Attendance recorded for: {name}")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Attendance", "attendance_export.csv",
            "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Profile Name", "Profile ID", "Time", "Status"])
                for row in range(self._table.rowCount()):
                    writer.writerow([
                        self._table.item(row, c).text()
                        for c in range(self._table.columnCount())
                    ])
        except Exception as exc:
            logger.error("Export failed: %s", exc)