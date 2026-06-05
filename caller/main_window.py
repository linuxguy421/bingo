"""
main_window.py — Bingo Caller main window.

Tabs:
  1. Setup    — create/load sessions, configure games
  2. Call     — draw balls, ball board, timer, pattern preview
  3. Verify   — serial lookup and winner recording
  4. Patterns — manage built-in and custom patterns
  5. Cards    — card generator (stub for Step 3)
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Parent directory on path so we can import from bingo_system root
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_manager import DatabaseManager
from models import Game, Pattern

from caller.ball_board     import BallBoardWidget
from caller.pattern_widget import PatternEditorWidget, PatternPreviewWidget
from caller.verify_panel   import VerifyPanel
from caller.ws_server      import WSServerThread


# ── Helper ───────────────────────────────────────────────────────────────────

def _combine_masks(patterns: list) -> list[list[bool]]:
    """Return a 5x5 mask that is the union (OR) of all supplied pattern masks."""
    combined = [[False] * 5 for _ in range(5)]
    for p in patterns:
        for r in range(5):
            for c in range(5):
                if p.mask[r][c]:
                    combined[r][c] = True
    return combined


# ── Stylesheet ────────────────────────────────────────────────────────────────

APP_STYLE = """
QMainWindow, QWidget {
    background-color: #F8FAFC;
    color: #1E293B;
    font-family: Arial, sans-serif;
}
QTabWidget::pane {
    border: 1px solid #CBD5E1;
    background: #F8FAFC;
    border-radius: 4px;
}
QTabBar::tab {
    background: #E2E8F0;
    color: #475569;
    padding: 8px 20px;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
    font-size: 12px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #2563EB;
    color: white;
}
QGroupBox {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    margin-top: 8px;
    padding: 8px;
    font-weight: bold;
    font-size: 11px;
    color: #334155;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 5px 8px;
    background: white;
    font-size: 12px;
}
QListWidget {
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    background: white;
}
QStatusBar {
    background: #1E293B;
    color: #94A3B8;
    font-size: 11px;
}
"""

BTN_PRIMARY  = "QPushButton{background:#2563EB;color:white;font-weight:bold;}QPushButton:hover{background:#1D4ED8;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"
BTN_SUCCESS  = "QPushButton{background:#16A34A;color:white;font-weight:bold;}QPushButton:hover{background:#15803D;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"
BTN_DANGER   = "QPushButton{background:#DC2626;color:white;font-weight:bold;}QPushButton:hover{background:#B91C1C;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"
BTN_NEUTRAL  = "QPushButton{background:#64748B;color:white;font-weight:bold;}QPushButton:hover{background:#475569;}QPushButton:disabled{background:#CBD5E1;color:#94A3B8;}"

AUTO_SPEEDS = [("5 sec", 5), ("10 sec", 10), ("15 sec", 15), ("30 sec", 30), ("60 sec", 60)]


# ── Main Window ───────────────────────────────────────────────────────────────

class CallerMainWindow(QMainWindow):
    """The top-level window for the Bingo Caller application."""

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__()
        self.db = db

        # ── Runtime state ─────────────────────────────────────────────────
        self._session          = None
        self._game             = None
        self._active_patterns: list[Pattern] = []
        self._called_balls: list[int] = []
        self._remaining_balls: list[int] = []
        self._clients_connected = 0

        # ── Auto-draw timer ───────────────────────────────────────────────
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._draw_ball)

        # ── WebSocket server ──────────────────────────────────────────────
        self._ws_server = WSServerThread(host="0.0.0.0", port=8765, parent=self)
        self._ws_server.server_ready.connect(self._on_server_ready)
        self._ws_server.server_error.connect(self._on_server_error)
        self._ws_server.client_count_changed.connect(self._on_client_count)
        self._ws_server.start()

        # ── UI ────────────────────────────────────────────────────────────
        self.setWindowTitle("🎱 Bingo Caller")
        self.resize(1200, 800)
        self.setStyleSheet(APP_STYLE)

        self._build_ui()
        self._build_status_bar()
        self._refresh_patterns_combo()
        self._update_ui_state()

    # ══════════════════════════════════════════════════════════════════════
    #  UI Construction
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_setup_tab(),    "⚙  Setup")
        self._tabs.addTab(self._build_call_tab(),     "🎱 Call")
        self._tabs.addTab(self._build_verify_tab(),   "✅ Verify")
        self._tabs.addTab(self._build_patterns_tab(), "🔲 Patterns")
        self._tabs.addTab(self._build_cards_tab(),    "🃏 Cards")

    # ── Setup Tab ─────────────────────────────────────────────────────────

    def _build_setup_tab(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)

        # Left: Session
        session_group = QGroupBox("Session")
        sf = QFormLayout(session_group)

        self._session_name_edit = QLineEdit()
        self._session_name_edit.setPlaceholderText("e.g. Friday Night Bingo")
        sf.addRow("Name:", self._session_name_edit)

        new_session_btn = QPushButton("Create New Session")
        new_session_btn.setStyleSheet(BTN_PRIMARY)
        new_session_btn.clicked.connect(self._create_session)
        sf.addRow(new_session_btn)

        self._session_status_label = QLabel("No active session")
        self._session_status_label.setStyleSheet("color:#64748B; font-style:italic;")
        sf.addRow(self._session_status_label)

        sf.addRow(QLabel("Recent sessions:"))
        self._sessions_list = QListWidget()
        self._sessions_list.setMaximumHeight(150)
        self._sessions_list.itemDoubleClicked.connect(self._load_session_from_list)
        sf.addRow(self._sessions_list)
        self._refresh_sessions_list()

        outer.addWidget(session_group)

        # Right: Game setup
        game_group = QGroupBox("Game Configuration")
        gf = QFormLayout(game_group)

        # Multi-select pattern list (checkboxes)
        gf.addRow(QLabel("Patterns (check one or more):"))
        self._pattern_list = QListWidget()
        self._pattern_list.setMaximumHeight(160)
        self._pattern_list.setToolTip(
            "Check multiple patterns — the player must satisfy ALL of them to win."
        )
        self._pattern_list.itemChanged.connect(self._on_pattern_selection_changed)
        gf.addRow(self._pattern_list)

        self._combined_label = QLabel()
        self._combined_label.setStyleSheet("color:#2563EB; font-size:11px; font-style:italic;")
        self._combined_label.setWordWrap(True)
        gf.addRow(self._combined_label)

        self._prize_spin = QDoubleSpinBox()
        self._prize_spin.setPrefix("$ ")
        self._prize_spin.setRange(0, 999999)
        self._prize_spin.setDecimals(2)
        self._prize_spin.setValue(0)
        gf.addRow("Prize Amount:", self._prize_spin)

        self._start_game_btn = QPushButton("▶  Start Game")
        self._start_game_btn.setStyleSheet(BTN_SUCCESS)
        self._start_game_btn.setFixedHeight(38)
        self._start_game_btn.clicked.connect(self._start_game)
        gf.addRow(self._start_game_btn)

        self._end_game_btn = QPushButton("⏹  End Game")
        self._end_game_btn.setStyleSheet(BTN_DANGER)
        self._end_game_btn.setFixedHeight(38)
        self._end_game_btn.clicked.connect(self._end_game)
        gf.addRow(self._end_game_btn)

        gf.addRow(QLabel("Games in session:"))
        self._games_list = QListWidget()
        self._games_list.setMaximumHeight(150)
        gf.addRow(self._games_list)

        outer.addWidget(game_group)
        return w

    # ── Call Tab ──────────────────────────────────────────────────────────

    def _build_call_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)

        # Left: Ball board
        board_group = QGroupBox("Ball Board")
        bl = QVBoxLayout(board_group)
        self._ball_board = BallBoardWidget()
        bl.addWidget(self._ball_board)
        layout.addWidget(board_group, stretch=3)

        # Right: Controls
        ctrl_panel = QVBoxLayout()
        layout.addLayout(ctrl_panel, stretch=1)

        # Last ball
        last_group = QGroupBox("Last Ball Drawn")
        ll = QVBoxLayout(last_group)
        self._last_ball_label = QLabel("—")
        self._last_ball_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_ball_label.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        self._last_ball_label.setStyleSheet("color:#2563EB; min-height:80px;")
        ll.addWidget(self._last_ball_label)
        self._ball_letter_label = QLabel()
        self._ball_letter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ball_letter_label.setFont(QFont("Arial", 16))
        ll.addWidget(self._ball_letter_label)
        ctrl_panel.addWidget(last_group)

        # Stats
        stats_group = QGroupBox("Stats")
        sl = QFormLayout(stats_group)
        self._called_count_label = QLabel("0 / 75")
        self._called_count_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        sl.addRow("Called:", self._called_count_label)
        ctrl_panel.addWidget(stats_group)

        # Draw controls
        draw_group = QGroupBox("Draw Controls")
        dl = QVBoxLayout(draw_group)

        self._draw_btn = QPushButton("🎱  DRAW BALL")
        self._draw_btn.setFixedHeight(56)
        self._draw_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self._draw_btn.setStyleSheet(BTN_PRIMARY)
        self._draw_btn.clicked.connect(self._draw_ball)
        dl.addWidget(self._draw_btn)

        auto_row = QHBoxLayout()
        self._auto_btn = QPushButton("⏱  Auto: OFF")
        self._auto_btn.setFixedHeight(34)
        self._auto_btn.setStyleSheet(BTN_NEUTRAL)
        self._auto_btn.setCheckable(True)
        self._auto_btn.clicked.connect(self._toggle_auto_draw)
        auto_row.addWidget(self._auto_btn)

        self._speed_combo = QComboBox()
        for label, _ in AUTO_SPEEDS:
            self._speed_combo.addItem(label)
        self._speed_combo.setCurrentIndex(1)    # default 10s
        self._speed_combo.currentIndexChanged.connect(self._update_auto_speed)
        auto_row.addWidget(self._speed_combo)
        dl.addLayout(auto_row)

        ctrl_panel.addWidget(draw_group)

        # Pattern preview
        pattern_group = QGroupBox("Active Pattern")
        pl = QVBoxLayout(pattern_group)
        self._pattern_name_label = QLabel("None")
        self._pattern_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pattern_name_label.setStyleSheet("font-weight:bold; font-size:12px;")
        pl.addWidget(self._pattern_name_label)
        self._pattern_preview = PatternPreviewWidget(cell_size=26)
        self._pattern_preview.setMaximumHeight(160)
        pl.addWidget(self._pattern_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        ctrl_panel.addWidget(pattern_group)

        # Prize
        prize_group = QGroupBox("Prize")
        prizl = QVBoxLayout(prize_group)
        self._prize_display = QLabel("$0.00")
        self._prize_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prize_display.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self._prize_display.setStyleSheet("color:#16A34A;")
        prizl.addWidget(self._prize_display)
        ctrl_panel.addWidget(prize_group)

        ctrl_panel.addStretch()
        return w

    # ── Verify Tab ────────────────────────────────────────────────────────

    def _build_verify_tab(self) -> QWidget:
        self._verify_panel = VerifyPanel()
        self._verify_panel.winner_recorded.connect(self._on_winner_recorded)
        return self._verify_panel

    # ── Patterns Tab ─────────────────────────────────────────────────────

    def _build_patterns_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup, QStackedWidget
        from caller.pattern_widget import CompoundEditorWidget

        w = QWidget()
        layout = QHBoxLayout(w)

        # ── Left: pattern list ────────────────────────────────────────────
        left = QVBoxLayout()
        left.addWidget(QLabel("Patterns:"))
        self._patterns_list = QListWidget()
        self._patterns_list.setMaximumWidth(230)
        self._patterns_list.currentItemChanged.connect(self._on_pattern_list_select)
        left.addWidget(self._patterns_list, stretch=1)

        btn_row = QHBoxLayout()
        new_pat_btn = QPushButton("New")
        new_pat_btn.setStyleSheet(BTN_PRIMARY)
        new_pat_btn.clicked.connect(self._new_pattern)
        btn_row.addWidget(new_pat_btn)
        self._del_pat_btn = QPushButton("Delete")
        self._del_pat_btn.setStyleSheet(BTN_DANGER)
        self._del_pat_btn.clicked.connect(self._delete_pattern)
        btn_row.addWidget(self._del_pat_btn)
        left.addLayout(btn_row)
        layout.addLayout(left)

        # ── Right: editor ─────────────────────────────────────────────────
        right = QVBoxLayout()

        # Name row
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._pat_name_edit = QLineEdit()
        name_row.addWidget(self._pat_name_edit, stretch=1)
        right.addLayout(name_row)

        # Mode toggle
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Type:"))
        self._simple_radio   = QRadioButton("Simple (draw cells)")
        self._compound_radio = QRadioButton("Compound (group patterns)")
        self._simple_radio.setChecked(True)
        self._pat_mode_group = QButtonGroup(w)
        self._pat_mode_group.addButton(self._simple_radio,   0)
        self._pat_mode_group.addButton(self._compound_radio, 1)
        mode_row.addWidget(self._simple_radio)
        mode_row.addWidget(self._compound_radio)
        mode_row.addStretch()
        right.addLayout(mode_row)

        # Stacked editors
        self._editor_stack = QStackedWidget()

        # Page 0 — simple
        simple_page = QWidget()
        sp_layout = QVBoxLayout(simple_page)
        sp_layout.setContentsMargins(0,0,0,0)
        self._pat_editor = PatternEditorWidget()
        sp_layout.addWidget(self._pat_editor, alignment=Qt.AlignmentFlag.AlignLeft)
        clr_btn = QPushButton("Clear")
        clr_btn.setStyleSheet(BTN_NEUTRAL)
        clr_btn.setMaximumWidth(80)
        clr_btn.clicked.connect(self._pat_editor.clear)
        sp_layout.addWidget(clr_btn)
        sp_layout.addStretch()
        self._editor_stack.addWidget(simple_page)

        # Page 1 — compound
        self._compound_editor = CompoundEditorWidget()
        self._editor_stack.addWidget(self._compound_editor)

        self._simple_radio.toggled.connect(
            lambda on: self._editor_stack.setCurrentIndex(0 if on else 1)
        )
        right.addWidget(self._editor_stack, stretch=1)

        # Save button
        self._save_pat_btn = QPushButton("💾  Save Pattern")
        self._save_pat_btn.setStyleSheet(BTN_SUCCESS)
        self._save_pat_btn.clicked.connect(self._save_pattern)
        right.addWidget(self._save_pat_btn)

        layout.addLayout(right, stretch=1)
        self._refresh_patterns_list()
        return w

    # ── Cards Tab ────────────────────────────────────────────────────────

    def _build_cards_tab(self) -> QWidget:
        from caller.card_panel import CardGeneratorPanel
        self._card_panel = CardGeneratorPanel()
        self._card_panel.db = self.db
        return self._card_panel

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_session = QLabel("Session: None")
        self._status_game    = QLabel("Game: None")
        self._status_server  = QLabel("Server: starting…")
        self._status_clients = QLabel("Displays: 0")
        for lbl in [self._status_session, self._status_game,
                    self._status_server, self._status_clients]:
            sb.addPermanentWidget(lbl)
            sb.addPermanentWidget(QLabel(" │ "))

    # ══════════════════════════════════════════════════════════════════════
    #  Session logic
    # ══════════════════════════════════════════════════════════════════════

    def _create_session(self) -> None:
        name = self._session_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Session Name", "Please enter a session name.")
            return
        self._session = self.db.create_session(name)
        self._session_name_edit.clear()
        self._session_status_label.setText(f"Active: {self._session.name}")
        self._status_session.setText(f"Session: {self._session.name}")
        self._refresh_sessions_list()
        self._refresh_games_list()
        self._update_ui_state()

    def _refresh_sessions_list(self) -> None:
        self._sessions_list.clear()
        for s in self.db.get_all_sessions():
            item = QListWidgetItem(f"{s.name}  [{s.created_at}]")
            item.setData(Qt.ItemDataRole.UserRole, s)
            self._sessions_list.addItem(item)

    def _load_session_from_list(self, item: QListWidgetItem) -> None:
        session = item.data(Qt.ItemDataRole.UserRole)
        self._session = session
        self._session_status_label.setText(f"Active: {session.name}")
        self._status_session.setText(f"Session: {session.name}")
        self._refresh_games_list()
        self._update_ui_state()

    # ══════════════════════════════════════════════════════════════════════
    #  Game logic
    # ══════════════════════════════════════════════════════════════════════

    def _start_game(self) -> None:
        if not self._session:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return

        patterns = self._get_selected_patterns()
        if not patterns:
            QMessageBox.warning(self, "No Pattern", "Select at least one pattern before starting.")
            return

        # End any active game first
        if self._game and self._game.status == "active":
            self._end_game()

        game = Game(
            session_id=self._session.id,
            pattern_ids=[p.id for p in patterns],
            prize_amount=self._prize_spin.value(),
            status="active",
        )
        self._game = self.db.create_game(game)
        self._game.status = "active"

        self._active_patterns = patterns          # list[Pattern]
        self._called_balls    = []
        self._remaining_balls = list(range(1, 76))

        # Reset UI
        self._ball_board.reset()
        self._last_ball_label.setText("—")
        self._ball_letter_label.clear()
        self._called_count_label.setText("0 / 75")
        self._prize_display.setText(f"${self._game.prize_amount:,.2f}")
        combined_name = " + ".join(p.name for p in patterns)
        self._pattern_name_label.setText(combined_name)
        combined_mask = _combine_masks(patterns)
        self._pattern_preview.set_pattern(combined_mask)

        self._verify_panel.set_context(
            self.db, self._game, self._active_patterns, self._called_balls
        )
        self._verify_panel.reset()
        self._verify_panel.set_context(
            self.db, self._game, self._active_patterns, self._called_balls
        )

        self._refresh_games_list()
        self._update_ui_state()
        self._broadcast_state()

        combined_name = " + ".join(p.name for p in patterns)
        self._status_game.setText(f"Game #{self._game.id} — {combined_name}")
        self._tabs.setCurrentIndex(1)   # jump to Call tab

    def _end_game(self) -> None:
        if not self._game:
            return
        self._auto_timer.stop()
        self._auto_btn.setChecked(False)
        self._auto_btn.setText("⏱  Auto: OFF")
        self.db.update_game_status(self._game.id, "completed")
        self._game.status = "completed"
        self._refresh_games_list()
        self._update_ui_state()
        self._broadcast_state()
        self._status_game.setText("Game: completed")

    def _refresh_games_list(self) -> None:
        self._games_list.clear()
        if not self._session:
            return
        for g in self.db.get_games_for_session(self._session.id):
            pat_names = []
            for pid in g.pattern_ids:
                p = self.db.get_pattern_by_id(pid)
                if p: pat_names.append(p.name)
            pat_label = " + ".join(pat_names) if pat_names else "?"
            self._games_list.addItem(
                f"#{g.id}  {pat_label}  ${g.prize_amount:,.2f}  [{g.status}]  "
                f"({len(g.drawn_balls)} balls)"
            )

    # ══════════════════════════════════════════════════════════════════════
    #  Ball drawing
    # ══════════════════════════════════════════════════════════════════════

    def _draw_ball(self) -> None:
        if not self._game or self._game.status != "active":
            return
        if not self._remaining_balls:
            QMessageBox.information(self, "All Balls Called", "All 75 balls have been called!")
            self._auto_timer.stop()
            return

        ball = random.choice(self._remaining_balls)
        self._remaining_balls.remove(ball)
        self._called_balls.append(ball)
        order = len(self._called_balls)

        self.db.record_ball(self._game.id, ball, order)

        # Update board
        self._ball_board.update_called(self._called_balls, last_ball=ball)
        self._last_ball_label.setText(str(ball))

        # Column letter label
        letter = self._ball_letter_label_for(ball)
        self._ball_letter_label.setText(f"  {letter}{ball}")

        self._called_count_label.setText(f"{len(self._called_balls)} / 75")

        # Sync verify panel
        self._verify_panel.add_ball(ball)

        self._broadcast_state()

    @staticmethod
    def _ball_letter_label_for(ball: int) -> str:
        col_names = ["B", "I", "N", "G", "O"]
        ranges = [range(1,16), range(16,31), range(31,46), range(46,61), range(61,76)]
        for letter, r in zip(col_names, ranges):
            if ball in r:
                return letter
        return ""

    # ── Auto-draw ─────────────────────────────────────────────────────────

    def _toggle_auto_draw(self, checked: bool) -> None:
        if checked:
            interval_s = AUTO_SPEEDS[self._speed_combo.currentIndex()][1]
            self._auto_timer.start(interval_s * 1000)
            self._auto_btn.setText("⏱  Auto: ON")
            self._auto_btn.setStyleSheet(
                "QPushButton{background:#D97706;color:white;font-weight:bold;}"
            )
        else:
            self._auto_timer.stop()
            self._auto_btn.setText("⏱  Auto: OFF")
            self._auto_btn.setStyleSheet(BTN_NEUTRAL)

    def _update_auto_speed(self) -> None:
        if self._auto_timer.isActive():
            interval_s = AUTO_SPEEDS[self._speed_combo.currentIndex()][1]
            self._auto_timer.setInterval(interval_s * 1000)

    # ══════════════════════════════════════════════════════════════════════
    #  Patterns
    # ══════════════════════════════════════════════════════════════════════

    def _refresh_patterns_combo(self) -> None:
        """Rebuild the setup-tab multi-select pattern checklist."""
        self._pattern_list.blockSignals(True)
        # Remember which names were checked
        checked_names = {
            self._pattern_list.item(i).text()
            for i in range(self._pattern_list.count())
            if self._pattern_list.item(i).checkState() == Qt.CheckState.Checked
        }
        self._pattern_list.clear()
        for p in self.db.get_all_patterns():
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = Qt.CheckState.Checked if p.name in checked_names else Qt.CheckState.Unchecked
            item.setCheckState(state)
            self._pattern_list.addItem(item)
        self._pattern_list.blockSignals(False)
        self._on_pattern_selection_changed()

    def _refresh_patterns_list(self) -> None:
        self._patterns_list.clear()
        for p in self.db.get_all_patterns():
            tag = ""
            if p.is_compound:
                op = p.compound_operator
                tag = f" [{op}]"
            elif p.is_custom:
                tag = " [custom]"
            item = QListWidgetItem(f"{p.name}{tag}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._patterns_list.addItem(item)

    def _on_pattern_selection_changed(self) -> None:
        """Update the combined-pattern label when the selection changes."""
        patterns = self._get_selected_patterns()
        if not patterns:
            self._combined_label.setText("No pattern selected")
        elif len(patterns) == 1:
            self._combined_label.setText(f"Pattern: {patterns[0].name}")
        else:
            names = " + ".join(p.name for p in patterns)
            self._combined_label.setText(f"Combined: {names}")

    def _get_selected_patterns(self) -> list[Pattern]:
        """Return all checked patterns from the setup-tab list."""
        result = []
        for i in range(self._pattern_list.count()):
            item = self._pattern_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    # kept for compat — returns first selected pattern or None
    def _get_selected_pattern(self) -> Pattern | None:
        pats = self._get_selected_patterns()
        return pats[0] if pats else None

    def _on_pattern_list_select(self, current: QListWidgetItem, _prev) -> None:
        if not current:
            return
        p: Pattern = current.data(Qt.ItemDataRole.UserRole)
        self._pat_name_edit.setText(p.name)
        self._del_pat_btn.setEnabled(p.is_custom)

        if p.is_compound:
            self._compound_radio.setChecked(True)
            self._editor_stack.setCurrentIndex(1)
            self._compound_editor.populate(self.db.get_all_patterns())
            self._compound_editor.load_compound(p)
        else:
            self._simple_radio.setChecked(True)
            self._editor_stack.setCurrentIndex(0)
            self._pat_editor.set_mask(p.mask)

    def _new_pattern(self) -> None:
        self._pat_name_edit.clear()
        self._pat_editor.clear()
        self._compound_editor.clear()
        self._simple_radio.setChecked(True)
        self._editor_stack.setCurrentIndex(0)
        self._patterns_list.clearSelection()
        self._del_pat_btn.setEnabled(False)
        # Refresh compound editor member list with latest patterns
        self._compound_editor.populate(self.db.get_all_patterns())

    def _save_pattern(self) -> None:
        name = self._pat_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Enter a name for the pattern.")
            return

        is_compound = self._compound_radio.isChecked()

        if is_compound:
            if not self._compound_editor.is_valid():
                QMessageBox.warning(self, "Too Few Patterns",
                                    "Select at least 2 component patterns.")
                return
            members = self._compound_editor.get_selected_patterns()
            operator = self._compound_editor.get_operator()
            # Compute union mask for display purposes
            union = [[False]*5 for _ in range(5)]
            for mp in members:
                for r in range(5):
                    for c in range(5):
                        if mp.mask[r][c]:
                            union[r][c] = True
            new_p = Pattern(
                name=name, mask=union, is_custom=True, is_compound=True,
                compound_operator=operator,
                compound_member_ids=[mp.id for mp in members],
            )
        else:
            if not self._pat_editor.has_cells_selected():
                QMessageBox.warning(self, "Empty Pattern", "Select at least one cell.")
                return
            new_p = Pattern(name=name, mask=self._pat_editor.get_mask(), is_custom=True)

        # If editing existing custom pattern, update in place
        current = self._patterns_list.currentItem()
        if current:
            existing: Pattern = current.data(Qt.ItemDataRole.UserRole)
            if existing.is_custom:
                existing.name = new_p.name
                existing.mask = new_p.mask
                existing.is_compound = new_p.is_compound
                existing.compound_operator = new_p.compound_operator
                existing.compound_member_ids = new_p.compound_member_ids
                self.db.update_pattern(existing)
                self._refresh_patterns_list()
                self._refresh_patterns_combo()
                return

        self.db.save_pattern(new_p)
        self._refresh_patterns_list()
        self._refresh_patterns_combo()

    def _delete_pattern(self) -> None:
        current = self._patterns_list.currentItem()
        if not current:
            return
        p: Pattern = current.data(Qt.ItemDataRole.UserRole)
        if not p.is_custom:
            QMessageBox.information(self, "Cannot Delete", "Built-in patterns cannot be deleted.")
            return
        if QMessageBox.question(
            self, "Delete Pattern",
            f"Delete '{p.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_pattern(p.id)
            self._refresh_patterns_list()
            self._refresh_patterns_combo()

    # ══════════════════════════════════════════════════════════════════════
    #  WebSocket server callbacks
    # ══════════════════════════════════════════════════════════════════════

    @pyqtSlot(str)
    def _on_server_ready(self, address: str) -> None:
        self._status_server.setText(f"Server: {address}")

    @pyqtSlot(str)
    def _on_server_error(self, msg: str) -> None:
        self._status_server.setText(f"Server error: {msg}")

    @pyqtSlot(int)
    def _on_client_count(self, count: int) -> None:
        self._clients_connected = count
        self._status_clients.setText(f"Displays: {count}")

    def _patterns_by_id(self) -> dict:
        """Convenience: return all DB patterns keyed by id for compound resolution."""
        return {p.id: p for p in self.db.get_all_patterns()}

    def _broadcast_state(self) -> None:
        patterns = getattr(self, "_active_patterns", [])
        if patterns:
            combined_name = " + ".join(p.name for p in patterns)
            combined_mask = _combine_masks(patterns)
        else:
            combined_name = ""
            combined_mask = None
        state = {
            "type":          "state",
            "session_name":  self._session.name if self._session else "",
            "game_id":       self._game.id if self._game else None,
            "game_status":   self._game.status if self._game else "idle",
            "pattern_name":  combined_name,
            "pattern_mask":  combined_mask,
            "prize_amount":  self._game.prize_amount if self._game else 0,
            "called_balls":  list(self._called_balls),
            "last_ball":     self._called_balls[-1] if self._called_balls else None,
            "ball_count":    len(self._called_balls),
        }
        self._ws_server.broadcast(state)

    # ══════════════════════════════════════════════════════════════════════
    #  UI state helpers
    # ══════════════════════════════════════════════════════════════════════

    def _update_ui_state(self) -> None:
        has_session = self._session is not None
        game_active = self._game is not None and self._game.status == "active"

        self._start_game_btn.setEnabled(has_session and not game_active)
        self._end_game_btn.setEnabled(game_active)
        self._draw_btn.setEnabled(game_active)
        self._auto_btn.setEnabled(game_active)
        self._speed_combo.setEnabled(game_active)

    @pyqtSlot(str)
    def _on_winner_recorded(self, serial: str) -> None:
        self._status_game.setText(
            self._status_game.text() + f"  |  Winner: {serial}"
        )

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._auto_timer.stop()
        self._ws_server.stop()
        self._ws_server.wait(2000)
        super().closeEvent(event)
