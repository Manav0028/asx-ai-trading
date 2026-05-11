"""
Layer 03 · AI Engine — Fundamental Scorer (Enhanced)
Scores P/E, Forward P/E, ROE, EPS growth, Debt/Equity, Profit Margin,
Revenue Growth, Dividend Yield. Returns 0-100 with rich metadata.
"""
import logging
from typing import Dict, Optional

import yfinance as yf

from storage.cache import cache_score, get_cached_score

logger = logging.getLogger(__name__)


def _safe(val, default=None) -> Optional[float]:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _score_pe(pe: Optional[float]) -> tuple:
    if pe is None or pe <= 0:
        return 45.0, "P/E unavailable"
    if pe < 8:
        return 55.0, f"P/E {pe:.1f} — very cheap but check for distress"
    if pe <= 14:
        return 95.0, f"P/E {pe:.1f} — excellent value"
    if pe <= 20:
        return 80.0, f"P/E {pe:.1f} — fair value"
    if pe <= 28:
        return 60.0, f"P/E {pe:.1f} — slight premium"
    if pe <= 40:
        return 38.0, f"P/E {pe:.1f} — expensive"
    return 18.0, f"P/E {pe:.1f} — very expensive"


def _score_forward_pe(fpe: Optional[float]) -> tuple:
    if fpe is None or fpe <= 0:
        return 50.0, ""
    if fpe <= 12:
        return 95.0, f"Forward P/E {fpe:.1f} — market expects strong earnings"
    if fpe <= 18:
        return 78.0, f"Forward P/E {fpe:.1f} — reasonable growth expectation"
    if fpe <= 25:
        return 58.0, f"Forward P/E {fpe:.1f} — priced for growth"
    return 35.0, f"Forward P/E {fpe:.1f} — high growth already priced in"


def _score_roe(roe: Optional[float]) -> tuple:
    if roe is None:
        return 45.0, "ROE unavailable"
    pct = roe * 100
    if pct >= 30:
        return 100.0, f"ROE {pct:.1f}% — exceptional profitability"
    if pct >= 20:
        return 85.0, f"ROE {pct:.1f}% — strong profitability"
    if pct >= 12:
        return 65.0, f"ROE {pct:.1f}% — decent profitability"
    if pct >= 5:
        return 45.0, f"ROE {pct:.1f}% — below-average returns"
    return 20.0, f"ROE {pct:.1f}% — poor profitability"


def _score_eps_growth(eps_ttm: Optional[float], eps_fwd: Optional[float]) -> tuple:
    if eps_ttm is None or eps_fwd is None or eps_ttm <= 0:
        return 50.0, "EPS growth unavailable"
    growth = (eps_fwd - eps_ttm) / abs(eps_ttm) * 100
    if growth >= 25:
        return 100.0, f"EPS growing {growth:.0f}% — strong earnings momentum"
    if growth >= 12:
        return 82.0, f"EPS growing {growth:.0f}% — solid earnings growth"
    if growth >= 3:
        return 63.0, f"EPS growing {growth:.0f}% — modest growth"
    if growth >= -5:
        return 45.0, f"EPS flat ({growth:.0f}%)"
    return 20.0, f"EPS declining {growth:.0f}% — earnings under pressure"


def _score_debt(de: Optional[float]) -> tuple:
    if de is None:
        return 55.0, "debt data unavailable"
    # yfinance returns D/E as percentage (e.g. 45 = 45%)
    de_ratio = de / 100
    if de_ratio < 0.2:
        return 100.0, f"D/E {de_ratio:.2f} — very low debt, financially strong"
    if de_ratio < 0.5:
        return 82.0, f"D/E {de_ratio:.2f} — manageable debt"
    if de_ratio < 1.0:
        return 62.0, f"D/E {de_ratio:.2f} — moderate debt load"
    if de_ratio < 2.0:
        return 40.0, f"D/E {de_ratio:.2f} — high debt, watch interest costs"
    return 18.0, f"D/E {de_ratio:.2f} — very high debt, significant risk"


def _score_margin(margin: Optional[float]) -> tuple:
    if margin is None:
        return 50.0, ""
    pct = margin * 100
    if pct >= 25:
        return 95.0, f"Net margin {pct:.1f}% — highly profitable business"
    if pct >= 12:
        return 75.0, f"Net margin {pct:.1f}% — good profitability"
    if pct >= 5:
        return 55.0, f"Net margin {pct:.1f}% — thin margins"
    if pct >= 0:
        return 38.0, f"Net margin {pct:.1f}% — very thin margins"
    return 15.0, f"Net margin {pct:.1f}% — loss-making"


def _score_revenue_growth(growth: Optional[float]) -> tuple:
    if growth is None:
        return 50.0, ""
    pct = growth * 100
    if pct >= 20:
        return 90.0, f"Revenue growing {pct:.0f}% — strong top-line growth"
    if pct >= 8:
        return 70.0, f"Revenue growing {pct:.0f}%"
    if pct >= 0:
        return 52.0, f"Revenue flat/slow ({pct:.0f}%)"
    return 30.0, f"Revenue declining {pct:.0f}%"


def _score_dividend(div_yield: Optional[float]) -> tuple:
    if div_yield is None or div_yield == 0:
        return 50.0, "no dividend"
    pct = div_yield * 100
    if pct >= 5:
        return 85.0, f"Dividend yield {pct:.1f}% — attractive income"
    if pct >= 3:
        return 70.0, f"Dividend yield {pct:.1f}% — solid income"
    if pct >= 1:
        return 55.0, f"Dividend yield {pct:.1f}%"
    return 45.0, f"Dividend yield {pct:.1f}% — minimal income"


def score_fundamental(ticker: str) -> float:
    cached = get_cached_score(ticker, "fundamental")
    if cached is not None:
        return cached
    meta = _compute_fundamental(ticker)
    score = meta["composite_score"]
    cache_score(ticker, "fundamental", score, ttl=3600 * 6)
    from storage.cache import set_value
    set_value(f"fund_meta:{ticker}", meta, ttl=3600 * 6)
    return score


def get_fundamental_meta(ticker: str) -> dict:
    from storage.cache import get_value
    meta = get_value(f"fund_meta:{ticker}")
    if meta:
        return meta
    return _compute_fundamental(ticker)


def _compute_fundamental(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        logger.warning("yFinance info failed for %s: %s", ticker, e)
        return {"composite_score": 50.0, "signals": [], "highlights": "Data unavailable"}

    pe_score,   pe_sig   = _score_pe(_safe(info.get("trailingPE")))
    fpe_score,  fpe_sig  = _score_forward_pe(_safe(info.get("forwardPE")))
    roe_score,  roe_sig  = _score_roe(_safe(info.get("returnOnEquity")))
    eps_score,  eps_sig  = _score_eps_growth(
        _safe(info.get("trailingEps")), _safe(info.get("forwardEps"))
    )
    debt_score, debt_sig = _score_debt(_safe(info.get("debtToEquity")))
    mgn_score,  mgn_sig  = _score_margin(_safe(info.get("profitMargins")))
    rev_score,  rev_sig  = _score_revenue_growth(_safe(info.get("revenueGrowth")))
    div_score,  div_sig  = _score_dividend(_safe(info.get("dividendYield")))

    composite = (
        pe_score   * 0.22
        + fpe_score  * 0.13
        + roe_score  * 0.20
        + eps_score  * 0.18
        + debt_score * 0.12
        + mgn_score  * 0.08
        + rev_score  * 0.05
        + div_score  * 0.02
    )
    composite = round(max(0.0, min(100.0, composite)), 2)

    # Build signal list (only non-empty)
    signals = [s for s in [pe_sig, fpe_sig, roe_sig, eps_sig, debt_sig, mgn_sig] if s]

    # One-line highlight for alerts
    best = max([(pe_score, pe_sig), (roe_score, roe_sig), (eps_score, eps_sig)],
               key=lambda x: x[0])
    worst = min([(debt_score, debt_sig), (mgn_score, mgn_sig)],
                key=lambda x: x[0])
    highlights = f"Best: {best[1]}. Watch: {worst[1]}."

    logger.debug("%s fundamentals: %.1f", ticker, composite)
    return {
        "composite_score": composite,
        "signals": signals,
        "highlights": highlights,
        "pe": _safe(info.get("trailingPE")),
        "roe": _safe(info.get("returnOnEquity")),
        "div_yield": _safe(info.get("dividendYield")),
    }


def batch_score_fundamental(tickers: list) -> dict:
    return {t: score_fundamental(t) for t in tickers}
