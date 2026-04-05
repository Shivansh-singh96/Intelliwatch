"""
main.py — IntelliWatch
Entry point: splash → login → main dashboard
"""

import sys
import os

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase

from ui.login_window import LoginWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("IntelliWatch")
    app.setOrganizationName("IntelliWatch")

    # Load stylesheet
    qss_path = os.path.join(ROOT, "assets", "styles", "dark_theme.qss")

    try:
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"Stylesheet not found at: {qss_path}")

    window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()