"""
Strategy Engine — Vectorised Indicator Arrays
Full-length indicator series computed once per ticker so every strategy can
evaluate any historical bar without recomputation.
"""
from typing import Dict

import numpy as np


def ema_arr(closes: np.ndarray, period: int) -> np.ndarray:
    k = 2 / (period + 1)
    out = np.zeros_like(closes)
    out[0] = closes[0]
    for i in range(1, len(closes)):
        out[i] = closes[i] * k + out[i - 1] * (1 - k)
    return out


def rsi_arr(closes: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full_like(closes, 50.0)
    if len(closes) < period + 1:
        return out
    deltas = np.diff(closes)
    for i in range(period, len(deltas) + 1):
        window = deltas[i - period:i]
        ag = np.mean(np.where(window > 0, window, 0.0))
        al = np.mean(np.where(window < 0, -window, 0.0))
        out[i] = 100 - (100 / (1 + ag / (al + 1e-9)))
    return out


def stoch_rsi_arr(closes: np.ndarray, rsi_period: int = 14, stoch_period: int = 14) -> np.ndarray:
    rsi = rsi_arr(closes, rsi_period)
    out = np.full_like(closes, 50.0)
    start = rsi_period + stoch_period
    for i in range(start, len(closes)):
        recent = rsi[i - stoch_period + 1: i + 1]
        lo, hi = np.min(recent), np.max(recent)
        out[i] = 50.0 if hi == lo else (rsi[i] - lo) / (hi - lo) * 100
    return out


def atr_arr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    out = closes * 0.02  # fallback: 2% of price
    if n < period + 1:
        return out
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    for i in range(period, n):
        out[i] = np.mean(tr[i - period:i])
    return out


def adx_arr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    out = np.full(n, 20.0)
    if n < period * 2:
        return out
    tr_list = np.zeros(n - 1)
    plus_dm = np.zeros(n - 1)
    minus_dm = np.zeros(n - 1)
    for i in range(1, n):
        h, l, ph, pl, pc = highs[i], lows[i], highs[i - 1], lows[i - 1], closes[i - 1]
        tr_list[i - 1] = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        plus_dm[i - 1] = up if up > dn and up > 0 else 0
        minus_dm[i - 1] = dn if dn > up and dn > 0 else 0
    for i in range(period * 2, n):
        tr_w = tr_list[i - period - 1: i - 1]
        pdi = 100 * np.mean(plus_dm[i - period - 1: i - 1]) / (np.mean(tr_w) + 1e-9)
        mdi = 100 * np.mean(minus_dm[i - period - 1: i - 1]) / (np.mean(tr_w) + 1e-9)
        out[i] = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-9)
    return out


def macd_hist_arr(closes: np.ndarray) -> np.ndarray:
    macd_line = ema_arr(closes, 12) - ema_arr(closes, 26)
    signal = ema_arr(macd_line, 9)
    return macd_line - signal


def bollinger_pct_arr(closes: np.ndarray, period: int = 20) -> np.ndarray:
    """%B position within the bands: 0 = at lower band, 1 = at upper band."""
    out = np.full_like(closes, 0.5)
    for i in range(period, len(closes)):
        window = closes[i - period + 1: i + 1]
        mid = np.mean(window)
        std = np.std(window)
        upper, lower = mid + 2 * std, mid - 2 * std
        out[i] = (closes[i] - lower) / (upper - lower + 1e-9)
    return out


def rolling_high_arr(highs: np.ndarray, period: int = 20) -> np.ndarray:
    """Highest high of the *previous* `period` bars (excludes current bar)."""
    out = np.copy(highs)
    for i in range(period, len(highs)):
        out[i] = np.max(highs[i - period:i])
    return out


def rolling_low_arr(lows: np.ndarray, period: int = 20) -> np.ndarray:
    """Lowest low of the *previous* `period` bars (excludes current bar)."""
    out = np.copy(lows)
    for i in range(period, len(lows)):
        out[i] = np.min(lows[i - period:i])
    return out


def sma_arr(closes: np.ndarray, period: int) -> np.ndarray:
    out = np.copy(closes)
    for i in range(period, len(closes)):
        out[i] = np.mean(closes[i - period + 1: i + 1])
    return out


def momentum_arr(closes: np.ndarray, lookback: int = 252, skip: int = 21) -> np.ndarray:
    """Classic 12-1 momentum: return from `lookback` bars ago to `skip` bars ago.
    Skipping the last month avoids the short-term reversal effect."""
    out = np.zeros_like(closes)
    for i in range(lookback, len(closes)):
        base = closes[i - lookback]
        out[i] = (closes[i - skip] - base) / (base + 1e-9)
    return out


def rolling_vol_avg_arr(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    """Average volume of the *previous* `period` bars (excludes current bar)."""
    out = np.copy(volumes).astype(float)
    for i in range(period, len(volumes)):
        out[i] = np.mean(volumes[i - period:i])
    return out


def precompute(ohlcv: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Build the full indicator set used by all strategies."""
    c, h, l, v = ohlcv["closes"], ohlcv["highs"], ohlcv["lows"], ohlcv["volumes"]
    o = ohlcv.get("opens")
    if o is None:
        o = np.copy(c)  # candle patterns degrade gracefully without opens
    return {
        "closes": c, "highs": h, "lows": l, "volumes": v, "opens": o,
        "ema20": ema_arr(c, 20),
        "ema50": ema_arr(c, 50),
        "rsi": rsi_arr(c),
        "stoch_rsi": stoch_rsi_arr(c),
        "atr": atr_arr(h, l, c),
        "adx": adx_arr(h, l, c),
        "macd_hist": macd_hist_arr(c),
        "bb_pct": bollinger_pct_arr(c),
        "high_20": rolling_high_arr(h, 20),
        "low_20": rolling_low_arr(l, 20),
        "high_55": rolling_high_arr(h, 55),
        "high_252": rolling_high_arr(h, 252),
        "vol_avg_20": rolling_vol_avg_arr(v, 20),
        "sma200": sma_arr(c, 200),
        "rsi2": rsi_arr(c, 2),
        "mom_12_1": momentum_arr(c),
    }
