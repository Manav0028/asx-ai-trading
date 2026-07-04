"""
Smart Money Concepts / ICT — order blocks, fair value gaps, liquidity sweeps,
break of structure / change of character, and the premium/discount zone gate.
All purely OHLCV-derived (see plan doc's research section for why these were
added and why order flow/footprint was deferred instead). Unlike the stateless
candlestick patterns, these need running state (active order blocks/FVGs,
prevailing structure direction), so each is a small tracker class rather than
a pure fires(ind, i) function — but every detection still returns the same
{"confidence", "reason", "direction", "pattern_name"} shape.
"""
from collections import deque
from typing import Dict, List, Optional, Tuple

from engine.swing_detector import SwingPoint

DISPLACEMENT_ATR_MULT = 1.5
MAX_ACTIVE_ZONES = 20


class OrderBlockTracker:
    """Last opposite-color candle before a displacement move; a retest of that
    candle's body range after the move fires bullish_ob_retest/bearish_ob_retest."""

    def __init__(self):
        self.bullish_obs: deque = deque(maxlen=MAX_ACTIVE_ZONES)
        self.bearish_obs: deque = deque(maxlen=MAX_ACTIVE_ZONES)

    def update(self, ind: Dict, i: int) -> Optional[Dict]:
        if i < 1:
            return None
        atr = ind["atr"][i]
        candle_range = ind["highs"][i] - ind["lows"][i]
        if atr and candle_range >= DISPLACEMENT_ATR_MULT * atr:
            body_i = ind["closes"][i] - ind["opens"][i]
            body_prev = ind["closes"][i - 1] - ind["opens"][i - 1]
            if body_i > 0 and body_prev < 0:
                self.bullish_obs.append({
                    "low": min(ind["opens"][i - 1], ind["closes"][i - 1]),
                    "high": max(ind["opens"][i - 1], ind["closes"][i - 1]),
                    "formed_at": i,
                })
            elif body_i < 0 and body_prev > 0:
                self.bearish_obs.append({
                    "low": min(ind["opens"][i - 1], ind["closes"][i - 1]),
                    "high": max(ind["opens"][i - 1], ind["closes"][i - 1]),
                    "formed_at": i,
                })

        low_now, high_now = ind["lows"][i], ind["highs"][i]
        for ob in self.bullish_obs:
            if ob["formed_at"] < i and low_now <= ob["high"] and low_now >= ob["low"]:
                return {"pattern_name": "bullish_ob_retest", "direction": "long",
                        "confidence": 0.65, "reason": "retest of bullish order block"}
        for ob in self.bearish_obs:
            if ob["formed_at"] < i and high_now >= ob["low"] and high_now <= ob["high"]:
                return {"pattern_name": "bearish_ob_retest", "direction": "short",
                        "confidence": 0.65, "reason": "retest of bearish order block"}
        return None


class FVGTracker:
    """3-candle imbalance where candle 1's high/low doesn't overlap candle 3's
    low/high; fires fvg_fill when price re-enters that gap. Research cites
    price revisits FVGs roughly 70% of the time."""

    def __init__(self):
        self.bullish_fvgs: deque = deque(maxlen=MAX_ACTIVE_ZONES)
        self.bearish_fvgs: deque = deque(maxlen=MAX_ACTIVE_ZONES)

    def update(self, ind: Dict, i: int) -> Optional[Dict]:
        if i < 2:
            return None
        if ind["highs"][i - 2] < ind["lows"][i]:
            self.bullish_fvgs.append({"low": ind["highs"][i - 2], "high": ind["lows"][i], "formed_at": i})
        if ind["lows"][i - 2] > ind["highs"][i]:
            self.bearish_fvgs.append({"low": ind["highs"][i], "high": ind["lows"][i - 2], "formed_at": i})

        for gap in self.bullish_fvgs:
            if gap["formed_at"] < i and ind["lows"][i] <= gap["high"] and ind["lows"][i] >= gap["low"]:
                return {"pattern_name": "fvg_fill_bullish", "direction": "long",
                        "confidence": 0.6, "reason": "price filled a bullish fair value gap"}
        for gap in self.bearish_fvgs:
            if gap["formed_at"] < i and ind["highs"][i] >= gap["low"] and ind["highs"][i] <= gap["high"]:
                return {"pattern_name": "fvg_fill_bearish", "direction": "short",
                        "confidence": 0.6, "reason": "price filled a bearish fair value gap"}
        return None


class LiquiditySweepDetector:
    """Price briefly pierces a prior confirmed swing high/low (where stop
    orders cluster) then closes back inside the same bar — fires a reversal
    signal back toward the range."""

    def check(self, ind: Dict, i: int, swings: List[SwingPoint]) -> Optional[Dict]:
        last_high = next((s for s in reversed(swings) if s.kind == "high"), None)
        last_low = next((s for s in reversed(swings) if s.kind == "low"), None)

        if last_high and ind["highs"][i] > last_high.price and ind["closes"][i] < last_high.price:
            return {"pattern_name": "liquidity_sweep_reversal", "direction": "short",
                    "confidence": 0.7, "reason": "swept liquidity above prior swing high, reversing down"}
        if last_low and ind["lows"][i] < last_low.price and ind["closes"][i] > last_low.price:
            return {"pattern_name": "liquidity_sweep_reversal", "direction": "long",
                    "confidence": 0.7, "reason": "swept liquidity below prior swing low, reversing up"}
        return None


class StructureTracker:
    """BOS = two consecutive closes beyond the last confirmed swing in the
    *prevailing* trend direction (continuation). CHoCH = the first opposite-
    direction structure break (early reversal warning)."""

    def __init__(self):
        self.trend: Optional[str] = None   # 'up' | 'down' | None

    def update(self, ind: Dict, i: int, swings: List[SwingPoint]) -> Optional[Dict]:
        if i < 1:
            return None
        last_high = next((s for s in reversed(swings) if s.kind == "high"), None)
        last_low = next((s for s in reversed(swings) if s.kind == "low"), None)

        if last_high and ind["closes"][i] > last_high.price and ind["closes"][i - 1] > last_high.price:
            reversal = self.trend == "down"
            self.trend = "up"
            if reversal:
                return {"pattern_name": "change_of_character", "direction": "long",
                        "confidence": 0.65, "reason": "CHoCH: bullish break reverses prior downtrend"}
            return {"pattern_name": "break_of_structure", "direction": "long",
                    "confidence": 0.55, "reason": "BOS: bullish continuation confirmed"}

        if last_low and ind["closes"][i] < last_low.price and ind["closes"][i - 1] < last_low.price:
            reversal = self.trend == "up"
            self.trend = "down"
            if reversal:
                return {"pattern_name": "change_of_character", "direction": "short",
                        "confidence": 0.65, "reason": "CHoCH: bearish break reverses prior uptrend"}
            return {"pattern_name": "break_of_structure", "direction": "short",
                    "confidence": 0.55, "reason": "BOS: bearish continuation confirmed"}
        return None


def zone_for_price(price: float, dealing_range: Optional[Tuple[float, float]]) -> str:
    """Premium/discount/equilibrium position within the current dealing range
    (most recent significant swing-low-to-swing-high leg)."""
    if not dealing_range:
        return "equilibrium"
    low, high = dealing_range
    if high <= low:
        return "equilibrium"
    pct = (price - low) / (high - low)
    if pct <= 0.25:
        return "discount"
    if pct >= 0.75:
        return "premium"
    return "equilibrium"


def zone_quality(direction: str, zone: str) -> float:
    """Feeds the smc_zone_quality term of the composite score (plan §7)."""
    if zone == "equilibrium":
        return 50.0
    favorable = (direction == "long" and zone == "discount") or (direction == "short" and zone == "premium")
    return 100.0 if favorable else 0.0


class SMCEngine:
    """Per-ticker/timeframe bundle of all SMC trackers, evaluated once per
    closed bar alongside the candlestick/chart-pattern families."""

    def __init__(self):
        self.order_blocks = OrderBlockTracker()
        self.fvg = FVGTracker()
        self.sweeps = LiquiditySweepDetector()
        self.structure = StructureTracker()

    def evaluate(self, ind: Dict, i: int, swings: List[SwingPoint]) -> List[Dict]:
        signals = []
        for result in (
            self.order_blocks.update(ind, i),
            self.fvg.update(ind, i),
            self.sweeps.check(ind, i, swings),
            self.structure.update(ind, i, swings),
        ):
            if result:
                result["pattern_type"] = "smc"
                signals.append(result)
        return signals
