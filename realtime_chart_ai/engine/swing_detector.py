"""
Swing-point (fractal) detection — classic 5-bar William's fractal. A bar is a
confirmed swing high/low once 2 bars on each side confirm it, which means an
unavoidable ~2-bar confirmation lag versus the live tip of the chart (true of
any live system, not a shortcut taken here). Feeds engine/levels.py (S/R +
Fibonacci) and engine/smc.py (order blocks, FVG, sweeps, BOS/CHoCH).
"""
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

MAXLEN_SWINGS = 50


@dataclass
class SwingPoint:
    index: int          # index into the ind arrays at time of confirmation
    ts: datetime
    price: float
    kind: str           # 'high' | 'low'


class SwingDetector:
    def __init__(self):
        self.swings: deque = deque(maxlen=MAXLEN_SWINGS)
        self._last_confirmed_index = -1

    def update(self, ind: Dict) -> List[SwingPoint]:
        """Call after every bar close. Returns newly confirmed swing points
        (usually 0 or 1, occasionally empty for many bars in a row)."""
        highs, lows, timestamps = ind["highs"], ind["lows"], ind["timestamps"]
        n = len(highs)
        center = n - 3   # need 2 bars of confirmation after the candidate bar
        if center < 2 or center <= self._last_confirmed_index:
            return []

        found = []
        left_highs, right_highs = highs[center - 2:center], highs[center + 1:center + 3]
        left_lows, right_lows = lows[center - 2:center], lows[center + 1:center + 3]

        if highs[center] > max(left_highs) and highs[center] > max(right_highs):
            sp = SwingPoint(center, timestamps[center], highs[center], "high")
            self.swings.append(sp)
            found.append(sp)

        if lows[center] < min(left_lows) and lows[center] < min(right_lows):
            sp = SwingPoint(center, timestamps[center], lows[center], "low")
            self.swings.append(sp)
            found.append(sp)

        self._last_confirmed_index = center
        return found

    def last_swing(self, kind: Optional[str] = None) -> Optional[SwingPoint]:
        for sp in reversed(self.swings):
            if kind is None or sp.kind == kind:
                return sp
        return None

    def dealing_range(self):
        """Most recent significant swing-low-to-swing-high leg, for the
        premium/discount zone gate in engine/smc.py. Returns (low, high) or None."""
        last_low = self.last_swing("low")
        last_high = self.last_swing("high")
        if last_low is None or last_high is None:
            return None
        return (min(last_low.price, last_high.price), max(last_low.price, last_high.price))
