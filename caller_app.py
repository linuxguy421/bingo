#!/usr/bin/env python

"""
caller_app.py — Entry point for the Bingo Caller application.

Usage:
    python caller_app.py
    python caller_app.py --db path/to/bingo.db
    python caller_app.py --port 9000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure root is on path for shared modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

from db_manager import DatabaseManager
from caller.main_window import CallerMainWindow, APP_STYLE


def main() -> None:
    parser = argparse.ArgumentParser(description="Bingo Caller Application")
    parser.add_argument("--db",   default="bingo.db",  help="Path to SQLite database")
    parser.add_argument("--port", default=8765, type=int, help="WebSocket server port")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Bingo Caller")
    app.setStyleSheet(APP_STYLE)

    db = DatabaseManager(args.db)
    db.initialize()

    window = CallerMainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
