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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from datasources.manager import DataSourceManager
from engine.signal_engine import SignalEngine
from engine.timeframe_store import EXECUTION_TIMEFRAME, TimeframeStore
from journal.db import init_db
from journal.recorder import get_open_positions, log_event, query_history
from server.schemas import AutoTradeToggleRequest
from server.ws_hub import hub
from settings import CONTEXT_TIMEFRAMES, RTC_ROUND_ROBIN_THRESHOLD, RTC_SIGNAL_THRESHOLD, RTC_TICKERS
from trading import state
from trading.position_tracker import tracker as position_tracker
from watchlists import TICKER_SECTOR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

manager = DataSourceManager()
stores = {}
signal_engines = {}
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
    logger.info("realtime_chart_ai server started — tracking %d ticker(s)", len(RTC_TICKERS))
    yield
    for source in (manager.primary, manager.fallback):
        if source is not None:
            await source.disconnect()
    for executor in _ticker_executors.values():
        executor.shutdown(wait=False)


app = FastAPI(title="realtime_chart_ai", lifespan=lifespan)


@app.get("/api/journal")
def get_journal(ticker: str = None, limit: int = 50):
    return query_history(ticker=ticker, limit=limit)


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


@app.get("/api/positions")
def get_positions(ticker: str = None):
    # Queried directly from rtc_open_positions (the DB is the source of
    # truth), not the in-memory tracker — reflects reality even right after
    # a restart or from a different process.
    return get_open_positions(ticker=ticker)


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
