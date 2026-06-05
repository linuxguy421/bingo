# Bingo System

A complete networked bingo management system consisting of three applications:

## Applications

| App | Entry Point | Purpose |
|-----|-------------|---------|
| Caller | `caller_app.py` | Admin console — draw balls, manage games, verify winners |
| Player Display | `display_app.py` | Hall screen — shows called balls and pattern in real time |
| (Card Generator) | Built into Caller → Cards tab | Generate and export printable bingo cards |

## Quick Start

```bash
pip install -r requirements.txt

# 1. Start the Caller on the admin machine
python caller_app.py

# 2. Start the Display on any other machine on the same network
python display_app.py --host <caller-machine-ip>
```

## Project Structure

```
bingo_system/
├── caller_app.py        Entry point — Caller application
├── display_app.py       Entry point — Player Display
├── models.py            Shared data classes (BingoCard, Game, Pattern, …)
├── db_manager.py        SQLite database layer
├── card_generator.py    Card generation, win verification, compound pattern resolution
├── card_pdf.py          PDF export (3×3 cards per page, US Letter)
├── tests.py             Test suite (run with: python tests.py)
├── requirements.txt
│
├── caller/              Caller application package
│   ├── main_window.py   Main window with Setup / Call / Verify / Patterns / Cards tabs
│   ├── ball_board.py    75-ball board widget
│   ├── pattern_widget.py Simple + Compound pattern editors
│   ├── verify_panel.py  Serial-number winner verification
│   ├── card_panel.py    Card generator UI (batch generation + PDF export)
│   └── ws_server.py     WebSocket broadcast server
│
└── display/             Player Display package
    ├── display_window.py Full-screen hall display
    └── ws_client.py      Auto-reconnecting WebSocket client
```

## Features

### Caller Application
- Session and multi-game management
- Manual or auto-timed ball draw (5 / 10 / 15 / 30 / 60 second intervals)
- Pattern selector with live combined preview
- **Compound patterns** — define named groups with AND / OR logic (e.g. Hardway Bingo)
- Winner verification by card serial number
- Real-time WebSocket broadcast to any number of display screens

### Pattern Types
- **Simple** — draw cells on a 5×5 grid
- **Compound OR** — player wins by completing *any one* of the selected patterns
  - Example: *Hardway Bingo* = any line that doesn't use the FREE space
- **Compound AND** — player must complete *all* selected patterns simultaneously
  - Example: *Progressive* = Four Corners AND a Diagonal

### Player Display
- Dark-theme full-screen layout optimised for large hall screens
- Auto-reconnects if the network drops
- Press **F11** to toggle full-screen

### Card Generator
- Generates 1–2000 unique cards per batch (background thread, non-blocking)
- Each card has a short unambiguous serial (e.g. `A3F8-KE29`)
- Exports to print-ready PDF — 9 cards per US Letter page with column colours
- Cards are stored in the database for instant serial-number lookup

## Running Tests

```bash
python tests.py
```

## Network Setup

The Caller app hosts a WebSocket server on port **8765** (configurable via `--port`).
All display machines connect to this port over the local network.

Firewall note: ensure TCP port 8765 is open on the caller machine.
