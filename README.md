# Smart Campus Insight System v2.0 — PyQt6 Edition

> Production-grade surveillance dashboard built with PyQt6.  
> All face recognition logic is **unchanged** from v1.

---

## Quick Start

```bash
pip install -r requirements.txt
python app/main.py
```

**Default admin credentials:**
| Field    | Value     |
|----------|-----------|
| Login ID | `admin`   |
| Password | `admin123`|

> Change immediately after first login via Settings.

---

## Project Structure

```
scis_pyqt6/
│
├── app/
│   └── main.py                  ← Entry point
│
├── ui/
│   ├── login_window.py          ← Full-screen tactical login
│   ├── register_dialog.py       ← Registration form (pending approval)
│   ├── main_window.py           ← QMainWindow + page orchestration
│   ├── sidebar.py               ← Navigation rail
│   ├── dashboard_page.py        ← Metric cards + activity feed
│   ├── live_recognition_page.py ← Live webcam + recognition log
│   ├── attendance_page.py       ← QTableWidget + search + export
│   ├── flagged_page.py          ← Security watchlist CRUD
│   ├── settings_page.py         ← Runtime config
│   ├── admin_panel.py           ← User approval & management
│   ├── camera_widget.py         ← QLabel-based frame display
│   └── alert_dialog.py          ← Danger alert modal
│
├── threads/
│   └── camera_thread.py         ← QThread: OpenCV + recognition
│
├── modules/
│   ├── config.py                ← All constants
│   ├── face_engine.py           ← ArcFace (unchanged)
│   ├── attendance_manager.py    ← CSV attendance (unchanged)
│   ├── flagged_manager.py       ← Re-exports SecurityManager
│   └── security_manager.py     ← Danger records + AlertSystem (unchanged)
│
├── services/
│   ├── firebase_service.py      ← Firebase RTDB (falls back to local JSON)
│   └── auth_service.py          ← bcrypt auth + role/status management
│
└── assets/
    └── styles/
        └── dark_theme.qss       ← Industrial dark theme
```

---

## Authentication Flow

```
App Start
  └─► LoginWindow
        ├─► [Register] → RegisterDialog
        │     └─► Account created (status: "pending")
        │           └─► Admin must approve in AdminPanel
        │
        └─► [Login] → AuthService.login()
              ├─► Validates login_id + bcrypt password
              ├─► Checks status == "approved"
              └─► Opens MainWindow(profile)
```

### Password Security
- All passwords hashed with **bcrypt** (cost factor 12)
- Plain-text passwords are **never** stored
- Hash comparison is timing-safe via `bcrypt.checkpw()`

---

## User Roles

| Role  | Capabilities |
|-------|-------------|
| admin | Full access · Approve/reject users · Admin Panel |
| user  | Dashboard · Live Feed · Attendance · Flagged view |

---

## Firebase / Local Storage

The app works **without Firebase** out of the box.  
If `pyrebase4` is not installed or credentials are missing, it automatically
falls back to a local `local_db.json` file.

To enable Firebase:
1. Edit `services/firebase_service.py`
2. Fill in `FIREBASE_CONFIG` with your project credentials

---

## Architecture Highlights

### CameraThread (QThread)
```
CameraThread
  ├── Captures frames via OpenCV
  ├── Runs FaceEngine.identify_frame() every Nth frame
  ├── Checks FlaggedManager.is_flagged()
  ├── Calls AttendanceManager.mark()
  └── Emits signals:
        frame_ready(np.ndarray)     → CameraWidget.update_frame()
        recognized(str, float)      → LiveRecognitionPage log
        flagged_detected(str, obj)  → DangerAlertDialog
        status_update(str)          → StatusBar
```

### QStackedWidget pages
```
MainWindow.stack
  [0] DashboardPage          ← default
  [1] LiveRecognitionPage
  [2] AttendancePage
  [3] FlaggedPage
  [4] SettingsPage
  [5] AdminPanel             ← admin only
```

---

## Unchanged from v1

The following files from the original Tkinter project are used **without modification**:

- `modules/face_engine.py` — ArcFace centroid matching
- `modules/attendance_manager.py` — CSV read/write + cooldown
- `modules/security_manager.py` — Danger records + AlertSystem
- `Dashboard.py` — Dash analytics (launched via subprocess)
- `Encodefile.p` — Pre-computed ArcFace embeddings
- `encode_students.py` — Encoding script

---

## Customisation

| What | Where |
|------|-------|
| Recognition threshold | `modules/config.py` or Settings page |
| Attendance cooldown | `modules/config.py` or Settings page |
| Camera index | `modules/config.py → CAMERA_INDEX` |
| Color scheme | `assets/styles/dark_theme.qss` |
| Admin password | Change after first login (stored as bcrypt hash) |
| Firebase project | `services/firebase_service.py → FIREBASE_CONFIG` |
