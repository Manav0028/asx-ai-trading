"""
Position sizing — dollar-risk model scaled by the firing signal's own
composite score (0.5x-1.5x by default, per the plan doc's confirmed decision:
sizing is driven by the CURRENT signal's conviction, not a per-ticker
historical win-rate). Formula shape cloned from signals/risk_params.py, with
a new isolated capital pool — not imported, no dependency on the EOD system.
Pure functions, no DB, no side effects — independently testable.
"""
from typing import Dict

from settings import (
    RTC_BASE_RISK_PCT, RTC_CAPITAL_POOL, RTC_MAX_POSITION_PCT,
    RTC_SCORE_MULT_CEIL, RTC_SCORE_MULT_FLOOR, RTC_SIGNAL_THRESHOLD,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def score_multiplier(composite_score: float) -> float:
    """Linear interpolation: composite == RTC_SIGNAL_THRESHOLD -> floor,
    composite == 100 -> ceiling, clamped outside that range."""
    span = 100 - RTC_SIGNAL_THRESHOLD
    progress = (composite_score - RTC_SIGNAL_THRESHOLD) / span if span else 0.0
    progress = _clamp(progress, 0.0, 1.0)
    return RTC_SCORE_MULT_FLOOR + (RTC_SCORE_MULT_CEIL - RTC_SCORE_MULT_FLOOR) * progress


def compute_position(entry_price: float, stop_price: float, composite_score: float) -> Dict:
    multiplier = score_multiplier(composite_score)
    dollar_risk = RTC_CAPITAL_POOL * RTC_BASE_RISK_PCT * multiplier
    stop_distance = abs(entry_price - stop_price)
    shares = dollar_risk / stop_distance if stop_distance else 0.0
    position_value = min(shares * entry_price, RTC_CAPITAL_POOL * RTC_MAX_POSITION_PCT)
    if entry_price:
        shares = position_value / entry_price  # re-derive if the cap clipped it
    return {
        "shares": shares,
        "position_value": position_value,
        "dollar_risk": dollar_risk,
        "multiplier": multiplier,
    }
