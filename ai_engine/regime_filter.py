"""
Layer 03 · AI Engine — Market Regime Filter
XJO above 200-day EMA → risk-on (regime_ok=True).
XJO below 200-day EMA → risk-off (regime_ok=False, suppress signals).
"""
import logging

import numpy as np

from config.settings import REGIME_EMA_DAYS, XJO_TICKER
from data_ingestion.macro_fetcher import get_xjo_series
from storage.cache import get_value, set_value

logger = logging.getLogger(__name__)

REGIME_CACHE_KEY = "regime:xjo_ok"
REGIME_CACHE_TTL = 3600 * 4


def _compute_ema(values: list, period: int) -> float:
    """Compute EMA of a chronological price list, return last value."""
    arr = np.array(values, dtype=float)
    if len(arr) < period:
        return float(np.mean(arr))
    k = 2 / (period + 1)
    ema = arr[0]
    for price in arr[1:]:
        ema = price * k + ema * (1 - k)
    return float(ema)


def is_regime_ok() -> bool:
    """
    Returns True if XJO is above its 200-day EMA (risk-on environment).
    Result is cached for 4 hours.
    """
    cached = get_value(REGIME_CACHE_KEY)
    if cached is not None:
        return bool(cached)

    series = get_xjo_series(days=REGIME_EMA_DAYS + 20)
    if len(series) < 50:
        logger.warning("Insufficient XJO data for regime filter, defaulting to risk-on")
        set_value(REGIME_CACHE_KEY, True, REGIME_CACHE_TTL)
        return True

    # series is newest-first; reverse for chronological
    prices = [v for _, v in reversed(series)]
    latest = prices[-1]
    ema_200 = _compute_ema(prices, REGIME_EMA_DAYS)

    regime_ok = latest > ema_200
    pct_above = ((latest - ema_200) / ema_200) * 100

    logger.info(
        "Regime filter: XJO=%.2f EMA200=%.2f → %s (%.2f%%)",
        latest, ema_200, "RISK-ON" if regime_ok else "RISK-OFF", pct_above,
    )

    set_value(REGIME_CACHE_KEY, regime_ok, REGIME_CACHE_TTL)
    return regime_ok


def get_regime_summary() -> dict:
    series = get_xjo_series(days=REGIME_EMA_DAYS + 20)
    if not series:
        return {"regime_ok": True, "xjo": None, "ema200": None, "pct_above": None}

    prices = [v for _, v in reversed(series)]
    latest = prices[-1]
    ema_200 = _compute_ema(prices, REGIME_EMA_DAYS)
    pct_above = ((latest - ema_200) / ema_200) * 100

    return {
        "regime_ok": latest > ema_200,
        "xjo": round(latest, 2),
        "ema200": round(ema_200, 2),
        "pct_above": round(pct_above, 2),
    }
