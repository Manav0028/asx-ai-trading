"""
Support/resistance clustering (from confirmed swing points) + Fibonacci
retracement levels. Both are pure reference layers consumed by the composite
score's proximity checks and by Claude's context — neither fires a signal on
its own.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from engine.swing_detector import SwingPoint

FIB_RATIOS = [0.236, 0.382, 0.5, 0.618, 0.786]


@dataclass
class Level:
    price: float
    kind: str        # 'support' | 'resistance' (assigned from the swing kind: low->support, high->resistance)
    touches: int = 1


class LevelTracker:
    def __init__(self, atr_tolerance_mult: float = 0.3):
        self.atr_tolerance_mult = atr_tolerance_mult
        self.levels: List[Level] = []

    def rebuild(self, swings: List[SwingPoint], atr: float) -> List[Level]:
        tolerance = self.atr_tolerance_mult * atr if atr else 0.0
        clusters: List[Dict] = []
        for sp in swings:
            kind = "support" if sp.kind == "low" else "resistance"
            match = next((c for c in clusters if c["kind"] == kind and abs(c["price"] - sp.price) <= tolerance), None)
            if match:
                new_touches = match["touches"] + 1
                match["price"] = (match["price"] * match["touches"] + sp.price) / new_touches
                match["touches"] = new_touches
            else:
                clusters.append({"price": sp.price, "kind": kind, "touches": 1})
        self.levels = [Level(**c) for c in clusters]
        self.levels.sort(key=lambda l: -l.touches)
        return self.levels

    def nearest(self, price: float, kind: Optional[str] = None) -> Optional[Level]:
        candidates = [l for l in self.levels if kind is None or l.kind == kind]
        if not candidates:
            return None
        return min(candidates, key=lambda l: abs(l.price - price))

    @staticmethod
    def fibonacci_retracement(swing_low: float, swing_high: float, move_direction: str) -> Dict[str, float]:
        """move_direction: 'up' (low->high, retracement levels below the high)
        or 'down' (high->low, retracement levels above the low)."""
        diff = swing_high - swing_low
        if move_direction == "up":
            return {f"fib_{int(r * 1000)}": swing_high - diff * r for r in FIB_RATIOS}
        return {f"fib_{int(r * 1000)}": swing_low + diff * r for r in FIB_RATIOS}
