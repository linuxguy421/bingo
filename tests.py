"""
tests.py — Automated tests for the Bingo system foundation.
Run with:  python tests.py
"""

import json
import os
import tempfile
import unittest

from card_generator import (
    COLUMN_RANGES,
    check_win,
    describe_missing,
    generate_card,
    generate_cards,
    generate_serial,
    get_marked_cells,
    get_missing_cells,
)
from db_manager import DatabaseManager
from models import BingoCard, Game, Pattern, Session


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_db() -> DatabaseManager:
    """Create a fresh in-memory-ish DB in a temp file."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    db = DatabaseManager(tf.name)
    db.initialize()
    return db


# ---------------------------------------------------------------------------
# Serial number tests
# ---------------------------------------------------------------------------

class TestSerialNumbers(unittest.TestCase):

    def test_format(self):
        serial = generate_serial()
        self.assertEqual(len(serial), 9)             # XXXX-XXXX
        self.assertEqual(serial[4], "-")

    def test_no_ambiguous_chars(self):
        for _ in range(500):
            serial = generate_serial().replace("-", "")
            for bad in "01ILO":
                self.assertNotIn(bad, serial, f"Ambiguous char '{bad}' in {serial}")

    def test_uniqueness(self):
        serials = {generate_serial() for _ in range(1000)}
        # Probability of collision in 1000 draws from ~1T pool is negligible
        self.assertGreater(len(serials), 990)


# ---------------------------------------------------------------------------
# Card structure tests
# ---------------------------------------------------------------------------

class TestCardGeneration(unittest.TestCase):

    def setUp(self):
        self.card = generate_card("TEST-0001")

    def test_grid_shape(self):
        self.assertEqual(len(self.card.grid), 5)
        for row in self.card.grid:
            self.assertEqual(len(row), 5)

    def test_free_space(self):
        self.assertEqual(self.card.grid[2][2], 0)

    def test_column_ranges(self):
        for row in range(5):
            for col in range(5):
                val = self.card.grid[row][col]
                if row == 2 and col == 2:
                    continue                       # FREE
                col_range = COLUMN_RANGES[col]
                self.assertIn(
                    val, col_range,
                    f"Value {val} at row={row},col={col} not in {col_range}"
                )

    def test_no_duplicates_per_column(self):
        for col in range(5):
            col_vals = [
                self.card.grid[row][col]
                for row in range(5)
                if not (row == 2 and col == 2)
            ]
            self.assertEqual(len(col_vals), len(set(col_vals)), f"Duplicate in column {col}")

    def test_bulk_generation(self):
        existing: set[str] = set()
        cards = generate_cards(50, lambda s: s in existing)
        serials = [c.serial for c in cards]
        self.assertEqual(len(serials), len(set(serials)))   # all unique
        self.assertEqual(len(cards), 50)

    def test_serial_format(self):
        self.assertEqual(len(self.card.serial), 9)


# ---------------------------------------------------------------------------
# Win verification tests
# ---------------------------------------------------------------------------

def make_pattern(cells: list[tuple[int, int]], name: str = "Test") -> Pattern:
    mask = [[False] * 5 for _ in range(5)]
    for r, c in cells:
        mask[r][c] = True
    return Pattern(name=name, mask=mask)


class TestWinVerification(unittest.TestCase):

    def setUp(self):
        # Build a deterministic card for predictable tests
        self.grid = [
            [7,  17, 31, 46, 61],
            [2,  22, 38, 52, 68],
            [14, 28,  0, 59, 73],   # row 2: FREE at col 2
            [5,  19, 43, 47, 65],
            [11, 30, 35, 55, 70],
        ]
        self.card = BingoCard(grid=self.grid, serial="ABCD-1234")

    def _all_values(self) -> list[int]:
        vals = []
        for row in self.grid:
            for v in row:
                if v != 0:
                    vals.append(v)
        return vals

    def test_free_space_not_required(self):
        """FREE space should never block a win."""
        pattern = make_pattern([(2, 2)])         # only FREE space required
        self.assertTrue(check_win(self.card, pattern, []))

    def test_row_win(self):
        pattern = make_pattern([(0, c) for c in range(5)])
        # Call all row-0 values
        called = [self.grid[0][c] for c in range(5)]
        self.assertTrue(check_win(self.card, pattern, called))

    def test_row_win_partial(self):
        pattern = make_pattern([(0, c) for c in range(5)])
        called = [self.grid[0][c] for c in range(4)]   # missing last
        self.assertFalse(check_win(self.card, pattern, called))

    def test_column_win(self):
        pattern = make_pattern([(r, 0) for r in range(5)])
        called = [self.grid[r][0] for r in range(5)]
        self.assertTrue(check_win(self.card, pattern, called))

    def test_four_corners(self):
        corners = [(0, 0), (0, 4), (4, 0), (4, 4)]
        pattern = make_pattern(corners)
        called = [self.grid[r][c] for r, c in corners]
        self.assertTrue(check_win(self.card, pattern, called))

    def test_blackout(self):
        mask = [[True] * 5 for _ in range(5)]
        pattern = Pattern(name="Blackout", mask=mask)
        self.assertFalse(check_win(self.card, pattern, []))
        self.assertTrue(check_win(self.card, pattern, self._all_values()))

    def test_extra_called_balls_do_not_hurt(self):
        """Calling extra numbers should never invalidate a win."""
        pattern = make_pattern([(0, c) for c in range(5)])
        called = self._all_values()
        self.assertTrue(check_win(self.card, pattern, called))

    def test_marked_cells(self):
        called = [self.grid[0][0]]        # only B7 called
        marked = get_marked_cells(self.card, called)
        self.assertTrue(marked[0][0])     # B7 called
        self.assertTrue(marked[2][2])     # FREE always marked
        self.assertFalse(marked[0][1])    # I17 not called

    def test_missing_cells(self):
        pattern = make_pattern([(0, c) for c in range(5)])
        called = [self.grid[0][0], self.grid[0][1]]   # only 2 of 5
        missing = get_missing_cells(self.card, pattern, called)
        self.assertEqual(len(missing), 3)

    def test_describe_missing(self):
        pattern = make_pattern([(0, c) for c in range(5)])
        called = [self.grid[0][c] for c in range(5)]
        self.assertEqual(describe_missing(self.card, pattern, called), "✓ BINGO!")
        partial = [self.grid[0][0]]
        desc = describe_missing(self.card, pattern, partial)
        self.assertIn("Needs:", desc)


# ---------------------------------------------------------------------------
# Database tests
# ---------------------------------------------------------------------------

class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.db = make_db()

    def tearDown(self):
        path = self.db.db_path
        self.db.close()
        os.unlink(path)

    def test_default_patterns_seeded(self):
        patterns = self.db.get_all_patterns()
        self.assertGreater(len(patterns), 0)
        names = [p.name for p in patterns]
        self.assertIn("Blackout", names)
        self.assertIn("Four Corners", names)

    def test_save_and_retrieve_card(self):
        card = generate_card("SAVE-TEST")
        saved = self.db.save_card(card)
        self.assertIsNotNone(saved.id)
        retrieved = self.db.get_card_by_serial("SAVE-TEST")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.grid, card.grid)

    def test_serial_exists(self):
        card = generate_card("EXST-TEST")
        self.db.save_card(card)
        self.assertTrue(self.db.serial_exists("EXST-TEST"))
        self.assertFalse(self.db.serial_exists("FAKE-0000"))

    def test_bulk_save(self):
        cards = generate_cards(100, self.db.serial_exists)
        self.db.save_cards_bulk(cards)
        self.assertEqual(self.db.get_total_cards(), 100)

    def test_session_and_game_lifecycle(self):
        session = self.db.create_session("Friday Night Bingo")
        self.assertIsNotNone(session.id)

        patterns = self.db.get_all_patterns()
        game = self.db.create_game(Game(
            session_id=session.id,
            pattern_ids=[patterns[0].id],
            prize_amount=100.0,
        ))
        self.assertIsNotNone(game.id)
        self.assertEqual(game.status, "pending")

        self.db.update_game_status(game.id, "active")
        active = self.db.get_active_game(session.id)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, game.id)

    def test_drawn_balls(self):
        session = self.db.create_session("Test Session")
        patterns = self.db.get_all_patterns()
        game = self.db.create_game(Game(session_id=session.id, pattern_ids=[patterns[0].id]))

        for i, ball in enumerate([7, 23, 45]):
            self.db.record_ball(game.id, ball, i)

        balls = self.db.get_drawn_balls(game.id)
        self.assertEqual(balls, [7, 23, 45])

    def test_winner_recording(self):
        card = generate_card("WINN-TEST")
        self.db.save_card(card)
        session = self.db.create_session("Win Test")
        patterns = self.db.get_all_patterns()
        game = self.db.create_game(Game(session_id=session.id, pattern_ids=[patterns[0].id]))

        winner = self.db.record_winner(game.id, card.serial)
        self.assertIsNotNone(winner.id)

        winners = self.db.get_winners_for_game(game.id)
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].card_serial, card.serial)

    def test_duplicate_winner_ignored(self):
        """Recording the same winner twice should not raise."""
        card = generate_card("DUPL-TEST")
        self.db.save_card(card)
        session = self.db.create_session("Dup Test")
        patterns = self.db.get_all_patterns()
        game = self.db.create_game(Game(session_id=session.id, pattern_ids=[patterns[0].id]))

        self.db.record_winner(game.id, card.serial)
        self.db.record_winner(game.id, card.serial)   # second call — should not raise
        self.assertEqual(len(self.db.get_winners_for_game(game.id)), 1)

    def test_custom_pattern_save_delete(self):
        pattern = Pattern(
            name="My Custom L",
            mask=[[False] * 5 for _ in range(5)],
            is_custom=True,
        )
        saved = self.db.save_pattern(pattern)
        self.assertIsNotNone(saved.id)

        self.db.delete_pattern(saved.id)
        retrieved = self.db.get_pattern_by_id(saved.id)
        self.assertIsNone(retrieved)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
