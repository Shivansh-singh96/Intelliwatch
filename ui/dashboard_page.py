"""
ui/dashboard_page.py
─────────────────────
DashboardPage — overview metrics & quick-status panel.

Cards  : Total Students · Present Today · Flagged Persons · Camera Status
Refresh: every 10 seconds automatically
"""

import logging
import subprocess
import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGridLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)


class _MetricCard(QFrame):
    """Single dashboard metric tile."""

    def __init__(self, title: str, value: str, icon: str,
                 accent: str = "#00C853", parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #0F1520;
                border: 1px solid #1E3A5F;
                border-radius: 4px;
                border-left: 3px solid {accent};
            }}
        """)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(110)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(4)

        top = QHBoxLayout()
        self._val_lbl = QLabel(value)
        self._val_lbl.setStyleSheet(
            f"font-size: 32px; font-weight: bold; color: {accent};"
            "letter-spacing: -1px;"
        )
        top.addWidget(self._val_lbl)
        top.addStretch()

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 24px; color: {accent}; opacity: 0.5;")
        top.addWidget(icon_lbl)
        lay.addLayout(top)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(
            "font-size: 12px; color: #3A7A9A; letter-spacing: 3px;"
        )
        lay.addWidget(title_lbl)

    def set_value(self, v: str):
        self._val_lbl.setText(v)


class DashboardPage(QWidget):

    def __init__(self, face_engine, attendance_manager,
                 flagged_manager, parent=None):
        super().__init__(parent)
        self._engine     = face_engine
        self._attendance = attendance_manager
        self._flagged    = flagged_manager
        self._cam_online = False

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(10_000)
        self.refresh()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(20)

        # Page header
        hdr = QHBoxLayout()
        title = QLabel("SYSTEM OVERVIEW")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #D8E8F4;"
            "letter-spacing: 3px;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self._refresh_btn = QPushButton("⟳  REFRESH")
        self._refresh_btn.setObjectName("ghostBtn")
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(self._refresh_btn)

        lay.addLayout(hdr)

        # Metric cards grid
        grid = QGridLayout()
        grid.setSpacing(14)

        self._card_students = _MetricCard(
            "Total Profiles", "—", "◎", "#00C853")
        self._card_present  = _MetricCard(
            "Present Today",  "—", "✓", "#00C853")
        self._card_flagged  = _MetricCard(
            "Flagged Persons","—", "⚑", "#FF3B3B", )
        self._card_camera   = _MetricCard(
            "Camera Status",  "OFFLINE", "◉", "#2A4A6A")

        grid.addWidget(self._card_students, 0, 0)
        grid.addWidget(self._card_present,  0, 1)
        grid.addWidget(self._card_flagged,  0, 2)
        grid.addWidget(self._card_camera,   0, 3)
        lay.addLayout(grid)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background-color: #0F1A27; max-height: 1px;")
        lay.addWidget(div)

        # Recent activity section
        act_hdr = QLabel("RECENT ACTIVITY")
        act_hdr.setStyleSheet(
            "font-size: 11px; color: #1E4A3A; letter-spacing: 3px;"
        )
        lay.addWidget(act_hdr)

        self._activity_panel = QVBoxLayout()
        self._activity_panel.setSpacing(6)

        activity_wrapper = QWidget()
        activity_wrapper.setLayout(self._activity_panel)
        lay.addWidget(activity_wrapper)

        lay.addStretch()

        # Analytics button
        btn_row = QHBoxLayout()
        dash_btn = QPushButton("◈  OPEN ANALYTICS DASHBOARD")
        dash_btn.setObjectName("ghostBtn")
        dash_btn.setFixedHeight(38)
        dash_btn.clicked.connect(self._open_dashboard)
        btn_row.addWidget(dash_btn)
        self._dash_btn = dash_btn
        btn_row.addStretch()
        lay.addLayout(btn_row)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        total    = len(self._engine.student_names) if self._engine.is_loaded else 0
        today    = len(self._attendance.get_today())
        flagged  = len(self._flagged.all_records())

        self._card_students.set_value(str(total))
        self._card_present.set_value(str(today))
        self._card_flagged.set_value(str(flagged))

        # Recent attendance
        while self._activity_panel.count():
            item = self._activity_panel.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        records = self._attendance.get_today()[-8:]
        for rec in reversed(records):
            row = self._make_activity_row(
                f"✓  {rec.name}",
                rec.timestamp.strftime("%H:%M:%S"),
                "#00C853",
            )
            self._activity_panel.addWidget(row)

        if not records:
            empty = QLabel("No activity recorded today.")
            empty.setStyleSheet("font-size: 13px; color: #3A6A8A; padding: 8px 0;")
            self._activity_panel.addWidget(empty)

    def set_camera_status(self, online: bool, label: str | None = None):
        self._cam_online = online
        if online:
            self._card_camera.set_value("ONLINE")
            self._card_camera.setStyleSheet(
                "QFrame { background-color: #0F1520; border: 1px solid #1E3A5F;"
                "border-radius: 4px; border-left: 3px solid #00C853; }"
            )
        else:
            self._card_camera.set_value(label or "OFFLINE")
            self._card_camera.setStyleSheet(
                "QFrame { background-color: #0F1520; border: 1px solid #1E3A5F;"
                "border-radius: 4px; border-left: 3px solid #2A4A6A; }"
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_activity_row(self, text: str, time_str: str,
                           color: str = "#C8D8E8") -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background-color: #0D1320; border-radius: 3px;"
            "border: 1px solid #0F1A27; }"
        )
        row.setFixedHeight(32)
        rlay = QHBoxLayout(row)
        rlay.setContentsMargins(12, 0, 12, 0)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 13px; color: {color};")
        rlay.addWidget(lbl)
        rlay.addStretch()

        t = QLabel(time_str)
        t.setStyleSheet("font-size: 12px; color: #3A6A8A; letter-spacing: 1px;")
        rlay.addWidget(t)
        return row

    def _open_dashboard(self):
        import threading, time, sys, socket, tempfile, os
        from modules.config import DASHBOARD_SCRIPT, DASHBOARD_URL

        def _kill_existing():
            """Kill any process holding port 8050 (Windows)."""
            try:
                import subprocess as _sp
                result = _sp.run(["netstat", "-ano"], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if ":8050" in line and "LISTENING" in line:
                        pid = line.strip().split()[-1]
                        _sp.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                        time.sleep(0.8)
                        break
            except Exception:
                pass

        def _is_running():
            try:
                s = socket.create_connection(("127.0.0.1", 8050), timeout=1)
                s.close(); return True
            except OSError:
                return False

        def _launch():
            try:
                _kill_existing()
                # Wait for port to free
                for _ in range(10):
                    if not _is_running(): break
                    time.sleep(0.3)

                # Write stderr to a temp file — avoids PIPE deadlock
                log_path = os.path.join(tempfile.gettempdir(), "intelliwatch_dash.log")
                log_file = open(log_path, "w")

                proc = subprocess.Popen(
                    [sys.executable, DASHBOARD_SCRIPT],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=os.path.dirname(DASHBOARD_SCRIPT),
                )
                # Poll up to 15 seconds for server to come up
                ready = False
                for _ in range(30):
                    time.sleep(0.5)
                    if _is_running():
                        ready = True
                        break
                log_file.flush()

                if not ready:
                    log_file.close()
                    try:
                        with open(log_path) as lf:
                            err = lf.read(1000)
                    except Exception:
                        err = f"Log: {log_path}"
                    logger.error("Dashboard failed to start. Log:\n%s", err)
                    self._dash_error = err
                    from PyQt6.QtCore import QMetaObject, Qt as _Qt
                    QMetaObject.invokeMethod(
                        self, "_on_dash_error",
                        _Qt.ConnectionType.QueuedConnection,
                    )
                    return

                log_file.close()
                webbrowser.open(DASHBOARD_URL)
            except Exception as exc:
                logger.error("Dashboard launch error: %s", exc)
                self._dash_error = str(exc)
                from PyQt6.QtCore import QMetaObject, Qt as _Qt
                QMetaObject.invokeMethod(
                    self, "_on_dash_error",
                    _Qt.ConnectionType.QueuedConnection,
                )

        threading.Thread(target=_launch, daemon=True).start()

    from PyQt6.QtCore import pyqtSlot

    @pyqtSlot()
    def _on_dash_error(self):
        from PyQt6.QtWidgets import QMessageBox
        err = getattr(self, "_dash_error", "")
        hint = ""
        if "No module named" in err:
            pkg = err.split("No module named")[-1].strip().strip("'\"")
            hint = f"\n\nMissing package detected: '{pkg}'\nFix:  pip install dash plotly dash-bootstrap-components pandas"
        elif err:
            hint = f"\n\nDetails:\n{err[:400]}"
        QMessageBox.critical(
            self, "Analytics Dashboard Error",
            f"Could not start the analytics server at 127.0.0.1:8050.{hint}\n\n"
            f"Make sure all required packages are installed and try again."
        )