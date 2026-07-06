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
from typing import Awaitable, Callable, Dict, List, Optional

from datasources.base import Candle, CandleDataSource
from journal.recorder import log_event
from settings import RTC_ROUND_ROBIN_SPACING_SECONDS

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
        # (connect()-level only — not per-ticker; see _last_poll_errors below.)
        self._last_error: Optional[str] = None
        # Per-ticker, so concurrent poll loops (small-watchlist path, one per
        # ticker) or the round-robin scanner (large-watchlist path, one
        # shared loop) each get correct error/recovery de-dup independently —
        # a single shared field here would let one ticker's error mask or
        # falsely "recover" another's.
        self._last_poll_errors: Dict[str, Optional[str]] = {}

    async def connect(self) -> bool:
        try:
            import yfinance  # noqa: F401 — import-time check the package is installed
        except ImportError:
            logger.error("yfinance is not installed — cannot use the delayed fallback source")
            self._healthy = False
            self._last_error = "yfinance package not installed"
            return False
        # No separate reachability probe anymore — it was one more Yahoo HTTP
        # request per restart, and every restart during tonight's debugging
        # compounded into a real YFRateLimitError from Yahoo (confirmed via
        # rtc_events). The real health check is the historical/poll fetches
        # that follow (fetch_historical, _poll_loop) — both already bounded
        # and already fail soft (empty result / logged-and-retried) rather
        # than raising, and _poll_loop now retries indefinitely (see below),
        # so a transient Yahoo issue self-heals without needing a restart —
        # unlike falling back to scripted_mock here, which would mask the
        # outage behind fake data and never automatically recover.
        ok = True
        self._healthy = ok
        return ok

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
            detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.warning("yfinance fetch_historical failed or timed out for %s/%s: %s", ticker, timeframe, e)
            log_event("error", source=self.name, ticker=ticker, detail=f"fetch_historical({timeframe}) failed: {detail}")
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

    async def _fetch_and_emit(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        """Fetch the latest bars for one ticker and emit any new ones. Shared
        by both the small-watchlist per-ticker poll loop and the large-
        watchlist round-robin scanner — same fetch/emit/error-dedup logic
        either way, just a different caller cadence."""
        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, ticker, "1m", "1d"), timeout=_HTTP_TIMEOUT_SECONDS,
            )
        except Exception as e:
            # A single failed fetch (e.g. a transient Yahoo rate limit) must
            # never permanently kill the caller's loop — it would never emit
            # another candle for the rest of the process's life even after
            # the underlying issue cleared. Log (de-duplicated per ticker
            # against rtc_events so a sustained outage doesn't flood the
            # journal) and let the caller just retry next cycle.
            detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.warning("yfinance fetch failed for %s: %s", ticker, e)
            if self._last_poll_errors.get(ticker) != detail:
                log_event("error", source=self.name, ticker=ticker, detail=f"poll failed: {detail}")
                self._last_poll_errors[ticker] = detail
            return
        if df is not None and not df.empty:
            # No prior _last_ts entry means this is genuinely the first time
            # this ticker has ever been fetched here — true for the
            # round-robin scanner's first cycle per ticker (no separate
            # historical backfill precedes it), but NOT for the small-
            # watchlist path (whose earlier explicit fetch_historical() call
            # already populated _last_ts before this ever runs) — so this
            # naturally only silences the round-robin's own backfill pass,
            # same principle as seed_historical(), without a separate code
            # path or flag threaded in from the caller.
            first_time = ticker not in self._last_ts
            last_seen: Optional[datetime] = self._last_ts.get(ticker)
            for idx, row in df.iterrows():
                ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                if last_seen is not None and ts <= last_seen:
                    continue
                await on_candle(Candle(
                    ticker=ticker, ts=ts, open=float(row["Open"]), high=float(row["High"]),
                    low=float(row["Low"]), close=float(row["Close"]), volume=float(row["Volume"]),
                    source=self.name, delayed=True, is_backfill=first_time,
                ))
                self._last_ts[ticker] = ts
        if self._last_poll_errors.get(ticker) is not None:
            log_event("connect", source=self.name, ticker=ticker, detail="poll recovered")
            self._last_poll_errors[ticker] = None

    async def subscribe(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        asyncio.create_task(self._poll_loop(ticker, on_candle))

    async def _poll_loop(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        while self._healthy:
            await self._fetch_and_emit(ticker, on_candle)
            await asyncio.sleep(_POLL_SECONDS)

    async def subscribe_watchlist(self, ticker_callbacks: Dict[str, Callable[[Candle], Awaitable[None]]]) -> None:
        asyncio.create_task(self._round_robin_loop(ticker_callbacks))

    async def _round_robin_loop(self, ticker_callbacks: Dict[str, Callable[[Candle], Awaitable[None]]]) -> None:
        """One shared loop cycling through every tracked ticker at a fixed
        request-rate budget (RTC_ROUND_ROBIN_SPACING_SECONDS between fetches,
        regardless of watchlist size) — see settings.py's comment on why
        spacing, not batching, is the actual lever for scaling to many
        tickers against Yahoo's real per-request rate limit."""
        tickers = list(ticker_callbacks.keys())
        if not tickers:
            return
        i = 0
        while self._healthy:
            ticker = tickers[i % len(tickers)]
            await self._fetch_and_emit(ticker, ticker_callbacks[ticker])
            i += 1
            await asyncio.sleep(RTC_ROUND_ROBIN_SPACING_SECONDS)
