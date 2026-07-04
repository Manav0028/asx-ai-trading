"""
CandleDataSource — the pluggable interface every real-time data provider implements.
Kept deliberately thin so DataSourceManager (manager.py) can fail over between
providers, and so a future provider (e.g. for US tickers) is a drop-in.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, List, Optional


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

    @abstractmethod
    def is_healthy(self) -> bool:
        """Cheap, non-blocking health check used by the manager's failover logic."""
