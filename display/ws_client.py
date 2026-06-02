"""
ws_client.py — Auto-reconnecting WebSocket client for the Player Display.

Runs its own asyncio loop on a background QThread.
Emits state_received(dict) on every game-state message from the caller.
Automatically retries the connection every 3 seconds if it drops.
"""

from __future__ import annotations

import asyncio
import json

from PyQt6.QtCore import QThread, pyqtSignal


class WSClientThread(QThread):
    """
    Background thread that maintains a WebSocket connection to the
    Caller application's broadcast server.

    Signals:
        state_received(state_dict)  — new game state arrived
        connected()                 — socket opened successfully
        disconnected()              — socket closed or failed
    """

    state_received = pyqtSignal(dict)
    connected      = pyqtSignal()
    disconnected   = pyqtSignal()

    RETRY_DELAY = 3          # seconds between reconnect attempts

    def __init__(self, host: str, port: int = 8765, parent=None) -> None:
        super().__init__(parent)
        self.host  = host
        self.port  = port
        self._running = True
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Thread entry ──────────────────────────────────────────────────────

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_loop())
        except RuntimeError:
            pass   # loop stopped during shutdown — expected

    async def _connect_loop(self) -> None:
        import websockets

        uri = f"ws://{self.host}:{self.port}"

        while self._running:
            try:
                async with websockets.connect(uri, open_timeout=5) as ws:
                    self.connected.emit()
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            state = json.loads(raw)
                            self.state_received.emit(state)
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass

            self.disconnected.emit()
            if self._running:
                await asyncio.sleep(self.RETRY_DELAY)

    # ── Public API ────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._running = False
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
