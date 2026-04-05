"""
ui/sidebar.py — Role-based navigation sidebar.

Admin : Dashboard · Live Feed · Attendance · Flagged · Settings · Admin Panel
User  : Dashboard · Attendance (own) · Flagged (view) · Settings (profile)
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

logger = logging.getLogger(__name__)

# (page_index, icon, label, tooltip)
_ADMIN_ITEMS = [
    (0, "⬡", "DASHBOARD",    "Overview & metrics"),
    (1, "◉", "LIVE FEED",    "Real-time recognition"),
    (2, "≡", "ATTENDANCE",   "All attendance records"),
    (3, "⚑", "FLAGGED",      "Security watchlist"),
    (4, "⚙", "SETTINGS",     "System configuration"),
    (5, "⊕", "ADMIN PANEL",  "User & profile management"),
]

_USER_ITEMS = [
    (0, "⬡", "DASHBOARD",   "Your overview"),
    (1, "≡", "ATTENDANCE",  "Your attendance"),
    (2, "⚑", "FLAGGED",     "Security watchlist"),
    (3, "⚙", "MY PROFILE",  "Your profile info"),
]


class NavButton(QPushButton):
    def __init__(self, icon: str, text: str, tooltip: str, idx: int):
        super().__init__()
        self._idx = idx
        self.setCheckable(False)
        self.setFixedHeight(54)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(tooltip)

        inner = QHBoxLayout(self)
        inner.setContentsMargins(16, 0, 16, 0)
        inner.setSpacing(12)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet("font-size: 17px; color: #3A6A9A; background: transparent;")
        self._icon_lbl.setFixedWidth(20)
        inner.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(text)
        self._text_lbl.setStyleSheet("font-size: 12px; color: #3A6A9A; letter-spacing: 2px; background: transparent;")
        inner.addWidget(self._text_lbl, 1)

        self._bar = QFrame()
        self._bar.setFixedWidth(3)
        self._bar.setStyleSheet("background: transparent; border-radius: 1px;")
        inner.addWidget(self._bar)

        self._apply_style(False)

    @property
    def index(self): return self._idx

    def set_active(self, active: bool):
        self._apply_style(active)

    def _apply_style(self, active: bool):
        if active:
            self.setStyleSheet("QPushButton { background-color: #0A2A1A; border: none; } QPushButton:hover { background-color: #0C3020; }")
            self._icon_lbl.setStyleSheet("font-size: 17px; color: #00C853; background: transparent;")
            self._text_lbl.setStyleSheet("font-size: 12px; color: #00C853; letter-spacing: 2px; background: transparent; font-weight: bold;")
            self._bar.setStyleSheet("background: #00C853; border-radius: 1px;")
        else:
            self.setStyleSheet("QPushButton { background-color: transparent; border: none; } QPushButton:hover { background-color: #0F1A27; }")
            self._icon_lbl.setStyleSheet("font-size: 17px; color: #3A6A9A; background: transparent;")
            self._text_lbl.setStyleSheet("font-size: 12px; color: #3A6A9A; letter-spacing: 2px; background: transparent;")
            self._bar.setStyleSheet("background: transparent; border-radius: 1px;")


class Sidebar(QWidget):
    page_changed = pyqtSignal(int)

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self._profile  = profile
        self._is_admin = (profile.role == "admin")
        self._buttons: list[NavButton] = []

        self.setFixedWidth(200)
        self.setStyleSheet("background-color: #060A10; border-right: 1px solid #0F1A27;")
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Logo
        logo_area = QWidget(); logo_area.setFixedHeight(80)
        logo_area.setStyleSheet("background-color: #03070D;")
        llay = QVBoxLayout(logo_area); llay.setContentsMargins(16, 14, 16, 14)
        logo = QLabel("IntelliWatch")
        logo.setStyleSheet("font-size: 16px; font-weight: bold; color: #00C853; letter-spacing: 2px;")
        llay.addWidget(logo)
        sub = QLabel("VISION SECURITY")
        sub.setStyleSheet("font-size: 12px; color: #2A5A7A; letter-spacing: 3px;")
        llay.addWidget(sub)
        lay.addWidget(logo_area)

        sec = QLabel("  NAVIGATION"); sec.setFixedHeight(28)
        sec.setStyleSheet("font-size: 11px; color: #2A5A7A; letter-spacing: 3px; background-color: #03070D; padding-left: 16px;")
        lay.addWidget(sec)

        items = _ADMIN_ITEMS if self._is_admin else _USER_ITEMS
        for idx, icon, text, tooltip in items:
            btn = NavButton(icon, text, tooltip, idx)
            btn.clicked.connect(lambda _, b=btn: self._on_nav_click(b))
            self._buttons.append(btn)
            lay.addWidget(btn)

        lay.addStretch()

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background-color: #0F1A27; max-height: 1px;")
        lay.addWidget(div)

        user_panel = QWidget(); user_panel.setFixedHeight(72)
        user_panel.setStyleSheet("background-color: #03070D;")
        ulay = QVBoxLayout(user_panel); ulay.setContentsMargins(16, 12, 16, 12); ulay.setSpacing(2)
        name_lbl = QLabel(self._profile.full_name or self._profile.login_id)
        name_lbl.setStyleSheet("font-size: 13px; color: #D8E8F4; font-weight: bold;")
        name_lbl.setWordWrap(True); ulay.addWidget(name_lbl)
        role_col = "#00C853" if self._is_admin else "#3A6A8A"
        role_lbl = QLabel(self._profile.role.upper())
        role_lbl.setStyleSheet(f"font-size: 11px; color: {role_col}; letter-spacing: 3px;")
        ulay.addWidget(role_lbl)
        lay.addWidget(user_panel)

        if self._buttons:
            self._buttons[0].set_active(True)

    def _on_nav_click(self, btn: NavButton):
        for b in self._buttons:
            b.set_active(b is btn)
        self.page_changed.emit(btn.index)

    def set_active(self, idx: int):
        for b in self._buttons:
            b.set_active(b.index == idx)