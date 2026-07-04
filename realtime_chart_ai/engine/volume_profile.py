"""
Session-anchored Volume Profile (Phase 2) — approximates volume-at-price by
distributing each bar's volume uniformly across its high-low range into
price buckets, without needing tick/order-book data. Produces the session
Point of Control (POC, highest-volume price) and Value Area High/Low (the
bounds of the 70%-of-volume region). Not itself a firing pattern — a context
layer that feeds the composite score's volume_confirmation term (see
engine/signal_engine.py) and Claude's prompt context, the same role
engine/levels.py's S/R ladder plays.
"""
from typing import Dict, List, Optional, Tuple

BUCKET_COUNT = 40
VALUE_AREA_PCT = 0.70


class VolumeProfileTracker:
    def __init__(self, bucket_count: int = BUCKET_COUNT, value_area_pct: float = VALUE_AREA_PCT):
        self.bucket_count = bucket_count
        self.value_area_pct = value_area_pct
        self._session_day = None
        self._bars: List[Tuple[float, float, float]] = []   # (high, low, volume)

    def update(self, ind: Dict, i: int) -> None:
        day = ind["timestamps"][i].date()
        if self._session_day != day:
            self._session_day = day
            self._bars = []
        self._bars.append((ind["highs"][i], ind["lows"][i], ind["volumes"][i]))

    def compute(self) -> Optional[Dict[str, float]]:
        if not self._bars:
            return None
        lo = min(b[1] for b in self._bars)
        hi = max(b[0] for b in self._bars)
        if hi <= lo:
            return None

        bucket_size = (hi - lo) / self.bucket_count
        volumes = [0.0] * self.bucket_count
        for bar_high, bar_low, vol in self._bars:
            start = max(0, int((bar_low - lo) / bucket_size))
            end = min(self.bucket_count - 1, int((bar_high - lo) / bucket_size))
            span = end - start + 1
            per_bucket = vol / span
            for b in range(start, end + 1):
                volumes[b] += per_bucket

        poc_idx = max(range(self.bucket_count), key=lambda b: volumes[b])
        poc_price = lo + (poc_idx + 0.5) * bucket_size

        total_vol = sum(volumes)
        target = total_vol * self.value_area_pct
        lo_i = hi_i = poc_idx
        acc = volumes[poc_idx]
        while acc < target and (lo_i > 0 or hi_i < self.bucket_count - 1):
            expand_lo = volumes[lo_i - 1] if lo_i > 0 else -1.0
            expand_hi = volumes[hi_i + 1] if hi_i < self.bucket_count - 1 else -1.0
            if expand_hi >= expand_lo:
                hi_i += 1
                acc += volumes[hi_i]
            else:
                lo_i -= 1
                acc += volumes[lo_i]

        return {
            "poc": poc_price,
            "vah": lo + (hi_i + 1) * bucket_size,
            "val": lo + lo_i * bucket_size,
        }

    def proximity_score(self, price: float) -> float:
        """0-100 volume-context score feeding volume_confirmation_score.
        Inside the value area = fair value (mild confirmation, price tends to
        consolidate); outside VAH/VAL = directional extension (stronger
        confirmation the move has conviction behind it)."""
        levels = self.compute()
        if not levels:
            return 50.0
        if levels["val"] <= price <= levels["vah"]:
            return 55.0
        return 65.0
