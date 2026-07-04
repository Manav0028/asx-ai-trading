"""
Multi-timeframe bar store: buckets the IBKR 5s real-time bars into the
execution timeframe (default 1m) and further aggregates upward into the
context timeframes (5m/15m/1d) used by the confluence gate. One
TimeframeStore per ticker; each timeframe owns its own IndicatorEngine
(engine/indicators.py) so pattern/indicator state never mixes across
timeframes.
"""
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from datasources.base import Candle
from engine.indicators import IndicatorEngine
from settings import CONTEXT_TIMEFRAMES, EXECUTION_TIMEFRAME_SECONDS

logger = logging.getLogger(__name__)

_TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900}
EXECUTION_TIMEFRAME = "1m" if EXECUTION_TIMEFRAME_SECONDS == 60 else f"{EXECUTION_TIMEFRAME_SECONDS}s"


class _Bucket:
    """Accumulates raw ticks/bars into one OHLCV bar for a fixed period."""

    def __init__(self, period_seconds: Optional[int] = None, daily: bool = False):
        self.period_seconds = period_seconds
        self.daily = daily
        self.bucket_key = None
        self.bar: Optional[Candle] = None

    def _key_for(self, ts: datetime):
        if self.daily:
            return ts.date()
        epoch = ts.timestamp()
        floored = int(epoch // self.period_seconds) * self.period_seconds
        return floored

    def add(self, candle: Candle) -> Optional[Candle]:
        """Returns the finalized previous bar if this candle starts a new bucket,
        else None (bucket still accumulating)."""
        key = self._key_for(candle.ts)
        finalized = None
        if self.bucket_key is None:
            self.bucket_key = key
            self.bar = Candle(candle.ticker, candle.ts, candle.open, candle.high,
                               candle.low, candle.close, candle.volume, candle.source, candle.delayed)
            return None
        if key != self.bucket_key:
            finalized = self.bar
            self.bucket_key = key
            self.bar = Candle(candle.ticker, candle.ts, candle.open, candle.high,
                               candle.low, candle.close, candle.volume, candle.source, candle.delayed)
        else:
            b = self.bar
            b.high = max(b.high, candle.high)
            b.low = min(b.low, candle.low)
            b.close = candle.close
            b.volume += candle.volume
            b.ts = candle.ts
        return finalized


class TimeframeStore:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.engines: Dict[str, IndicatorEngine] = {EXECUTION_TIMEFRAME: IndicatorEngine()}
        self._buckets: Dict[str, _Bucket] = {}
        for tf in CONTEXT_TIMEFRAMES:
            self.engines[tf] = IndicatorEngine()
            if tf == "1d":
                self._buckets[tf] = _Bucket(daily=True)
            else:
                self._buckets[tf] = _Bucket(period_seconds=_TIMEFRAME_SECONDS[tf])
        # Execution-timeframe bucket aggregates the raw source ticks (5s bars)
        self._exec_bucket = _Bucket(period_seconds=EXECUTION_TIMEFRAME_SECONDS)

        self._on_bar_closed_callbacks: List[Callable[[str, str, Dict], None]] = []

    def on_bar_closed(self, callback: Callable[[str, str, Dict], None]) -> None:
        """callback(ticker, timeframe, ind_snapshot) fired whenever ANY tracked
        timeframe closes a bar (execution timeframe or a context timeframe)."""
        self._on_bar_closed_callbacks.append(callback)

    def seed_historical(self, timeframe: str, candles: List[Candle]) -> None:
        """Bulk warmup for one timeframe's engine directly from historical
        bars — no callbacks fired (avoids flooding the journal/patterns with
        stale historical bars during startup backfill)."""
        engine = self.engines.get(timeframe)
        if engine is None:
            return
        for c in candles:
            engine.update(c)

    def seed_context_from_execution_bars(self, candles: List[Candle]) -> None:
        """Bulk-seed the 5m/15m context engines from a list of already-closed
        1m historical bars (1d is seeded directly via its own historical
        fetch instead). No callbacks fired — see seed_historical."""
        for tf, bucket in self._buckets.items():
            if tf == "1d":
                continue
            for c in candles:
                finalized = bucket.add(c)
                if finalized is not None:
                    self.engines[tf].update(finalized)

    def ingest_raw(self, candle: Candle) -> None:
        """Feed one raw tick/5s-bar from the data source. Rolls it up into the
        execution timeframe, and every closed execution bar is further rolled
        into each context timeframe."""
        finalized_exec = self._exec_bucket.add(candle)
        if finalized_exec is not None:
            self._close_bar(EXECUTION_TIMEFRAME, finalized_exec)
            for tf, bucket in self._buckets.items():
                finalized_ctx = bucket.add(finalized_exec)
                if finalized_ctx is not None:
                    self._close_bar(tf, finalized_ctx)

    def _close_bar(self, timeframe: str, bar: Candle) -> None:
        engine = self.engines[timeframe]
        ind = engine.update(bar)
        for cb in self._on_bar_closed_callbacks:
            cb(self.ticker, timeframe, ind)

    def latest_ind(self, timeframe: str) -> Optional[Dict]:
        engine = self.engines.get(timeframe)
        return engine.snapshot() if engine and engine.closes else None
