"""
ui/main_window.py  —  Root window after login.

Pages
─────
 Admin : Dashboard · Live Feed · Attendance (all) · Flagged · Settings · Admin Panel
 User  : Dashboard (own) · Attendance (own) · Flagged (view) · Settings (own info)
"""

import logging
import sys
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QStackedWidget,
    QStatusBar, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui  import QColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules.face_engine        import FaceEngine
from modules.attendance_manager import AttendanceManager
from modules.flagged_manager    import FlaggedManager, AlertSystem
from threads.camera_thread      import CameraThread
from ui.sidebar               import Sidebar
from ui.dashboard_page        import DashboardPage
from ui.attendance_page       import AttendancePage
from ui.flagged_page          import FlaggedPage
from ui.settings_page         import SettingsPage
from services.auth_service    import get_auth
from ui.alert_dialog          import SecurityAlertDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):

    def __init__(self, profile):
        super().__init__()
        self._profile  = profile
        self._auth     = get_auth()
        self._is_admin = (profile.role == "admin")

        # Core modules
        self._engine     = FaceEngine()
        self._attendance = AttendanceManager()
        self._flagged    = FlaggedManager()
        self._alert      = AlertSystem()
        self._engine.load()
        self._flagged.load()

        # Camera thread (always running for live feed)
        self._cam_thread = CameraThread(
            self._engine, self._flagged, self._attendance)
        self._cam_thread.status_update.connect(self._on_cam_status)
        self._cam_thread.flagged_detected.connect(self._on_flagged_detected)

        self.setWindowTitle(
            f"IntelliWatch  —  {profile.full_name or profile.login_id}"
            f"  [{profile.role.upper()}]"
        )
        self.setMinimumSize(900, 600)   # prevent layout from growing unboundedly
        self.resize(1280, 800)
        self.showMaximized()

        self._build_ui()
        self._update_status(
            f"ONLINE  ·  {len(self._engine.student_names)} profiles  ·  "
            f"Logged in as {profile.login_id}"
        )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body_widget = QWidget()
        body = QHBoxLayout(body_widget)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._sidebar = Sidebar(self._profile)
        self._sidebar.page_changed.connect(self._switch_page)
        body.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background-color: #0A0E17;")
        self._build_pages()
        body.addWidget(self._stack, 1)

        root.addWidget(body_widget, 1)

        self._status_bar = QStatusBar()
        self._status_bar.setObjectName("statusBar")
        self.setStatusBar(self._status_bar)

    def _build_header(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(58)
        bar.setStyleSheet(
            "QFrame { background-color: #03070D; border-bottom: 1px solid #0F1A27; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)

        sys_lbl = QLabel("IntelliWatch — AI-Powered Vision Security & Recognition")
        sys_lbl.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #00C853; letter-spacing: 3px;"
        )
        lay.addWidget(sys_lbl)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #0F1A27;"); sep.setFixedWidth(1)
        lay.addWidget(sep)

        self._clock = QLabel()
        self._clock.setStyleSheet("font-size: 13px; color: #3A7AAA; letter-spacing: 2px;")
        lay.addWidget(self._clock)
        timer = QTimer(self); timer.timeout.connect(self._tick_clock); timer.start(1000)
        self._tick_clock()
        lay.addStretch()

        role_col = "#00C853" if self._is_admin else "#3A6A8A"
        user_lbl = QLabel(
            f"{self._profile.login_id.upper()}  "
            f"<span style='color:{role_col}'>◈ {self._profile.role.upper()}</span>"
        )
        user_lbl.setStyleSheet("font-size: 13px; color: #D8E8F4; letter-spacing: 1px;")
        user_lbl.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(user_lbl)

        logout_btn = QPushButton("⏻  LOGOUT")
        logout_btn.setObjectName("ghostBtn")
        logout_btn.setFixedHeight(30)
        logout_btn.clicked.connect(self._logout)
        lay.addWidget(logout_btn)
        return bar

    def _build_pages(self):
        """
        Page indices are role-dependent.
        Admin:  0=Dash  1=Live  2=Attendance(all)  3=Flagged  4=Settings  5=AdminPanel
        User:   0=Dash  1=Attendance(own)  2=Flagged(view)  3=Settings(profile)
        """
        # 0: Dashboard
        self._dash_page = DashboardPage(
            self._engine, self._attendance, self._flagged)
        self._stack.addWidget(self._dash_page)

        if self._is_admin:
            # 1: Live Recognition
            from ui.live_recognition_page import LiveRecognitionPage
            self._live_page = LiveRecognitionPage(
                self._cam_thread, self._flagged, self._attendance)
            self._stack.addWidget(self._live_page)

        # 2 (admin) / 1 (user): Attendance
        self._att_page = AttendancePage(self._attendance, self._profile)
        self._stack.addWidget(self._att_page)

        # 3 (admin) / 2 (user): Flagged
        self._flag_page = FlaggedPage(self._flagged, self._engine, self._profile)
        self._stack.addWidget(self._flag_page)

        # 4 (admin) / 3 (user): Settings
        self._set_page = SettingsPage(self._profile)
        self._stack.addWidget(self._set_page)

        # 5 (admin only): Admin Panel
        if self._is_admin:
            from ui.admin_panel import AdminPanel
            self._admin_page = AdminPanel()
            self._stack.addWidget(self._admin_page)

    @pyqtSlot(int)
    def _switch_page(self, idx: int):
        self._stack.setCurrentIndex(idx)
        if idx == 0:
            self._dash_page.refresh()
        elif self._is_admin and idx == 2:
            self._att_page.load_records()
        elif not self._is_admin and idx == 1:
            self._att_page.load_records()
        elif (self._is_admin and idx == 3) or (not self._is_admin and idx == 2):
            self._flag_page.load_records()
        elif self._is_admin and idx == 5:
            self._admin_page.refresh()

    @pyqtSlot(str)
    def _on_cam_status(self, msg: str):
        online = "ONLINE" in msg.upper()
        self._dash_page.set_camera_status(online, msg)
        self._update_status(msg)

    @pyqtSlot(str, object, object)
    def _on_flagged_detected(self, name: str, record, frame):
        self._alert.play()

        snapshot = frame if frame is not None else None

        dlg = SecurityAlertDialog(
            person_name  = name,
            record       = record,
            snapshot     = snapshot,
            auto_dismiss = 0,
            parent       = self,
        )
        dlg.dismissed.connect(lambda _: self._alert.stop())
        dlg.exec()
        self._alert.stop()

    def _tick_clock(self):
        from datetime import datetime
        self._clock.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    def _update_status(self, msg: str):
        self._status_bar.showMessage(f"  {msg}")

    def _logout(self):
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Logout", "End current session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._cam_thread.isRunning():
            self._cam_thread.stop()
        self._alert.stop()
        self._auth.logout()
        from ui.login_window import LoginWindow
        self._login_win = LoginWindow()
        self._login_win.show()
        self.close()

    def closeEvent(self, event):
        if self._cam_thread.isRunning():
            self._cam_thread.stop()
        self._alert.stop()
        super().closeEvent(event)