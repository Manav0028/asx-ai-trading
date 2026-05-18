"""
Dynamic Risk Parameters
=======================
Replaces static percentages with per-stock, volatility-aware values.

Three improvements over the static defaults:

1. POSITION SIZING — ATR dollar-risk model
   Instead of Kelly (score only), size each trade so that hitting the stop
   costs a fixed % of capital (default 1.5%).  High-ATR stocks get fewer
   shares; low-ATR stocks get more — dollar risk is the same.
   Capped at MAX_POSITION_PCT and boosted/reduced by fundamental quality.

2. TRAILING STOP — ATR-based activation and distance
   Instead of fixed 5%/5% for every stock, the trail activates after
   1 × ATR and trails 1.5 × ATR below the peak.
   Volatile stocks get wider trails; quiet stocks get tighter ones.

3. STALE DAYS — ADX trend-strength adjustment
   Trending stocks (high ADX) deserve more patience.
   Choppy stocks (low ADX) should be exited sooner.

All three fall back gracefully to static defaults when ATR/ADX data
is unavailable (e.g. new listing with <14 days of price history).
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Tunable constants ────────────────────────────────────────────────────────

DOLLAR_RISK_PCT       = 0.015   # risk 1.5 % of portfolio capital per trade
ATR_STOP_MULT         = 2.0     # stop  = entry − (N × ATR)
ATR_TARGET_MULT       = 3.5     # target = entry + (M × ATR); ensures ~1.75 R:R
MIN_STOP_PCT          = 0.03    # never stop tighter than 3 %   (avoids noise exits)
MAX_STOP_PCT          = 0.12    # never risk more than 12 % per position
MIN_RR_RATIO          = 1.5     # enforce minimum 1.5 : 1 reward-to-risk
TRAIL_ACTIVATE_MULT   = 1.0     # start trailing after 1 × ATR gain
TRAIL_DISTANCE_MULT   = 1.5     # trail 1.5 × ATR below peak
TRAIL_MIN_PCT         = 0.02    # clamp trail activate / distance to ≥ 2 %
TRAIL_MAX_PCT         = 0.08    # clamp trail activate / distance to ≤ 8 %
STALE_DAYS_BASE       = 45      # default stale-exit threshold
STALE_ADX_STRONG      = 30      # ADX above this → trend present → more patience
STALE_ADX_WEAK        = 20      # ADX below this → sideways → exit sooner
STALE_DAYS_TREND      = 65      # stale days when trending
STALE_DAYS_SIDEWAYS   = 28      # stale days when sideways/choppy
# Fundamental quality multipliers on dollar-risk amount
QUAL_HIGH_THRESHOLD   = 75.0    # fundamental score ≥ this → +20 % risk budget
QUAL_LOW_THRESHOLD    = 55.0    # fundamental score < this → −20 % risk budget


# ── Position sizing ──────────────────────────────────────────────────────────

def compute_position_size(
    entry_price:        float,
    stop_price:         float,
    fundamental_score:  float = 50.0,
    regime_ok:          bool  = True,
    atr:                Optional[float] = None,
) -> float:
    """
    ATR dollar-risk position sizing.

    Algorithm
    ---------
    1. dollar_risk  = portfolio_capital × DOLLAR_RISK_PCT
    2. Adjust by fundamental quality (±20 %)
    3. Halve in RISK-OFF regime
    4. stop_distance = entry − stop
    5. shares       = dollar_risk / stop_distance
    6. position_aud = shares × entry
    7. Cap at MAX_POSITION_PCT of capital

    Falls back to half-Kelly when stop_distance ≤ 0 or no ATR data.
    """
    from config.settings import PORTFOLIO_CAPITAL, MAX_POSITION_PCT, STOP_LOSS_PCT

    max_position = PORTFOLIO_CAPITAL * MAX_POSITION_PCT

    stop_distance = entry_price - stop_price if (entry_price and stop_price) else 0

    if stop_distance <= 0 or not entry_price:
        # Fallback: half-Kelly with regime reduction
        from signals.kelly_sizer import compute_kelly_size
        _, pos = compute_kelly_size(65.0)          # use neutral score for fallback
        if not regime_ok:
            pos *= 0.5
        return round(min(pos, max_position), 2)

    # 1. Base dollar risk
    dollar_risk = PORTFOLIO_CAPITAL * DOLLAR_RISK_PCT

    # 2. Fundamental quality multiplier
    if fundamental_score >= QUAL_HIGH_THRESHOLD:
        dollar_risk *= 1.20    # quality business — tolerate slightly more risk
    elif fundamental_score < QUAL_LOW_THRESHOLD:
        dollar_risk *= 0.80    # weaker business — reduce risk

    # 3. Regime
    if not regime_ok:
        dollar_risk *= 0.50

    # 4–6. Dollar-risk sizing
    shares       = dollar_risk / stop_distance
    position_aud = shares * entry_price

    # 7. Cap
    position_aud = min(position_aud, max_position)

    logger.debug(
        "Dollar-risk sizing: entry=%.3f stop=%.3f distance=%.3f "
        "risk=$%.0f → %.0f shares → $%.0f",
        entry_price, stop_price, stop_distance,
        dollar_risk, shares, position_aud,
    )

    return round(position_aud, 2)


# ── Stop / target ────────────────────────────────────────────────────────────

def compute_stop_target(
    entry_price: float,
    atr:         Optional[float],
    regime_ok:   bool = True,
) -> Dict:
    """
    Return ATR-based stop_loss_price and target_price.

    In RISK-OFF regime the target multiplier is tightened (take profits
    sooner — market environment is unfavourable for holding).

    Falls back to −7 % / +10 % when ATR is unavailable.
    """
    from config.settings import STOP_LOSS_PCT

    if atr and entry_price and atr > 0:
        # --- stop ---
        raw_stop_pct = (ATR_STOP_MULT * atr) / entry_price
        stop_pct     = max(MIN_STOP_PCT, min(MAX_STOP_PCT, raw_stop_pct))
        stop_price   = round(entry_price * (1 - stop_pct), 4)

        # --- target (tighter in risk-off) ---
        target_mult     = ATR_TARGET_MULT * (0.80 if not regime_ok else 1.0)
        raw_target_pct  = (target_mult * atr) / entry_price
        min_target_pct  = stop_pct * MIN_RR_RATIO
        target_pct      = max(raw_target_pct, min_target_pct)
        target_price    = round(entry_price * (1 + target_pct), 4)

        reward_risk = target_pct / stop_pct if stop_pct else 0

        return {
            "stop_loss_price": stop_price,
            "target_price":    target_price,
            "stop_pct":        round(stop_pct  * 100, 2),
            "target_pct":      round(target_pct * 100, 2),
            "reward_risk":     round(reward_risk, 2),
            "method":          "atr",
        }

    # Fallback
    stop_price   = round(entry_price * (1 - STOP_LOSS_PCT), 4) if entry_price else None
    target_price = round(entry_price * 1.10, 4) if entry_price else None
    rr           = 10.0 / (STOP_LOSS_PCT * 100) if STOP_LOSS_PCT else 0

    return {
        "stop_loss_price": stop_price,
        "target_price":    target_price,
        "stop_pct":        round(STOP_LOSS_PCT * 100, 2),
        "target_pct":      10.0,
        "reward_risk":     round(rr, 2),
        "method":          "static_fallback",
    }


# ── Trailing stop ────────────────────────────────────────────────────────────

def compute_trail_params(
    entry_price: float,
    atr:         Optional[float],
) -> Dict:
    """
    Return ATR-based trailing stop parameters.

    activate_pct  — how much price must rise (from entry) before trailing starts
    distance_pct  — how far the stop trails below the running peak

    Both clamped to [TRAIL_MIN_PCT, TRAIL_MAX_PCT] so very quiet or very
    volatile stocks stay within reasonable bounds.

    Falls back to 5 % / 5 % static defaults.
    """
    if atr and entry_price and atr > 0:
        activate_pct = (TRAIL_ACTIVATE_MULT * atr) / entry_price
        distance_pct = (TRAIL_DISTANCE_MULT * atr) / entry_price

        activate_pct = max(TRAIL_MIN_PCT, min(TRAIL_MAX_PCT, activate_pct))
        distance_pct = max(TRAIL_MIN_PCT, min(TRAIL_MAX_PCT, distance_pct))

        return {
            "trail_activate_pct": round(activate_pct, 4),
            "trail_distance_pct": round(distance_pct, 4),
            "method": "atr",
        }

    return {
        "trail_activate_pct": 0.05,
        "trail_distance_pct": 0.05,
        "method": "static_fallback",
    }


# ── Stale-exit days ──────────────────────────────────────────────────────────

def compute_stale_days(adx: Optional[float]) -> int:
    """
    ADX-adjusted stale-exit threshold.

    Strong trend  (ADX ≥ 30) → 65 days  — give trending stocks more room
    Normal        (20 ≤ ADX < 30) → 45 days (default)
    Sideways/weak (ADX < 20)  → 28 days  — exit choppy stocks sooner

    Falls back to base 45 when ADX unavailable.
    """
    if adx is None:
        return STALE_DAYS_BASE
    if adx >= STALE_ADX_STRONG:
        return STALE_DAYS_TREND
    if adx < STALE_ADX_WEAK:
        return STALE_DAYS_SIDEWAYS
    return STALE_DAYS_BASE


# ── Convenience wrapper ───────────────────────────────────────────────────────

def get_all_risk_params(
    ticker:             str,
    entry_price:        float,
    atr:                Optional[float],
    adx:                Optional[float],
    composite_score:    float,
    fundamental_score:  float,
    regime_ok:          bool,
) -> Dict:
    """
    Single call that returns all dynamic risk parameters for a signal.

    Used by signals/aggregator.py when computing a new signal.
    """
    st = compute_stop_target(entry_price, atr, regime_ok)
    tr = compute_trail_params(entry_price, atr)
    pos = compute_position_size(
        entry_price,
        st["stop_loss_price"],
        fundamental_score,
        regime_ok,
        atr,
    )
    stale = compute_stale_days(adx)

    result = {
        **st,
        **tr,
        "position_size_aud": pos,
        "stale_days":        stale,
        "atr":               round(atr, 4) if atr else None,
        "adx":               round(adx, 1) if adx else None,
    }

    logger.info(
        "%s dynamic params: stop=%.3f(%.1f%%) target=%.3f(%.1f%%) "
        "RR=%.1f pos=$%.0f trail_act=%.1f%% trail_dist=%.1f%% stale=%dd [%s]",
        ticker,
        st["stop_loss_price"], st["stop_pct"],
        st["target_price"],    st["target_pct"],
        st["reward_risk"],
        pos,
        tr["trail_activate_pct"] * 100,
        tr["trail_distance_pct"] * 100,
        stale,
        st["method"],
    )

    return result
