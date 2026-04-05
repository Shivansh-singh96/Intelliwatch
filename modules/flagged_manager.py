"""
modules/flagged_manager.py
───────────────────────────
Thin re-export so the rest of the PyQt6 codebase imports from one place.
Wraps SecurityManager + DangerRecord from the existing security_manager.py.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Re-export the existing, tested classes unchanged
from modules.security_manager import SecurityManager as FlaggedManager  # noqa
from modules.security_manager import DangerRecord, AlertSystem            # noqa

__all__ = ["FlaggedManager", "DangerRecord", "AlertSystem"]
