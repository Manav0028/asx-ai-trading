"""
Scripted mock data source — dev/verification only, NOT a real data provider.

Exists because this environment cannot reach IBKR TWS (no broker terminal)
nor Yahoo Finance (query1/query2.finance.yahoo.com are not on this sandbox's
network egress allowlist — see datasources/yfinance_fallback.py's docstring).
Replays a bullish order-block-retest setup through the REAL engine (indicators,
swing detection, SMC, confluence, composite score, journal, AI rationale,
paper trading) so the pipeline can be verified end-to-end without external
network access. Tag everything `source="scripted_mock"` so the UI/journal are
honest that this is not live market data — never enable this in production.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List

from datasources.base import Candle, CandleDataSource

logger = logging.getLogger(__name__)

N_PRE = 150            # pre-event consolidation bars — kept < engine MAXLEN (250)
STREAM_INTERVAL_SECONDS = 2.0  # wall-clock seconds between emitted 1-min bars (accelerated for demo)
STARTUP_GRACE_SECONDS = 15.0   # delay before the scripted event starts streaming, so a client
                                # has time to load the page and open the WS after server start


def _build_series(seed: int = 20260705, n_pre: int = N_PRE) -> List[dict]:
    rnd = random.Random(seed)
    ts0 = datetime.now(timezone.utc) - timedelta(minutes=n_pre + 20)
    bars = []
    p = 41.75
    drift_target = 41.98
    for i in range(n_pre):
        o = p
        p = p + (drift_target - p) * 0.01 + (rnd.random() - 0.48) * 0.035
        p = max(41.60, min(42.05, p))
        h = max(o, p) + rnd.random() * 0.02
        l = min(o, p) - rnd.random() * 0.02
        vol = 4000 + rnd.random() * 1500
        bars.append(dict(ts=ts0 + timedelta(minutes=i), open=o, high=h, low=l, close=p, volume=vol))

    last_close = bars[-1]["close"]
    script = [
        (last_close, last_close + 0.02, 0.015, 0.02, 1.0),
        (last_close + 0.02, last_close + 0.05, 0.015, 0.02, 1.0),
        (last_close + 0.05, last_close + 0.01, 0.015, 0.02, 1.0),
        (last_close + 0.01, last_close - 0.07, 0.02, 0.015, 1.3),   # order block (down candle)
        (last_close - 0.07, last_close + 0.30, 0.02, 0.015, 3.2),   # displacement up
        (last_close + 0.30, last_close + 0.22, 0.015, 0.02, 1.1),
        (last_close + 0.22, last_close + 0.15, 0.015, 0.02, 1.0),
        (last_close + 0.15, last_close + 0.09, 0.015, 0.02, 1.0),
        (last_close + 0.09, last_close + 0.02, 0.015, 0.02, 1.6),   # retest dips into OB zone
        (last_close + 0.02, last_close + 0.04, 0.015, 0.02, 1.0),
        (last_close + 0.04, last_close + 0.08, 0.015, 0.02, 1.0),
        (last_close + 0.08, last_close + 0.13, 0.015, 0.02, 1.0),
    ]
    base_vol = 4500
    for k, (o, c, hp, lp, vmult) in enumerate(script):
        h = max(o, c) + hp
        l = min(o, c) - lp
        bars.append(dict(ts=ts0 + timedelta(minutes=n_pre + k), open=o, high=h, low=l, close=c, volume=base_vol * vmult))

    return bars


class ScriptedMockSource(CandleDataSource):
    """Replays one bullish order-block-retest scenario, then continues an
    unscripted random walk indefinitely so the server stays "live" for
    further manual testing (toggling auto-trade, asking the copilot, etc.)."""

    name = "scripted_mock"

    def __init__(self):
        self._connected = False
        self._series = {}     # ticker -> list of historical (pre-event) bars
        self._rng = {}        # ticker -> Random continuing past the scripted event

    async def connect(self) -> bool:
        self._connected = True
        logger.warning(
            "ScriptedMockSource active — this is NOT real market data. "
            "Dev/verification only; see module docstring."
        )
        return True

    async def disconnect(self) -> None:
        self._connected = False

    def is_healthy(self) -> bool:
        return self._connected

    async def fetch_historical(self, ticker: str, timeframe: str, lookback: str) -> List[Candle]:
        if timeframe == "1d":
            rnd = random.Random(hash(ticker) & 0xFFFF)
            ts0 = datetime.now(timezone.utc) - timedelta(days=30)
            p = 41.5
            out = []
            for i in range(30):
                o = p
                p = p + (rnd.random() - 0.5) * 0.6
                h, l = max(o, p) + rnd.random() * 0.3, min(o, p) - rnd.random() * 0.3
                out.append(Candle(ticker, ts0 + timedelta(days=i), o, h, l, p, 500000 + rnd.random() * 200000,
                                   self.name, delayed=False))
            return out

        full = _build_series()
        self._series[ticker] = full
        pre_event = full[:N_PRE]
        return [
            Candle(ticker, b["ts"], b["open"], b["high"], b["low"], b["close"], b["volume"], self.name, delayed=False)
            for b in pre_event
        ]

    async def subscribe(self, ticker: str, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        full = self._series.get(ticker) or _build_series()
        event_bars = full[N_PRE:]
        rnd = random.Random((hash(ticker) & 0xFFFF) + 1)

        async def _run():
            await asyncio.sleep(STARTUP_GRACE_SECONDS)
            last = event_bars[-1] if event_bars else full[-1]
            minute = last["ts"]
            for b in event_bars:
                await asyncio.sleep(STREAM_INTERVAL_SECONDS)
                await on_candle(Candle(ticker, b["ts"], b["open"], b["high"], b["low"], b["close"],
                                        b["volume"], self.name, delayed=False))
                minute = b["ts"]
            # scripted event exhausted — keep the server "live" with an
            # unscripted gentle random walk so further manual testing works
            price = last["close"]
            while self._connected:
                await asyncio.sleep(STREAM_INTERVAL_SECONDS)
                minute = minute + timedelta(minutes=1)
                o = price
                price = max(41.5, min(42.8, price + (rnd.random() - 0.5) * 0.04))
                h, l = max(o, price) + rnd.random() * 0.015, min(o, price) - rnd.random() * 0.015
                vol = 4000 + rnd.random() * 1500
                await on_candle(Candle(ticker, minute, o, h, l, price, vol, self.name, delayed=False))

        asyncio.create_task(_run())
