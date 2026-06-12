"""
Layer 03 · AI Engine — Technical Engine (Enhanced)
Indicators: RSI, Stochastic RSI, MACD, Bollinger Bands, EMA Cross, Volume Spike, ATR, ADX.
Returns 0-100 composite technical score + rich metadata for alerts.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from data_ingestion.price_fetcher import get_price_series
from storage.cache import cache_score, get_cached_score
from storage.database import get_session
from storage.models import Price

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
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def _macd(prices: np.ndarray) -> Tuple[float, float, float]:
    """Returns (macd_line, signal_line, histogram) for the latest bar."""
    if len(prices) < 26:
        return 0.0, 0.0, 0.0
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    macd_line = ema12 - ema26
    signal = _ema(macd_line, 9)
    return float(macd_line[-1]), float(signal[-1]), float(macd_line[-1] - signal[-1])


def _bollinger(prices: np.ndarray, period: int = 20) -> Tuple[float, float, float]:
    if len(prices) < period:
        p = prices[-1]
        return p, p, p
    window = prices[-period:]
    mid = np.mean(window)
    std = np.std(window)
    return float(mid + 2 * std), float(mid), float(mid - 2 * std)


def _ema_crossover(prices: np.ndarray) -> Tuple[float, str]:
    """Returns (score, description)."""
    if len(prices) < 55:
        return 50.0, "insufficient data"
    ema20 = _ema(prices, 20)
    ema50 = _ema(prices, 50)
    diff_now = ema20[-1] - ema50[-1]
    diff_prev = ema20[-2] - ema50[-2]
    if diff_now > 0 and diff_prev <= 0:
        return 90.0, "golden cross (bullish breakout)"
    if diff_now < 0 and diff_prev >= 0:
        return 10.0, "death cross (bearish breakdown)"
    if diff_now > 0:
        return 65.0, "uptrend (20-day above 50-day)"
    return 35.0, "downtrend (20-day below 50-day)"


def _volume_spike(volumes: np.ndarray, lookback: int = 20) -> Tuple[float, str]:
    """Detects unusual volume — sign of institutional activity."""
    if len(volumes) < lookback + 1:
        return 50.0, "no volume data"
    avg_vol = np.mean(volumes[-(lookback + 1):-1])
    today_vol = volumes[-1]
    if avg_vol == 0:
        return 50.0, "no volume data"
    ratio = today_vol / avg_vol
    if ratio >= 3.0:
        return 90.0, f"volume {ratio:.1f}x average (strong interest)"
    if ratio >= 2.0:
        return 75.0, f"volume {ratio:.1f}x average (elevated interest)"
    if ratio >= 1.3:
        return 60.0, f"volume {ratio:.1f}x average (slightly elevated)"
    if ratio < 0.5:
        return 35.0, f"volume {ratio:.1f}x average (low activity)"
    return 50.0, f"volume {ratio:.1f}x average (normal)"


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Average True Range — measures volatility for dynamic stop sizing."""
    if len(closes) < period + 1:
        return float(closes[-1] * 0.02)
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1]),
        )
    )
    return float(np.mean(tr[-period:]))


def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> Tuple[float, str]:
    """Average Directional Index — measures trend strength (not direction)."""
    if len(closes) < period * 2:
        return 25.0, "trend unknown"
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        h, l, ph, pl, pc = highs[i], lows[i], highs[i-1], lows[i-1], closes[i-1]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        up = h - ph
        dn = pl - l
        plus_dm.append(up if up > dn and up > 0 else 0)
        minus_dm.append(dn if dn > up and dn > 0 else 0)
    tr_arr = np.array(tr_list[-period:])
    pdi = 100 * np.mean(plus_dm[-period:]) / (np.mean(tr_arr) + 1e-9)
    mdi = 100 * np.mean(minus_dm[-period:]) / (np.mean(tr_arr) + 1e-9)
    dx = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-9)
    if dx >= 40:
        trend = "strong trend"
    elif dx >= 25:
        trend = "moderate trend"
    else:
        trend = "weak/sideways"
    return float(dx), trend


def _stoch_rsi(prices: np.ndarray, rsi_period: int = 14, stoch_period: int = 14) -> float:
    if len(prices) < rsi_period + stoch_period:
        return 50.0
    deltas = np.diff(prices)
    rsi_vals = []
    for i in range(rsi_period, len(deltas) + 1):
        window = deltas[i - rsi_period:i]
        ag = np.mean(np.where(window > 0, window, 0.0))
        al = np.mean(np.where(window < 0, -window, 0.0))
        rsi_vals.append(100 - (100 / (1 + ag / (al + 1e-9))))
    if len(rsi_vals) < stoch_period:
        return 50.0
    recent = rsi_vals[-stoch_period:]
    low, high = min(recent), max(recent)
    if high == low:
        return 50.0
    return round((rsi_vals[-1] - low) / (high - low) * 100, 2)


def _get_ohlcv(ticker: str, days: int = 300) -> Optional[Dict[str, np.ndarray]]:
    """Pull OHLCV arrays from DB for a ticker."""
    with get_session() as session:
        rows = (
            session.query(Price.date, Price.open, Price.high, Price.low, Price.close, Price.volume)
            .filter(Price.ticker == ticker)
            .order_by(Price.date.desc())   # newest first then reverse — asc+limit returns the OLDEST bars
            .limit(days)
            .all()
        )
    if len(rows) < 30:
        return None
    rows = list(reversed(rows))            # oldest → newest for indicator math
    return {
        "opens":   np.array([r.open or r.close for r in rows], dtype=float),
        "highs":   np.array([r.high or r.close for r in rows], dtype=float),
        "lows":    np.array([r.low or r.close for r in rows], dtype=float),
        "closes":  np.array([r.close for r in rows], dtype=float),
        "volumes": np.array([r.volume or 0 for r in rows], dtype=float),
    }


def score_technical(ticker: str) -> float:
    cached = get_cached_score(ticker, "technical")
    if cached is not None:
        return cached
    meta = _compute_technical(ticker)
    score = meta["composite_score"]
    cache_score(ticker, "technical", score)
    # Cache rich metadata for alerts
    from storage.cache import set_value
    set_value(f"tech_meta:{ticker}", meta, ttl=3600 * 4)
    return score


def get_technical_meta(ticker: str) -> dict:
    from storage.cache import get_value
    meta = get_value(f"tech_meta:{ticker}")
    if meta:
        return meta
    return _compute_technical(ticker)


def _compute_technical(ticker: str) -> dict:
    ohlcv = _get_ohlcv(ticker)
    if ohlcv is None:
        return {"composite_score": 50.0, "signals": [], "atr": 0, "rsi": 50,
                "trend": "unknown", "entry": None, "target": None, "stop": None}

    closes = ohlcv["closes"]
    highs = ohlcv["highs"]
    lows = ohlcv["lows"]
    volumes = ohlcv["volumes"]
    latest = closes[-1]

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi = _rsi(closes)
    if rsi < 25:
        rsi_score, rsi_signal = 90.0, f"RSI {rsi:.0f} — heavily oversold, strong bounce potential"
    elif rsi < 35:
        rsi_score, rsi_signal = 78.0, f"RSI {rsi:.0f} — oversold, likely to recover"
    elif rsi < 45:
        rsi_score, rsi_signal = 65.0, f"RSI {rsi:.0f} — mildly oversold"
    elif rsi < 55:
        rsi_score, rsi_signal = 55.0, f"RSI {rsi:.0f} — neutral momentum"
    elif rsi < 65:
        rsi_score, rsi_signal = 45.0, f"RSI {rsi:.0f} — mildly overbought"
    elif rsi < 75:
        rsi_score, rsi_signal = 32.0, f"RSI {rsi:.0f} — overbought, may pull back"
    else:
        rsi_score, rsi_signal = 18.0, f"RSI {rsi:.0f} — very overbought"

    # ── MACD ──────────────────────────────────────────────────────────────────
    macd_val, signal_val, hist = _macd(closes)
    prev_hist = float(_macd(closes[:-1])[2]) if len(closes) > 27 else 0
    if hist > 0 and prev_hist <= 0:
        macd_score, macd_signal = 85.0, "MACD just turned bullish (momentum building)"
    elif hist < 0 and prev_hist >= 0:
        macd_score, macd_signal = 15.0, "MACD just turned bearish (momentum fading)"
    elif hist > 0:
        macd_score, macd_signal = 65.0, "MACD bullish (upward momentum)"
    else:
        macd_score, macd_signal = 35.0, "MACD bearish (downward momentum)"

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    upper, mid, lower = _bollinger(closes)
    band_width = upper - lower
    bb_pct = (latest - lower) / (band_width + 1e-9)
    if bb_pct < 0.1:
        bb_score, bb_signal = 88.0, f"Price near lower Bollinger band — potential bounce from ${latest:.2f}"
    elif bb_pct < 0.25:
        bb_score, bb_signal = 72.0, "Price in lower quarter of Bollinger band — buy zone"
    elif bb_pct < 0.45:
        bb_score, bb_signal = 58.0, "Price below Bollinger midpoint"
    elif bb_pct < 0.6:
        bb_score, bb_signal = 52.0, "Price near Bollinger midpoint"
    elif bb_pct < 0.75:
        bb_score, bb_signal = 42.0, "Price above Bollinger midpoint"
    elif bb_pct < 0.9:
        bb_score, bb_signal = 28.0, "Price in upper quarter — approaching resistance"
    else:
        bb_score, bb_signal = 15.0, f"Price at upper Bollinger band — stretched, may pull back"

    # ── EMA Crossover ─────────────────────────────────────────────────────────
    cross_score, cross_signal = _ema_crossover(closes)

    # ── Volume ────────────────────────────────────────────────────────────────
    vol_score, vol_signal = _volume_spike(volumes)

    # ── ADX (trend strength) ──────────────────────────────────────────────────
    adx_val, adx_desc = _adx(highs, lows, closes)
    # ADX boosts or dampens: strong trend = more reliable signals
    adx_multiplier = 1.1 if adx_val >= 30 else (0.95 if adx_val < 20 else 1.0)

    # ── Stochastic RSI ──────────────────────────────────────────────────────────
    stoch_rsi = _stoch_rsi(closes)
    if stoch_rsi < 20:
        stoch_score, stoch_signal = 85.0, f"StochRSI {stoch_rsi:.0f} — oversold momentum"
    elif stoch_rsi < 40:
        stoch_score, stoch_signal = 65.0, f"StochRSI {stoch_rsi:.0f} — momentum building"
    elif stoch_rsi < 60:
        stoch_score, stoch_signal = 50.0, f"StochRSI {stoch_rsi:.0f} — neutral"
    elif stoch_rsi < 80:
        stoch_score, stoch_signal = 35.0, f"StochRSI {stoch_rsi:.0f} — momentum fading"
    else:
        stoch_score, stoch_signal = 15.0, f"StochRSI {stoch_rsi:.0f} — overbought momentum"

    # ── ATR (for dynamic stop/target) ─────────────────────────────────────────
    atr = _atr(highs, lows, closes)
    stop_price = round(latest - 2.0 * atr, 3)   # 2× ATR stop
    target_price = round(latest + 3.0 * atr, 3)  # 3× ATR target (1:1.5 R:R)

    # ── Composite ─────────────────────────────────────────────────────────────
    raw = (
        rsi_score * 0.22
        + macd_score * 0.20
        + bb_score * 0.18
        + cross_score * 0.15
        + vol_score * 0.10
        + stoch_score * 0.15
    ) * adx_multiplier

    composite = round(max(0.0, min(100.0, raw)), 2)

    signals = [rsi_signal, macd_signal, bb_signal, cross_signal, stoch_signal]
    if vol_score >= 70:
        signals.append(vol_signal)

    logger.debug(
        "%s tech: RSI=%.0f MACD=%.0f BB=%.0f Cross=%.0f Vol=%.0f Stoch=%.0f ADX=%.0f → %.1f",
        ticker, rsi_score, macd_score, bb_score, cross_score, vol_score, stoch_score, adx_val, composite,
    )

    return {
        "composite_score": composite,
        "rsi": rsi,
        "stoch_rsi": stoch_rsi,
        "macd_bullish": hist > 0,
        "bb_position_pct": round(bb_pct * 100, 1),
        "adx": round(adx_val, 1),
        "adx_desc": adx_desc,
        "atr": round(atr, 3),
        "signals": signals,
        "entry": round(latest, 3),
        "target": target_price,
        "stop": stop_price,
        "trend": cross_signal,
    }


def batch_score_technical(tickers: list) -> dict:
    return {t: score_technical(t) for t in tickers}
