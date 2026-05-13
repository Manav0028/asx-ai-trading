"""
Layer 01 · Data Ingestion — yFinance OHLCV
Runs daily before market open for all tickers of the active exchange.
Batch downloads first; per-ticker fallback for any that fail in the batch.
"""
import logging
from datetime import date, timedelta
from typing import List, Optional, Set

import yfinance as yf
from sqlalchemy.dialects.postgresql import insert

from config import get_active_exchange
from storage.database import get_session
from storage.models import Price

logger = logging.getLogger(__name__)


def _store_rows(session, ticker: str, df) -> int:
    """Upsert rows from a single-ticker DataFrame. Returns count stored."""
    df = df.dropna(subset=["Close"])
    count = 0
    for idx, row in df.iterrows():
        stmt = insert(Price).values(
            ticker=ticker,
            date=idx.date(),
            open=float(row.get("Open", 0) or 0),
            high=float(row.get("High", 0) or 0),
            low=float(row.get("Low", 0) or 0),
            close=float(row["Close"]),
            volume=float(row.get("Volume", 0) or 0),
        ).on_conflict_do_update(
            constraint="uq_price_ticker_date",
            set_={"close": float(row["Close"]), "volume": float(row.get("Volume", 0) or 0)},
        )
        session.execute(stmt)
        count += 1
    return count


def _fetch_single(ticker: str, start: str) -> int:
    """Individual ticker fallback when batch download fails."""
    try:
        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if df.empty:
            return 0
        # Single-ticker download has flat columns
        import pandas as pd
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(ticker, axis=1, level="Ticker")
        with get_session() as session:
            return _store_rows(session, ticker, df)
    except Exception as e:
        logger.warning("Per-ticker fallback failed for %s: %s", ticker, e)
        return 0


def fetch_prices(tickers: List[str] = None, days_back: int = 5) -> int:
    tickers = tickers or get_active_exchange().tickers
    start = (date.today() - timedelta(days=days_back)).isoformat()
    stored = 0
    failed: Set[str] = set()

    logger.info("Fetching OHLCV for %d tickers from %s", len(tickers), start)
    data = yf.download(
        tickers,
        start=start,
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if data.empty:
        logger.warning("Batch download returned empty — falling back to per-ticker")
        failed = set(tickers)
    else:
        with get_session() as session:
            for ticker in tickers:
                try:
                    df = data.xs(ticker, axis=1, level="Ticker")
                    stored += _store_rows(session, ticker, df)
                except Exception:
                    failed.add(ticker)

    # Per-ticker retry for any that failed in the batch
    if failed:
        logger.info("Retrying %d tickers individually: %s", len(failed), sorted(failed))
        for ticker in sorted(failed):
            n = _fetch_single(ticker, start)
            if n:
                stored += n
                logger.info("Fallback OK: %s (%d rows)", ticker, n)
            else:
                logger.warning("No data for %s — may be delisted or symbol changed", ticker)

    logger.info("Stored %d price rows", stored)
    return stored


def get_latest_price(ticker: str) -> Optional[float]:
    with get_session() as session:
        row = (
            session.query(Price)
            .filter(Price.ticker == ticker)
            .order_by(Price.date.desc())
            .first()
        )
        return row.close if row else None


def get_price_series(ticker: str, days: int = 300):
    """Returns list of (date, close) tuples newest-first."""
    with get_session() as session:
        rows = (
            session.query(Price.date, Price.close)
            .filter(Price.ticker == ticker)
            .order_by(Price.date.desc())
            .limit(days)
            .all()
        )
        return [(r.date, r.close) for r in rows]
