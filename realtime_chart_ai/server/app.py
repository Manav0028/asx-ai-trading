"""
FastAPI app — REST (journal query, static frontend) + WebSocket
(/ws/candles/{ticker}) in one process/port, per the plan doc's transport
decision. Startup wires: DataSourceManager -> per-ticker TimeframeStore ->
SignalEngine -> historical backfill -> live subscription -> ws_hub broadcast.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from datasources.manager import DataSourceManager
from engine.signal_engine import SignalEngine
from engine.timeframe_store import EXECUTION_TIMEFRAME, TimeframeStore
from journal.db import init_db
from journal.recorder import log_event, query_history
from server.ws_hub import hub
from settings import CONTEXT_TIMEFRAMES, RTC_TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

manager = DataSourceManager()
stores = {}
signal_engines = {}


def _candle_update_payload(ticker: str, timeframe: str, ind: dict) -> dict:
    i = len(ind["closes"]) - 1
    ts = ind["timestamps"][i]
    return {
        "type": "candle_update", "ticker": ticker, "timeframe": timeframe,
        "ts": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        "open": ind["opens"][i], "high": ind["highs"][i], "low": ind["lows"][i],
        "close": ind["closes"][i], "volume": ind["volumes"][i],
    }


async def _bootstrap_ticker(ticker: str) -> None:
    store = TimeframeStore(ticker)
    engine = SignalEngine(ticker, store, data_source_name=manager.current_source_name())
    engine.on_signal(lambda payload, t=ticker: hub.broadcast(t, payload))
    engine.on_bar(lambda tk, tf, ind, t=ticker: hub.broadcast(t, _candle_update_payload(tk, tf, ind)))
    stores[ticker] = store
    signal_engines[ticker] = engine

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

    async def on_candle(candle):
        store.ingest_raw(candle)

    await manager.stream(ticker, on_candle)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await manager.start()
    for ticker in RTC_TICKERS:
        await _bootstrap_ticker(ticker)
    logger.info("realtime_chart_ai server started — tracking %s", RTC_TICKERS)
    yield
    for source in (manager.primary, manager.fallback):
        if source is not None:
            await source.disconnect()


app = FastAPI(title="realtime_chart_ai", lifespan=lifespan)


@app.get("/api/journal")
def get_journal(ticker: str = None, limit: int = 50):
    return query_history(ticker=ticker, limit=limit)


@app.get("/api/tickers")
def get_tickers():
    return {"tickers": RTC_TICKERS, "active_source": manager.current_source_name()}


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
