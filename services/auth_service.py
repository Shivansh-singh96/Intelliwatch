"""
services/auth_service.py
─────────────────────────
Secure authentication: registration, login, admin approval.

Password storage  : bcrypt — NEVER plain text
Firebase path     : users/{uid}/profile
Account statuses  : "pending" | "approved" | "rejected"
Roles             : "admin" | "user"
"""

import hashlib
import logging
import time
import uuid
import os
from dataclasses import dataclass
from typing import Optional

import bcrypt

from services.firebase_service import get_firebase

logger = logging.getLogger(__name__)

# ── Seed admin account (first run) ───────────────────────────────────────────
_DEFAULT_ADMIN_ID  = "admin"
_DEFAULT_ADMIN_PWD = "admin123"   # change after first login


@dataclass
class UserProfile:
    uid:        str
    full_name:  str
    email:      str
    department: str
    login_id:   str
    role:       str   # "admin" | "user"
    status:     str   # "pending" | "approved" | "rejected"

    @classmethod
    def from_dict(cls, uid: str, d: dict) -> "UserProfile":
        return cls(
            uid        = uid,
            full_name  = d.get("full_name",  ""),
            email      = d.get("email",      ""),
            department = d.get("department", ""),
            login_id   = d.get("login_id",   ""),
            role       = d.get("role",       "user"),
            status     = d.get("status",     "pending"),
        )


class AuthError(Exception):
    pass


class AuthService:
    """
    Handles registration, login, and user management.

    All passwords are stored as bcrypt hashes.
    All data lives under   users/{uid}/profile   in Firebase.
    """

    def __init__(self):
        self._db      = get_firebase()
        self._current: Optional[UserProfile] = None
        self._ensure_admin()

    # ── Current session ───────────────────────────────────────────────────────

    @property
    def current_user(self) -> Optional[UserProfile]:
        return self._current

    @property
    def is_admin(self) -> bool:
        return self._current is not None and self._current.role == "admin"

    def logout(self) -> None:
        self._current = None

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        full_name:  str,
        email:      str,
        department: str,
        login_id:   str,
        password:   str,
    ) -> str:
        """
        Register a new user.
        Returns the new uid on success.
        Raises AuthError on validation failure.
        """
        # Validate
        if not all([full_name, email, department, login_id, password]):
            raise AuthError("All fields are required.")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if "@" not in email:
            raise AuthError("Invalid email address.")
        if self._find_by_login_id(login_id) is not None:
            raise AuthError(f"Login ID '{login_id}' is already taken.")
        if self._find_by_email(email.strip().lower()) is not None:
            raise AuthError(f"Email '{email}' is already registered.")

        # Hash password
        pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        uid = str(uuid.uuid4())
        profile = {
            "uid":        uid,
            "full_name":  full_name.strip(),
            "email":      email.strip().lower(),
            "department": department.strip(),
            "login_id":   login_id.strip(),
            "password":   pwd_hash,
            "role":       "user",
            "status":     "pending",
            "created_at": int(time.time()),
        }
        self._db.set(f"users/{uid}/profile", profile)
        logger.info("Registered new user: %s (%s)", login_id, uid)
        return uid

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, login_id: str, password: str) -> UserProfile:
        """
        Authenticate a user.
        Returns UserProfile on success.
        Raises AuthError with a descriptive message on failure.
        """
        uid, data = self._find_by_login_id(login_id) or (None, None)
        if uid is None:
            raise AuthError("Invalid Login ID or password.")

        stored_hash = data.get("password", "")
        try:
            match = bcrypt.checkpw(password.encode(), stored_hash.encode())
        except Exception:
            match = False

        if not match:
            raise AuthError("Invalid Login ID or password.")

        status = data.get("status", "pending")
        if status == "pending":
            raise AuthError("Account pending admin approval.")
        if status == "rejected":
            raise AuthError("Account has been rejected. Contact an administrator.")
        if status != "approved":
            raise AuthError("Account is not active.")

        profile = UserProfile.from_dict(uid, data)
        self._current = profile
        logger.info("Login success: %s (%s)", login_id, profile.role)
        return profile

    # ── Admin: user management ────────────────────────────────────────────────

    def get_pending_users(self) -> list[UserProfile]:
        return self._get_users_by_status("pending")

    def get_all_users(self) -> list[UserProfile]:
        users = []
        all_users = self._db.get_children("users")
        for uid, node in all_users.items():
            if isinstance(node, dict) and "profile" in node:
                users.append(UserProfile.from_dict(uid, node["profile"]))
        return users

    def approve_user(self, uid: str) -> bool:
        ok = self._db.update(f"users/{uid}/profile", {"status": "approved"})
        if ok:
            profile = self._get_profile(uid)
            student_id = (profile or {}).get("login_id", "")
            if student_id:
                import threading
                from encode_students import encode_single_student
                def _encode():
                    success, msg = encode_single_student(student_id)
                    logger.info("Auto-encode %s: %s", student_id, msg)
                threading.Thread(target=_encode, daemon=True).start()
        return ok

    def reject_user(self, uid: str) -> bool:
        profile = self._get_profile(uid)
        ok = self._db.update(f"users/{uid}/profile", {"status": "rejected"})
        if ok and profile:
            self._delete_student_data(profile.get("login_id", ""))
        return ok

    def delete_user(self, uid: str) -> bool:
        profile = self._get_profile(uid)
        ok = self._db.delete(f"users/{uid}")
        if ok and profile:
            self._delete_student_data(profile.get("login_id", ""))
        return ok

    def promote_user(self, uid: str) -> bool:
        return self._db.update(f"users/{uid}/profile", {"role": "admin"})

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_profile(self, uid: str) -> dict | None:
        node = self._db.get_children("users").get(uid, {})
        return node.get("profile") if isinstance(node, dict) else None

    def _delete_student_data(self, student_id: str) -> None:
        """Delete photo folder and remove from encodefile."""
        if not student_id:
            return
        import shutil
        from modules.config import STUDENTS_DIR
        from encode_students import remove_student_from_encodefile

        folder = os.path.join(STUDENTS_DIR, student_id)
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
                logger.info("Deleted photo folder: Students/%s/", student_id)
            except Exception as exc:
                logger.error("Could not delete folder %s: %s", folder, exc)

        removed = remove_student_from_encodefile(student_id)
        if removed:
            logger.info("Removed %s from Encodefile.p", student_id)

    def update_user(self, uid: str, full_name: str, email: str,
                    department: str, login_id: str, role: str) -> None:
        """Update a user's editable fields. Raises AuthError on conflict."""
        email = email.strip().lower()
        login_id = login_id.strip()

        # Check login_id uniqueness (exclude self)
        existing = self._find_by_login_id(login_id)
        if existing is not None and existing[0] != uid:
            raise AuthError(f"Login ID '{login_id}' is already taken by another user.")

        # Check email uniqueness (exclude self)
        existing_e = self._find_by_email(email)
        if existing_e is not None and existing_e[0] != uid:
            raise AuthError(f"Email '{email}' is already used by another user.")

        self._db.update(f"users/{uid}/profile", {
            "full_name":  full_name.strip(),
            "email":      email,
            "department": department.strip(),
            "login_id":   login_id,
            "role":       role,
        })
        logger.info("Admin updated user %s", uid)

    def register_approved(
        self, full_name: str, email: str, department: str,
        login_id: str, password: str, role: str = "user",
    ) -> str:
        """Admin-side registration — account is immediately approved."""
        if not all([full_name, email, department, login_id, password]):
            raise AuthError("All fields are required.")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if "@" not in email:
            raise AuthError("Invalid email address.")
        if self._find_by_login_id(login_id) is not None:
            raise AuthError(f"Login ID '{login_id}' is already taken.")
        if self._find_by_email(email.strip().lower()) is not None:
            raise AuthError(f"Email '{email}' is already registered.")

        pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        uid = str(uuid.uuid4())
        profile = {
            "uid":        uid,
            "full_name":  full_name.strip(),
            "email":      email.strip().lower(),
            "department": department.strip(),
            "login_id":   login_id.strip(),
            "password":   pwd_hash,
            "role":       role,
            "status":     "approved",
            "created_at": int(time.time()),
        }
        self._db.set(f"users/{uid}/profile", profile)
        logger.info("Admin registered approved user: %s (%s)", login_id, uid)
        return uid

    def _find_by_login_id(self, login_id: str) -> Optional[tuple[str, dict]]:
        """Return (uid, profile_dict) if login_id exists, else None."""
        all_users = self._db.get_children("users")
        for uid, node in all_users.items():
            if isinstance(node, dict):
                profile = node.get("profile", {})
                if profile.get("login_id") == login_id:
                    return uid, profile
        return None

    def _find_by_email(self, email: str) -> Optional[tuple[str, dict]]:
        """Return (uid, profile_dict) if email exists, else None."""
        all_users = self._db.get_children("users")
        for uid, node in all_users.items():
            if isinstance(node, dict):
                profile = node.get("profile", {})
                if profile.get("email", "").lower() == email.lower():
                    return uid, profile
        return None

    def _get_users_by_status(self, status: str) -> list[UserProfile]:
        users = []
        all_users = self._db.get_children("users")
        for uid, node in all_users.items():
            if isinstance(node, dict) and "profile" in node:
                p = node["profile"]
                if p.get("status") == status:
                    users.append(UserProfile.from_dict(uid, p))
        return users


    def sync_students_from_encodefile(self) -> int:
        """
        Auto-create approved 'user' accounts for every student in Encodefile.p
        that does not already have an account.
        Returns count of newly created accounts.
        Default credentials: login_id = student folder name
                             password = 'student@123'
        """
        import pickle, os
        from modules.config import ENCODE_FILE, STUDENTS_DIR

        created = 0
        student_ids: list[str] = []

        # Prefer to read IDs from Encodefile.p (authoritative)
        if os.path.exists(ENCODE_FILE):
            try:
                with open(ENCODE_FILE, 'rb') as fh:
                    _, names = pickle.load(fh)
                student_ids = sorted(set(names))
            except Exception:
                pass

        # Fallback: scan Students/ folder
        if not student_ids and os.path.isdir(STUDENTS_DIR):
            student_ids = sorted([
                d for d in os.listdir(STUDENTS_DIR)
                if os.path.isdir(os.path.join(STUDENTS_DIR, d))
            ])

        default_pwd_hash = bcrypt.hashpw(b'student@123', bcrypt.gensalt()).decode()

        for sid in student_ids:
            if self._find_by_login_id(sid) is not None:
                continue   # already has an account

            uid = str(uuid.uuid4())
            profile = {
                'uid':        uid,
                'full_name':  sid,          # admin can update later
                'email':      f'{sid}@scis.local',
                'department': 'Student',
                'login_id':   sid,
                'password':   default_pwd_hash,
                'role':       'user',
                'status':     'approved',
                'created_at': int(time.time()),
            }
            self._db.set(f'users/{uid}/profile', profile)
            logger.info('Auto-created student account: %s', sid)
            created += 1

        return created

    def _ensure_admin(self) -> None:
        """Seed a default admin account on first run."""
        if self._find_by_login_id(_DEFAULT_ADMIN_ID) is not None:
            return
        pwd_hash = bcrypt.hashpw(
            _DEFAULT_ADMIN_PWD.encode(), bcrypt.gensalt()
        ).decode()
        uid = "admin-default"
        profile = {
            "uid":        uid,
            "full_name":  "System Administrator",
            "email":      "admin@scis.local",
            "department": "IT Security",
            "login_id":   _DEFAULT_ADMIN_ID,
            "password":   pwd_hash,
            "role":       "admin",
            "status":     "approved",
            "created_at": int(time.time()),
        }
        self._db.set(f"users/{uid}/profile", profile)
        logger.info("Default admin account created (login_id=admin)")


# Singleton
_instance: AuthService | None = None

def get_auth() -> AuthService:
    global _instance
    if _instance is None:
        _instance = AuthService()
    return _instance
