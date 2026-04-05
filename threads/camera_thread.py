"""
threads/camera_thread.py
─────────────────────────
CameraThread — QThread for camera capture.

KEY FIXES:
  - No pre-downscale: full 640×480 sent to recognition (small faces need it)
  - No wait loop: face_engine.is_loaded=True only after insightface is ready
  - ThreadPoolExecutor: recognition never blocks the display loop
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, Future

import cv2
cv2.setLogLevel(0)
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from modules.config import (
    CAMERA_INDEX, FRAME_SKIP, FRAME_WIDTH, FRAME_HEIGHT,
    RECOGNITION_FPS_CAP,
)

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recognition")


class CameraThread(QThread):
    frame_ready      = pyqtSignal(np.ndarray)
    recognized       = pyqtSignal(str, float, bool)  # name, confidence, already_marked
    flagged_detected = pyqtSignal(str, object, object)  # name, record, frame
    status_update    = pyqtSignal(str)
    error            = pyqtSignal(str)

    def __init__(self, face_engine, flagged_manager, attendance_manager,
                 parent=None):
        super().__init__(parent)
        self._engine     = face_engine
        self._flagged    = flagged_manager
        self._attendance = attendance_manager

        self._running         = False
        self._paused          = False
        self._frame_count     = 0
        self._last_recog_time = 0.0
        self._recog_interval  = 1.0 / max(RECOGNITION_FPS_CAP, 1)
        self._pending: Future | None = None

        self._alerted: dict[str, float] = {}
        self._alert_cooldown = 30.0
        self._recognized_last: dict[str, float] = {}   # cooldown for log entries
        self._recognized_cooldown = 5.0                # show in log every 5s max

    def pause(self):  self._paused = True
    def resume(self): self._paused = False

    def stop(self):
        self._running = False
        self.wait(3000)

    def run(self):
        self._running = True

        # is_loaded is only True after insightface app is fully ready —
        # so we wait here instead of racing against model download
        while not self._engine.is_loaded and self._running:
            time.sleep(0.5)

        if not self._running:
            return

        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error.emit(f"Cannot open camera (index {CAMERA_INDEX})")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.status_update.emit("CAMERA ONLINE")

        try:
            fail_count = 0
            while self._running:
                if self._paused:
                    time.sleep(0.05)
                    continue

                ret, frame = cap.read()
                if not ret:
                    fail_count += 1
                    time.sleep(0.05)
                    # After 30 consecutive failures (~1.5s), reopen camera
                    if fail_count >= 30:
                        logger.warning("Camera stream lost — reopening with DirectShow")
                        cap.release()
                        time.sleep(1.0)
                        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
                        if cap.isOpened():
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            self.status_update.emit("CAMERA ONLINE")
                        else:
                            self.status_update.emit("CAMERA ERROR — retrying")
                        fail_count = 0
                    continue

                fail_count = 0  # reset on good frame

                # Only update display and run recognition when not paused
                if not self._paused:
                    self.frame_ready.emit(frame.copy())

                self._frame_count += 1
                now = time.time()

                # Submit recognition only when previous job is done
                if (self._frame_count % FRAME_SKIP == 0
                        and now - self._last_recog_time >= self._recog_interval
                        and (self._pending is None or self._pending.done())):
                    self._last_recog_time = now
                    # Send FULL frame — no downscale (small faces need quality)
                    self._pending = _EXECUTOR.submit(self._process, frame.copy())

        except Exception as exc:
            logger.error("CameraThread: %s", exc)
            self.error.emit(str(exc))
        finally:
            cap.release()
            self.status_update.emit("CAMERA OFFLINE")

    def _process(self, frame: np.ndarray):
        # Don't emit any signals if recognition has been paused or stopped
        if self._paused or not self._running:
            return
        if not self._engine.is_loaded:
            return
        try:
            results = self._engine.identify_frame(frame)
        except Exception as exc:
            logger.warning("Recognition error: %s", exc)
            return

        for match in results:
            if not match.is_known:
                continue
            # Guard again — state may have changed while recognition was running
            if self._paused or not self._running:
                return
            name, confidence = match.name, match.score

            # Flagged check FIRST — block attendance, trigger alert
            if self._flagged.is_flagged(name):
                now = time.time()
                if now - self._alerted.get(name, 0) >= self._alert_cooldown:
                    self._alerted[name] = now
                    record = self._flagged.get(name)
                    self._flagged.log_detection(name, confidence)
                    self.flagged_detected.emit(name, record, frame.copy())
                continue   # do NOT mark attendance

            ok, _ = self._attendance.mark(name, confidence)
            already = not ok
            # Throttle log emissions — max once per 5s per person
            now2 = time.time()
            if now2 - self._recognized_last.get(name, 0) >= self._recognized_cooldown:
                self._recognized_last[name] = now2
                self.recognized.emit(name, confidence, already)