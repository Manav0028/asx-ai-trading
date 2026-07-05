"""
ATR-based stop/target/trailing-stop — formula shape cloned from
signals/risk_params.py and execution/stop_loss.py, with new RTC_-prefixed
clamp bounds tightened for 1-minute-bar ATR (intraday scale is naturally
tighter than the EOD system's daily-bar ATR scale). Pure functions, no DB,
no side effects — independently testable.
"""
from typing import Dict

from settings import (
    RTC_MAX_STOP_PCT, RTC_MIN_RR_RATIO, RTC_MIN_STOP_PCT,
    RTC_TRAIL_ACTIVATE_MULT, RTC_TRAIL_DISTANCE_MULT, RTC_TRAIL_MAX_PCT, RTC_TRAIL_MIN_PCT,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_stop_target(entry_price: float, atr: float, direction: str,
                         stop_mult: float, target_mult: float) -> Dict:
    atr = atr or entry_price * 0.01  # fallback if ATR isn't warmed up yet
    stop_pct = _clamp((stop_mult * atr) / entry_price, RTC_MIN_STOP_PCT, RTC_MAX_STOP_PCT)
    target_pct = max((target_mult * atr) / entry_price, stop_pct * RTC_MIN_RR_RATIO)
    if direction == "long":
        stop_price = entry_price * (1 - stop_pct)
        target_price = entry_price * (1 + target_pct)
    else:
        stop_price = entry_price * (1 + stop_pct)
        target_price = entry_price * (1 - target_pct)
    return {
        "stop_price": stop_price, "target_price": target_price,
        "stop_pct": stop_pct, "target_pct": target_pct,
    }


def compute_trail_params(entry_price: float, atr: float) -> Dict:
    atr = atr or entry_price * 0.01
    activate_pct = _clamp((RTC_TRAIL_ACTIVATE_MULT * atr) / entry_price, RTC_TRAIL_MIN_PCT, RTC_TRAIL_MAX_PCT)
    distance_pct = _clamp((RTC_TRAIL_DISTANCE_MULT * atr) / entry_price, RTC_TRAIL_MIN_PCT, RTC_TRAIL_MAX_PCT)
    return {"activate_pct": activate_pct, "distance_pct": distance_pct}


def update_trailing_stop(direction: str, entry_price: float, current_price: float,
                          peak_price: float, current_stop: float,
                          activate_pct: float, distance_pct: float) -> Dict:
    """`peak_price` tracks the best price seen since entry — the running high
    for longs, the running low for shorts. Returns {"new_stop", "new_peak",
    "activated"}. The stop only ever ratchets favorably, never loosens."""
    if direction == "long":
        gain_pct = (current_price - entry_price) / entry_price
        new_peak = max(peak_price, current_price)
        if gain_pct >= activate_pct:
            candidate_stop = new_peak * (1 - distance_pct)
            return {"new_stop": max(current_stop, candidate_stop), "new_peak": new_peak, "activated": True}
        return {"new_stop": current_stop, "new_peak": new_peak, "activated": False}
    else:
        gain_pct = (entry_price - current_price) / entry_price
        new_peak = min(peak_price, current_price)
        if gain_pct >= activate_pct:
            candidate_stop = new_peak * (1 + distance_pct)
            return {"new_stop": min(current_stop, candidate_stop), "new_peak": new_peak, "activated": True}
        return {"new_stop": current_stop, "new_peak": new_peak, "activated": False}
