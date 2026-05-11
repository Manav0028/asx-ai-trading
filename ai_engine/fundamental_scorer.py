"""
Layer 03 · AI Engine — Fundamental Scorer
Uses yFinance info dict to score P/E, ROE, EPS growth, debt/equity.
Returns 0-100.
"""
import logging
from typing import Optional

import yfinance as yf

from storage.cache import cache_score, get_cached_score

logger = logging.getLogger(__name__)


def _safe_float(val, default=None) -> Optional[float]:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _score_pe(pe: Optional[float]) -> float:
    """Lower P/E → higher score. Ideal range 8-20."""
    if pe is None or pe <= 0:
        return 40.0
    if pe < 8:
        return 60.0   # possibly distressed / cyclical
    if pe <= 15:
        return 100.0
    if pe <= 20:
        return 85.0
    if pe <= 30:
        return 65.0
    if pe <= 50:
        return 40.0
    return 20.0


def _score_roe(roe: Optional[float]) -> float:
    """Higher ROE → higher score. Ideal > 15%."""
    if roe is None:
        return 40.0
    roe_pct = roe * 100
    if roe_pct >= 25:
        return 100.0
    if roe_pct >= 15:
        return 80.0
    if roe_pct >= 10:
        return 60.0
    if roe_pct >= 0:
        return 40.0
    return 10.0


def _score_eps_growth(eps_ttm: Optional[float], eps_fwd: Optional[float]) -> float:
    """Positive EPS growth → higher score."""
    if eps_ttm is None or eps_fwd is None or eps_ttm <= 0:
        return 50.0
    growth = (eps_fwd - eps_ttm) / abs(eps_ttm)
    if growth >= 0.20:
        return 100.0
    if growth >= 0.10:
        return 80.0
    if growth >= 0.0:
        return 60.0
    if growth >= -0.10:
        return 35.0
    return 15.0


def _score_debt(de_ratio: Optional[float]) -> float:
    """Lower debt/equity → higher score."""
    if de_ratio is None:
        return 50.0
    if de_ratio < 0.3:
        return 100.0
    if de_ratio < 0.7:
        return 80.0
    if de_ratio < 1.0:
        return 60.0
    if de_ratio < 2.0:
        return 40.0
    return 20.0


def score_fundamental(ticker: str) -> float:
    """Returns fundamental score 0-100."""
    cached = get_cached_score(ticker, "fundamental")
    if cached is not None:
        return cached

    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        logger.warning("yFinance info failed for %s: %s", ticker, e)
        cache_score(ticker, "fundamental", 50.0, ttl=3600 * 6)
        return 50.0

    pe = _safe_float(info.get("trailingPE"))
    roe = _safe_float(info.get("returnOnEquity"))
    eps_ttm = _safe_float(info.get("trailingEps"))
    eps_fwd = _safe_float(info.get("forwardEps"))
    de_ratio = _safe_float(info.get("debtToEquity"))
    if de_ratio is not None:
        de_ratio /= 100  # yFinance returns as percentage

    pe_score = _score_pe(pe)
    roe_score = _score_roe(roe)
    eps_score = _score_eps_growth(eps_ttm, eps_fwd)
    debt_score = _score_debt(de_ratio)

    composite = (pe_score * 0.30 + roe_score * 0.30 + eps_score * 0.25 + debt_score * 0.15)
    composite = round(max(0.0, min(100.0, composite)), 2)

    logger.debug(
        "%s fundamental: PE=%.1f ROE=%.1f EPS=%.1f Debt=%.1f → %.1f",
        ticker, pe_score, roe_score, eps_score, debt_score, composite,
    )

    cache_score(ticker, "fundamental", composite, ttl=3600 * 6)
    return composite


def batch_score_fundamental(tickers: list) -> dict:
    return {t: score_fundamental(t) for t in tickers}
