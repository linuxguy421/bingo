"""
ws_server.py — WebSocket broadcast server for the Bingo caller app.

Runs an asyncio event loop on a background QThread.
The Qt main thread calls broadcast() to push JSON state to every
connected player-display client.  New clients immediately receive
the last known state so they sync instantly on connect.
"""

from __future__ import annotations

import asyncio
import json
from PyQt6.QtCore import QThread, pyqtSignal


class WSServerThread(QThread):
    """
    Background thread that owns an asyncio event loop + WebSocket server.

    Signals (emitted from the asyncio thread — Qt queues them automatically):
        server_ready(address)       — server is listening
        server_error(message)       — fatal startup error
        client_count_changed(n)     — number of connected display clients changed
    """

    server_ready          = pyqtSignal(str)
    server_error          = pyqtSignal(str)
    client_count_changed  = pyqtSignal(int)

    def __init__(self, host: str = "0.0.0.0", port: int = 8765, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set = set()
        self._last_state: str | None = None
        self._stop_event: asyncio.Event | None = None   # set in _serve()

    # ── Thread entry point ────────────────────────────────────────────────

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:
            self.server_error.emit(str(exc))

    async def _serve(self) -> None:
        try:
            import websockets
            self._stop_event = asyncio.Event()
            async with websockets.serve(self._handler, self.host, self.port):
                self.server_ready.emit(f"{self.host}:{self.port}")
                await self._stop_event.wait()   # blocks until stop() sets the event
        except Exception as exc:
            self.server_error.emit(str(exc))

    # ── Connection handler ────────────────────────────────────────────────

    async def _handler(self, websocket) -> None:
        self._clients.add(websocket)
        self.client_count_changed.emit(len(self._clients))

        # Immediately sync new client to current game state
        if self._last_state:
            try:
                await websocket.send(self._last_state)
            except Exception:
                pass

        try:
            async for _ in websocket:
                pass                            # player displays are receive-only
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            self.client_count_changed.emit(len(self._clients))

    # ── Public API (called from Qt main thread) ───────────────────────────

    def broadcast(self, state: dict) -> None:
        """Serialize state to JSON and push to every connected client."""
        message = json.dumps(state)
        self._last_state = message
        if self._loop and not self._loop.is_closed() and self._clients:
            asyncio.run_coroutine_threadsafe(self._do_broadcast(message), self._loop)

    async def _do_broadcast(self, message: str) -> None:
        if not self._clients:
            return
        await asyncio.gather(
            *(c.send(message) for c in list(self._clients)),
            return_exceptions=True,             # don't let one bad client kill others
        )

    async def _signal_stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()

    def stop(self) -> None:
        """Gracefully stop the server by signalling the stop event."""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._signal_stop(), self._loop)
