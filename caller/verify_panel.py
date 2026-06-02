"""
verify_panel.py — Winner verification panel for the Caller application.

The caller types or scans a card's serial number.
The panel checks it against the current game's called balls and active pattern,
shows the card grid with marks, and allows the caller to officially record winners.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

COLUMNS = ["B", "I", "N", "G", "O"]
COLUMN_RANGES = [range(1,16), range(16,31), range(31,46), range(46,61), range(61,76)]


class CardGridWidget(QWidget):
    """5x5 display of a bingo card with called cells highlighted."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cells: list[list[QLabel]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setSpacing(3)

        for c, letter in enumerate(COLUMNS):
            hdr = QLabel(letter)
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr.setStyleSheet("font-weight: bold; font-size: 12px;")
            layout.addWidget(hdr, 0, c)

        for r in range(5):
            row: list[QLabel] = []
            for c in range(5):
                cell = QLabel()
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFixedSize(50, 50)
                cell.setFont(QFont("Arial", 11, QFont.Weight.Bold))
                cell.setStyleSheet(self._style("empty"))
                layout.addWidget(cell, r + 1, c)
                row.append(cell)
            self._cells.append(row)

    @staticmethod
    def _style(state: str) -> str:
        styles = {
            "empty":    "background:#E2E8F0; color:#94A3B8; border-radius:5px;",
            "unmarked": "background:#F1F5F9; color:#334155; border:2px solid #CBD5E1; border-radius:5px;",
            "marked":   "background:#16A34A; color:#FFF; border:2px solid #15803D; border-radius:5px;",
            "free":     "background:#FDE047; color:#000; border:2px solid #EAB308; border-radius:5px; font-size:9px;",
            "needed":   "background:#FEE2E2; color:#991B1B; border:2px solid #EF4444; border-radius:5px;",
        }
        return f"QLabel {{ {styles.get(state, styles['empty'])} }}"

    def show_card(
        self,
        grid: list[list[int]],
        called_set: set[int],
        pattern_mask: list[list[bool]] | None = None,
    ) -> None:
        for r in range(5):
            for c in range(5):
                cell = self._cells[r][c]
                val  = grid[r][c]

                if r == 2 and c == 2:
                    cell.setText("FREE")
                    cell.setStyleSheet(self._style("free"))
                    continue

                cell.setText(str(val))
                required = pattern_mask[r][c] if pattern_mask else False

                if val in called_set:
                    cell.setStyleSheet(self._style("marked"))
                elif required:
                    cell.setStyleSheet(self._style("needed"))   # uncalled but required
                else:
                    cell.setStyleSheet(self._style("unmarked"))

    def clear(self) -> None:
        for r in range(5):
            for c in range(5):
                self._cells[r][c].setText("")
                self._cells[r][c].setStyleSheet(self._style("empty"))


class VerifyPanel(QWidget):
    """
    Full verification panel.

    Signals:
        winner_recorded(serial)  — emitted after the caller officially records a win
    """

    winner_recorded = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Injected by the main window before use
        self._db          = None
        self._game        = None   # current active Game object
        self._pattern     = None   # current Pattern object
        self._called_balls: list[int] = []

        self._verified_card   = None   # last successfully looked-up BingoCard
        self._verified_is_win = False

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Serial input ──────────────────────────────────────────────────
        input_group = QGroupBox("Card Lookup")
        input_layout = QHBoxLayout(input_group)

        self._serial_edit = QLineEdit()
        self._serial_edit.setPlaceholderText("Enter serial  e.g.  AB3C-D4EF")
        self._serial_edit.setMaxLength(9)
        self._serial_edit.setFont(QFont("Courier", 14))
        self._serial_edit.returnPressed.connect(self._do_verify)
        input_layout.addWidget(self._serial_edit, stretch=1)

        verify_btn = QPushButton("🔍 Verify")
        verify_btn.setFixedHeight(36)
        verify_btn.setStyleSheet(
            "QPushButton { background:#2563EB; color:white; border-radius:5px; font-weight:bold; padding:0 16px;}"
            "QPushButton:hover { background:#1D4ED8; }"
        )
        verify_btn.clicked.connect(self._do_verify)
        input_layout.addWidget(verify_btn)

        root.addWidget(input_group)

        # ── Middle: card grid + result ─────────────────────────────────────
        mid = QHBoxLayout()

        self._card_grid = CardGridWidget()
        mid.addWidget(self._card_grid)

        result_box = QGroupBox("Result")
        result_layout = QVBoxLayout(result_box)

        self._result_label = QLabel("—")
        self._result_label.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setMinimumWidth(220)
        result_layout.addWidget(self._result_label)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(self._detail_label)

        result_layout.addStretch()

        self._record_btn = QPushButton("✅  Record Winner")
        self._record_btn.setFixedHeight(40)
        self._record_btn.setEnabled(False)
        self._record_btn.setStyleSheet(
            "QPushButton { background:#16A34A; color:white; border-radius:5px; font-size:14px; font-weight:bold;}"
            "QPushButton:hover { background:#15803D; }"
            "QPushButton:disabled { background:#CBD5E1; color:#94A3B8; }"
        )
        self._record_btn.clicked.connect(self._record_winner)
        result_layout.addWidget(self._record_btn)

        mid.addWidget(result_box)
        root.addLayout(mid)

        # ── Winners list ──────────────────────────────────────────────────
        winners_group = QGroupBox("Verified Winners — Current Game")
        wl = QVBoxLayout(winners_group)
        self._winners_list = QListWidget()
        self._winners_list.setMaximumHeight(120)
        wl.addWidget(self._winners_list)
        root.addWidget(winners_group)

    # ── Public API ────────────────────────────────────────────────────────

    def set_context(self, db, game, patterns, called_balls: list[int]) -> None:
        self._db           = db
        self._game         = game
        self._patterns     = patterns if isinstance(patterns, list) else [patterns]
        self._called_balls = called_balls
        self._refresh_winners_list()

    def add_ball(self, ball: int) -> None:
        """Called whenever a new ball is drawn, so live re-verify is possible."""
        if ball not in self._called_balls:
            self._called_balls.append(ball)
        if self._verified_card:
            self._do_verify()   # re-check with updated ball list

    def reset(self) -> None:
        self._game         = None
        self._pattern      = None
        self._called_balls = []
        self._verified_card   = None
        self._verified_is_win = False
        self._serial_edit.clear()
        self._card_grid.clear()
        self._result_label.setText("—")
        self._result_label.setStyleSheet("")
        self._detail_label.clear()
        self._record_btn.setEnabled(False)
        self._winners_list.clear()

    # ── Internal ──────────────────────────────────────────────────────────

    def _do_verify(self) -> None:
        from card_generator import check_win, describe_missing

        serial = self._serial_edit.text().strip().upper()
        if not serial:
            return

        if not self._db:
            self._show_error("No database connected.")
            return

        card = self._db.get_card_by_serial(serial)
        if card is None:
            self._card_grid.clear()
            self._result_label.setText("NOT FOUND")
            self._result_label.setStyleSheet("color: #DC2626;")
            self._detail_label.setText(f"Serial '{serial}' is not in the database.")
            self._record_btn.setEnabled(False)
            self._verified_card = None
            return

        self._verified_card = card
        called_set = set(self._called_balls)
        # Build combined mask for display (union of all selected patterns)
        if self._patterns:
            combined_mask = [[False]*5 for _ in range(5)]
            for p in self._patterns:
                for r in range(5):
                    for c in range(5):
                        if p.mask[r][c]:
                            combined_mask[r][c] = True
        else:
            combined_mask = None

        self._card_grid.show_card(card.grid, called_set, combined_mask)

        if self._game and self._patterns:
            is_win = check_win(card, self._patterns, self._called_balls)
            self._verified_is_win = is_win

            if is_win:
                self._result_label.setText("🎉 BINGO!")
                self._result_label.setStyleSheet("color: #16A34A;")
                pat_names = " + ".join(p.name for p in self._patterns)
                self._detail_label.setText(
                    f"Pattern: {pat_names}\n"
                    f"Balls called: {len(self._called_balls)}"
                )
                # Only allow recording if not already recorded
                existing = [w.card_serial for w in self._db.get_winners_for_game(self._game.id)]
                self._record_btn.setEnabled(serial not in existing)
            else:
                self._result_label.setText("✗ No Bingo")
                self._result_label.setStyleSheet("color: #DC2626;")
                desc = describe_missing(card, self._patterns, self._called_balls)
                self._detail_label.setText(desc)
                self._record_btn.setEnabled(False)
        else:
            self._result_label.setText("Card found")
            self._result_label.setStyleSheet("color: #2563EB;")
            self._detail_label.setText("No active game to verify against.")
            self._record_btn.setEnabled(False)

    def _record_winner(self) -> None:
        if not self._verified_card or not self._game or not self._db:
            return

        serial = self._verified_card.serial
        self._db.record_winner(self._game.id, serial)
        self._record_btn.setEnabled(False)
        self._refresh_winners_list()
        self.winner_recorded.emit(serial)

        QMessageBox.information(
            self,
            "Winner Recorded",
            f"Card {serial} has been recorded as a winner!",
        )

    def _refresh_winners_list(self) -> None:
        self._winners_list.clear()
        if not self._db or not self._game:
            return
        for w in self._db.get_winners_for_game(self._game.id):
            self._winners_list.addItem(f"✅  {w.card_serial}   —   {w.verified_at}")

    def _show_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Verification Error", msg)
