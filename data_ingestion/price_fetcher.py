"""
Layer 01 · Data Ingestion — yFinance OHLCV
Runs daily before market open for all tickers of the active exchange.
"""
import logging
from datetime import date, timedelta
from typing import List, Optional

import yfinance as yf
from sqlalchemy.dialects.postgresql import insert

from config import get_active_exchange
from storage.database import get_session
from storage.models import Price

logger = logging.getLogger(__name__)


def fetch_prices(tickers: List[str] = None, days_back: int = 5) -> int:
    tickers = tickers or get_active_exchange().tickers
    start = date.today() - timedelta(days=days_back)
    stored = 0

    logger.info("Fetching OHLCV for %d tickers from %s", len(tickers), start)
    data = yf.download(
        tickers,
        start=start.isoformat(),
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if data.empty:
        logger.warning("yFinance returned empty dataframe")
        return 0

    with get_session() as session:
        for ticker in tickers:
            try:
                # yfinance 1.x always returns MultiIndex (Price, Ticker)
                df = data.xs(ticker, axis=1, level="Ticker")
                df = df.dropna(subset=["Close"])
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
                    stored += 1
            except Exception as e:
                logger.warning("Failed to store prices for %s: %s", ticker, e)

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
