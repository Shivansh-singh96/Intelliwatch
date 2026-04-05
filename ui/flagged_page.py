"""
ui/flagged_page.py
───────────────────
FlaggedPage — security watchlist.
Admin : full CRUD (add, remove, view all).
User  : read-only view.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QLineEdit, QComboBox,
    QFormLayout, QDialogButtonBox, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QColor

logger = logging.getLogger(__name__)

_LEVEL_COLORS = {
    "High":   "#FF3B3B",
    "Medium": "#FF9500",
    "Low":    "#FFD60A",
}


class _AddFlagDialog(QDialog):
    def __init__(self, known_students: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to Security Watchlist")
        self.setMinimumWidth(360)
        self.setStyleSheet(
            "QDialog { background-color: #0A0E17; border: 1px solid #1E3A5F; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)
        lay.addWidget(QLabel("FLAG PROFILE FOR SECURITY WATCHLIST"))
        form = QFormLayout(); form.setSpacing(10)
        self._name = QComboBox(); self._name.setEditable(True)
        self._name.addItems(known_students); self._name.setFixedHeight(36)
        form.addRow("PROFILE ID / NAME", self._name)
        self._reason = QLineEdit(); self._reason.setFixedHeight(36)
        self._reason.setPlaceholderText("e.g. Trespassing, Suspicious activity")
        form.addRow("REASON", self._reason)
        self._level = QComboBox(); self._level.addItems(["High", "Medium", "Low"])
        self._level.setFixedHeight(36)
        form.addRow("THREAT LEVEL", self._level)
        lay.addLayout(form)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    @property
    def values(self):
        return (self._name.currentText().strip(),
                self._reason.text().strip(),
                self._level.currentText())


class FlaggedPage(QWidget):

    def __init__(self, flagged_manager, face_engine, profile=None, parent=None):
        super().__init__(parent)
        self._manager  = flagged_manager
        self._engine   = face_engine
        self._is_admin = (profile.role == "admin") if profile else True
        self._build_ui()
        self.load_records()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        hdr = QHBoxLayout()
        title = QLabel("SECURITY WATCHLIST")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #D8E8F4; letter-spacing: 3px;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        if not self._is_admin:
            badge = QLabel("⊘  VIEW ONLY")
            badge.setStyleSheet(
                "font-size: 12px; color: #FF9500; letter-spacing: 2px;"
                "background: #1A0E00; border: 1px solid #3A2000;"
                "border-radius: 3px; padding: 4px 10px;"
            )
            hdr.addWidget(badge)
        else:
            add_btn = QPushButton("⊕  FLAG PERSON")
            add_btn.setObjectName("dangerBtn")
            add_btn.setFixedHeight(34)
            add_btn.clicked.connect(self._add_flagged)
            hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        warn = QFrame()
        warn.setStyleSheet(
            "QFrame { background-color: #1A0808; border: 1px solid #3A1010;"
            "border-radius: 3px; }"
        )
        warn.setFixedHeight(36)
        wlay = QHBoxLayout(warn); wlay.setContentsMargins(12, 0, 12, 0)
        wlay.addWidget(QLabel("⚠"))
        w_lbl = QLabel("Persons on this list trigger an immediate alert when detected.")
        w_lbl.setStyleSheet("font-size: 13px; color: #FF4444;")
        wlay.addWidget(w_lbl); wlay.addStretch()
        lay.addWidget(warn)

        self._table = QTableWidget()
        cols = ["NAME / ID", "REASON", "THREAT LEVEL", "DATE ADDED"]
        if self._is_admin:
            cols.append("ACTIONS")
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.setShowGrid(False)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hv.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        if self._is_admin:
            hv.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._table, 1)

        self._count_lbl = QLabel("0 PERSONS FLAGGED")
        self._count_lbl.setStyleSheet("font-size: 12px; color: #3A6A8A; letter-spacing: 2px;")
        lay.addWidget(self._count_lbl)

    def load_records(self):
        records = self._manager.all_records()
        self._table.setRowCount(0)
        for row_idx, rec in enumerate(records):
            self._table.insertRow(row_idx)
            col = _LEVEL_COLORS.get(rec.level, "#C8D8E8")
            name_item = QTableWidgetItem(rec.name)
            name_item.setForeground(QColor(col))
            self._table.setItem(row_idx, 0, name_item)
            self._table.setItem(row_idx, 1, QTableWidgetItem(rec.reason))
            level_item = QTableWidgetItem(rec.level.upper())
            level_item.setForeground(QColor(col))
            self._table.setItem(row_idx, 2, level_item)
            self._table.setItem(row_idx, 3, QTableWidgetItem(rec.added_date))
            if self._is_admin:
                remove_btn = QPushButton("✖  REMOVE")
                remove_btn.setStyleSheet(
                    "QPushButton { background: #1A0808; color: #FF3B3B;"
                    "border: 1px solid #3A1010; border-radius: 3px;"
                    "padding: 4px 10px; font-size: 12px; }"
                    "QPushButton:hover { background: #FF3B3B; color: #000; }"
                )
                remove_btn.clicked.connect(lambda _, n=rec.name: self._remove_flagged(n))
                self._table.setCellWidget(row_idx, 4, remove_btn)

        n = len(records)
        self._count_lbl.setText(f"{n} PERSON{'S' if n != 1 else ''} FLAGGED")

    def _add_flagged(self):
        known = self._engine.student_names if self._engine.is_loaded else []
        dlg = _AddFlagDialog(known, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, reason, level = dlg.values
        if not name:
            return
        if not reason:
            QMessageBox.warning(self, "Validation", "Please provide a reason.")
            return
        ok = self._manager.add(name, reason, level)
        if ok:
            self.load_records()
        else:
            QMessageBox.information(self, "Already Flagged",
                                    f"'{name}' is already on the watchlist.")

    def _remove_flagged(self, name: str):
        reply = QMessageBox.question(
            self, "Remove Flag",
            f"Remove '{name}' from the security watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.remove(name)
            self.load_records()