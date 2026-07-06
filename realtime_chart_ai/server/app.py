"""
FastAPI app — REST (journal query, static frontend) + WebSocket
(/ws/candles/{ticker}) in one process/port, per the plan doc's transport
decision. Startup wires: DataSourceManager -> per-ticker TimeframeStore ->
SignalEngine -> historical backfill -> live subscription -> ws_hub broadcast.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from datasources.manager import DataSourceManager
from engine.signal_engine import SignalEngine
from engine.timeframe_store import EXECUTION_TIMEFRAME, TimeframeStore
from journal.db import init_db
from journal.recorder import get_open_positions, log_event, query_history
from server.schemas import AutoTradeToggleRequest, ManualEntryRequest, ManualUpdateRequest
from server.ws_hub import hub
from settings import CONTEXT_TIMEFRAMES, RTC_ROUND_ROBIN_THRESHOLD, RTC_SIGNAL_THRESHOLD, RTC_TICKERS
from trading import state
from trading.position_tracker import tracker as position_tracker
from trading.stops import compute_stop_target
from watchlists import TICKER_SECTOR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

manager = DataSourceManager()
stores = {}
signal_engines = {}
# How often the priority-refresh set (currently-viewed ticker(s) + every
# ticker with an open position) is recomputed and pushed to the data source
# — see YFinanceFallbackSource._priority_loop, which is what actually
# consumes this set on a much tighter cadence than the full-watchlist scan.
_PRIORITY_RECOMPUTE_SECONDS = 5
# One single-worker executor per ticker: ingest_raw() -> pattern evaluation ->
# Claude rationale call -> journal writes are all synchronous and can take
# seconds (Claude's HTTP round-trip). Running that inline in on_candle (an
# async coroutine with no awaits) would freeze the whole event loop —
# including WebSocket connections and Render's health check — every time a
# signal fires (this caused the deployed instance to be marked unhealthy and
# cycled repeatedly). A single worker keeps per-ticker bar order intact while
# fully decoupling this work from the request-serving loop.
_ticker_executors: dict = {}


def _candle_update_payload(ticker: str, timeframe: str, ind: dict) -> dict:
    i = len(ind["closes"]) - 1
    ts = ind["timestamps"][i]
    return {
        "type": "candle_update", "ticker": ticker, "timeframe": timeframe,
        "ts": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        "open": ind["opens"][i], "high": ind["highs"][i], "low": ind["lows"][i],
        "close": ind["closes"][i], "volume": ind["volumes"][i],
        "source": ind["sources"][i] if ind.get("sources") else "unknown",
        "delayed": ind["delayed"][i] if ind.get("delayed") else False,
    }


def _setup_ticker(ticker: str) -> Callable:
    """Synchronous, no network calls: creates the TimeframeStore/SignalEngine,
    wires broadcast callbacks, and returns the on_candle callback to hand to
    whichever subscription path is used (per-ticker stream() or the shared
    stream_watchlist() round-robin)."""
    store = TimeframeStore(ticker)
    engine = SignalEngine(ticker, store, data_source_name=manager.current_source_name())
    engine.on_signal(lambda payload, t=ticker: hub.broadcast(t, payload))
    engine.on_bar(lambda tk, tf, ind, t=ticker: hub.broadcast(t, _candle_update_payload(tk, tf, ind)))
    stores[ticker] = store
    signal_engines[ticker] = engine

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"rtc-{ticker}")
    _ticker_executors[ticker] = executor
    loop = asyncio.get_running_loop()

    async def on_candle(candle):
        await loop.run_in_executor(executor, store.ingest_raw, candle)

    return on_candle


async def _bootstrap_ticker(ticker: str) -> None:
    """Small-watchlist path (<= RTC_ROUND_ROBIN_THRESHOLD tickers, the
    original/still-default behavior): full historical backfill awaited
    during startup, then its own dedicated stream()."""
    on_candle = _setup_ticker(ticker)
    store = stores[ticker]

    # Historical backfill: 1m for ~30 days (chained requests inside ibkr_source),
    # daily for 2 years (matches the EOD system's existing backfill convention).
    minute_candles = await manager.fetch_historical(ticker, EXECUTION_TIMEFRAME, "30 D")
    store.seed_historical(EXECUTION_TIMEFRAME, minute_candles)
    store.seed_context_from_execution_bars(minute_candles)
    if "1d" in CONTEXT_TIMEFRAMES:
        daily_candles = await manager.fetch_historical(ticker, "1d", "2 Y")
        store.seed_historical("1d", daily_candles)
    log_event("backfill_complete", source=manager.current_source_name(), ticker=ticker,
              detail=f"{len(minute_candles)} 1m bars backfilled")

    await manager.stream(ticker, on_candle)


async def _bootstrap_watchlist_lean(tickers: list) -> None:
    """Large-watchlist path (> RTC_ROUND_ROBIN_THRESHOLD tickers, e.g.
    RTC_TICKERS=ASX200): skips the per-ticker historical-fetch-then-subscribe
    sequence entirely — with hundreds of tickers, awaiting two Yahoo requests
    each before startup completes would take minutes and almost certainly
    burst well past Yahoo's rate limit right at boot. Instead: set up all
    ticker stores/engines synchronously (no network calls, near-instant even
    for hundreds of tickers) and hand the whole batch to
    DataSourceManager.stream_watchlist(), whose round-robin scanner naturally
    backfills each ticker's first cycle (up to ~1 day of 1m bars) the same
    way it emits every subsequent live update — one shared, paced loop
    instead of N separate ones."""
    ticker_callbacks = {ticker: _setup_ticker(ticker) for ticker in tickers}
    await manager.stream_watchlist(ticker_callbacks)


async def _priority_recompute_loop() -> None:
    """Keeps the data source's priority-refresh set current: whichever
    ticker(s) someone actually has open on screen (hub.active_tickers()) plus
    every ticker with a live position (position_tracker.open_tickers()) —
    both cheap, purely in-process lookups, no new state to maintain. See the
    plan behind /api/prioritize/{ticker} below for the complementary
    on-selection immediate fetch."""
    while True:
        try:
            priority = hub.active_tickers() | set(position_tracker.open_tickers())
            manager.set_priority_tickers(priority)
        except Exception:
            logger.exception("priority-ticker recompute failed")
        await asyncio.sleep(_PRIORITY_RECOMPUTE_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.set_loop(asyncio.get_running_loop())
    init_db()
    position_tracker.load_open_positions()  # recover any position still open from before a restart
    await manager.start()
    if len(RTC_TICKERS) > RTC_ROUND_ROBIN_THRESHOLD:
        await _bootstrap_watchlist_lean(RTC_TICKERS)
    else:
        for ticker in RTC_TICKERS:
            await _bootstrap_ticker(ticker)
    priority_task = asyncio.create_task(_priority_recompute_loop())
    logger.info("realtime_chart_ai server started — tracking %d ticker(s)", len(RTC_TICKERS))
    yield
    priority_task.cancel()
    for source in (manager.primary, manager.fallback):
        if source is not None:
            await source.disconnect()
    for executor in _ticker_executors.values():
        executor.shutdown(wait=False)


app = FastAPI(title="realtime_chart_ai", lifespan=lifespan)


@app.get("/api/journal")
def get_journal(ticker: str = None, limit: int = 50, start: str = None, end: str = None):
    # start/end are ISO date or datetime strings (e.g. "2026-07-01" or a full
    # ISO timestamp) — used by the frontend's global Trades view date filter.
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    return query_history(ticker=ticker, limit=limit, start=start_dt, end=end_dt)


@app.get("/api/tickers")
def get_tickers():
    return {
        "tickers": RTC_TICKERS, "active_source": manager.current_source_name(),
        "signal_threshold": RTC_SIGNAL_THRESHOLD,
        # ticker -> sector, for the frontend's category/sector filter chips.
        # Only populated for tickers actually in watchlists.py's ASX200
        # mapping — a custom RTC_TICKERS list of tickers outside that
        # snapshot just won't have a sector entry (frontend treats that as
        # "Other"), not an error.
        "sectors": {t: TICKER_SECTOR[t] for t in RTC_TICKERS if t in TICKER_SECTOR},
    }


@app.get("/api/auto-trade")
def get_auto_trade_status():
    return {"enabled": state.is_enabled()}


@app.post("/api/auto-trade")
def set_auto_trade(body: AutoTradeToggleRequest):
    new_state = state.set_enabled(body.enabled, actor="api")
    return {"enabled": new_state}


@app.post("/api/prioritize/{ticker}")
async def prioritize_ticker(ticker: str):
    """Called by the frontend the moment a ticker is selected — forces one
    immediate out-of-band fetch instead of waiting for that ticker's next
    turn in the round-robin scan (which, spread across the full ASX200
    watchlist, can otherwise be minutes away). The full background scan
    keeps running unchanged; this just jumps the queue for whatever the user
    is looking at right now."""
    ok = await manager.prioritize_ticker(ticker)
    return {"ticker": ticker, "prioritized": ok}


@app.get("/api/positions")
def get_positions(ticker: str = None):
    # Queried directly from rtc_open_positions (the DB is the source of
    # truth), not the in-memory tracker — reflects reality even right after
    # a restart or from a different process.
    return get_open_positions(ticker=ticker)


def _latest_price_and_atr(ticker: str):
    store = stores.get(ticker)
    if store is None:
        return None, None
    ind = store.latest_ind(EXECUTION_TIMEFRAME)
    if not ind or not ind.get("closes"):
        return None, None
    price = ind["closes"][-1]
    atr = ind["atr"][-1] if ind.get("atr") else 0.0
    return price, atr


@app.post("/api/positions/manual-entry")
def manual_entry(body: ManualEntryRequest):
    """User-initiated paper trade — bypasses the composite-score/auto-trade
    gate entirely. Sized and priced by the caller (shares, optional
    stop/target); if stop/target are omitted, the same ATR-based formula the
    automated path uses fills in a sane default so a manual entry never
    ships with an unbounded risk."""
    if body.direction not in ("long", "short"):
        raise HTTPException(status_code=400, detail="direction must be 'long' or 'short'")
    if body.shares <= 0:
        raise HTTPException(status_code=400, detail="shares must be positive")
    price, atr = _latest_price_and_atr(body.ticker)
    if price is None:
        raise HTTPException(status_code=409, detail=f"no price data yet for {body.ticker}")
    if position_tracker.has_open_position(body.ticker):
        raise HTTPException(status_code=409, detail=f"{body.ticker} already has an open position")
    stop_price, target_price = body.stop_price, body.target_price
    if stop_price is None or target_price is None:
        preview = compute_stop_target(price, atr or 0.0, body.direction, stop_mult=1.5, target_mult=3.0)
        stop_price = stop_price if stop_price is not None else preview["stop_price"]
        target_price = target_price if target_price is not None else preview["target_price"]
    result = position_tracker.manual_open(body.ticker, body.direction, price, body.shares, stop_price, target_price, atr=atr or 0.0)
    if result is None:
        raise HTTPException(status_code=409, detail=f"{body.ticker} already has an open position")
    return result


@app.post("/api/positions/{ticker}/exit")
def manual_exit(ticker: str):
    price, _ = _latest_price_and_atr(ticker)
    if price is None:
        raise HTTPException(status_code=409, detail=f"no price data yet for {ticker}")
    result = position_tracker.manual_exit(ticker, price)
    if result is None:
        raise HTTPException(status_code=404, detail=f"no open position for {ticker}")
    hub.broadcast(ticker, result)
    return result


@app.patch("/api/positions/{ticker}")
def manual_update(ticker: str, body: ManualUpdateRequest):
    result = position_tracker.update_manual(
        ticker, stop_price=body.stop_price, target_price=body.target_price, shares=body.shares,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"no open position for {ticker}")
    return result


@app.get("/api/candles/{ticker}")
def get_candles(ticker: str, timeframe: str = EXECUTION_TIMEFRAME, limit: int = 200):
    # There's no separate historical-candles store — TimeframeStore's
    # per-timeframe IndicatorEngines already hold up to MAXLEN closed bars in
    # memory each, which is exactly what a freshly-connected frontend needs
    # to hydrate its chart before the first live candle_update arrives.
    tf = "1d" if timeframe.lower() in ("1d", "1day") else timeframe
    store = stores.get(ticker)
    if store is None or tf not in store.engines:
        return {"ticker": ticker, "timeframe": tf, "candles": []}
    ind = store.latest_ind(tf)
    if not ind:
        return {"ticker": ticker, "timeframe": tf, "candles": []}
    n = len(ind["closes"])
    idx = range(max(0, n - limit), n)
    candles = [{
        "ts": ind["timestamps"][i].isoformat() if isinstance(ind["timestamps"][i], datetime) else str(ind["timestamps"][i]),
        "open": ind["opens"][i], "high": ind["highs"][i], "low": ind["lows"][i],
        "close": ind["closes"][i], "volume": ind["volumes"][i],
        "source": ind["sources"][i] if ind.get("sources") else "unknown",
        "delayed": ind["delayed"][i] if ind.get("delayed") else False,
    } for i in idx]
    return {"ticker": ticker, "timeframe": tf, "candles": candles}


@app.websocket("/ws/candles/{ticker}")
async def ws_candles(websocket: WebSocket, ticker: str):
    await hub.connect(ticker, websocket)
    try:
        while True:
            await websocket.receive_text()   # frontend doesn't send anything meaningful; just keeps the socket open
    except WebSocketDisconnect:
        hub.disconnect(ticker, websocket)


_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
