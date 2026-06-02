"""
card_panel.py — Card Generator panel for the Caller application's Cards tab.

Features:
  • Generate 1–2000 cards in a background thread (non-blocking)
  • Progress bar for large batches
  • Scrollable table of generated serials
  • Export selection (or all) to PDF
  • Preview a card by clicking its serial
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from card_generator import generate_cards
from models import BingoCard

BTN_PRIMARY = "QPushButton{background:#2563EB;color:white;font-weight:bold;border-radius:5px;padding:6px 14px;}QPushButton:hover{background:#1D4ED8;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"
BTN_SUCCESS = "QPushButton{background:#16A34A;color:white;font-weight:bold;border-radius:5px;padding:6px 14px;}QPushButton:hover{background:#15803D;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"
BTN_NEUTRAL = "QPushButton{background:#64748B;color:white;font-weight:bold;border-radius:5px;padding:6px 14px;}QPushButton:hover{background:#475569;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"


# ── Background worker ──────────────────────────────────────────────────────

class CardGenWorker(QThread):
    """Generates cards off the main thread to keep the UI responsive."""

    progress  = pyqtSignal(int)         # 0-100
    finished  = pyqtSignal(list)        # list[BingoCard]
    error     = pyqtSignal(str)

    def __init__(self, count: int, serial_exists_fn, parent=None) -> None:
        super().__init__(parent)
        self._count = count
        self._serial_exists = serial_exists_fn

    def run(self) -> None:
        try:
            cards = []
            batch = 50
            for start in range(0, self._count, batch):
                chunk_size = min(batch, self._count - start)
                chunk = generate_cards(chunk_size, self._serial_exists)
                cards.extend(chunk)
                pct = int(len(cards) / self._count * 100)
                self.progress.emit(pct)
            self.finished.emit(cards)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Card preview widget ────────────────────────────────────────────────────

class CardPreviewWidget(QWidget):
    """Read-only 5×5 card grid for the preview panel."""

    COLUMNS = "BINGO"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cells: list[list[QLabel]] = []
        layout = QGridLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(4, 4, 4, 4)

        for c, letter in enumerate(self.COLUMNS):
            hdr = QLabel(letter)
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            hdr.setFixedHeight(24)
            layout.addWidget(hdr, 0, c)

        for r in range(5):
            row = []
            for c in range(5):
                cell = QLabel()
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFixedSize(46, 40)
                cell.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                cell.setStyleSheet("QLabel{background:#F1F5F9;border-radius:4px;color:#334155;}")
                layout.addWidget(cell, r + 1, c)
                row.append(cell)
            self._cells.append(row)

        self._serial_lbl = QLabel()
        self._serial_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._serial_lbl.setFont(QFont("Courier", 12, QFont.Weight.Bold))
        self._serial_lbl.setStyleSheet("color:#2563EB; margin-top:4px;")
        layout.addWidget(self._serial_lbl, 6, 0, 1, 5)

    def show_card(self, card: BingoCard) -> None:
        col_bgs = ["#DBEAFE", "#FEE2E2", "#EDE9FE", "#D1FAE5", "#FEF3C7"]
        for r in range(5):
            for c in range(5):
                cell = self._cells[r][c]
                val  = card.grid[r][c]
                if r == 2 and c == 2:
                    cell.setText("★")
                    cell.setStyleSheet("QLabel{background:#FDE047;border-radius:4px;color:#000;font-size:16px;}")
                else:
                    cell.setText(str(val))
                    cell.setStyleSheet(
                        f"QLabel{{background:{col_bgs[c]};border-radius:4px;color:#1E293B;}}"
                    )
        self._serial_lbl.setText(card.serial)

    def clear(self) -> None:
        for r in range(5):
            for c in range(5):
                self._cells[r][c].setText("")
                self._cells[r][c].setStyleSheet("QLabel{background:#F1F5F9;border-radius:4px;}")
        self._serial_lbl.clear()


# ── Card Generator Panel ───────────────────────────────────────────────────

class CardGeneratorPanel(QWidget):
    """
    Full card-generation panel.  Set db before the user interacts with it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.db = None                          # injected by main window
        self._generated_cards: list[BingoCard] = []
        self._worker: CardGenWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setSpacing(10)

        # ── Left: controls + list ─────────────────────────────────────────
        left = QVBoxLayout()

        gen_group = QGroupBox("Generate Cards")
        gf = QHBoxLayout(gen_group)

        gf.addWidget(QLabel("Number of cards:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 2000)
        self._count_spin.setValue(10)
        self._count_spin.setFixedWidth(80)
        gf.addWidget(self._count_spin)

        self._gen_btn = QPushButton("⚡  Generate")
        self._gen_btn.setStyleSheet(BTN_PRIMARY)
        self._gen_btn.setFixedHeight(34)
        self._gen_btn.clicked.connect(self._start_generation)
        gf.addWidget(self._gen_btn)
        left.addWidget(gen_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(10)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar{border-radius:5px;background:#E2E8F0;}"
            "QProgressBar::chunk{background:#2563EB;border-radius:5px;}"
        )
        left.addWidget(self._progress)

        # Stats
        self._stats_label = QLabel("No cards generated yet.")
        self._stats_label.setStyleSheet("color:#64748B; font-size:11px;")
        left.addWidget(self._stats_label)

        # List of serials
        list_lbl = QLabel("Generated Cards (click to preview):")
        list_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        left.addWidget(list_lbl)

        self._cards_list = QListWidget()
        self._cards_list.setFont(QFont("Courier", 11))
        self._cards_list.currentItemChanged.connect(self._preview_selected)
        left.addWidget(self._cards_list, stretch=1)

        # Export button
        export_row = QHBoxLayout()
        self._export_btn = QPushButton("📄  Export All to PDF")
        self._export_btn.setStyleSheet(BTN_SUCCESS)
        self._export_btn.setFixedHeight(36)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_pdf)
        export_row.addWidget(self._export_btn)

        self._clear_btn = QPushButton("Clear List")
        self._clear_btn.setStyleSheet(BTN_NEUTRAL)
        self._clear_btn.setFixedHeight(36)
        self._clear_btn.clicked.connect(self._clear_list)
        export_row.addWidget(self._clear_btn)
        left.addLayout(export_row)

        root.addLayout(left, stretch=2)

        # ── Right: preview ────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        preview_group = QGroupBox("Card Preview")
        pf = QVBoxLayout(preview_group)
        self._preview = CardPreviewWidget()
        pf.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignCenter)

        self._db_count_label = QLabel()
        self._db_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._db_count_label.setStyleSheet("color:#64748B; font-size:11px;")
        pf.addWidget(self._db_count_label)

        right.addWidget(preview_group)
        right.addStretch()
        root.addLayout(right, stretch=1)

        self._refresh_db_count()

    # ── Card generation ───────────────────────────────────────────────────

    def _start_generation(self) -> None:
        if not self.db:
            QMessageBox.warning(self, "No Database", "Database not connected.")
            return

        count = self._count_spin.value()
        self._gen_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._worker = CardGenWorker(count, self.db.serial_exists, parent=self)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_generation_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.start()

    def _on_generation_done(self, cards: list[BingoCard]) -> None:
        # Save to DB in bulk
        self.db.save_cards_bulk(cards)
        self._generated_cards.extend(cards)

        for card in cards:
            item = QListWidgetItem(card.serial)
            item.setData(Qt.ItemDataRole.UserRole, card)
            self._cards_list.addItem(item)

        count = len(cards)
        self._stats_label.setText(
            f"✓ {count} new card{'s' if count != 1 else ''} generated and saved to database."
        )
        self._progress.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._export_btn.setEnabled(bool(self._generated_cards))
        self._refresh_db_count()

    def _on_generation_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._gen_btn.setEnabled(True)
        QMessageBox.critical(self, "Generation Error", f"Failed to generate cards:\n{msg}")

    # ── Preview ───────────────────────────────────────────────────────────

    def _preview_selected(self, current: QListWidgetItem, _prev) -> None:
        if not current:
            self._preview.clear()
            return
        card: BingoCard = current.data(Qt.ItemDataRole.UserRole)
        self._preview.show_card(card)

    # ── Export ────────────────────────────────────────────────────────────

    def _export_pdf(self) -> None:
        if not self._generated_cards:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", "bingo_cards.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return

        try:
            from card_pdf import export_cards_to_pdf
            out = export_cards_to_pdf(self._generated_cards, path)
            QMessageBox.information(
                self, "PDF Exported",
                f"Saved {len(self._generated_cards)} cards to:\n{out}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _clear_list(self) -> None:
        self._generated_cards.clear()
        self._cards_list.clear()
        self._preview.clear()
        self._export_btn.setEnabled(False)
        self._stats_label.setText("List cleared.")

    def _refresh_db_count(self) -> None:
        if self.db:
            total = self.db.get_total_cards()
            self._db_count_label.setText(f"Total cards in database: {total:,}")
