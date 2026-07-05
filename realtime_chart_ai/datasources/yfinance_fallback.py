"""
yfinance delayed fallback — the plan doc's Phase 2 item ("wired into
manager.py failover — not yet built"). Emergency, clearly-delayed data source
used when IBKR TWS is unreachable (see plan doc's data-source research:
yfinance is free but Yahoo intraday data runs ~15-20 min delayed, so every
candle here is tagged `delayed=True` — never treat this as a peer of the IBKR
real-time source).

NOTE for this environment specifically: Yahoo's endpoints
(query1/query2.finance.yahoo.com) are not on this sandbox's network egress
allowlist, so this module cannot be exercised here — see
datasources/scripted_mock_source.py for the source actually used to verify
the pipeline in this session. This file is real, production-shaped code for
when RTC_PRIMARY_SOURCE/RTC_FALLBACK_SOURCE=yfinance_delayed is run somewhere
with real internet access (e.g. after whitelisting those hosts).

yfinance has no push/streaming API, so `subscribe()` polls on an interval
instead of a persistent connection, emitting only bars newer than the last
one seen. yfinance's own historical-depth limits (~7 days for 1-minute bars,
~60 days for 5m/15m, long history for daily) are Yahoo's, not ours — logged
clearly rather than silently truncated.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, List, Optional

from datasources.base import Candle, CandleDataSource

logger = logging.getLogger(__name__)

_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1d": "1d"}
# Yahoo's own caps on how far back each intraday interval can be queried.
_MAX_PERIOD = {"1m": "7d", "5m": "60d", "15m": "60d", "1d": "2y"}
_POLL_SECONDS = 30


class YFinanceFallbackSource(CandleDataSource):
    name = "yfinance_delayed"

    def __init__(self):
        self._healthy = False
        self._last_ts: dict = {}   # ticker -> last emitted bar timestamp

    async def connect(self) -> bool:
        try:
            import yfinance  # noqa: F401 — import-time check the package is installed
        except ImportError:
            logger.error("yfinance is not installed — cannot use the delayed fallback source")
            self._healthy = False
            return False
        # A cheap reachability probe; failures here (including this sandbox's
        # "host not in allowlist" 403) are expected/handled, not raised.
        try:
            ok = await asyncio.to_thread(self._probe)
        except Exception as e:
            logger.warning("yfinance reachability probe failed: %s", e)
            ok = False
        self._healthy = ok
        return ok

    def _probe(self) -> bool:
        import yfinance as yf
        df = yf.Ticker("BHP.AX").history(period="1d", interval="1d")
        return df is not None and not df.empty

    async def disconnect(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy

    def _fetch_sync(self, ticker: str, timeframe: str, period: str):
        import yfinance as yf
        interval = _INTERVAL[timeframe]
        return yf.Ticker(ticker).history(period=period, interval=interval)

    async def fetch_historical(self, ticker: str, timeframe: str, lookback: str) -> List[Candle]:
        period = _MAX_PERIOD.get(timeframe, "5d")
        if timeframe in ("1m", "5m", "15m"):
            logger.info(
                "yfinance intraday history is capped by Yahoo at period=%s for interval=%s "
                "(requested lookback=%s cannot be honoured exactly)", period, timeframe, lookback,
            )
        df = await asyncio.to_thread(self._fetch_sync, ticker, timeframe, period)
        if df is None or df.empty:
            return []
        candles = [
            Candle(
                ticker=ticker,
                ts=idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
                open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]), close=float(row["Close"]),
                volume=float(row["Volume"]), source=self.name, delayed=True,
            )
            for idx, row in df.iterrows()
        ]
        if candles:
            self._last_ts[ticker] = candles[-1].ts
        return candles

    async def subscribe(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        asyncio.create_task(self._poll_loop(ticker, on_candle))

    async def _poll_loop(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        while self._healthy:
            try:
                df = await asyncio.to_thread(self._fetch_sync, ticker, "1m", "1d")
                if df is not None and not df.empty:
                    last_seen: Optional[datetime] = self._last_ts.get(ticker)
                    for idx, row in df.iterrows():
                        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                        if last_seen is not None and ts <= last_seen:
                            continue
                        await on_candle(Candle(
                            ticker=ticker, ts=ts, open=float(row["Open"]), high=float(row["High"]),
                            low=float(row["Low"]), close=float(row["Close"]), volume=float(row["Volume"]),
                            source=self.name, delayed=True,
                        ))
                        self._last_ts[ticker] = ts
            except Exception as e:
                logger.warning("yfinance poll failed for %s: %s", ticker, e)
                self._healthy = False
                return
            await asyncio.sleep(_POLL_SECONDS)
