"""
Chart-pattern family (Phase 2) — swing-point-based patterns with no daily-bar
equivalent in the existing EOD system: double top/bottom, head & shoulders,
triangles, flags. All consume the same SwingPoint series as engine/smc.py
(engine/swing_detector.py), so this is purely additive to the pipeline —
see engine/signal_engine.py's _evaluate_patterns() for the wiring.
"""
from typing import Dict, List, Optional

from engine.swing_detector import SwingPoint

NECKLINE_TOLERANCE_PCT = 0.005   # similarity tolerance for matching swing peaks/troughs
FLAG_LOOKBACK = 10


class DoubleTopBottomDetector:
    """Two similar-height swings + a neckline break (the low/high between them)."""

    def check(self, ind: Dict, i: int, swings: List[SwingPoint]) -> Optional[Dict]:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        price = ind["closes"][i]

        if len(highs) >= 2 and lows:
            h1, h2 = highs[-2], highs[-1]
            similar = abs(h1.price - h2.price) <= NECKLINE_TOLERANCE_PCT * h1.price
            between = [l for l in lows if h1.index < l.index < h2.index]
            if similar and between:
                neckline = min(l.price for l in between)
                if price < neckline:
                    return {"pattern_name": "double_top_breakdown", "direction": "short",
                            "confidence": 0.65, "reason": "double top neckline break",
                            "pattern_type": "chart"}

        if len(lows) >= 2 and highs:
            l1, l2 = lows[-2], lows[-1]
            similar = abs(l1.price - l2.price) <= NECKLINE_TOLERANCE_PCT * l1.price
            between = [h for h in highs if l1.index < h.index < l2.index]
            if similar and between:
                neckline = max(h.price for h in between)
                if price > neckline:
                    return {"pattern_name": "double_bottom_breakout", "direction": "long",
                            "confidence": 0.65, "reason": "double bottom neckline break",
                            "pattern_type": "chart"}
        return None


class HeadAndShouldersDetector:
    """Three swings, middle highest/lowest (the head), shoulders roughly equal,
    confirmed on a break of the neckline connecting the intervening troughs/peaks."""

    def check(self, ind: Dict, i: int, swings: List[SwingPoint]) -> Optional[Dict]:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        price = ind["closes"][i]

        if len(highs) >= 3 and lows:
            left, head, right = highs[-3], highs[-2], highs[-1]
            is_hs = (head.price > left.price and head.price > right.price
                     and abs(left.price - right.price) <= 0.01 * head.price)
            between = [l for l in lows if left.index < l.index < right.index]
            if is_hs and between:
                neckline = min(l.price for l in between)
                if price < neckline:
                    return {"pattern_name": "head_shoulders_breakdown", "direction": "short",
                            "confidence": 0.7, "reason": "head & shoulders neckline break",
                            "pattern_type": "chart"}

        if len(lows) >= 3 and highs:
            left, head, right = lows[-3], lows[-2], lows[-1]
            is_inv = (head.price < left.price and head.price < right.price
                      and abs(left.price - right.price) <= 0.01 * abs(head.price))
            between = [h for h in highs if left.index < h.index < right.index]
            if is_inv and between:
                neckline = max(h.price for h in between)
                if price > neckline:
                    return {"pattern_name": "inv_head_shoulders_breakout", "direction": "long",
                            "confidence": 0.7, "reason": "inverse head & shoulders neckline break",
                            "pattern_type": "chart"}
        return None


class TriangleDetector:
    """Linear-regression trendline fit through recent swing highs/lows;
    fires on a volume-confirmed breakout beyond either converging trendline."""

    @staticmethod
    def _slope_intercept(points: List[SwingPoint]):
        xs = [p.index for p in points]
        ys = [p.price for p in points]
        n = len(xs)
        mean_x, mean_y = sum(xs) / n, sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = sum((x - mean_x) ** 2 for x in xs) or 1e-9
        slope = num / den
        return slope, mean_y - slope * mean_x

    def check(self, ind: Dict, i: int, swings: List[SwingPoint]) -> Optional[Dict]:
        highs = [s for s in swings if s.kind == "high"][-4:]
        lows = [s for s in swings if s.kind == "low"][-4:]
        if len(highs) < 3 or len(lows) < 3:
            return None

        slope_high, intercept_high = self._slope_intercept(highs)
        slope_low, intercept_low = self._slope_intercept(lows)
        converging = (
            (slope_high < 0 < slope_low)
            or (abs(slope_high) < abs(slope_low) * 0.3)
            or (abs(slope_low) < abs(slope_high) * 0.3)
        )
        vol_ok = ind["volumes"][i] >= 1.2 * ind["vol_avg_20"][i]
        if not (converging and vol_ok):
            return None

        proj_high = slope_high * i + intercept_high
        proj_low = slope_low * i + intercept_low
        price = ind["closes"][i]
        if price > proj_high:
            return {"pattern_name": "triangle_breakout", "direction": "long",
                    "confidence": 0.6, "reason": "triangle breakout above upper trendline on volume",
                    "pattern_type": "chart"}
        if price < proj_low:
            return {"pattern_name": "triangle_breakdown", "direction": "short",
                    "confidence": 0.6, "reason": "triangle breakdown below lower trendline on volume",
                    "pattern_type": "chart"}
        return None


class FlagDetector:
    """Sharp directional impulse move followed by a tight, narrowing-range
    consolidation; fires on a volume-confirmed breakout continuing the impulse."""

    def check(self, ind: Dict, i: int) -> Optional[Dict]:
        if i < FLAG_LOOKBACK + 5:
            return None
        impulse_start, impulse_end = i - FLAG_LOOKBACK - 5, i - FLAG_LOOKBACK
        impulse_move = ind["closes"][impulse_end] - ind["closes"][impulse_start]
        atr = ind["atr"][i] or 1e-9
        strong_impulse = abs(impulse_move) >= 3 * atr

        recent_ranges = [ind["highs"][j] - ind["lows"][j] for j in range(i - FLAG_LOOKBACK, i + 1)]
        narrowing = recent_ranges[0] > 0 and recent_ranges[-1] < recent_ranges[0] * 0.7
        vol_ok = ind["volumes"][i] >= 1.3 * ind["vol_avg_20"][i]
        if not (strong_impulse and narrowing and vol_ok):
            return None

        direction = "long" if impulse_move > 0 else "short"
        window_highs = ind["highs"][i - FLAG_LOOKBACK:i]
        window_lows = ind["lows"][i - FLAG_LOOKBACK:i]
        broke_out = (
            ind["closes"][i] > max(window_highs) if direction == "long"
            else ind["closes"][i] < min(window_lows)
        )
        if broke_out:
            name = "flag_breakout" if direction == "long" else "flag_breakdown"
            return {"pattern_name": name, "direction": direction, "confidence": 0.62,
                    "reason": f"flag continuation {direction} breakout after impulse move",
                    "pattern_type": "chart"}
        return None


class ChartPatternEngine:
    def __init__(self):
        self.double_detector = DoubleTopBottomDetector()
        self.hs_detector = HeadAndShouldersDetector()
        self.triangle_detector = TriangleDetector()
        self.flag_detector = FlagDetector()

    def evaluate(self, ind: Dict, i: int, swings: List[SwingPoint]) -> List[Dict]:
        signals = []
        for result in (
            self.double_detector.check(ind, i, swings),
            self.hs_detector.check(ind, i, swings),
            self.triangle_detector.check(ind, i, swings),
            self.flag_detector.check(ind, i),
        ):
            if result:
                signals.append(result)
        return signals
