"""
pattern_widget.py — Pattern display and editor widgets.

PatternPreviewWidget  : read-only 5x5 mini grid shown in the Call tab.
PatternEditorWidget   : interactive 5x5 toggle grid for creating custom patterns.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

_ACTIVE_STYLE = """
    QPushButton {
        background-color: #2563EB;
        color: #FFFFFF;
        border: 2px solid #1D4ED8;
        border-radius: 4px;
        font-weight: bold;
        font-size: 11px;
    }
"""
_INACTIVE_STYLE = """
    QPushButton {
        background-color: #E2E8F0;
        color: #94A3B8;
        border: 2px solid #CBD5E1;
        border-radius: 4px;
        font-size: 10px;
    }
"""
_FREE_STYLE = """
    QPushButton {
        background-color: #FDE047;
        color: #000000;
        border: 2px solid #EAB308;
        border-radius: 4px;
        font-weight: bold;
        font-size: 9px;
    }
"""

# Preview-only styles (smaller)
_PRV_ACTIVE = """
    QLabel {
        background-color: #2563EB;
        color: white;
        border-radius: 3px;
        font-size: 8px;
        font-weight: bold;
    }
"""
_PRV_INACTIVE = """
    QLabel {
        background-color: #E2E8F0;
        border-radius: 3px;
    }
"""
_PRV_FREE = """
    QLabel {
        background-color: #FDE047;
        border-radius: 3px;
    }
"""


# ---------------------------------------------------------------------------
# PatternPreviewWidget — small read-only grid
# ---------------------------------------------------------------------------

class PatternPreviewWidget(QWidget):
    """Compact 5x5 display of which cells are required for the active pattern."""

    def __init__(self, cell_size: int = 22, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cell_size = cell_size
        self._cells: list[list[QLabel]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 2, 2, 2)

        for r in range(5):
            row = []
            for c in range(5):
                cell = QLabel()
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFixedSize(self._cell_size, self._cell_size)
                if r == 2 and c == 2:
                    cell.setText("★")
                    cell.setStyleSheet(_PRV_FREE)
                else:
                    cell.setStyleSheet(_PRV_INACTIVE)
                layout.addWidget(cell, r, c)
                row.append(cell)
            self._cells.append(row)

    def set_pattern(self, mask: list[list[bool]] | None) -> None:
        for r in range(5):
            for c in range(5):
                cell = self._cells[r][c]
                if r == 2 and c == 2:
                    cell.setStyleSheet(_PRV_FREE)
                elif mask and mask[r][c]:
                    cell.setStyleSheet(_PRV_ACTIVE)
                else:
                    cell.setStyleSheet(_PRV_INACTIVE)

    def clear(self) -> None:
        self.set_pattern(None)


# ---------------------------------------------------------------------------
# PatternEditorWidget — interactive editor
# ---------------------------------------------------------------------------

class PatternEditorWidget(QWidget):
    """
    Interactive 5x5 toggle grid for building custom patterns.
    Emits pattern_changed(mask) whenever a cell is toggled.
    The FREE space (row 2, col 2) is always active and not toggleable.
    """

    pattern_changed = pyqtSignal(list)   # emits 5x5 list[list[bool]]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[list[QPushButton]] = []
        self._mask: list[list[bool]] = [[False] * 5 for _ in range(5)]
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        col_letters = "BINGO"
        for c, letter in enumerate(col_letters):
            header = QLabel(letter)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            layout.addWidget(header, 0, c)

        for r in range(5):
            row_btns: list[QPushButton] = []
            for c in range(5):
                btn = QPushButton()
                btn.setFixedSize(44, 44)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

                if r == 2 and c == 2:
                    btn.setText("FREE")
                    btn.setStyleSheet(_FREE_STYLE)
                    btn.setEnabled(False)
                else:
                    btn.setStyleSheet(_INACTIVE_STYLE)
                    btn.clicked.connect(lambda _, row=r, col=c: self._toggle(row, col))

                layout.addWidget(btn, r + 1, c)
                row_btns.append(btn)
            self._buttons.append(row_btns)

    def _toggle(self, row: int, col: int) -> None:
        self._mask[row][col] = not self._mask[row][col]
        self._refresh_cell(row, col)
        self.pattern_changed.emit([r[:] for r in self._mask])

    def _refresh_cell(self, row: int, col: int) -> None:
        if row == 2 and col == 2:
            return
        style = _ACTIVE_STYLE if self._mask[row][col] else _INACTIVE_STYLE
        self._buttons[row][col].setStyleSheet(style)

    # ── Public API ────────────────────────────────────────────────────────

    def get_mask(self) -> list[list[bool]]:
        return [r[:] for r in self._mask]

    def set_mask(self, mask: list[list[bool]]) -> None:
        for r in range(5):
            for c in range(5):
                if r == 2 and c == 2:
                    continue
                self._mask[r][c] = mask[r][c]
                self._refresh_cell(r, c)

    def clear(self) -> None:
        self._mask = [[False] * 5 for _ in range(5)]
        for r in range(5):
            for c in range(5):
                if r == 2 and c == 2:
                    continue
                self._buttons[r][c].setStyleSheet(_INACTIVE_STYLE)

    def has_cells_selected(self) -> bool:
        return any(self._mask[r][c] for r in range(5) for c in range(5))
