"""
ui/login_window.py
───────────────────
LoginWindow — Full-screen, resolution-aware login screen.

Design: industrial-tactical operator interface.
• Animated scan-line grid background
• Split layout: left brand panel | right auth card
• Role buttons: USER / ADMIN
• On success → calls on_success(role, profile)
"""

import logging

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QSizePolicy,
    QGraphicsOpacityEffect, QApplication,
)
from PyQt6.QtCore    import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect,
)
from PyQt6.QtGui     import (
    QColor, QPainter, QPen, QFont, QPixmap, QLinearGradient, QBrush,
    QKeySequence,
)

from services.auth_service import get_auth, AuthError

logger = logging.getLogger(__name__)


class _ScanlineBackground(QWidget):
    """Animated grid background — pure QPainter, no images needed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)

    def _tick(self):
        self._offset = (self._offset + 1) % 40
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()

        # Background gradient
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor("#060A12"))
        grad.setColorAt(1.0, QColor("#030608"))
        p.fillRect(0, 0, w, h, grad)

        # Grid lines
        pen = QPen(QColor(30, 60, 90, 60), 1)
        p.setPen(pen)
        step = 40
        off  = self._offset
        for x in range(-step, w + step, step):
            p.drawLine(x, 0, x, h)
        for y in range((-step + off) % step - step, h + step, step):
            p.drawLine(0, y, w, y)

        # Diagonal accent lines (top-left corner)
        pen2 = QPen(QColor(0, 200, 83, 15), 1)
        p.setPen(pen2)
        for i in range(0, 400, 20):
            p.drawLine(0, i, i, 0)

        p.end()


class LoginWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._auth = get_auth()
        self._main_window = None

        self.setWindowTitle("IntelliWatch — Authentication")
        self.setMinimumSize(1000, 650)
        self.showMaximized()

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Animated background as central widget
        bg = _ScanlineBackground(self)
        self.setCentralWidget(bg)

        root = QHBoxLayout(bg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_brand_panel(), 55)
        root.addWidget(self._build_auth_card(),   45)

    # ── Brand panel (left) ────────────────────────────────────────────────────

    def _build_brand_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(60, 60, 40, 60)
        layout.setSpacing(0)

        # Corner badge
        badge = QLabel("[ CLASSIFIED SYSTEM ]")
        badge.setStyleSheet(
            "font-size: 11px; color: #2A5A7A; letter-spacing: 3px;"
            "background: transparent;"
        )
        layout.addWidget(badge)
        layout.addSpacing(40)

        # System tag
        tag = QLabel("IntelliWatch")
        tag.setStyleSheet(
            "font-size: 58px; font-weight: bold; color: #00C853;"
            "letter-spacing: -2px; background: transparent;"
            "font-family: 'Consolas', monospace;"
        )
        layout.addWidget(tag)

        sub = QLabel("AI-Powered Vision Security\n& Recognition")
        sub.setStyleSheet(
            "font-size: 15px; color: #3A7A9A; letter-spacing: 3px;"
            "line-height: 1.8; background: transparent;"
        )
        layout.addWidget(sub)
        layout.addSpacing(40)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #1E3A5F; max-height: 1px;")
        layout.addWidget(line)
        layout.addSpacing(32)

        # Feature list
        for txt in [
            "◈  ArcFace neural recognition",
            "◈  Real-time threat detection",
            "◈  Automated attendance logging",
            "◈  Multi-user secure access",
            "◈  Firebase cloud sync",
        ]:
            lbl = QLabel(txt)
            lbl.setStyleSheet(
                "font-size: 12px; color: #3A6A8A; letter-spacing: 1px;"
                "background: transparent; padding: 4px 0;"
            )
            layout.addWidget(lbl)

        layout.addStretch()

        version = QLabel("v2.0.0  ·  PyQt6  ·  ArcFace  ·  IntelliWatch")
        version.setStyleSheet(
            "font-size: 11px; color: #1E3A5F; letter-spacing: 2px;"
            "background: transparent;"
        )
        layout.addWidget(version)
        return panel

    # ── Auth card (right) ─────────────────────────────────────────────────────

    def _build_auth_card(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 18, 30, 0.92);
                border: 1px solid #1E3A5F;
                border-radius: 6px;
            }
        """)
        card.setFixedWidth(380)
        card.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 36, 36, 36)
        lay.setSpacing(0)

        # Header
        title = QLabel("OPERATOR LOGIN")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #EAFAFF;"
            "letter-spacing: 4px; border: none; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(4)

        subtitle = QLabel("AUTHORIZED PERSONNEL ONLY")
        subtitle.setStyleSheet(
            "font-size: 11px; color: #2A5A7A; letter-spacing: 3px;"
            "background: transparent; border: none;"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(subtitle)
        lay.addSpacing(28)

        # Fields
        def _field(placeholder: str, echo=False) -> QLineEdit:
            f = QLineEdit()
            f.setPlaceholderText(placeholder)
            f.setFixedHeight(42)
            if echo:
                f.setEchoMode(QLineEdit.EchoMode.Password)
            return f

        id_lbl = QLabel("LOGIN ID")
        id_lbl.setStyleSheet(
            "font-size: 12px; color: #3A7A9A; letter-spacing: 2px;"
            "background: transparent; border: none;"
        )
        lay.addWidget(id_lbl)
        lay.addSpacing(4)
        self._id_field = _field("Enter login ID")
        lay.addWidget(self._id_field)
        lay.addSpacing(16)

        pw_lbl = QLabel("PASSWORD")
        pw_lbl.setStyleSheet(
            "font-size: 12px; color: #3A7A9A; letter-spacing: 2px;"
            "background: transparent; border: none;"
        )
        lay.addWidget(pw_lbl)
        lay.addSpacing(4)
        self._pw_field = _field("Enter password", echo=True)
        self._pw_field.returnPressed.connect(self._do_login)
        lay.addWidget(self._pw_field)
        lay.addSpacing(6)

        # Error label
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet(
            "font-size: 12px; color: #FF4444; background: transparent;"
            "border: none; padding: 4px 0;"
        )
        self._err_lbl.setWordWrap(True)
        self._err_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._err_lbl)
        lay.addSpacing(6)

        # Login button
        self._login_btn = QPushButton("ACCESS SYSTEM")
        self._login_btn.setObjectName("primaryBtn")
        self._login_btn.setFixedHeight(44)
        self._login_btn.setStyleSheet(
            "QPushButton#primaryBtn {"
            "  background-color: #00C853; color: #000000;"
            "  border: none; border-radius: 4px;"
            "  font-size: 13px; font-weight: bold; letter-spacing: 3px;"
            "}"
            "QPushButton#primaryBtn:hover { background-color: #00E060; }"
            "QPushButton#primaryBtn:pressed { background-color: #00A040; }"
        )
        self._login_btn.clicked.connect(self._do_login)
        lay.addWidget(self._login_btn)
        lay.addSpacing(16)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background-color: #0F1A27; max-height: 1px; border: none;")
        lay.addWidget(div)
        lay.addSpacing(16)

        # Register
        reg_lbl = QLabel("No account?")
        reg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reg_lbl.setStyleSheet(
            "font-size: 12px; color: #3A6A8A; background: transparent; border: none;"
        )
        lay.addWidget(reg_lbl)
        lay.addSpacing(6)

        reg_btn = QPushButton("REQUEST ACCESS")
        reg_btn.setObjectName("ghostBtn")
        reg_btn.setFixedHeight(38)
        reg_btn.clicked.connect(self._open_register)
        lay.addWidget(reg_btn)

        # Attendance divider
        lay.addSpacing(10)
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("background-color: #0F1A27; max-height: 1px; border: none;")
        lay.addWidget(div2)
        lay.addSpacing(10)

        # Quick attendance mark
        att_lbl = QLabel("Mark your attendance")
        att_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        att_lbl.setStyleSheet(
            "font-size: 12px; color: #3A6A8A; background: transparent; border: none;"
        )
        lay.addWidget(att_lbl)
        lay.addSpacing(6)

        att_btn = QPushButton("≡  MARK ATTENDANCE")
        att_btn.setObjectName("ghostBtn")
        att_btn.setFixedHeight(38)
        att_btn.setStyleSheet(
            "QPushButton { background-color: #0A1A2A; color: #3A8ABF;"
            "border: 1px solid #1E3A5F; border-radius: 4px;"
            "font-size: 11px; letter-spacing: 2px; }"
            "QPushButton:hover { background-color: #1E3A5F; color: #C8D8E8; }"
        )
        att_btn.clicked.connect(self._open_attendance_mark)
        lay.addWidget(att_btn)

        outer.addWidget(card)
        return wrapper

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_login(self):
        login_id = self._id_field.text().strip()
        password = self._pw_field.text()
        self._err_lbl.setText("")

        if not login_id or not password:
            self._set_error("Login ID and password are required.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("AUTHENTICATING...")

        try:
            profile = self._auth.login(login_id, password)
            self._on_login_success(profile)
        except AuthError as e:
            self._set_error(str(e))
        finally:
            self._login_btn.setEnabled(True)
            self._login_btn.setText("ACCESS SYSTEM")

    def _set_error(self, msg: str):
        self._err_lbl.setText(f"⚠  {msg}")
        # Shake animation on error field
        orig = self._id_field.x()
        for dx in [6, -6, 4, -4, 2, -2, 0]:
            QTimer.singleShot(
                20 * [6, -6, 4, -4, 2, -2, 0].index(dx),
                lambda d=dx: self._id_field.move(orig + d, self._id_field.y())
            )

    def _on_login_success(self, profile):
        logger.info("Login: %s (%s)", profile.login_id, profile.role)
        self._open_main_window(profile)

    def _open_main_window(self, profile):
        from ui.main_window import MainWindow
        self._main_window = MainWindow(profile)
        self._main_window.show()
        self.close()

    def _open_attendance_mark(self):
        """Quick attendance marking from login screen using face recognition."""
        from ui.login_attendance_dialog import LoginAttendanceDialog
        dlg = LoginAttendanceDialog(self)
        dlg.exec()

    def _open_register(self):
        from ui.register_dialog import RegisterDialog
        dlg = RegisterDialog(self)
        if dlg.exec():
            self._id_field.setText(dlg.registered_login_id or "")
            self._err_lbl.setStyleSheet(
                "font-size: 12px; color: #00C853; background: transparent;"
                "border: none; padding: 4px 0;"
            )
            self._err_lbl.setText(
                "✓  Registration submitted. Awaiting admin approval."
            )