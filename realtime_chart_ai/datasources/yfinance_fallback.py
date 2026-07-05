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
# Yahoo silently rate-limits/blocks many cloud-provider IP ranges (Render,
# AWS, GCP) without a clean error — the underlying request can just hang.
# yfinance's requests session has no default timeout, so every call here
# must be wrapped in asyncio.wait_for; without this, a stuck probe during
# DataSourceManager.start() blocks FastAPI's lifespan startup forever and
# the whole service never responds to anything (found via a real deploy).
_HTTP_TIMEOUT_SECONDS = 15


class YFinanceFallbackSource(CandleDataSource):
    name = "yfinance_delayed"

    def __init__(self):
        self._healthy = False
        self._last_ts: dict = {}   # ticker -> last emitted bar timestamp
        # Surfaced by DataSourceManager.start() into the rtc_events row it
        # writes on failure, so the actual reason is queryable straight from
        # the journal DB — no application-log/dashboard access needed to
        # diagnose why the cloud deploy fell back to the mock source.
        self._last_error: Optional[str] = None

    async def connect(self) -> bool:
        try:
            import yfinance  # noqa: F401 — import-time check the package is installed
        except ImportError:
            logger.error("yfinance is not installed — cannot use the delayed fallback source")
            self._healthy = False
            self._last_error = "yfinance package not installed"
            return False
        # A cheap reachability probe; failures here (including this sandbox's
        # "host not in allowlist" 403, or Yahoo silently hanging on a
        # cloud-provider IP) are expected/handled, not raised — bounded by
        # an explicit timeout so a hang here can never block the caller
        # (DataSourceManager.start(), called from FastAPI's lifespan) forever.
        try:
            ok = await asyncio.wait_for(asyncio.to_thread(self._probe), timeout=_HTTP_TIMEOUT_SECONDS)
            if not ok:
                self._last_error = "probe returned no data (empty/None dataframe from yfinance)"
        except Exception as e:
            logger.warning("yfinance reachability probe failed or timed out: %s", e)
            ok = False
            self._last_error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
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
        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, ticker, timeframe, period), timeout=_HTTP_TIMEOUT_SECONDS,
            )
        except Exception as e:
            logger.warning("yfinance fetch_historical failed or timed out for %s/%s: %s", ticker, timeframe, e)
            return []
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
                df = await asyncio.wait_for(
                    asyncio.to_thread(self._fetch_sync, ticker, "1m", "1d"), timeout=_HTTP_TIMEOUT_SECONDS,
                )
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
