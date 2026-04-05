"""
services/firebase_service.py
─────────────────────────────
Thin wrapper around Firebase Realtime Database (pyrebase4 or firebase-admin).
Falls back to a local JSON file store if Firebase is unavailable, so the
app runs out-of-the-box without credentials.
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Local fallback store path ─────────────────────────────────────────────────
_LOCAL_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "local_db.json"
)

# ── Firebase config — fill in your own credentials ───────────────────────────
FIREBASE_CONFIG = {
    "apiKey":            "YOUR_API_KEY",
    "authDomain":        "YOUR_PROJECT.firebaseapp.com",
    "databaseURL":       "https://YOUR_PROJECT-default-rtdb.firebaseio.com",
    "projectId":         "YOUR_PROJECT",
    "storageBucket":     "YOUR_PROJECT.appspot.com",
    "messagingSenderId": "YOUR_SENDER_ID",
    "appId":             "YOUR_APP_ID",
}


class FirebaseService:
    """
    Provides get / set / push / delete against Firebase RTDB.
    Falls back silently to a local JSON file if Firebase is not configured.
    """

    def __init__(self):
        self._firebase  = None
        self._db        = None
        self._use_local = True
        self._local: dict = {}
        self._connect()

    # ── Connection ────────────────────────────────────────────────────────────

    def _is_placeholder(self) -> bool:
        url = FIREBASE_CONFIG.get("databaseURL", "")
        key = FIREBASE_CONFIG.get("apiKey", "")
        return "YOUR_PROJECT" in url or "YOUR_API_KEY" in key

    def _connect(self) -> None:
        if self._is_placeholder():
            logger.info("Firebase config not set — using local JSON store")
            self._use_local = True
            self._load_local()
            return
        try:
            import pyrebase  # pyrebase4
            fb = pyrebase.initialize_app(FIREBASE_CONFIG)
            self._db        = fb.database()
            self._use_local = False
            logger.info("FirebaseService: connected to Realtime DB")
        except Exception as exc:
            logger.warning("Firebase unavailable (%s) — using local JSON store", exc)
            self._use_local = True
            self._load_local()

    def _load_local(self) -> None:
        if os.path.exists(_LOCAL_DB_PATH):
            try:
                with open(_LOCAL_DB_PATH) as f:
                    self._local = json.load(f)
            except Exception:
                self._local = {}
        else:
            self._local = {}

    def _save_local(self) -> None:
        try:
            with open(_LOCAL_DB_PATH, "w") as f:
                json.dump(self._local, f, indent=2)
        except Exception as exc:
            logger.error("Local DB save failed: %s", exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _nav_local(self, path: str) -> tuple[dict, str]:
        """Navigate local dict to parent, return (parent, key)."""
        parts = [p for p in path.strip("/").split("/") if p]
        node  = self._local
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        return node, parts[-1] if parts else ("", "")

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, path: str) -> Any:
        """Return the value at path, or None."""
        if self._use_local:
            parent, key = self._nav_local(path)
            return parent.get(key)
        try:
            return self._db.child(path).get().val()
        except Exception as exc:
            logger.error("Firebase get(%s): %s", path, exc)
            return None

    def set(self, path: str, value: Any) -> bool:
        """Set value at path. Returns True on success."""
        if self._use_local:
            parent, key = self._nav_local(path)
            parent[key] = value
            self._save_local()
            return True
        try:
            self._db.child(path).set(value)
            return True
        except Exception as exc:
            logger.error("Firebase set(%s): %s", path, exc)
            return False

    def push(self, path: str, value: Any) -> str | None:
        """Push a new child node. Returns the new key or None."""
        if self._use_local:
            parent, key = self._nav_local(path)
            target = parent.setdefault(key, {})
            new_key = str(int(time.time() * 1000))
            target[new_key] = value
            self._save_local()
            return new_key
        try:
            result = self._db.child(path).push(value)
            return result["name"]
        except Exception as exc:
            logger.error("Firebase push(%s): %s", path, exc)
            return None

    def update(self, path: str, updates: dict) -> bool:
        """Partial update at path."""
        if self._use_local:
            parent, key = self._nav_local(path)
            node = parent.setdefault(key, {})
            node.update(updates)
            self._save_local()
            return True
        try:
            self._db.child(path).update(updates)
            return True
        except Exception as exc:
            logger.error("Firebase update(%s): %s", path, exc)
            return False

    def delete(self, path: str) -> bool:
        """Remove node at path."""
        if self._use_local:
            parent, key = self._nav_local(path)
            parent.pop(key, None)
            self._save_local()
            return True
        try:
            self._db.child(path).remove()
            return True
        except Exception as exc:
            logger.error("Firebase delete(%s): %s", path, exc)
            return False

    def get_children(self, path: str) -> dict:
        """Return all children at path as a dict."""
        result = self.get(path)
        if isinstance(result, dict):
            return result
        return {}

    @property
    def is_online(self) -> bool:
        return not self._use_local


# Singleton
_instance: FirebaseService | None = None

def get_firebase() -> FirebaseService:
    global _instance
    if _instance is None:
        _instance = FirebaseService()
    return _instance
