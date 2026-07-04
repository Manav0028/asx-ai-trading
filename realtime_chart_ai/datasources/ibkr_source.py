"""
IBKR TWS real-time data source — the primary (and, for now, only) live provider.
Connection/retry style replicates execution/ibkr_trader.py's _get_ib(), adapted
to a persistent async connection (this process streams continuously instead of
connect-per-order), and uses a separate client-id range so it never collides
with the EOD system's own IBKR connections if both run at once.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable, List

from datasources.base import Candle, CandleDataSource
from settings import IBKR_CLIENT_ID_REALTIME, IBKR_HOST, IBKR_PORT

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 2          # seconds: 2, 4, 8 — same backoff shape as ibkr_trader.py
_CONNECT_TIMEOUT = 15
_CLIENT_ID_RANGE = (IBKR_CLIENT_ID_REALTIME, IBKR_CLIENT_ID_REALTIME + 9)

# IBKR historical-data pacing: stay well under the "60 requests / 10 min per
# contract+params" limit when chaining requests to build up 1-min history.
_HISTORICAL_PACING_SECONDS = 2

# TWS bar-size strings per timeframe key used throughout this project
_BAR_SIZE = {"1m": "1 min", "5m": "5 mins", "15m": "15 mins", "1d": "1 day"}


def _build_contract(ticker: str):
    """ASX: Stock(symbol, 'ASX', 'AUD'); NSE: Stock(symbol, 'NSE', 'INR').
    Deliberately re-implemented (not imported) from execution/ibkr_trader.py's
    _build_contract to avoid depending on a private function across packages."""
    from ib_insync import Stock

    if ticker.endswith(".AX"):
        return Stock(ticker[:-3], "ASX", "AUD")
    if ticker.endswith(".NS"):
        return Stock(ticker[:-3], "NSE", "INR")
    # Fallback: assume US-listed, no suffix
    return Stock(ticker, "SMART", "USD")


class IBKRSource(CandleDataSource):
    name = "ibkr"

    def __init__(self):
        self._ib = None
        self._connected = False
        self._bar_lists = {}   # ticker -> ib_insync RealTimeBarList (keeps a reference alive)
        self._contracts = {}   # ticker -> qualified Contract

    async def connect(self) -> bool:
        from ib_insync import IB

        last_error = None
        for attempt in range(1, _MAX_RETRIES + 1):
            client_id = _CLIENT_ID_RANGE[0] + ((attempt - 1) % (_CLIENT_ID_RANGE[1] - _CLIENT_ID_RANGE[0]))
            # A fresh IB() per attempt — matching execution/ibkr_trader.py's proven
            # pattern. Reusing one IB() instance across retries corrupts ib_insync's
            # internal event-loop/Future bookkeeping on the second connectAsync call.
            ib = IB()
            try:
                await ib.connectAsync(
                    IBKR_HOST, IBKR_PORT, clientId=client_id, timeout=_CONNECT_TIMEOUT
                )
                self._ib = ib
                self._connected = True
                self._ib.disconnectedEvent += self._on_disconnected
                logger.info(
                    "Connected to IBKR at %s:%s (attempt %d, clientId %d)",
                    IBKR_HOST, IBKR_PORT, attempt, client_id,
                )
                return True
            except Exception as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))
                    logger.warning(
                        "IBKR connect attempt %d/%d failed: %s — retrying in %ds",
                        attempt, _MAX_RETRIES, e, wait,
                    )
                    await asyncio.sleep(wait)
        logger.error("IBKR connection FAILED after %d attempts: %s", _MAX_RETRIES, last_error)
        self._connected = False
        return False

    def _on_disconnected(self):
        logger.warning("IBKR TWS disconnected — manager will detect via is_healthy() and fail over")
        self._connected = False

    async def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()
        self._connected = False

    def is_healthy(self) -> bool:
        return self._connected and self._ib is not None and self._ib.isConnected()

    async def subscribe(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        contract = _build_contract(ticker)
        await self._ib.qualifyContractsAsync(contract)
        self._contracts[ticker] = contract

        # 5-second real-time bars — the finest granularity IBKR streams without
        # a tick-by-tick/Level 2 data add-on (see plan doc's Phase 4 deferral).
        bars = self._ib.reqRealTimeBars(contract, 5, "TRADES", useRTH=False)
        self._bar_lists[ticker] = bars

        async def _on_update(bar_list, has_new_bar):
            if not has_new_bar:
                return
            bar = bar_list[-1]
            candle = Candle(
                ticker=ticker,
                ts=bar.time,
                open=bar.open_,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=float(bar.volume),
                source=self.name,
                delayed=False,
            )
            await on_candle(candle)

        def _on_update_sync(bar_list, has_new_bar):
            asyncio.create_task(_on_update(bar_list, has_new_bar))

        bars.updateEvent += _on_update_sync
        logger.info("Subscribed to real-time 5s bars for %s", ticker)

    async def fetch_historical(self, ticker: str, timeframe: str, lookback: str) -> List[Candle]:
        contract = self._contracts.get(ticker) or _build_contract(ticker)
        bar_size = _BAR_SIZE[timeframe]

        if timeframe == "1d":
            # Daily bars have no restrictive per-request windowing — one call covers years.
            bars = await self._ib.reqHistoricalDataAsync(
                contract, endDateTime="", durationStr=lookback,
                barSizeSetting=bar_size, whatToShow="TRADES", useRTH=True, formatDate=1,
            )
            return [self._to_candle(ticker, b) for b in bars]

        # 1m/5m/15m: IBKR caps ~1 day of 1-min bars per request, so chain requests
        # backwards until `lookback` days are covered.
        target_days = int(lookback.strip().split()[0]) if lookback.strip()[0].isdigit() else 30
        all_candles: List[Candle] = []
        end_dt = ""
        seen_days = 0
        while seen_days < target_days:
            bars = await self._ib.reqHistoricalDataAsync(
                contract, endDateTime=end_dt, durationStr="1 D",
                barSizeSetting=bar_size, whatToShow="TRADES", useRTH=False, formatDate=1,
            )
            if not bars:
                break
            candles = [self._to_candle(ticker, b) for b in bars]
            all_candles = candles + all_candles
            earliest = bars[0].date
            end_dt = (earliest - timedelta(seconds=1)).strftime("%Y%m%d %H:%M:%S")
            seen_days += 1
            await asyncio.sleep(_HISTORICAL_PACING_SECONDS)  # respect IBKR pacing limits
        return all_candles

    def _to_candle(self, ticker: str, bar) -> Candle:
        ts = bar.date if isinstance(bar.date, datetime) else datetime.fromisoformat(str(bar.date))
        return Candle(
            ticker=ticker, ts=ts, open=bar.open, high=bar.high, low=bar.low,
            close=bar.close, volume=float(bar.volume), source=self.name, delayed=False,
        )
