"""
card_pdf.py — Export Bingo cards to a print-ready PDF file.

Layout:
  • US Letter (612 × 792 pt)
  • 3 cards per row, 3 rows per page  →  9 cards per page
  • Each card: B-I-N-G-O header, 5×5 number grid, serial number footer
  • FREE space shown as a star (★)
  • Alternating row shading for readability
  • Card serial in monospace below the grid
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from models import BingoCard

# ── Page geometry (all values in points) ──────────────────────────────────

PAGE_W, PAGE_H = letter          # 612 × 792
MARGIN         = 28
CARD_COLS      = 3
CARD_ROWS      = 3
H_GAP          = 8               # gap between cards horizontally
V_GAP          = 10              # gap between cards vertically

CARDS_PER_PAGE = CARD_COLS * CARD_ROWS

_usable_w = PAGE_W - 2 * MARGIN
CARD_W    = (_usable_w - (CARD_COLS - 1) * H_GAP) / CARD_COLS   # ≈ 180pt

HEADER_H  = 22    # B-I-N-G-O column header row
CELL_H    = 28    # each data row
SERIAL_H  = 16    # serial number strip at the bottom
CARD_H    = HEADER_H + 5 * CELL_H + SERIAL_H                    # ≈ 198pt

_usable_h = PAGE_H - 2 * MARGIN
# Verify 3 rows fit; if not, shrink V_GAP (won't happen at these sizes)
assert CARD_H * CARD_ROWS + V_GAP * (CARD_ROWS - 1) <= _usable_h, \
    "Cards don't fit on the page — adjust sizes."

CELL_W = CARD_W / 5

# ── Colours ────────────────────────────────────────────────────────────────

COL_HEADER_BG = [
    colors.HexColor("#3B82F6"),  # B — blue
    colors.HexColor("#EF4444"),  # I — red
    colors.HexColor("#8B5CF6"),  # N — purple
    colors.HexColor("#10B981"),  # G — green
    colors.HexColor("#F59E0B"),  # O — amber
]
COL_HEADER_FG = [colors.white] * 4 + [colors.black]

ROW_SHADE     = colors.HexColor("#F1F5F9")   # light grey for even rows
FREE_BG       = colors.HexColor("#FDE047")   # yellow for FREE
FREE_FG       = colors.black
GRID_LINE     = colors.HexColor("#CBD5E1")
CARD_BORDER   = colors.HexColor("#334155")
SERIAL_FG     = colors.HexColor("#1E293B")

# ── Drawing helpers ────────────────────────────────────────────────────────

def _draw_card(c: Canvas, card: BingoCard, x: float, y: float) -> None:
    """
    Draw a single bingo card with its top-left corner at (x, y).
    ReportLab y-axis points UP, so y is the TOP of the card.
    """
    cols = "BINGO"

    # ── Column headers ──────────────────────────────────────────────────
    for col in range(5):
        cx = x + col * CELL_W
        cy = y - HEADER_H
        c.setFillColor(COL_HEADER_BG[col])
        c.rect(cx, cy, CELL_W, HEADER_H, fill=1, stroke=0)
        c.setFillColor(COL_HEADER_FG[col])
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(cx + CELL_W / 2, cy + 6, cols[col])

    # ── Data cells ──────────────────────────────────────────────────────
    for row in range(5):
        row_y = y - HEADER_H - (row + 1) * CELL_H
        shade = row % 2 == 1

        for col in range(5):
            cx = x + col * CELL_W
            val = card.grid[row][col]
            is_free = (row == 2 and col == 2)

            if is_free:
                c.setFillColor(FREE_BG)
            elif shade:
                c.setFillColor(ROW_SHADE)
            else:
                c.setFillColor(colors.white)

            c.rect(cx, row_y, CELL_W, CELL_H, fill=1, stroke=0)

            if is_free:
                c.setFillColor(FREE_FG)
                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(cx + CELL_W / 2, row_y + 7, "★")
            else:
                c.setFillColor(colors.black)
                c.setFont("Helvetica-Bold", 12)
                c.drawCentredString(cx + CELL_W / 2, row_y + 8, str(val))

    # ── Grid lines ──────────────────────────────────────────────────────
    c.setStrokeColor(GRID_LINE)
    c.setLineWidth(0.4)
    grid_top    = y
    grid_bottom = y - HEADER_H - 5 * CELL_H

    for col in range(6):
        lx = x + col * CELL_W
        c.line(lx, grid_top, lx, grid_bottom)

    c.line(x, y, x + CARD_W, y)
    for row in range(7):                     # 1 header + 5 data + 1 bottom
        ry = y - HEADER_H - row * CELL_H if row > 0 else y - HEADER_H
        c.line(x, ry, x + CARD_W, ry)
    c.line(x, grid_bottom, x + CARD_W, grid_bottom)

    # ── Card border ──────────────────────────────────────────────────────
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(1.2)
    c.rect(x, grid_bottom - SERIAL_H, CARD_W, CARD_H, fill=0, stroke=1)

    # ── Serial number ────────────────────────────────────────────────────
    serial_y = grid_bottom - SERIAL_H + 3
    c.setFillColor(SERIAL_FG)
    c.setFont("Courier-Bold", 9)
    c.drawCentredString(x + CARD_W / 2, serial_y, card.serial)


# ── Public API ─────────────────────────────────────────────────────────────

def export_cards_to_pdf(
    cards: list[BingoCard],
    output_path: str | Path,
    title: str = "Bingo Cards",
) -> Path:
    """
    Write all cards to a PDF file.  Returns the resolved output path.

    Cards are laid out 9-per-page (3 × 3).
    A page number and title are added at the bottom of each page.
    """
    output_path = Path(output_path)
    c = Canvas(str(output_path), pagesize=letter)
    c.setTitle(title)

    total = len(cards)

    for page_start in range(0, total, CARDS_PER_PAGE):
        page_cards = cards[page_start : page_start + CARDS_PER_PAGE]
        page_num   = page_start // CARDS_PER_PAGE + 1
        total_pages = (total + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

        for idx, card in enumerate(page_cards):
            grid_col = idx % CARD_COLS
            grid_row = idx // CARD_COLS

            card_x = MARGIN + grid_col * (CARD_W + H_GAP)
            # Top of card, counting down from top of page
            card_y = PAGE_H - MARGIN - grid_row * (CARD_H + V_GAP)

            _draw_card(c, card, card_x, card_y)

        # Page footer
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.drawCentredString(
            PAGE_W / 2, 14,
            f"{title}  —  Page {page_num} of {total_pages}  —  {total} cards total"
        )

        c.showPage()

    c.save()
    return output_path
