"""
Per-ticker WebSocket connection registry + broadcast fan-out. Kept separate
from app.py so Phase 3's /ws/scanner endpoint can reuse the same registry
without restructuring.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Must be called once from the main event loop at startup. Signal-engine
        callbacks (and therefore broadcast()) now run on a per-ticker worker
        thread (see server/app.py), so scheduling sends via asyncio.create_task
        (which requires being called from the loop's own thread) would raise —
        run_coroutine_threadsafe works from any thread."""
        self._loop = loop

    async def connect(self, ticker: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[ticker].add(ws)
        logger.info("WS client connected for %s (total: %d)", ticker, len(self._connections[ticker]))

    def disconnect(self, ticker: str, ws: WebSocket) -> None:
        self._connections[ticker].discard(ws)

    def active_tickers(self) -> Set[str]:
        """Tickers with at least one connected WS client right now — i.e.
        whatever's actually on someone's screen. Used to build the data
        source's priority-refresh set (see server/app.py's periodic task)."""
        return {t for t, conns in self._connections.items() if conns}

    def broadcast(self, ticker: str, message: dict) -> None:
        """Thread-safe: called from per-ticker worker threads (signal-engine
        callbacks), not the event loop thread."""
        conns = list(self._connections.get(ticker, []))
        if not conns or self._loop is None:
            return
        for ws in conns:
            asyncio.run_coroutine_threadsafe(self._safe_send(ticker, ws, message), self._loop)

    async def _safe_send(self, ticker: str, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(ticker, ws)


hub = WebSocketHub()
