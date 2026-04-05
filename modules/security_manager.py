"""
security_manager.py
--------------------
SecurityManager  —  dangerous-persons database + alert logic.

Keeps all security / flagging concerns out of the GUI file.

Classes
-------
  DangerRecord        Data class for one flagged person.
  SecurityManager     CRUD on the CSV + in-memory dict.
  AlertSystem         Audio alert (pygame) with stop support.
"""

import csv
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from modules.config import (
    DANGEROUS_PERSONS_CSV, DANGEROUS_LOG_CSV,
    ALERT_FREQUENCY, ALERT_DURATION, ALERT_BEEP_INTERVAL
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Data class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DangerRecord:
    name       : str
    reason     : str
    level      : str          # "High" | "Medium" | "Low"
    added_date : str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_row(self) -> list:
        return [self.name, self.reason, self.level, self.added_date]


# ─────────────────────────────────────────────────────────────────────────────
#  SecurityManager
# ─────────────────────────────────────────────────────────────────────────────

class SecurityManager:
    """
    CRUD wrapper around dangerous_persons.csv.

    Usage
    -----
        sm = SecurityManager()
        sm.load()
        sm.add("0302CS221101", "Trespassing", "High")
        rec = sm.get("0302CS221101")   # → DangerRecord | None
        sm.remove("0302CS221101")
    """

    CSV_HEADERS = ["Name", "Reason", "Level", "Date"]

    def __init__(self, csv_path: str = DANGEROUS_PERSONS_CSV):
        self.path   = csv_path
        self._data  : dict[str, DangerRecord] = {}
        self._ensure_file()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def load(self) -> int:
        """Load from CSV into memory. Returns number of records loaded."""
        self._data.clear()
        try:
            with open(self.path, newline="") as fh:
                for row in csv.DictReader(fh):
                    rec = DangerRecord(
                        name       = row["Name"],
                        reason     = row["Reason"],
                        level      = row["Level"],
                        added_date = row["Date"],
                    )
                    self._data[rec.name] = rec
            logger.info("Loaded %d flagged persons", len(self._data))
        except Exception as exc:
            logger.error("Failed to load dangerous persons: %s", exc)
        return len(self._data)

    # ── Queries ───────────────────────────────────────────────────────────────

    def is_flagged(self, name: str) -> bool:
        name = name.strip()
        return name in self._data or name.lower() in {k.lower() for k in self._data}

    def get(self, name: str) -> DangerRecord | None:
        name = name.strip()
        if name in self._data:
            return self._data[name]
        # case-insensitive fallback
        for k, v in self._data.items():
            if k.lower() == name.lower():
                return v
        return None

    def all_records(self) -> list[DangerRecord]:
        return list(self._data.values())

    def names(self) -> list[str]:
        return list(self._data.keys())

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add(self, name: str, reason: str, level: str) -> bool:
        """Returns False if already flagged."""
        if name in self._data:
            return False
        rec = DangerRecord(name=name, reason=reason, level=level)
        self._data[name] = rec
        self._save()
        logger.info("Flagged person added: %s (%s)", name, level)
        return True

    def remove(self, name: str) -> bool:
        """Returns False if not found."""
        if name not in self._data:
            return False
        del self._data[name]
        self._save()
        logger.info("Flagged person removed: %s", name)
        return True

    # ── Detection logging ─────────────────────────────────────────────────────

    def log_detection(self, name: str, score: float, action: str = "Alert Triggered") -> None:
        rec    = self._data.get(name)
        reason = rec.reason if rec else "Unknown"
        level  = rec.level  if rec else "Unknown"
        self._ensure_log_file()
        with open(DANGEROUS_LOG_CSV, "a", newline="") as fh:
            csv.writer(fh).writerow([
                name, reason, level,
                f"{score:.4f}",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                action,
            ])
        logger.warning("DANGEROUS PERSON DETECTED: %s (%s) — %s", name, level, reason)

    def log_security_call(self, name: str) -> None:
        self.log_detection(name, 1.0, "Security Contacted")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ensure_file(self) -> None:
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="") as fh:
                csv.writer(fh).writerow(self.CSV_HEADERS)

    def _ensure_log_file(self) -> None:
        if not os.path.exists(DANGEROUS_LOG_CSV):
            with open(DANGEROUS_LOG_CSV, "w", newline="") as fh:
                csv.writer(fh).writerow(
                    ["Name", "Reason", "Level", "Confidence", "DateTime", "Action"]
                )

    def _save(self) -> None:
        with open(self.path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(self.CSV_HEADERS)
            for rec in self._data.values():
                writer.writerow(rec.to_row())


# ─────────────────────────────────────────────────────────────────────────────
#  AlertSystem
# ─────────────────────────────────────────────────────────────────────────────

class AlertSystem:
    """
    Plays a repeating beep using pygame (with fallback to console bell).

    Usage
    -----
        alert = AlertSystem()
        alert.play(duration=10)   # non-blocking — runs in background thread
        alert.stop()
    """

    def __init__(self):
        self._active = False
        self._thread : threading.Thread | None = None
        self._init_pygame()

    def _init_pygame(self) -> None:
        # Try winsound first on Windows — built-in, always works
        import sys
        if sys.platform == "win32":
            try:
                import winsound
                self._winsound   = winsound
                self._winsound_ok = True
                self._pygame_ok  = False
                return
            except Exception:
                self._winsound_ok = False
        else:
            self._winsound_ok = False

        try:
            import pygame
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self._pygame = pygame
            self._pygame_ok = True
        except Exception as exc:
            logger.warning("pygame unavailable: %s", exc)
            self._pygame_ok = False

    def play(self, duration: float = ALERT_DURATION) -> None:
        """Start alert in a background daemon thread."""
        self.stop()   # cancel any previous alert
        self._active = True
        self._thread = threading.Thread(
            target=self._run, args=(duration,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._active = False

    def _run(self, duration: float) -> None:
        end_time = time.time() + duration

        # Windows: winsound — built-in, always works
        if self._winsound_ok:
            # Repeating MB_ICONHAND (system Critical sound) for full duration
            while time.time() < end_time and self._active:
                try:
                    self._winsound.MessageBeep(self._winsound.MB_ICONHAND)
                    time.sleep(0.6)   # gap between each system beep
                except Exception:
                    time.sleep(0.6)
            return

        if self._pygame_ok:
            try:
                pg   = self._pygame
                sr   = 22050
                freq = ALERT_FREQUENCY
                ln   = 0.3
                t    = np.linspace(0, ln, int(sr * ln))
                tone = np.sin(2 * np.pi * freq * t)
                fade = int(sr * 0.01)
                tone[:fade]  *= np.linspace(0, 1, fade)
                tone[-fade:] *= np.linspace(1, 0, fade)
                stereo = np.column_stack((tone, tone))
                audio  = (stereo * 32767).astype(np.int16)
                sound  = pg.sndarray.make_sound(audio)

                while time.time() < end_time and self._active:
                    sound.play()
                    time.sleep(ALERT_BEEP_INTERVAL)
                return
            except Exception as exc:
                logger.error("pygame playback error: %s", exc)

        # Fallback: console bell
        while time.time() < end_time and self._active:
            print("\a")
            time.sleep(ALERT_BEEP_INTERVAL)
