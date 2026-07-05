"""
DataSourceManager — the seam that makes both the dual-provider requirement and
the later multi-ticker generalization possible. Primary/fallback providers are
built from PRIMARY_SOURCE/FALLBACK_SOURCE (settings.py) via _build_source's
name registry: "ibkr" | "yfinance_delayed" | "scripted_mock" (the last is
dev/verification-only, see datasources/scripted_mock_source.py). Calling
`stream()` once per ticker is exactly what Phase 3's multi-ticker scanner will
do concurrently — no rewrite needed.
"""
import logging
from typing import Awaitable, Callable, Optional

from datasources.base import Candle, CandleDataSource
from journal.recorder import log_event
from settings import FALLBACK_SOURCE, PRIMARY_SOURCE

logger = logging.getLogger(__name__)


def _build_source(name: str) -> Optional[CandleDataSource]:
    """Name -> CandleDataSource factory, keyed by the same strings used in
    PRIMARY_SOURCE/FALLBACK_SOURCE. Imports are local so an unused provider's
    dependency (e.g. ib_insync) is never required to be installed."""
    if name == "ibkr":
        from datasources.ibkr_source import IBKRSource
        return IBKRSource()
    if name == "yfinance_delayed":
        from datasources.yfinance_fallback import YFinanceFallbackSource
        return YFinanceFallbackSource()
    if name == "scripted_mock":
        from datasources.scripted_mock_source import ScriptedMockSource
        return ScriptedMockSource()
    if not name:
        return None
    raise ValueError(f"Unknown data source name: {name!r} (expected ibkr/yfinance_delayed/scripted_mock)")


class DataSourceManager:
    def __init__(self):
        self.primary: CandleDataSource = _build_source(PRIMARY_SOURCE)
        self.fallback: Optional[CandleDataSource] = _build_source(FALLBACK_SOURCE)
        self._active: Optional[CandleDataSource] = None

    async def start(self) -> None:
        ok = await self.primary.connect()
        if ok:
            self._active = self.primary
            log_event("connect", source=self.primary.name, detail=f"{self.primary.name} connected")
            return
        log_event("error", source=self.primary.name, detail=f"{self.primary.name} connect failed")
        if self.fallback is not None:
            ok = await self.fallback.connect()
            if ok:
                self._active = self.fallback
                log_event("failover", source=self.fallback.name, detail="primary failed at startup, using fallback")
                return
            log_event("error", source=self.fallback.name, detail=f"{self.fallback.name} connect also failed")
        raise ConnectionError(
            f"No data source available (primary={self.primary.name} unreachable"
            + (f", fallback={self.fallback.name} unreachable" if self.fallback else ", no fallback configured")
            + ")"
        )

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
