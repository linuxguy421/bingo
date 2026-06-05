"""
pattern_widget.py — Pattern display and editor widgets.

PatternPreviewWidget    : read-only 5x5 mini grid (Call tab / Display).
PatternEditorWidget     : interactive 5x5 toggle grid (simple patterns).
CompoundEditorWidget    : build compound (AND/OR) patterns from existing ones.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_ACTIVE_STYLE = """
    QPushButton {
        background-color: #2563EB; color: #FFFFFF;
        border: 2px solid #1D4ED8; border-radius: 4px;
        font-weight: bold; font-size: 11px;
    }
"""
_INACTIVE_STYLE = """
    QPushButton {
        background-color: #E2E8F0; color: #94A3B8;
        border: 2px solid #CBD5E1; border-radius: 4px; font-size: 10px;
    }
"""
_FREE_STYLE = """
    QPushButton {
        background-color: #FDE047; color: #000000;
        border: 2px solid #EAB308; border-radius: 4px;
        font-weight: bold; font-size: 9px;
    }
"""
_PRV_ACTIVE   = "QLabel{background:#2563EB;color:white;border-radius:3px;font-size:8px;font-weight:bold;}"
_PRV_INACTIVE = "QLabel{background:#E2E8F0;border-radius:3px;}"
_PRV_FREE     = "QLabel{background:#FDE047;border-radius:3px;}"
_PRV_COMPOUND = "QLabel{background:#8B5CF6;color:white;border-radius:3px;font-size:7px;}"


# ---------------------------------------------------------------------------
# PatternPreviewWidget — small read-only grid
# ---------------------------------------------------------------------------

class PatternPreviewWidget(QWidget):
    """Compact 5×5 display of a pattern's mask."""

    def __init__(self, cell_size: int = 22, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cell_size = cell_size
        self._cells: list[list[QLabel]] = []
        self._operator_label = QLabel()
        self._operator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._operator_label.setStyleSheet("font-size:9px; color:#8B5CF6; font-weight:bold;")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 2, 2, 2)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)

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
                grid.addWidget(cell, r, c)
                row.append(cell)
            self._cells.append(row)

        layout.addWidget(grid_w)
        layout.addWidget(self._operator_label)

    def set_pattern(self, mask: list[list[bool]] | None,
                    is_compound: bool = False, operator: str = "OR") -> None:
        for r in range(5):
            for c in range(5):
                cell = self._cells[r][c]
                if r == 2 and c == 2:
                    cell.setStyleSheet(_PRV_FREE)
                    continue
                if mask and mask[r][c]:
                    cell.setStyleSheet(_PRV_COMPOUND if is_compound else _PRV_ACTIVE)
                else:
                    cell.setStyleSheet(_PRV_INACTIVE)

        if is_compound:
            self._operator_label.setText(f"[{operator} compound]")
        else:
            self._operator_label.setText("")

    def clear(self) -> None:
        self.set_pattern(None)


# ---------------------------------------------------------------------------
# PatternEditorWidget — interactive 5×5 toggle grid
# ---------------------------------------------------------------------------

class PatternEditorWidget(QWidget):
    """
    Interactive 5×5 toggle grid for building simple patterns.
    Emits pattern_changed(mask) whenever a cell is toggled.
    """

    pattern_changed = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[list[QPushButton]] = []
        self._mask: list[list[bool]] = [[False] * 5 for _ in range(5)]
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        for c, letter in enumerate("BINGO"):
            hdr = QLabel(letter)
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            layout.addWidget(hdr, 0, c)

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


# ---------------------------------------------------------------------------
# CompoundEditorWidget — build AND/OR compound patterns from existing ones
# ---------------------------------------------------------------------------

class CompoundEditorWidget(QWidget):
    """
    UI for creating and editing compound (grouped) patterns.

    Shows all non-compound patterns as checkable items.
    The user picks AND or OR, checks the components, and saves.

    Example — Hardway Bingo:
        Operator : OR
        Members  : Row 1, Row 2, Row 4, Row 5, Col B, Col I, Col G, Col O
        Meaning  : complete ANY one of these lines (none pass through FREE)

    Example — Progressive Jackpot:
        Operator : AND
        Members  : Four Corners, Diagonal (\\)
        Meaning  : must complete BOTH simultaneously
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._available_patterns: list = []   # list[Pattern] — simple patterns to pick from
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(6, 6, 6, 6)

        # Operator selector
        op_group = QGroupBox("Win Condition")
        op_layout = QHBoxLayout(op_group)
        self._and_radio = QRadioButton("AND — must complete ALL selected patterns")
        self._or_radio  = QRadioButton("OR  — complete ANY ONE of the selected patterns")
        self._or_radio.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self._and_radio)
        bg.addButton(self._or_radio)
        op_layout.addWidget(self._or_radio)
        op_layout.addWidget(self._and_radio)
        root.addWidget(op_group)

        # Help text
        self._help_label = QLabel()
        self._help_label.setWordWrap(True)
        self._help_label.setStyleSheet("color:#64748B; font-size:11px; font-style:italic;")
        self._update_help()
        self._or_radio.toggled.connect(self._update_help)
        root.addWidget(self._help_label)

        # Component pattern list
        root.addWidget(QLabel("Component Patterns (check to include):"))
        self._members_list = QListWidget()
        self._members_list.setMinimumHeight(180)
        self._members_list.itemChanged.connect(self._on_member_changed)
        root.addWidget(self._members_list, stretch=1)

        # Live preview
        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Preview:"))
        self._preview = PatternPreviewWidget(cell_size=24)
        preview_row.addWidget(self._preview)
        preview_row.addStretch()
        self._selected_count = QLabel("0 patterns selected")
        self._selected_count.setStyleSheet("color:#64748B; font-size:11px;")
        preview_row.addWidget(self._selected_count)
        root.addLayout(preview_row)

    def _update_help(self) -> None:
        if self._or_radio.isChecked():
            self._help_label.setText(
                "OR example: Hardway Bingo — select all lines that don't pass through "
                "the FREE space. A player wins by completing any one of them."
            )
        else:
            self._help_label.setText(
                "AND example: Progressive — select Four Corners AND a Diagonal. "
                "A player must complete ALL selected patterns simultaneously."
            )

    def _on_member_changed(self, _item: QListWidgetItem) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        checked = self.get_selected_patterns()
        count = len(checked)
        self._selected_count.setText(f"{count} pattern{'s' if count != 1 else ''} selected")

        if not checked:
            self._preview.clear()
            return

        # Build union mask for preview
        union = [[False] * 5 for _ in range(5)]
        for p in checked:
            for r in range(5):
                for c in range(5):
                    if p.mask[r][c]:
                        union[r][c] = True

        op = "OR" if self._or_radio.isChecked() else "AND"
        self._preview.set_pattern(union, is_compound=True, operator=op)

    # ── Public API ────────────────────────────────────────────────────────

    def populate(self, patterns: list) -> None:
        """
        Reload the member list from a fresh list of available patterns.
        Call this whenever the pattern library changes.
        Only non-compound patterns are offered as members (prevents circular refs).
        """
        # Remember checked names
        checked_names = self.get_checked_names()

        self._available_patterns = [p for p in patterns if not p.is_compound]
        self._members_list.blockSignals(True)
        self._members_list.clear()
        for p in self._available_patterns:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = Qt.CheckState.Checked if p.name in checked_names else Qt.CheckState.Unchecked
            item.setCheckState(state)
            self._members_list.addItem(item)
        self._members_list.blockSignals(False)
        self._refresh_preview()

    def load_compound(self, pattern) -> None:
        """Populate editor fields from an existing compound Pattern object."""
        if pattern.compound_operator == "AND":
            self._and_radio.setChecked(True)
        else:
            self._or_radio.setChecked(True)

        member_id_set = set(pattern.compound_member_ids)
        self._members_list.blockSignals(True)
        for i in range(self._members_list.count()):
            item = self._members_list.item(i)
            p = item.data(Qt.ItemDataRole.UserRole)
            checked = p.id in member_id_set
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._members_list.blockSignals(False)
        self._refresh_preview()

    def get_operator(self) -> str:
        return "AND" if self._and_radio.isChecked() else "OR"

    def get_selected_patterns(self) -> list:
        return [
            self._members_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._members_list.count())
            if self._members_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def get_checked_names(self) -> set[str]:
        return {
            self._members_list.item(i).text()
            for i in range(self._members_list.count())
            if self._members_list.item(i).checkState() == Qt.CheckState.Checked
        }

    def clear(self) -> None:
        for i in range(self._members_list.count()):
            self._members_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._or_radio.setChecked(True)
        self._preview.clear()

    def is_valid(self) -> bool:
        return len(self.get_selected_patterns()) >= 2
