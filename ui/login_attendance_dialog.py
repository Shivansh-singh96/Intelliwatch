"""
ui/login_attendance_dialog.py
──────────────────────────────
Quick face-recognition attendance marking accessible from the login screen.
Opens camera, runs face recognition, marks attendance, then closes.
No login required.
"""

import logging
import time
import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui  import QImage, QPixmap, QColor

import modules.config as cfg
from modules.face_engine        import FaceEngine
from modules.attendance_manager import AttendanceManager
from modules.flagged_manager    import FlaggedManager, AlertSystem
from ui.alert_dialog            import SecurityAlertDialog

logger = logging.getLogger(__name__)


class _RecogThread(QThread):
    """Runs face recognition in background."""
    result_ready    = pyqtSignal(str, float, bool)     # name, confidence, already_marked
    flagged_spotted = pyqtSignal(str, object, object)  # name, DangerRecord, frame

    def __init__(self, engine, attendance, flagged):
        super().__init__()
        self._engine     = engine
        self._attendance = attendance
        self._flagged    = flagged
        self._running    = False
        self._alerted: dict[str, float] = {}

    def stop(self): self._running = False; self.wait(2000)

    def run(self):
        self._running = True
        cap = cv2.VideoCapture(cfg.CAMERA_INDEX, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        last_time = 0.0
        fail_count = 0

        while self._running:
            ret, frame = cap.read()
            if not ret:
                fail_count += 1
                time.sleep(0.05)
                if fail_count >= 30:
                    cap.release()
                    time.sleep(1.0)
                    cap = cv2.VideoCapture(cfg.CAMERA_INDEX, cv2.CAP_DSHOW)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    fail_count = 0
                continue
            fail_count = 0

            now = time.time()
            if now - last_time < 0.5: continue
            last_time = now

            if not self._engine.is_loaded: continue
            try:
                results = self._engine.identify_frame(frame)
                for r in results:
                    if not r.is_known:
                        continue
                    if self._flagged.is_flagged(r.name):
                        if now - self._alerted.get(r.name, 0) >= 30:
                            self._alerted[r.name] = now
                            record = self._flagged.get(r.name)
                            self._flagged.log_detection(r.name, r.score)
                            # Pass frame snapshot directly — captured at detection moment
                            self.flagged_spotted.emit(r.name, record, frame.copy())
                        continue
                    ok, _ = self._attendance.mark(r.name, r.score)
                    already = not ok
                    # Throttle — emit max once per 5s per person
                    if now - self._alerted.get(f"__recog_{r.name}", 0) >= 5:
                        self._alerted[f"__recog_{r.name}"] = now
                        self.result_ready.emit(r.name, r.score, already)
            except Exception:
                pass

        cap.release()


class LoginAttendanceDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mark Attendance")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(520)
        self.setStyleSheet("QDialog { background-color: #0A0E17; border: 1px solid #1E3A5F; }")

        self._engine     = FaceEngine()
        self._attendance = AttendanceManager()
        self._flagged    = FlaggedManager()
        self._alert      = AlertSystem()
        self._flagged.load()
        self._engine.load()

        self._cap       = None
        self._cam_timer = QTimer(self)
        self._cam_timer.timeout.connect(self._cam_tick)
        self._recog     = _RecogThread(self._engine, self._attendance, self._flagged)
        self._recog.result_ready.connect(self._on_recognized)
        self._recog.flagged_spotted.connect(self._on_flagged)
        self._build_ui()
        self._start()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        # Header
        title = QLabel("FACE RECOGNITION ATTENDANCE")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #C8D8E8; letter-spacing: 3px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("Look at the camera — attendance will be marked automatically")
        sub.setStyleSheet("font-size: 10px; color: #2A5A7A; letter-spacing: 1px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)

        # Camera feed
        self._cam_lbl = QLabel()
        self._cam_lbl.setFixedSize(460, 300)
        self._cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl.setStyleSheet(
            "background: #060A10; border: 1px solid #1E3A5F; border-radius: 4px;")
        self._cam_lbl.setText("Starting camera...")
        lay.addWidget(self._cam_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # Status
        self._status_lbl = QLabel("Initializing face recognition engine...")
        self._status_lbl.setStyleSheet("font-size: 10px; color: #2A5A7A;")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status_lbl)

        # Log of marked profiles
        log_hdr = QLabel("MARKED TODAY")
        log_hdr.setStyleSheet("font-size: 9px; color: #1E4A3A; letter-spacing: 3px;")
        lay.addWidget(log_hdr)

        self._log = QListWidget()
        self._log.setFixedHeight(90)
        self._log.setStyleSheet(
            "QListWidget { font-size: 12px; font-family: Consolas, monospace; }"
            "QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #0F1A27; }"
        )
        lay.addWidget(self._log)

        close_btn = QPushButton("✓  DONE")
        close_btn.setObjectName("primaryBtn")
        close_btn.setFixedHeight(40)
        close_btn.clicked.connect(self._on_done)
        lay.addWidget(close_btn)

    def _start(self):
        self._cap = cv2.VideoCapture(cfg.CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._status_lbl.setText("⚠ Camera unavailable")
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cam_timer.start(33)
        self._recog.start()
        engine_ok = self._engine.is_loaded
        self._status_lbl.setText(
            "✓ Camera + recognition active" if engine_ok
            else "⚠ Face model not loaded — run encode_students.py first"
        )
        self._status_lbl.setStyleSheet(
            f"font-size: 10px; color: {'#00C853' if engine_ok else '#FF9500'};"
        )

    def _cam_tick(self):
        if not self._cap or not self._cap.isOpened(): return
        ret, frame = self._cap.read()
        if not ret: return
        h, w = frame.shape[:2]
        rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img  = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pix  = QPixmap.fromImage(img).scaled(
            460, 300, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self._cam_lbl.setPixmap(pix)

    def _on_recognized(self, name: str, confidence: float, already_marked: bool):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        if already_marked:
            label  = f"  ✓  {name}   {confidence:.0%}   {ts}   [already marked]"
            color  = "#3A8ABF"
            status = f"✓ Already marked: {name}  ({confidence:.0%})"
            s_col  = "#3A8ABF"
        else:
            label  = f"  ✓  {name}   {confidence:.0%}   {ts}   [marked]"
            color  = "#00C853"
            status = f"✓ Marked: {name}  ({confidence:.0%})"
            s_col  = "#00C853"
        item = QListWidgetItem(label)
        item.setForeground(QColor(color))
        self._log.insertItem(0, item)
        self._status_lbl.setText(status)
        self._status_lbl.setStyleSheet(f"font-size: 12px; color: {s_col};")

    def _on_flagged(self, name: str, record, frame):
        # Stop camera timer and recog thread — but NOT the alert
        self._cam_timer.stop()
        self._recog.stop()
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

        # frame arrives directly from recognition thread — always available
        snapshot = frame if frame is not None else None

        self._alert.play()

        dlg = SecurityAlertDialog(
            person_name  = name,
            record       = record,
            snapshot     = snapshot,
            auto_dismiss = 0,
            parent       = self,
        )
        dlg.exec()
        self._alert.stop()
        self.reject()

    def _on_done(self):
        self._stop(); self.accept()

    def _stop(self):
        self._cam_timer.stop()
        self._recog.stop()
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)