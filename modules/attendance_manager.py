"""
attendance_manager.py
---------------------
AttendanceManager  —  marks + reads attendance records.

Keeps the 45-minute cooldown logic, CSV creation, and querying
completely separate from the GUI and face engine.
"""

import csv
import logging
import os
from datetime import datetime, timedelta

from modules.config import ATTENDANCE_CSV, ATTENDANCE_COOLDOWN

logger = logging.getLogger(__name__)

CSV_HEADERS = ["Name", "Time"]


class AttendanceRecord:
    """Lightweight data class for one attendance entry."""
    __slots__ = ("name", "timestamp")

    def __init__(self, name: str, timestamp: datetime | None = None):
        self.name      = name
        self.timestamp = timestamp or datetime.now()

    def to_row(self) -> list:
        return [self.name, self.timestamp.strftime("%Y-%m-%d %H:%M:%S")]

    def __repr__(self):
        return f"<{self.name} @ {self.timestamp:%H:%M:%S}>"


class AttendanceManager:
    """
    Handles all read / write operations on Attendance.csv.

    Public methods
    --------------
    mark(name)              Mark attendance (respects cooldown). Returns bool.
    mark_force(name)        Mark regardless of cooldown (manual entry).
    already_marked(name)    True if marked within cooldown window.
    get_today()             List[AttendanceRecord] for today.
    get_all()               All records as list of dicts (for dashboard).
    """

    def __init__(self, csv_path: str = ATTENDANCE_CSV):
        self.path = csv_path
        self._ensure_file()

    # ── Public API ────────────────────────────────────────────────────────────

    def mark(self, name: str, score: float = 0.0) -> tuple[bool, str]:
        """
        Attempt to mark attendance.
        Returns (success: bool, message: str).
        """
        if self.already_marked(name):
            msg = f"Attendance for '{name}' already marked (within {ATTENDANCE_COOLDOWN} min)."
            logger.info(msg)
            return False, msg

        self._append(AttendanceRecord(name))
        msg = f"Attendance marked for '{name}'."
        logger.info(msg)
        return True, msg

    def mark_force(self, name: str) -> None:
        """Bypass cooldown — used for manual corrections."""
        self._append(AttendanceRecord(name))
        logger.info("Force-marked attendance for '%s'", name)

    def already_marked(self, name: str) -> bool:
        """True if the student was marked within the cooldown window."""
        cutoff = datetime.now() - timedelta(minutes=ATTENDANCE_COOLDOWN)
        for rec in self._read_all():
            if rec.name == name and rec.timestamp >= cutoff:
                return True
        return False

    def get_today(self) -> list[AttendanceRecord]:
        today = datetime.now().date()
        return [r for r in self._read_all() if r.timestamp.date() == today]

    def get_all(self) -> list[dict]:
        """Return every record as a plain dict (easy for pandas / display)."""
        return [
            {"Name": r.name, "Time": r.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
            for r in self._read_all()
        ]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ensure_file(self) -> None:
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="") as fh:
                csv.writer(fh).writerow(CSV_HEADERS)

    def _append(self, record: AttendanceRecord) -> None:
        with open(self.path, "a", newline="") as fh:
            csv.writer(fh).writerow(record.to_row())

    def _read_all(self) -> list[AttendanceRecord]:
        records = []
        try:
            with open(self.path, newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        ts = datetime.strptime(row["Time"], "%Y-%m-%d %H:%M:%S")
                        records.append(AttendanceRecord(row["Name"], ts))
                    except (KeyError, ValueError):
                        continue
        except FileNotFoundError:
            pass
        return records
