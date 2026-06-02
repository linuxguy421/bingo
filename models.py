"""
models.py — Dataclasses used throughout the Bingo system.
These are plain data containers with no dependencies on PyQt or the DB.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

@dataclass
class BingoCard:
    """
    Represents a single 5x5 Bingo card.

    grid:   A 5x5 list-of-lists of integers.
            The FREE space (row 2, col 2) is stored as 0.
            Columns map to:  B=col0 (1-15)  I=col1 (16-30)  N=col2 (31-45)
                             G=col3 (46-60)  O=col4 (61-75)
    serial: Short unique identifier, e.g. "A3F-82K".
    id:     SQLite primary key (None until persisted).
    """
    grid: list[list[int]]
    serial: str
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    def column_values(self, col: int) -> list[int]:
        """Return the five values in a given column (0-4)."""
        return [self.grid[row][col] for row in range(5)]

    def is_free(self, row: int, col: int) -> bool:
        return row == 2 and col == 2

    def __str__(self) -> str:
        header = "  B   I   N   G   O"
        lines = [header]
        for r in range(5):
            row_vals = []
            for c in range(5):
                val = self.grid[r][c]
                row_vals.append(" FR" if val == 0 else f"{val:3d}")
            lines.append(" ".join(row_vals))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pattern
# ---------------------------------------------------------------------------

@dataclass
class Pattern:
    """
    A 5x5 boolean mask defining which cells must be marked for a win.
    True  = cell must be marked
    False = cell is irrelevant
    The FREE space is always treated as marked automatically.
    """
    name: str
    mask: list[list[bool]]       # mask[row][col]
    is_custom: bool = False
    id: Optional[int] = None

    def required_cells(self) -> list[tuple[int, int]]:
        """Return (row, col) pairs that must be marked to satisfy this pattern."""
        return [
            (r, c)
            for r in range(5)
            for c in range(5)
            if self.mask[r][c]
        ]


# ---------------------------------------------------------------------------
# Session & Game
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """A named Bingo event that groups one or more games."""
    name: str
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Game:
    """
    A single round within a Session.
    status: 'pending' | 'active' | 'completed'

    pattern_ids: one or more Pattern IDs — the card must satisfy ALL of them
                 simultaneously to win (e.g. Four Corners AND a Diagonal).
    """
    session_id: int
    pattern_ids: list[int] = field(default_factory=list)
    prize_amount: float = 0.0
    status: str = "pending"
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    # Populated at runtime, not stored in DB
    drawn_balls: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Winner
# ---------------------------------------------------------------------------

@dataclass
class Winner:
    game_id: int
    card_serial: str
    id: Optional[int] = None
    verified_at: Optional[datetime] = None
