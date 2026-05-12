"""
Layer 01 · Data Ingestion — Macro Indicators
Runs daily. Fetches exchange-specific macro indicators via yFinance.
"""
import logging
from datetime import date, timedelta

import yfinance as yf

from config import get_active_exchange
from storage.database import get_session
from storage.models import MacroIndicator
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger(__name__)


def _extract_close(df, symbol: str):
    """Extract Close series from yfinance 1.x MultiIndex (Price, Ticker) format."""
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        return df.xs(symbol, axis=1, level="Ticker")["Close"]
    return df["Close"]


def fetch_macro(days_back: int = 5) -> int:
    exchange = get_active_exchange()
    macro_symbols = exchange.macro_symbols
    start = date.today() - timedelta(days=days_back)
    stored = 0

    for indicator, yf_symbol in macro_symbols.items():
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
    """Returns latest value of each macro indicator for the active exchange."""
    exchange = get_active_exchange()
    snapshot = {}
    with get_session() as session:
        for indicator in exchange.macro_symbols:
            row = (
                session.query(MacroIndicator)
                .filter(MacroIndicator.indicator == indicator)
                .order_by(MacroIndicator.date.desc())
                .first()
            )
            snapshot[indicator] = row.value if row else None
    return snapshot


def get_index_series(days: int = 250):
    """Returns list of (date, close) for the active exchange's benchmark index."""
    exchange = get_active_exchange()
    with get_session() as session:
        rows = (
            session.query(MacroIndicator.date, MacroIndicator.value)
            .filter(MacroIndicator.indicator == exchange.index_macro_key)
            .order_by(MacroIndicator.date.desc())
            .limit(days)
            .all()
        )
        return [(r.date, r.value) for r in rows]


# Backward-compat alias used by older regime_filter code
def get_xjo_series(days: int = 250):
    return get_index_series(days)
