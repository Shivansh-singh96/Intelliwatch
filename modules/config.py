"""
modules/config.py — Single source of truth for all settings.
Mirrors the original config.py; adds new PyQt6-specific constants.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Paths ─────────────────────────────────────────────────────────────────────
STUDENTS_DIR          = os.path.join(BASE_DIR, "Students")
DEBUG_DIR             = os.path.join(BASE_DIR, "Debug")
LOGO_DIR              = os.path.join(BASE_DIR, "assets", "icons")
ENCODE_FILE           = os.path.join(BASE_DIR, "Encodefile.p")
ATTENDANCE_CSV        = os.path.join(BASE_DIR, "Attendance.csv")
DANGEROUS_PERSONS_CSV = os.path.join(BASE_DIR, "dangerous_persons.csv")
DANGEROUS_LOG_CSV     = os.path.join(BASE_DIR, "dangerous_detections.csv")
LOG_FILE              = os.path.join(BASE_DIR, "face_recognition.log")
DASHBOARD_SCRIPT      = os.path.join(BASE_DIR, "Dashboard.py")

# ── Recognition thresholds ────────────────────────────────────────────────────
RECOGNITION_THRESHOLD       = 0.50
GROUP_RECOGNITION_THRESHOLD = 0.45
KNN_K                       = 4
KNN_VOTE_THRESHOLD          = 0.35
KNN_MARGIN                  = 0.02

# ── Attendance ────────────────────────────────────────────────────────────────
ATTENDANCE_COOLDOWN = 45     # minutes

# ── Encoding ─────────────────────────────────────────────────────────────────
ENCODING_MODEL    = "ArcFace"
BLUR_THRESHOLD    = 20.0   # Laplacian variance — 20 works for typical webcams (was 100, too strict)
BRIGHTNESS_MIN    = 30     # allow slightly darker rooms
BRIGHTNESS_MAX    = 230

# ── Alert Audio ───────────────────────────────────────────────────────────────
ALERT_FREQUENCY    = 1500
ALERT_DURATION     = 60
ALERT_BEEP_INTERVAL = 0.4

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_INDEX        = 0
FRAME_SKIP          = 6      # process every Nth frame for recognition
FRAME_WIDTH         = 640
FRAME_HEIGHT        = 480
RECOGNITION_FPS_CAP = 2      # max recognition calls per second

# ── UI — PyQt6 ────────────────────────────────────────────────────────────────
APP_TITLE    = "IntelliWatch"
WINDOW_SIZE  = (1280, 800)

# Color tokens (also in QSS — kept here for runtime use e.g. QPainter)
BG_COLOR      = "#6D96F6"
PANEL_COLOR   = "#739DEC"
ACCENT_COLOR  = "#00C853"
ALERT_COLOR   = "#FF3B3B"
TEXT_COLOR    = "#1B1D1F"
MUTED_COLOR   = "#3A6A8A"
BORDER_COLOR  = "#1E3A5F"

# ── Dashboard URL ─────────────────────────────────────────────────────────────
DASHBOARD_URL          = "http://127.0.0.1:8050"
DASHBOARD_LAUNCH_DELAY = 3