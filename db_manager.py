"""
db_manager.py — SQLite database manager for the Bingo system.

All database access goes through DatabaseManager.  The caller app creates
one instance at startup and passes it to every component that needs data.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import BingoCard, Game, Pattern, Session, Winner


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Patterns ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS patterns (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    mask               TEXT    NOT NULL,   -- JSON 5x5 boolean array (union for compounds)
    is_custom          INTEGER NOT NULL DEFAULT 0,
    is_compound        INTEGER NOT NULL DEFAULT 0,
    compound_operator  TEXT    NOT NULL DEFAULT 'OR',
    compound_members   TEXT    NOT NULL DEFAULT '[]',  -- JSON list of member pattern IDs
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Cards ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    serial      TEXT    NOT NULL UNIQUE,
    grid        TEXT    NOT NULL,   -- JSON 5x5 integer array
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Sessions ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Games ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    pattern_id   INTEGER NOT NULL REFERENCES patterns(id),
    prize_amount REAL    NOT NULL DEFAULT 0.0,
    status       TEXT    NOT NULL DEFAULT 'pending',   -- pending|active|completed
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Drawn Balls ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS drawn_balls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ball        INTEGER NOT NULL,
    draw_order  INTEGER NOT NULL,
    drawn_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (game_id, ball)
);

-- ── Game ↔ Pattern (many-to-many) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS game_patterns (
    game_id    INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    pattern_id INTEGER NOT NULL REFERENCES patterns(id),
    PRIMARY KEY (game_id, pattern_id)
);

-- ── Winners ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS winners (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    card_serial TEXT    NOT NULL REFERENCES cards(serial),
    verified_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (game_id, card_serial)
);
"""


# ---------------------------------------------------------------------------
# Default built-in patterns
# ---------------------------------------------------------------------------

def _row(r: int) -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for c in range(5):
        mask[r][c] = True
    return mask

def _col(c: int) -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for r in range(5):
        mask[r][c] = True
    return mask

def _diag_main() -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for i in range(5):
        mask[i][i] = True
    return mask

def _diag_anti() -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for i in range(5):
        mask[i][4 - i] = True
    return mask

def _four_corners() -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for r, c in [(0, 0), (0, 4), (4, 0), (4, 4)]:
        mask[r][c] = True
    return mask

def _x_pattern() -> list[list[bool]]:
    main = _diag_main()
    anti = _diag_anti()
    return [[main[r][c] or anti[r][c] for c in range(5)] for r in range(5)]

def _t_pattern() -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for c in range(5):
        mask[0][c] = True   # top row
    for r in range(5):
        mask[r][2] = True   # middle column
    return mask

def _l_pattern() -> list[list[bool]]:
    mask = [[False] * 5 for _ in range(5)]
    for r in range(5):
        mask[r][0] = True   # left column
    for c in range(5):
        mask[4][c] = True   # bottom row
    return mask

def _blackout() -> list[list[bool]]:
    return [[True] * 5 for _ in range(5)]

def _frame() -> list[list[bool]]:
    """Outer ring of the card."""
    mask = [[False] * 5 for _ in range(5)]
    for c in range(5):
        mask[0][c] = True
        mask[4][c] = True
    for r in range(1, 4):
        mask[r][0] = True
        mask[r][4] = True
    return mask

DEFAULT_PATTERNS: list[tuple[str, list[list[bool]]]] = [
    ("Any Single Line",   [[True if r == 0 else False for c in range(5)] for r in range(5)]),  # placeholder — handled specially
    ("Row 1",             _row(0)),
    ("Row 2",             _row(1)),
    ("Row 3 (Middle)",    _row(2)),
    ("Row 4",             _row(3)),
    ("Row 5",             _row(4)),
    ("Col B",             _col(0)),
    ("Col I",             _col(1)),
    ("Col N",             _col(2)),
    ("Col G",             _col(3)),
    ("Col O",             _col(4)),
    ("Diagonal (\\)",     _diag_main()),
    ("Diagonal (/)",      _diag_anti()),
    ("Four Corners",      _four_corners()),
    ("X Pattern",         _x_pattern()),
    ("T Pattern",         _t_pattern()),
    ("L Pattern",         _l_pattern()),
    ("Frame",             _frame()),
    ("Blackout",          _blackout()),
]


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """
    Central access point for all SQLite operations.

    Usage:
        db = DatabaseManager("bingo.db")
        db.initialize()          # creates tables + seeds default patterns
    """

    def __init__(self, db_path: str | Path = "bingo.db") -> None:
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._connection = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def _cursor(self):
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        cur = self._connection.cursor()
        try:
            yield cur
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()

    # ── Init ──────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create schema, run migrations, and seed default patterns."""
        self.connect()
        with self._cursor() as cur:
            cur.executescript(SCHEMA)
        self._migrate()
        self._seed_default_patterns()

    def _migrate(self) -> None:
        """
        Auto-upgrade older databases.
        Safe to call on a fresh DB — all operations use IF NOT EXISTS / INSERT OR IGNORE.
        """
        # Ensure game_patterns table exists (may already exist from SCHEMA on fresh DB)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS game_patterns (
                game_id    INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                pattern_id INTEGER NOT NULL REFERENCES patterns(id),
                PRIMARY KEY (game_id, pattern_id)
            )
        """)
        # If old games table has a pattern_id column, migrate existing rows
        cols = [r[1] for r in self._connection.execute("PRAGMA table_info(games)")]
        if 'pattern_id' in cols:
            self._connection.execute("""
                INSERT OR IGNORE INTO game_patterns (game_id, pattern_id)
                SELECT id, pattern_id FROM games WHERE pattern_id IS NOT NULL
            """)
        # Add compound columns to patterns table if they don't exist yet
        pat_cols = [r[1] for r in self._connection.execute("PRAGMA table_info(patterns)")]
        if 'is_compound' not in pat_cols:
            self._connection.execute(
                "ALTER TABLE patterns ADD COLUMN is_compound INTEGER NOT NULL DEFAULT 0")
        if 'compound_operator' not in pat_cols:
            self._connection.execute(
                "ALTER TABLE patterns ADD COLUMN compound_operator TEXT NOT NULL DEFAULT 'OR'")
        if 'compound_members' not in pat_cols:
            self._connection.execute(
                "ALTER TABLE patterns ADD COLUMN compound_members TEXT NOT NULL DEFAULT '[]'")
        self._connection.commit()

    def _seed_default_patterns(self) -> None:
        with self._cursor() as cur:
            for name, mask in DEFAULT_PATTERNS:
                cur.execute(
                    "INSERT OR IGNORE INTO patterns (name, mask, is_custom) VALUES (?, ?, 0)",
                    (name, json.dumps(mask)),
                )

    # ── Cards ─────────────────────────────────────────────────────────────

    def save_card(self, card: BingoCard) -> BingoCard:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO cards (serial, grid) VALUES (?, ?)",
                (card.serial, json.dumps(card.grid)),
            )
            card.id = cur.lastrowid
            card.created_at = datetime.now()
        return card

    def save_cards_bulk(self, cards: list[BingoCard]) -> list[BingoCard]:
        """Insert many cards in a single transaction for performance."""
        with self._cursor() as cur:
            data = [(c.serial, json.dumps(c.grid)) for c in cards]
            cur.executemany("INSERT INTO cards (serial, grid) VALUES (?, ?)", data)
        # Fetch back ids
        serials = [c.serial for c in cards]
        placeholders = ",".join("?" * len(serials))
        with self._cursor() as cur:
            cur.execute(
                f"SELECT id, serial FROM cards WHERE serial IN ({placeholders})",
                serials,
            )
            id_map = {row["serial"]: row["id"] for row in cur.fetchall()}
        for card in cards:
            card.id = id_map.get(card.serial)
        return cards

    def get_card_by_serial(self, serial: str) -> Optional[BingoCard]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM cards WHERE serial = ?", (serial,))
            row = cur.fetchone()
        if row is None:
            return None
        return BingoCard(
            id=row["id"],
            serial=row["serial"],
            grid=json.loads(row["grid"]),
            created_at=row["created_at"],
        )

    def serial_exists(self, serial: str) -> bool:
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM cards WHERE serial = ?", (serial,))
            return cur.fetchone() is not None

    def get_total_cards(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cards")
            return cur.fetchone()[0]

    # ── Patterns ──────────────────────────────────────────────────────────

    def get_all_patterns(self) -> list[Pattern]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM patterns ORDER BY is_custom, id")
            rows = cur.fetchall()
        return [
            Pattern(
                id=r["id"],
                name=r["name"],
                mask=json.loads(r["mask"]),
                is_custom=bool(r["is_custom"]),
                is_compound=bool(r["is_compound"]),
                compound_operator=r["compound_operator"],
                compound_member_ids=json.loads(r["compound_members"]),
            )
            for r in rows
        ]

    def save_pattern(self, pattern: Pattern) -> Pattern:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO patterns (name, mask, is_custom, is_compound, compound_operator, compound_members) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pattern.name, json.dumps(pattern.mask), int(pattern.is_custom),
                 int(pattern.is_compound), pattern.compound_operator,
                 json.dumps(pattern.compound_member_ids)),
            )
            pattern.id = cur.lastrowid
        return pattern

    def update_pattern(self, pattern: Pattern) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE patterns SET name = ?, mask = ?, is_compound = ?, "
                "compound_operator = ?, compound_members = ? WHERE id = ?",
                (pattern.name, json.dumps(pattern.mask), int(pattern.is_compound),
                 pattern.compound_operator, json.dumps(pattern.compound_member_ids),
                 pattern.id),
            )

    def delete_pattern(self, pattern_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM patterns WHERE id = ? AND is_custom = 1", (pattern_id,))

    def get_pattern_by_id(self, pattern_id: int) -> Optional[Pattern]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return Pattern(
            id=row["id"],
            name=row["name"],
            mask=json.loads(row["mask"]),
            is_custom=bool(row["is_custom"]),
            is_compound=bool(row["is_compound"]),
            compound_operator=row["compound_operator"],
            compound_member_ids=json.loads(row["compound_members"]),
        )

    # ── Sessions ──────────────────────────────────────────────────────────

    def create_session(self, name: str) -> Session:
        with self._cursor() as cur:
            cur.execute("INSERT INTO sessions (name) VALUES (?)", (name,))
            session_id = cur.lastrowid
        return Session(id=session_id, name=name, created_at=datetime.now())

    def get_all_sessions(self) -> list[Session]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM sessions ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [Session(id=r["id"], name=r["name"], created_at=r["created_at"]) for r in rows]

    # ── Games ─────────────────────────────────────────────────────────────

    def create_game(self, game: Game) -> Game:
        # Keep pattern_id column populated for backward-compat with existing DBs.
        # The authoritative source is game_patterns.
        first_pid = game.pattern_ids[0] if game.pattern_ids else None
        with self._cursor() as cur:
            cols = [r[1] for r in cur.execute("PRAGMA table_info(games)")]
            if 'pattern_id' in cols:
                cur.execute(
                    "INSERT INTO games (session_id, pattern_id, prize_amount, status) "
                    "VALUES (?, ?, ?, ?)",
                    (game.session_id, first_pid, game.prize_amount, game.status),
                )
            else:
                cur.execute(
                    "INSERT INTO games (session_id, prize_amount, status) VALUES (?, ?, ?)",
                    (game.session_id, game.prize_amount, game.status),
                )
            game.id = cur.lastrowid
            game.created_at = datetime.now()
            for pid in game.pattern_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO game_patterns (game_id, pattern_id) VALUES (?, ?)",
                    (game.id, pid),
                )
        return game

    def update_game_status(self, game_id: int, status: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE games SET status = ? WHERE id = ?", (status, game_id))

    def get_pattern_ids_for_game(self, game_id: int) -> list[int]:
        """Return all pattern IDs associated with a game, in insertion order."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT pattern_id FROM game_patterns WHERE game_id = ? ORDER BY rowid",
                (game_id,),
            )
            rows = cur.fetchall()
        if rows:
            return [r["pattern_id"] for r in rows]
        # Fallback: read legacy pattern_id column
        cols = [r[1] for r in self._connection.execute("PRAGMA table_info(games)")]
        if 'pattern_id' in cols:
            with self._cursor() as cur:
                cur.execute("SELECT pattern_id FROM games WHERE id = ?", (game_id,))
                row = cur.fetchone()
            if row and row["pattern_id"]:
                return [row["pattern_id"]]
        return []

    def get_games_for_session(self, session_id: int) -> list[Game]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM games WHERE session_id = ? ORDER BY id", (session_id,))
            rows = cur.fetchall()
        games = []
        for r in rows:
            g = Game(
                id=r["id"],
                session_id=r["session_id"],
                pattern_ids=self.get_pattern_ids_for_game(r["id"]),
                prize_amount=r["prize_amount"],
                status=r["status"],
                created_at=r["created_at"],
            )
            g.drawn_balls = self.get_drawn_balls(g.id)
            games.append(g)
        return games

    def get_active_game(self, session_id: int) -> Optional[Game]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM games WHERE session_id = ? AND status = 'active' LIMIT 1",
                (session_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        g = Game(
            id=row["id"],
            session_id=row["session_id"],
            pattern_ids=self.get_pattern_ids_for_game(row["id"]),
            prize_amount=row["prize_amount"],
            status=row["status"],
        )
        g.drawn_balls = self.get_drawn_balls(g.id)
        return g

    # ── Drawn Balls ───────────────────────────────────────────────────────

    def record_ball(self, game_id: int, ball: int, draw_order: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO drawn_balls (game_id, ball, draw_order) VALUES (?, ?, ?)",
                (game_id, ball, draw_order),
            )

    def get_drawn_balls(self, game_id: int) -> list[int]:
        """Return balls in draw order."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT ball FROM drawn_balls WHERE game_id = ? ORDER BY draw_order",
                (game_id,),
            )
            return [row["ball"] for row in cur.fetchall()]

    # ── Winners ───────────────────────────────────────────────────────────

    def record_winner(self, game_id: int, card_serial: str) -> Winner:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO winners (game_id, card_serial) VALUES (?, ?)",
                (game_id, card_serial),
            )
            winner_id = cur.lastrowid
        return Winner(id=winner_id, game_id=game_id, card_serial=card_serial, verified_at=datetime.now())

    def get_winners_for_game(self, game_id: int) -> list[Winner]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM winners WHERE game_id = ?", (game_id,))
            rows = cur.fetchall()
        return [
            Winner(id=r["id"], game_id=r["game_id"], card_serial=r["card_serial"], verified_at=r["verified_at"])
            for r in rows
        ]
