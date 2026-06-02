"""
display_window.py — Player Display main window.

Designed to run full-screen on a dedicated monitor in the bingo hall.
Receives live game state via WebSocket and updates in real time.

Layout:
  ┌─────────────────────────────────────────────────────────────┐
  │  Header: session name  ·  prize  ·  pattern name           │
  ├────────────────────────┬────────────────────────────────────┤
  │                        │  LAST BALL (giant)                 │
  │   75-Ball Board        │  Called count                     │
  │                        │  Pattern grid                     │
  │                        │  Recent calls                     │
  ├────────────────────────┴────────────────────────────────────┤
  │  Status bar: connection state                              │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from caller.ball_board import COLUMN_RANGES, COLUMN_COLOURS, COLUMNS

# ── Display Palette ────────────────────────────────────────────────────────
BG        = "#0F172A"
BG_CARD   = "#1E293B"
BG_HEADER = "#1E3A5F"
FG_DIM    = "#64748B"
FG_MID    = "#94A3B8"
FG_BRIGHT = "#F1F5F9"
GOLD      = "#FDE047"
GOLD_DK   = "#EAB308"
GREEN     = "#16A34A"

DISPLAY_STYLE = f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {FG_BRIGHT}; font-family: Arial, sans-serif; }}
QLabel {{ color: {FG_BRIGHT}; }}
QFrame {{ background-color: {BG_CARD}; border-radius: 10px; }}
QStatusBar {{ background: #020617; color: {FG_DIM}; font-size: 11px; }}
"""


# ── Large Ball Board (display-optimised) ──────────────────────────────────

class DisplayBallLabel(QLabel):
    """Single cell in the display board."""

    def __init__(self, number: int, col: int) -> None:
        super().__init__(str(number))
        self.number  = number
        self.col     = col
        self._called = False
        self._last   = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(48, 48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self._refresh()

    def set_state(self, called: bool, last: bool = False) -> None:
        self._called = called
        self._last   = last
        self._refresh()

    def _refresh(self) -> None:
        called_bg, called_fg, _ = COLUMN_COLOURS[self.col]
        if self._last:
            self.setStyleSheet(
                f"QLabel{{background:{GOLD};color:#000;border:3px solid {GOLD_DK};"
                f"border-radius:24px;font-size:14px;font-weight:bold;}}"
            )
        elif self._called:
            self.setStyleSheet(
                f"QLabel{{background:{called_bg};color:{called_fg};"
                f"border-radius:24px;font-size:13px;font-weight:bold;}}"
            )
        else:
            self.setStyleSheet(
                f"QLabel{{background:#1E293B;color:{FG_DIM};"
                f"border-radius:24px;font-size:12px;}}"
            )


class DisplayBoardWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._labels: dict[int, DisplayBallLabel] = {}
        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        for col, (letter, col_range, colours) in enumerate(
            zip(COLUMNS, COLUMN_RANGES, COLUMN_COLOURS)
        ):
            _, _, hdr_bg = colours
            hdr = QLabel(letter)
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            hdr.setMinimumSize(48, 36)
            hdr.setStyleSheet(
                f"QLabel{{background:{hdr_bg};color:white;"
                f"border-radius:5px;font-size:16px;font-weight:bold;}}"
            )
            layout.addWidget(hdr, 0, col)
            for row_idx, number in enumerate(col_range):
                lbl = DisplayBallLabel(number, col)
                self._labels[number] = lbl
                layout.addWidget(lbl, row_idx + 1, col)

    def update_called(self, called: list[int], last: int | None) -> None:
        called_set = set(called)
        for num, lbl in self._labels.items():
            lbl.set_state(num in called_set, num == last)

    def reset(self) -> None:
        for lbl in self._labels.values():
            lbl.set_state(False)


# ── Pattern Mini-Grid (display version) ───────────────────────────────────

class DisplayPatternGrid(QWidget):
    def __init__(self, cell: int = 28, parent=None) -> None:
        super().__init__(parent)
        self._cells: list[list[QLabel]] = []
        layout = QGridLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 4, 4, 4)
        for r in range(5):
            row = []
            for c in range(5):
                lbl = QLabel("★" if (r == 2 and c == 2) else "")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFixedSize(cell, cell)
                lbl.setStyleSheet(self._free_style() if (r == 2 and c == 2) else self._off_style())
                layout.addWidget(lbl, r, c)
                row.append(lbl)
            self._cells.append(row)

    @staticmethod
    def _on_style()   -> str: return "QLabel{background:#2563EB;border-radius:4px;}"
    @staticmethod
    def _off_style()  -> str: return "QLabel{background:#334155;border-radius:4px;}"
    @staticmethod
    def _free_style() -> str: return f"QLabel{{background:{GOLD};color:#000;border-radius:4px;font-size:10px;font-weight:bold;}}"

    def set_pattern(self, mask: list[list[bool]] | None) -> None:
        for r in range(5):
            for c in range(5):
                if r == 2 and c == 2:
                    self._cells[r][c].setStyleSheet(self._free_style())
                    continue
                active = mask[r][c] if mask else False
                self._cells[r][c].setStyleSheet(self._on_style() if active else self._off_style())


# ── Right Info Panel ──────────────────────────────────────────────────────

class InfoPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Last ball
        last_frame = QFrame()
        last_frame.setStyleSheet(f"QFrame{{background:{BG_HEADER};border-radius:12px;}}")
        lf = QVBoxLayout(last_frame)

        last_title = QLabel("LAST BALL")
        last_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        last_title.setStyleSheet(f"color:{FG_DIM};font-size:13px;font-weight:bold;background:transparent;")
        lf.addWidget(last_title)

        self._last_letter = QLabel("—")
        self._last_letter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_letter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self._last_letter.setStyleSheet(f"color:{FG_MID};background:transparent;")
        lf.addWidget(self._last_letter)

        self._last_number = QLabel("—")
        self._last_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_number.setFont(QFont("Arial", 88, QFont.Weight.Bold))
        self._last_number.setStyleSheet(f"color:{GOLD};background:transparent;min-height:120px;")
        lf.addWidget(self._last_number)

        layout.addWidget(last_frame)

        # Count
        self._count_label = QLabel("0 of 75 balls called")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_label.setFont(QFont("Arial", 16))
        self._count_label.setStyleSheet(f"color:{FG_MID};")
        layout.addWidget(self._count_label)

        # Pattern
        pattern_frame = QFrame()
        pattern_frame.setStyleSheet(f"QFrame{{background:{BG_CARD};border-radius:8px;}}")
        pf = QVBoxLayout(pattern_frame)

        self._pattern_name = QLabel("No Pattern")
        self._pattern_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pattern_name.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self._pattern_name.setStyleSheet("background:transparent;")
        pf.addWidget(self._pattern_name)

        self._pattern_grid = DisplayPatternGrid(cell=30)
        self._pattern_grid.setStyleSheet("background:transparent;")
        pf.addWidget(self._pattern_grid, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(pattern_frame)

        # Recent calls
        recent_lbl = QLabel("RECENT CALLS")
        recent_lbl.setStyleSheet(f"color:{FG_DIM};font-size:11px;font-weight:bold;")
        layout.addWidget(recent_lbl)

        self._recent_label = QLabel("—")
        self._recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recent_label.setWordWrap(True)
        self._recent_label.setFont(QFont("Arial", 13))
        self._recent_label.setStyleSheet(f"color:{FG_BRIGHT};")
        layout.addWidget(self._recent_label)

        layout.addStretch()

    # ── Update methods ────────────────────────────────────────────────────

    def update_state(self, state: dict) -> None:
        last = state.get("last_ball")
        count = state.get("ball_count", 0)
        called = state.get("called_balls", [])
        pattern_name = state.get("pattern_name", "")
        pattern_mask = state.get("pattern_mask")

        # Last ball display
        if last:
            letter = self._letter_for(last)
            self._last_letter.setText(letter)
            self._last_number.setText(str(last))
            col_idx = ["B","I","N","G","O"].index(letter)
            col_color = COLUMN_COLOURS[col_idx][0]
            self._last_number.setStyleSheet(
                f"color:{col_color};background:transparent;min-height:120px;font-weight:bold;"
            )
        else:
            self._last_letter.setText("—")
            self._last_number.setText("—")
            self._last_number.setStyleSheet(f"color:{GOLD};background:transparent;min-height:120px;")

        self._count_label.setText(f"{count} of 75 balls called")
        self._pattern_name.setText(pattern_name or "No Pattern")
        self._pattern_grid.set_pattern(pattern_mask)

        # Recent calls (last 8, most recent first, with letter prefix)
        recent = [f"{self._letter_for(b)}{b}" for b in reversed(called[-8:])]
        self._recent_label.setText("  ".join(recent) if recent else "—")

    @staticmethod
    def _letter_for(ball: int) -> str:
        for letter, r in zip("BINGO", COLUMN_RANGES):
            if ball in r:
                return letter
        return ""

    def reset(self) -> None:
        self._last_number.setText("—")
        self._last_letter.setText("—")
        self._count_label.setText("0 of 75 balls called")
        self._pattern_name.setText("No Pattern")
        self._pattern_grid.set_pattern(None)
        self._recent_label.setText("—")


# ── Main Display Window ───────────────────────────────────────────────────

class DisplayWindow(QMainWindow):
    """
    Full-screen player display.  Press F11 or Escape to toggle full-screen.
    """

    def __init__(self, host: str, port: int = 8765) -> None:
        super().__init__()
        self.host = host
        self.port = port

        self.setWindowTitle("🎱 Bingo — Player Display")
        self.resize(1280, 800)
        self.setStyleSheet(DISPLAY_STYLE)

        self._build_ui()
        self._build_status_bar()
        self._start_client()

        # F11 toggles full-screen
        fs_shortcut = QShortcut(QKeySequence("F11"), self)
        fs_shortcut.activated.connect(self._toggle_fullscreen)
        esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        esc_shortcut.activated.connect(self._exit_fullscreen)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(6)

        # ── Header bar ─────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(f"QFrame{{background:{BG_HEADER};border-radius:8px;}}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 4, 16, 4)

        self._session_lbl = QLabel("Waiting for caller…")
        self._session_lbl.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self._session_lbl.setStyleSheet("background:transparent;")
        hl.addWidget(self._session_lbl, stretch=2)

        self._prize_lbl = QLabel("")
        self._prize_lbl.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self._prize_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prize_lbl.setStyleSheet(f"color:{GREEN};background:transparent;")
        hl.addWidget(self._prize_lbl, stretch=1)

        self._status_icon = QLabel("⬤")
        self._status_icon.setStyleSheet(f"color:{FG_DIM};background:transparent;font-size:14px;")
        hl.addWidget(self._status_icon)
        outer.addWidget(header)

        # ── Main content ───────────────────────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(8)

        board_frame = QFrame()
        board_layout = QVBoxLayout(board_frame)
        board_layout.setContentsMargins(6, 6, 6, 6)
        self._board = DisplayBoardWidget()
        board_layout.addWidget(self._board)
        content.addWidget(board_frame, stretch=3)

        self._info = InfoPanel()
        content.addWidget(self._info, stretch=1)

        outer.addLayout(content, stretch=1)

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._conn_label = QLabel(f"Connecting to {self.host}:{self.port}…")
        sb.addPermanentWidget(self._conn_label)
        sb.addPermanentWidget(QLabel("  |  Press F11 for full-screen"))

    def _start_client(self) -> None:
        from display.ws_client import WSClientThread
        self._client = WSClientThread(self.host, self.port, parent=self)
        self._client.state_received.connect(self._on_state)
        self._client.connected.connect(self._on_connected)
        self._client.disconnected.connect(self._on_disconnected)
        self._client.start()

    # ── WebSocket callbacks ───────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_state(self, state: dict) -> None:
        # Header
        session = state.get("session_name", "")
        prize   = state.get("prize_amount", 0)
        self._session_lbl.setText(f"🎱  {session}" if session else "Waiting for caller…")
        self._prize_lbl.setText(f"Prize: ${prize:,.2f}" if prize else "")

        # Board
        called = state.get("called_balls", [])
        last   = state.get("last_ball")
        self._board.update_called(called, last)

        # Info panel
        self._info.update_state(state)

    @pyqtSlot()
    def _on_connected(self) -> None:
        self._conn_label.setText(f"✅  Connected to {self.host}:{self.port}")
        self._status_icon.setStyleSheet("color:#16A34A;background:transparent;font-size:14px;")

    @pyqtSlot()
    def _on_disconnected(self) -> None:
        self._conn_label.setText(
            f"⚠  Disconnected — retrying {self.host}:{self.port}…"
        )
        self._status_icon.setStyleSheet(f"color:#DC2626;background:transparent;font-size:14px;")

    # ── Fullscreen ────────────────────────────────────────────────────────

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event) -> None:
        self._client.stop()
        self._client.wait(2000)
        super().closeEvent(event)
