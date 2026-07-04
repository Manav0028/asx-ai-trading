"""
DataSourceManager — the seam that makes both the dual-provider requirement and
the later multi-ticker generalization possible. Phase 1: IBKR only (see plan
doc's data-source research — Twelve Data was rejected, yfinance fallback is
Phase 2). Calling `stream()` once per ticker is exactly what Phase 3's
multi-ticker scanner will do concurrently — no rewrite needed.
"""
import logging
from typing import Awaitable, Callable, Optional

from datasources.base import Candle, CandleDataSource
from datasources.ibkr_source import IBKRSource
from journal.recorder import log_event

logger = logging.getLogger(__name__)


class DataSourceManager:
    def __init__(self):
        self.primary: CandleDataSource = IBKRSource()
        self.fallback: Optional[CandleDataSource] = None  # wired in Phase 2 (yfinance_fallback)
        self._active: Optional[CandleDataSource] = None

    async def start(self) -> None:
        ok = await self.primary.connect()
        if ok:
            self._active = self.primary
            log_event("connect", source=self.primary.name, detail="IBKR connected")
        else:
            log_event("error", source=self.primary.name, detail="IBKR connect failed, no fallback available yet")
            raise ConnectionError("No data source available (IBKR unreachable, no fallback configured)")

    async def stream(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        if self._active is None:
            raise RuntimeError("DataSourceManager.start() must be called before stream()")
        await self._active.subscribe(ticker, on_candle)
        log_event("subscribe", source=self._active.name, ticker=ticker, detail="live subscription started")

    async def fetch_historical(self, ticker: str, timeframe: str, lookback: str):
        return await self._active.fetch_historical(ticker, timeframe, lookback)

    def current_source_name(self) -> str:
        return self._active.name if self._active else "none"

    async def check_health(self) -> None:
        """Called periodically by the engine loop; fails over if the active
        source goes unhealthy and a fallback exists (Phase 2+)."""
        if self._active is not None and self._active.is_healthy():
            return
        logger.warning("Active data source %s unhealthy", self._active.name if self._active else "?")
        log_event("failover", source=self._active.name if self._active else "?", detail="source unhealthy")
        if self.fallback is not None:
            ok = await self.fallback.connect()
            if ok:
                self._active = self.fallback
                log_event("failover", source=self.fallback.name, detail="switched to fallback source")
                return
        log_event("error", source="manager", detail="no healthy data source available")
