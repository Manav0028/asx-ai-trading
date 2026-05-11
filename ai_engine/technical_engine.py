"""
Layer 03 · AI Engine — Technical Engine
Computes RSI, MACD, Bollinger Bands, EMA crossover signals.
Returns 0-100 composite technical score.
"""
import logging
from typing import List, Optional, Tuple

import numpy as np

from data_ingestion.price_fetcher import get_price_series
from storage.cache import cache_score, get_cached_score

logger = logging.getLogger(__name__)


def _ema(prices: np.ndarray, period: int) -> np.ndarray:
    k = 2 / (period + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = prices[i] * k + ema[i - 1] * (1 - k)
    return ema


def _rsi(prices: np.ndarray, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(prices: np.ndarray) -> Tuple[float, float]:
    """Returns (macd_line, signal_line) for the latest bar."""
    if len(prices) < 26:
        return 0.0, 0.0
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    return macd_line[-1], signal_line[-1]


def _bollinger(prices: np.ndarray, period: int = 20) -> Tuple[float, float, float]:
    """Returns (upper, mid, lower) bands for latest bar."""
    if len(prices) < period:
        p = prices[-1]
        return p, p, p
    window = prices[-period:]
    mid = np.mean(window)
    std = np.std(window)
    return mid + 2 * std, mid, mid - 2 * std


def _ema_crossover(prices: np.ndarray) -> float:
    """EMA 20/50 crossover signal: 1.0 bullish, -1.0 bearish, 0 neutral."""
    if len(prices) < 50:
        return 0.0
    ema20 = _ema(prices, 20)
    ema50 = _ema(prices, 50)
    diff_now = ema20[-1] - ema50[-1]
    diff_prev = ema20[-2] - ema50[-2]
    if diff_now > 0 and diff_prev <= 0:
        return 1.0   # golden cross
    if diff_now < 0 and diff_prev >= 0:
        return -1.0  # death cross
    return 1.0 if diff_now > 0 else -1.0


def score_technical(ticker: str) -> float:
    """Returns technical score 0-100."""
    cached = get_cached_score(ticker, "technical")
    if cached is not None:
        return cached

    series = get_price_series(ticker, days=300)
    if len(series) < 30:
        cache_score(ticker, "technical", 50.0)
        return 50.0

    # series is newest-first, reverse for chronological order
    prices = np.array([c for _, c in reversed(series)], dtype=float)
    latest = prices[-1]

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi = _rsi(prices)
    # RSI scoring: oversold (<30)=bullish, overbought(>70)=bearish
    if rsi < 30:
        rsi_score = 85.0
    elif rsi < 45:
        rsi_score = 70.0
    elif rsi < 55:
        rsi_score = 55.0
    elif rsi < 70:
        rsi_score = 45.0
    else:
        rsi_score = 25.0

    # ── MACD ──────────────────────────────────────────────────────────────────
    macd_val, signal_val = _macd(prices)
    macd_score = 65.0 if macd_val > signal_val else 35.0

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    upper, mid, lower = _bollinger(prices)
    bb_pct = (latest - lower) / (upper - lower + 1e-9)
    if bb_pct < 0.2:
        bb_score = 80.0   # near lower band — potential bounce
    elif bb_pct < 0.4:
        bb_score = 65.0
    elif bb_pct < 0.6:
        bb_score = 55.0
    elif bb_pct < 0.8:
        bb_score = 45.0
    else:
        bb_score = 30.0   # near upper band — potentially overbought

    # ── EMA Crossover ─────────────────────────────────────────────────────────
    cross_signal = _ema_crossover(prices)
    cross_score = 70.0 if cross_signal > 0 else 30.0

    composite = (
        rsi_score * 0.30
        + macd_score * 0.25
        + bb_score * 0.25
        + cross_score * 0.20
    )
    composite = round(max(0.0, min(100.0, composite)), 2)

    logger.debug(
        "%s technical: RSI=%.1f MACD=%.1f BB=%.1f Cross=%.1f → %.1f",
        ticker, rsi_score, macd_score, bb_score, cross_score, composite,
    )

    cache_score(ticker, "technical", composite)
    return composite


def get_entry_target_prices(ticker: str) -> Tuple[Optional[float], Optional[float]]:
    """Returns (entry_price, target_price) based on Bollinger mid/upper."""
    series = get_price_series(ticker, days=60)
    if not series:
        return None, None
    prices = np.array([c for _, c in reversed(series)], dtype=float)
    entry = prices[-1]
    _, _, upper, mid, _ = (*prices[-2:], *_bollinger(prices))
    target = round(mid + (upper - mid) * 0.5, 3)
    return round(entry, 3), round(target, 3)


def batch_score_technical(tickers: list) -> dict:
    return {t: score_technical(t) for t in tickers}
