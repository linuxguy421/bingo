"""
ball_board.py — The 75-ball display board widget.

Shows all balls arranged in B-I-N-G-O columns.
Called balls light up in their column colour.
The most-recently-drawn ball gets a gold highlight.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

# Column definitions
COLUMNS = ["B", "I", "N", "G", "O"]
COLUMN_RANGES = [
    range(1,  16),
    range(16, 31),
    range(31, 46),
    range(46, 61),
    range(61, 76),
]

# Colours — (called_bg, called_text, header_bg)
COLUMN_COLOURS = [
    ("#3B82F6", "#FFFFFF", "#1D4ED8"),   # B — blue
    ("#EF4444", "#FFFFFF", "#B91C1C"),   # I — red
    ("#8B5CF6", "#FFFFFF", "#6D28D9"),   # N — purple
    ("#10B981", "#FFFFFF", "#047857"),   # G — green
    ("#F59E0B", "#000000", "#B45309"),   # O — amber
]

_UNCALLED_BG   = "#E2E8F0"
_UNCALLED_TEXT = "#475569"
_LAST_BG       = "#FDE047"
_LAST_TEXT     = "#000000"
_LAST_BORDER   = "#EAB308"


class BallLabel(QLabel):
    """A single ball cell in the board."""

    def __init__(self, number: int, col: int) -> None:
        super().__init__(str(number))
        self.number  = number
        self.col     = col
        self._called = False
        self._last   = False

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(38, 38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        font = QFont("Arial", 10, QFont.Weight.Bold)
        self.setFont(font)
        self._refresh()

    # ── State ─────────────────────────────────────────────────────────────

    def set_called(self, called: bool, last: bool = False) -> None:
        self._called = called
        self._last   = last
        self._refresh()

    def reset(self) -> None:
        self._called = False
        self._last   = False
        self._refresh()

    # ── Appearance ────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        called_bg, called_text, _ = COLUMN_COLOURS[self.col]

        if self._last:
            bg, fg, border, radius = _LAST_BG, _LAST_TEXT, _LAST_BORDER, "19px"
        elif self._called:
            bg, fg, border, radius = called_bg, called_text, called_bg, "19px"
        else:
            bg, fg, border, radius = _UNCALLED_BG, _UNCALLED_TEXT, _UNCALLED_BG, "19px"

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 2px solid {border};
                border-radius: {radius};
            }}
        """)


class BallBoardWidget(QWidget):
    """
    The full 75-ball display arranged in 5 columns (B-I-N-G-O),
    each column showing 15 balls vertically.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: dict[int, BallLabel] = {}   # ball number → label
        self._last_ball: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 4, 4, 4)

        for col, (letter, col_range, colours) in enumerate(
            zip(COLUMNS, COLUMN_RANGES, COLUMN_COLOURS)
        ):
            # Column header
            header = QLabel(letter)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setMinimumSize(38, 32)
            _, _, header_bg = colours
            header.setStyleSheet(f"""
                QLabel {{
                    background-color: {header_bg};
                    color: #FFFFFF;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
            layout.addWidget(header, 0, col)

            # Ball cells (rows 1-15)
            for row_idx, number in enumerate(col_range):
                label = BallLabel(number, col)
                self._labels[number] = label
                layout.addWidget(label, row_idx + 1, col)

    # ── Public API ────────────────────────────────────────────────────────

    def update_called(self, called_balls: list[int], last_ball: int | None = None) -> None:
        """Refresh the entire board from a list of called ball numbers."""
        called_set = set(called_balls)
        self._last_ball = last_ball

        for number, label in self._labels.items():
            is_called = number in called_set
            is_last   = (number == last_ball)
            label.set_called(is_called, is_last)

    def reset(self) -> None:
        """Clear all called state."""
        self._last_ball = None
        for label in self._labels.values():
            label.reset()
