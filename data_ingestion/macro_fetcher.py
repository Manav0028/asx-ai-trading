"""
Layer 01 · Data Ingestion — Macro Indicators
Runs daily. Fetches RBA rate, AUD/USD, iron ore, gold, oil via yFinance.
"""
import logging
from datetime import date, timedelta

import yfinance as yf

from storage.database import get_session
from storage.models import MacroIndicator
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger(__name__)

MACRO_SYMBOLS = {
    "aud_usd":   "AUDUSD=X",
    "iron_ore":  "IRON.L",       # proxy — London-listed iron ore ETF
    "gold_usd":  "GC=F",
    "oil_brent": "BZ=F",
    "xjo_index": "^AXJO",
    "sp500":     "^GSPC",
    "vix":       "^VIX",
    "copper":    "HG=F",
}

# RBA cash rate — updated from RBA website (static refresh weekly is fine)
RBA_RATE_TICKER = None  # We'll store manually / scrape separately


def _extract_close(df, symbol: str):
    """Extract Close series from yfinance 1.x MultiIndex (Price, Ticker) format."""
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        return df.xs(symbol, axis=1, level="Ticker")["Close"]
    return df["Close"]


def fetch_macro(days_back: int = 5) -> int:
    start = date.today() - timedelta(days=days_back)
    stored = 0

    for indicator, yf_symbol in MACRO_SYMBOLS.items():
        try:
            df = yf.download(
                yf_symbol,
                start=start.isoformat(),
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                continue

            close_series = _extract_close(df, yf_symbol)
            with get_session() as session:
                for idx, val in close_series.dropna().items():
                    val = float(val)
                    stmt = insert(MacroIndicator).values(
                        date=idx.date(),
                        indicator=indicator,
                        value=val,
                    ).on_conflict_do_update(
                        constraint="uq_macro_date_indicator",
                        set_={"value": val},
                    )
                    session.execute(stmt)
                    stored += 1
        except Exception as e:
            logger.warning("Macro fetch failed for %s (%s): %s", indicator, yf_symbol, e)

    logger.info("Stored %d macro indicator rows", stored)
    return stored


def get_macro_snapshot() -> dict:
    """Returns latest value of each macro indicator."""
    snapshot = {}
    with get_session() as session:
        for indicator in MACRO_SYMBOLS:
            row = (
                session.query(MacroIndicator)
                .filter(MacroIndicator.indicator == indicator)
                .order_by(MacroIndicator.date.desc())
                .first()
            )
            snapshot[indicator] = row.value if row else None
    return snapshot


def get_xjo_series(days: int = 250):
    """Returns list of (date, close) for XJO regime filter."""
    with get_session() as session:
        rows = (
            session.query(MacroIndicator.date, MacroIndicator.value)
            .filter(MacroIndicator.indicator == "xjo_index")
            .order_by(MacroIndicator.date.desc())
            .limit(days)
            .all()
        )
        return [(r.date, r.value) for r in rows]
