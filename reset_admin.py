"""
reset_admin.py
--------------
Run this once to create or reset the default admin account.
Place in the scis_pyqt6 root folder and run:

    python reset_admin.py

Then login with:
    Login ID : admin
    Password : admin123
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_db.json")

ADMIN_ID  = "admin"
ADMIN_PWD = "admin123"

print("=" * 50)
print("  SCIS — Admin Account Reset")
print("=" * 50)

# ── Try bcrypt first ──────────────────────────────────────────────────────────
try:
    import bcrypt
    pwd_hash = bcrypt.hashpw(ADMIN_PWD.encode(), bcrypt.gensalt()).decode()
    print("  [OK] bcrypt available — password will be hashed")
except ImportError:
    print("  [!!] bcrypt not installed — installing now...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "bcrypt"])
    import bcrypt
    pwd_hash = bcrypt.hashpw(ADMIN_PWD.encode(), bcrypt.gensalt()).decode()
    print("  [OK] bcrypt installed and ready")

# ── Load or create local_db.json ─────────────────────────────────────────────
if os.path.exists(LOCAL_DB):
    with open(LOCAL_DB) as f:
        db = json.load(f)
    print(f"  [OK] Loaded existing local_db.json")
else:
    db = {}
    print("  [OK] Creating new local_db.json")

# ── Write admin profile ───────────────────────────────────────────────────────
uid = "admin-default"
db.setdefault("users", {})[uid] = {
    "profile": {
        "uid":        uid,
        "full_name":  "System Administrator",
        "email":      "admin@scis.local",
        "department": "IT Security",
        "login_id":   ADMIN_ID,
        "password":   pwd_hash,
        "role":       "admin",
        "status":     "approved",
        "created_at": int(time.time()),
    }
}

with open(LOCAL_DB, "w") as f:
    json.dump(db, f, indent=2)

print()
print("=" * 50)
print("  Admin account created/reset successfully!")
print("=" * 50)
print(f"  Login ID : {ADMIN_ID}")
print(f"  Password : {ADMIN_PWD}")
print("=" * 50)
print()
print("  Now run:  python app/main.py")
print()
