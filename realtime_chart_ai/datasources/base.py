"""
CandleDataSource — the pluggable interface every real-time data provider implements.
Kept deliberately thin so DataSourceManager (manager.py) can fail over between
providers, and so a future provider (e.g. for US tickers) is a drop-in.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional


@dataclass
class Candle:
    ticker: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str            # 'ibkr' | 'yfinance_delayed'
    delayed: bool = False
    # Set by the round-robin scanner for a ticker's first fetch (which
    # doubles as backfill — see YFinanceFallbackSource._fetch_and_emit).
    # TimeframeStore.ingest_raw uses this to seed indicators/swings without
    # firing pattern evaluation/journal writes/paper trades against bars that
    # already happened hours ago — the same principle the small-watchlist
    # path's seed_historical() already applies, just via a per-candle flag
    # instead of a separate bulk method.
    is_backfill: bool = False


class CandleDataSource(ABC):
    """One live data provider. All methods are async — the pipeline runs on asyncio."""

    name: str = "base"

    @abstractmethod
    async def connect(self) -> bool:
        """Establish the connection. Returns True on success, False on failure
        (never raises for expected failure modes — the manager decides what to do)."""

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def subscribe(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        """Start streaming real-time candles for `ticker`, invoking `on_candle`
        for every completed bar at the source's native granularity (the caller —
        TimeframeStore — is responsible for aggregating into the working timeframe)."""

    @abstractmethod
    async def fetch_historical(self, ticker: str, timeframe: str, lookback: str) -> List[Candle]:
        """One-shot historical backfill. `timeframe` in {'1m','5m','15m','1d'},
        `lookback` a provider-agnostic hint like '30 D' or '2 Y'."""

    async def subscribe_watchlist(self, ticker_callbacks: Dict[str, Callable[[Candle], Awaitable[None]]]) -> None:
        """Start streaming for many tickers at once. Default: subscribe to each
        independently (the existing one-loop-per-ticker model) — fine for
        providers without a shared per-request rate budget to protect (IBKR's
        own subscription model, or the synthetic scripted_mock source).
        Override when many independent per-ticker loops would overwhelm a
        shared resource — see YFinanceFallbackSource's round-robin override,
        which exists because Yahoo's real rate limit doesn't improve with
        batching (one HTTP request per ticker either way); the only safe lever
        is spreading requests over time as the watchlist grows."""
        for ticker, cb in ticker_callbacks.items():
            await self.subscribe(ticker, cb)

    @abstractmethod
    def is_healthy(self) -> bool:
        """Cheap, non-blocking health check used by the manager's failover logic."""
