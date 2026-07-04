"""
Per-ticker WebSocket connection registry + broadcast fan-out. Kept separate
from app.py so Phase 3's /ws/scanner endpoint can reuse the same registry
without restructuring.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, ticker: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[ticker].add(ws)
        logger.info("WS client connected for %s (total: %d)", ticker, len(self._connections[ticker]))

    def disconnect(self, ticker: str, ws: WebSocket) -> None:
        self._connections[ticker].discard(ws)

    def broadcast(self, ticker: str, message: dict) -> None:
        """Sync-callable (called from non-async signal-engine callbacks);
        schedules the actual async send."""
        conns = list(self._connections.get(ticker, []))
        if not conns:
            return
        for ws in conns:
            asyncio.create_task(self._safe_send(ticker, ws, message))

    async def _safe_send(self, ticker: str, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(ticker, ws)


hub = WebSocketHub()
