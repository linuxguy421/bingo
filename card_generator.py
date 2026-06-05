"""
card_generator.py — Bingo card generation, serial numbers, and win verification.

Design rules for a valid 75-ball card:
  Col 0  B :  5 unique numbers from  1–15
  Col 1  I :  5 unique numbers from 16–30
  Col 2  N :  4 unique numbers from 31–45  (row 2 = FREE space, stored as 0)
  Col 3  G :  5 unique numbers from 46–60
  Col 4  O :  5 unique numbers from 61–75

Serial number format:  XXXX-XXXX  (8 chars from a safe alphabet, dash in middle)
Safe alphabet excludes visually ambiguous chars: 0, 1, I, O, L
"""

from __future__ import annotations

import random
import secrets
import string
from typing import Optional

from models import BingoCard, Pattern


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLUMN_RANGES = [
    range(1,  16),   # B
    range(16, 31),   # I
    range(31, 46),   # N
    range(46, 61),   # G
    range(61, 76),   # O
]

# Visually unambiguous characters for serial numbers
_SAFE_ALPHA = "".join(
    c for c in (string.digits + string.ascii_uppercase)
    if c not in "01ILO"
)  # 32-char alphabet  →  32^8 ≈ 1 trillion unique serials


# ---------------------------------------------------------------------------
# Serial number helpers
# ---------------------------------------------------------------------------

def generate_serial() -> str:
    """
    Generate a random 8-character serial in format XXXX-XXXX.
    Uses secrets for cryptographically-random selection.
    """
    part1 = "".join(secrets.choice(_SAFE_ALPHA) for _ in range(4))
    part2 = "".join(secrets.choice(_SAFE_ALPHA) for _ in range(4))
    return f"{part1}-{part2}"


def generate_unique_serial(existing_check) -> str:
    """
    Keep generating serials until we get one not already in the DB.

    existing_check: callable(serial: str) -> bool
        Should return True if the serial already exists.
    """
    for _ in range(100):           # 100 attempts is astronomically safe
        serial = generate_serial()
        if not existing_check(serial):
            return serial
    raise RuntimeError("Failed to generate a unique serial after 100 attempts.")


# ---------------------------------------------------------------------------
# Card generation
# ---------------------------------------------------------------------------

def generate_card(serial: str) -> BingoCard:
    """
    Generate a single valid 75-ball Bingo card with the given serial.
    The FREE space at row 2, col 2 is stored as 0.
    """
    grid: list[list[int]] = []

    for col, col_range in enumerate(COLUMN_RANGES):
        pool = list(col_range)
        if col == 2:
            # N column: only 4 values, leave row 2 as FREE
            chosen = sorted(random.sample(pool, 4))
            col_values = chosen[:2] + [0] + chosen[2:]   # insert FREE at row 2
        else:
            col_values = sorted(random.sample(pool, 5))
        grid.append(col_values)

    # grid is currently [col][row] — transpose to [row][col]
    transposed = [[grid[col][row] for col in range(5)] for row in range(5)]
    return BingoCard(grid=transposed, serial=serial)


def generate_cards(count: int, existing_check) -> list[BingoCard]:
    """
    Generate `count` unique Bingo cards.

    existing_check: callable(serial: str) -> bool
        Should return True if the serial is already in the database.
    """
    cards: list[BingoCard] = []
    used_serials: set[str] = set()

    def is_taken(serial: str) -> bool:
        return serial in used_serials or existing_check(serial)

    for _ in range(count):
        serial = generate_unique_serial(is_taken)
        used_serials.add(serial)
        cards.append(generate_card(serial))

    return cards


# ---------------------------------------------------------------------------
# Win verification
# ---------------------------------------------------------------------------

def check_win(
    card: BingoCard,
    patterns: "Pattern | list[Pattern]",
    called_balls: list[int],
) -> bool:
    """
    Return True if the card satisfies ALL supplied patterns given the called balls.

    Accepts a single Pattern or a list of Patterns — a win requires every
    pattern to be satisfied simultaneously (e.g. Four Corners AND a Diagonal).
    The FREE space (row 2, col 2) is always considered marked.
    """
    if not isinstance(patterns, list):
        patterns = [patterns]

    called_set = set(called_balls)

    for pattern in patterns:
        for row, col in pattern.required_cells():
            if row == 2 and col == 2:
                continue                        # FREE space is always marked
            if card.grid[row][col] not in called_set:
                return False
    return True


def get_marked_cells(
    card: BingoCard,
    called_balls: list[int],
) -> list[list[bool]]:
    """
    Return a 5x5 boolean grid showing which cells are currently marked.
    Useful for rendering the card state in the UI.
    """
    called_set = set(called_balls)
    marked = []
    for row in range(5):
        row_marks = []
        for col in range(5):
            if row == 2 and col == 2:
                row_marks.append(True)          # FREE space
            else:
                row_marks.append(card.grid[row][col] in called_set)
        marked.append(row_marks)
    return marked


def get_missing_cells(
    card: BingoCard,
    patterns: "Pattern | list[Pattern]",
    called_balls: list[int],
) -> list[tuple[int, int, int]]:
    """
    Return a list of (row, col, value) for cells required by ANY pattern but not yet called.
    Useful for the caller's verification panel to show 'still needs: N35, G52'.
    """
    if not isinstance(patterns, list):
        patterns = [patterns]

    called_set = set(called_balls)
    seen: set[tuple[int, int]] = set()
    missing: list[tuple[int, int, int]] = []

    for pattern in patterns:
        for row, col in pattern.required_cells():
            if row == 2 and col == 2:
                continue
            if (row, col) in seen:
                continue
            seen.add((row, col))
            val = card.grid[row][col]
            if val not in called_set:
                missing.append((row, col, val))
    return missing


# ---------------------------------------------------------------------------
# Card statistics (useful for the UI)
# ---------------------------------------------------------------------------

COLUMN_LETTERS = ["B", "I", "N", "G", "O"]


def cell_label(value: int) -> str:
    """Return the Bingo label for a number, e.g. 23 → 'I23'."""
    if value == 0:
        return "FREE"
    for col, col_range in enumerate(COLUMN_RANGES):
        if value in col_range:
            return f"{COLUMN_LETTERS[col]}{value}"
    return str(value)


def describe_missing(
    card: BingoCard,
    patterns: "Pattern | list[Pattern]",
    called_balls: list[int],
) -> str:
    """Human-readable string of uncalled cells needed for this card to win."""
    missing = get_missing_cells(card, patterns, called_balls)
    if not missing:
        return "✓ BINGO!"
    labels = [cell_label(v) for _, _, v in missing]
    return "Needs: " + ", ".join(labels)


# ---------------------------------------------------------------------------
# Compound-pattern resolution
# ---------------------------------------------------------------------------

def resolve_win(
    card: BingoCard,
    patterns: "list[Pattern]",
    called_balls: list[int],
    all_patterns: "dict[int, Pattern]",
) -> bool:
    """
    Win check that fully supports compound patterns (AND / OR groups).

    patterns        — game-level selected patterns; ALL must be satisfied.
    all_patterns    — dict {id: Pattern} used to look up compound members.

    Each pattern may itself be compound (AND/OR of sub-patterns), allowing
    arbitrarily nested definitions such as Hardway Bingo.
    """
    return all(
        _resolve_one(card, p, called_balls, all_patterns)
        for p in patterns
    )


def _resolve_one(
    card: BingoCard,
    pattern: "Pattern",
    called_balls: list[int],
    all_patterns: "dict[int, Pattern]",
) -> bool:
    if not pattern.is_compound:
        return check_win(card, pattern, called_balls)

    members = [all_patterns[mid] for mid in pattern.compound_member_ids if mid in all_patterns]
    if not members:
        return False

    results = [_resolve_one(card, m, called_balls, all_patterns) for m in members]
    return any(results) if pattern.compound_operator == "OR" else all(results)


def resolve_missing(
    card: BingoCard,
    patterns: "list[Pattern]",
    called_balls: list[int],
    all_patterns: "dict[int, Pattern]",
) -> list[tuple[int, int, int]]:
    """
    Return (row, col, value) tuples still needed for a win.

    For AND patterns / AND compounds  : union of all missing cells.
    For OR compounds                  : cells missing from the *nearest* member
                                        (the one with fewest uncalled required cells).
    Plain check_win / get_missing_cells still work for simple patterns.
    """
    missing: list[tuple[int, int, int]] = []
    for p in patterns:
        missing.extend(_missing_one(card, p, called_balls, all_patterns))
    # Deduplicate while preserving order
    seen: set[tuple[int,int]] = set()
    unique = []
    for item in missing:
        key = (item[0], item[1])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _missing_one(
    card: BingoCard,
    pattern: "Pattern",
    called_balls: list[int],
    all_patterns: "dict[int, Pattern]",
) -> list[tuple[int, int, int]]:
    if not pattern.is_compound:
        return get_missing_cells(card, pattern, called_balls)

    members = [all_patterns[mid] for mid in pattern.compound_member_ids if mid in all_patterns]
    if not members:
        return []

    if pattern.compound_operator == "AND":
        # Must complete ALL members — show union of missing cells
        missing: list[tuple[int, int, int]] = []
        seen: set[tuple[int,int]] = set()
        for m in members:
            for item in _missing_one(card, m, called_balls, all_patterns):
                key = (item[0], item[1])
                if key not in seen:
                    seen.add(key)
                    missing.append(item)
        return missing
    else:
        # OR — already won if any member is satisfied
        if any(_resolve_one(card, m, called_balls, all_patterns) for m in members):
            return []
        # Return the nearest member (fewest missing cells)
        candidates = [_missing_one(card, m, called_balls, all_patterns) for m in members]
        return min(candidates, key=len) if candidates else []


def resolve_describe(
    card: BingoCard,
    patterns: "list[Pattern]",
    called_balls: list[int],
    all_patterns: "dict[int, Pattern]",
) -> str:
    """Human-readable win status using compound-aware resolution."""
    if resolve_win(card, patterns, called_balls, all_patterns):
        return "✓ BINGO!"
    missing = resolve_missing(card, patterns, called_balls, all_patterns)
    if not missing:
        return "✓ BINGO!"
    labels = [cell_label(v) for _, _, v in missing]
    return "Needs: " + ", ".join(labels)
