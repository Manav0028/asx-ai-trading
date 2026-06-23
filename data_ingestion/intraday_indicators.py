"""
Intraday Indicators — computed from yfinance 1-min bars.

VWAP = Σ(typical_price × volume) / Σ(volume)
where typical_price = (H + L + C) / 3, accumulated from the first
bar of the trading day to the current bar.

Called from job_intraday_rescan() to filter intraday entries:
  long  → only enter when current_price >= VWAP (buying strength)
  short → only enter when current_price <= VWAP (selling weakness)
"""
import logging
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


def compute_vwap_from_bars(raw_df) -> Dict[str, float]:
    """
    Compute VWAP for every ticker in a multi-ticker yfinance 1-min DataFrame.

    raw_df: the full DataFrame from:
        yf.download(tickers, period="1d", interval="1m", auto_adjust=True)

    Returns {ticker: vwap_price}. Tickers with missing or zero volume are excluded.
    """
    if raw_df is None or raw_df.empty:
        return {}

    try:
        import pandas as pd
        is_multi = isinstance(raw_df.columns, pd.MultiIndex)
    except Exception:
        return {}

    tickers = []
    if is_multi:
        tickers = raw_df.columns.get_level_values(1).unique().tolist()
    else:
        tickers = ["__single__"]

    result: Dict[str, float] = {}
    for ticker in tickers:
        try:
            if is_multi:
                high   = raw_df["High"][ticker].dropna()
                low    = raw_df["Low"][ticker].dropna()
                close  = raw_df["Close"][ticker].dropna()
                volume = raw_df["Volume"][ticker].dropna()
            else:
                high   = raw_df["High"].dropna()
                low    = raw_df["Low"].dropna()
                close  = raw_df["Close"].dropna()
                volume = raw_df["Volume"].dropna()

            idx = (high.index
                   .intersection(low.index)
                   .intersection(close.index)
                   .intersection(volume.index))
            if idx.empty:
                continue

            h = high.loc[idx].values.astype(float)
            l = low.loc[idx].values.astype(float)
            c = close.loc[idx].values.astype(float)
            v = volume.loc[idx].values.astype(float)

            total_vol = v.sum()
            if total_vol == 0:
                continue

            typical = (h + l + c) / 3.0
            vwap = np.sum(typical * v) / total_vol
            key = ticker if ticker != "__single__" else tickers[0]
            result[key] = round(float(vwap), 4)

        except Exception as e:
            logger.debug("VWAP failed for %s: %s", ticker, e)

    return result


def compute_vwap_single(ticker: str) -> Optional[float]:
    """Fetch 1-min bars for one ticker and return its VWAP. Use for one-off calls."""
    try:
        import yfinance as yf
        raw = yf.download(ticker, period="1d", interval="1m",
                          progress=False, auto_adjust=True)
        return compute_vwap_from_bars(raw).get(ticker)
    except Exception as e:
        logger.warning("compute_vwap_single(%s) failed: %s", ticker, e)
        return None
