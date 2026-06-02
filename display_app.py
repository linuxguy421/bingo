"""
display_app.py — Entry point for the Bingo Player Display.

Shows a connection dialog at startup, then opens the full-screen display.

Usage:
    python display_app.py
    python display_app.py --host 192.168.1.10
    python display_app.py --host 192.168.1.10 --port 8765
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


class ConnectDialog(QDialog):
    """Small dialog to enter the caller machine's IP address and port."""

    def __init__(self, default_host: str = "192.168.1.1", default_port: int = 8765) -> None:
        super().__init__()
        self.setWindowTitle("Connect to Bingo Caller")
        self.setMinimumWidth(360)
        self.setStyleSheet("""
            QDialog  { background:#1E293B; color:#F1F5F9; }
            QLabel   { color:#F1F5F9; font-size:13px; }
            QLineEdit, QSpinBox { background:#0F172A; color:#F1F5F9;
                                   border:1px solid #334155; border-radius:5px;
                                   padding:6px; font-size:13px; }
            QPushButton { background:#2563EB; color:white; border-radius:5px;
                          padding:8px 20px; font-weight:bold; font-size:13px; }
            QPushButton:hover { background:#1D4ED8; }
        """)
        layout = QVBoxLayout(self)

        title = QLabel("🎱  Player Display")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Enter the IP address of the Caller computer on your network.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#94A3B8; font-size:11px;")
        layout.addWidget(sub)

        form = QFormLayout()
        self._host_edit = QLineEdit(default_host)
        self._host_edit.setPlaceholderText("e.g. 192.168.1.10")
        form.addRow("Caller IP Address:", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(default_port)
        form.addRow("Port:", self._port_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        layout.addWidget(buttons)

    @property
    def host(self) -> str:
        return self._host_edit.text().strip() or "localhost"

    @property
    def port(self) -> int:
        return self._port_spin.value()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bingo Player Display")
    parser.add_argument("--host", default=None, help="Caller machine IP address")
    parser.add_argument("--port", default=8765, type=int, help="WebSocket port")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Bingo Display")

    host = args.host
    port = args.port

    # If host not given on command line, show dialog
    if not host:
        dlg = ConnectDialog(default_port=port)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        host = dlg.host
        port = dlg.port

    from display.display_window import DisplayWindow
    window = DisplayWindow(host=host, port=port)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
