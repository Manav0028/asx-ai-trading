"""
Strategy Engine — Chart-Reading (Price-Action) Strategies
The candlestick/price-action patterns with the strongest documented edges
(Bulkowski's pattern statistics, Connors' quantified candle studies), long AND
short. Like every other strategy, a pattern only trades a ticker after that
ticker's own history validates it in-sample and out-of-sample.
"""
from typing import Dict, Optional

import numpy as np

from strategies.base import Strategy


def _body(ind, i) -> float:
    return ind["closes"][i] - ind["opens"][i]


def _range(ind, i) -> float:
    return max(ind["highs"][i] - ind["lows"][i], 1e-9)


class BullishEngulfing(Strategy):
    """Buy a bullish engulfing candle after a multi-day decline — one of the
    highest-ranked bullish reversal patterns in Bulkowski's statistics."""
    name = "bull_engulf"
    description = "Bullish engulfing after a 3-day fall with RSI<45"
    direction = "long"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_days = 15

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 5:
            return None
        fell = ind["closes"][i - 1] < ind["closes"][i - 4]          # prior decline
        prev_red = _body(ind, i - 1) < 0
        now_green = _body(ind, i) > 0
        engulfs = (ind["opens"][i] <= ind["closes"][i - 1]
                   and ind["closes"][i] >= ind["opens"][i - 1])
        washed = ind["rsi"][i] < 45
        if fell and prev_red and now_green and engulfs and washed:
            strength = abs(_body(ind, i)) / _range(ind, i)
            return {"confidence": round(min(1.0, 0.5 + strength / 2), 2),
                    "reason": f"bullish engulfing after decline (RSI {ind['rsi'][i]:.0f})"}
        return None


class HammerAtSupport(Strategy):
    """Buy a hammer candle printed at the 20-day low — sellers exhausted,
    long lower wick shows the dip was bought aggressively."""
    name = "hammer"
    description = "Hammer (long lower wick, close in top third) at the 20-day low"
    direction = "long"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_days = 15

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 25:
            return None
        rng = _range(ind, i)
        lower_wick = min(ind["opens"][i], ind["closes"][i]) - ind["lows"][i]
        close_pos = (ind["closes"][i] - ind["lows"][i]) / rng
        at_low = ind["lows"][i] <= ind["low_20"][i] * 1.01
        hammer = lower_wick >= 2 * abs(_body(ind, i)) and close_pos >= 0.66
        if at_low and hammer:
            return {"confidence": round(min(1.0, 0.5 + lower_wick / rng), 2),
                    "reason": "hammer rejection at 20-day support"}
        return None


class InsideBarBreakout(Strategy):
    """Buy the upside break of an inside-bar consolidation — volatility
    contraction resolving with volume is a classic continuation pattern."""
    name = "inside_break"
    description = "Inside bar then breakout above the mother bar high on volume"
    direction = "long"
    stop_mult = 1.8
    target_mult = 3.5
    max_hold_days = 20

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 25:
            return None
        inside = (ind["highs"][i - 1] <= ind["highs"][i - 2]
                  and ind["lows"][i - 1] >= ind["lows"][i - 2])
        breaks_up = ind["closes"][i] > ind["highs"][i - 2]
        vol_ok = ind["volumes"][i] >= 1.2 * ind["vol_avg_20"][i]
        uptrend = ind["ema20"][i] > ind["ema50"][i]
        if inside and breaks_up and vol_ok and uptrend:
            return {"confidence": 0.65,
                    "reason": "inside-bar squeeze broke out upward on volume"}
        return None


class BearishEngulfing(Strategy):
    """Short a bearish engulfing candle after a rally — buyers trapped at the
    top, the mirror image of the bullish engulfing edge."""
    name = "bear_engulf"
    description = "SHORT: bearish engulfing after a 3-day rally with RSI>60"
    direction = "short"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_days = 15

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 5:
            return None
        rose = ind["closes"][i - 1] > ind["closes"][i - 4]
        prev_green = _body(ind, i - 1) > 0
        now_red = _body(ind, i) < 0
        engulfs = (ind["opens"][i] >= ind["closes"][i - 1]
                   and ind["closes"][i] <= ind["opens"][i - 1])
        stretched = ind["rsi"][i] > 60
        if rose and prev_green and now_red and engulfs and stretched:
            strength = abs(_body(ind, i)) / _range(ind, i)
            return {"confidence": round(min(1.0, 0.5 + strength / 2), 2),
                    "reason": f"bearish engulfing after rally (RSI {ind['rsi'][i]:.0f})"}
        return None


class ShootingStar(Strategy):
    """Short a shooting star at the 20-day high — a failed thrust with a long
    upper wick shows distribution into strength."""
    name = "shooting_star"
    description = "SHORT: shooting star (long upper wick) at the 20-day high"
    direction = "short"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_days = 15

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 25:
            return None
        rng = _range(ind, i)
        upper_wick = ind["highs"][i] - max(ind["opens"][i], ind["closes"][i])
        close_pos = (ind["closes"][i] - ind["lows"][i]) / rng
        at_high = ind["highs"][i] >= ind["high_20"][i] * 0.99
        star = upper_wick >= 2 * abs(_body(ind, i)) and close_pos <= 0.34
        if at_high and star:
            return {"confidence": round(min(1.0, 0.5 + upper_wick / rng), 2),
                    "reason": "shooting star rejection at 20-day high"}
        return None


class Breakdown(Strategy):
    """Short a close below the 20-day low on heavy volume — the short side of
    the Donchian breakout, strongest in downtrends."""
    name = "breakdown"
    description = "SHORT: close below the 20-day low on ≥1.5x volume in a downtrend"
    direction = "short"
    stop_mult = 2.0
    target_mult = 4.0
    max_hold_days = 30

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 60:
            return None
        new_low = ind["closes"][i] < ind["low_20"][i]
        vol_ratio = ind["volumes"][i] / (ind["vol_avg_20"][i] + 1e-9)
        downtrend = ind["ema20"][i] < ind["ema50"][i]
        if new_low and vol_ratio >= 1.5 and downtrend:
            return {"confidence": round(min(1.0, 0.5 + vol_ratio / 6), 2),
                    "reason": f"20-day low breakdown on {vol_ratio:.1f}x volume"}
        return None


PATTERN_STRATEGIES = [
    BullishEngulfing(),
    HammerAtSupport(),
    InsideBarBreakout(),
    BearishEngulfing(),
    ShootingStar(),
    Breakdown(),
]
