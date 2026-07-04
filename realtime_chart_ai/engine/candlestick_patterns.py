"""
Candlestick pattern family — the existing 6 daily-bar patterns from
strategies/patterns.py ported to the streaming `ind` dict (same fires(ind, i)
contract), plus new single/multi-bar patterns per the plan's research
(doji, morning/evening star, piercing line/dark cloud cover, three white
soldiers/black crows, marubozu). All operate on whatever timeframe's `ind`
snapshot they're given — normally the 1-minute execution timeframe.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional


class LivePatternStrategy(ABC):
    name: str = "base"
    description: str = ""
    direction: str = "long"     # "long" or "short"
    stop_mult: float = 2.0
    target_mult: float = 3.5
    max_hold_bars: int = 60     # bar-count analogue of strategies/base.py's max_hold_days
    pattern_type: str = "candlestick"

    @abstractmethod
    def fires(self, ind: Dict, i: int) -> Optional[Dict]:
        """Returns None or {"confidence": 0-1, "reason": str}."""

    def evaluate_latest(self, ind: Dict) -> Optional[Dict]:
        return self.fires(ind, len(ind["closes"]) - 1)


def _body(ind, i) -> float:
    return ind["closes"][i] - ind["opens"][i]


def _range(ind, i) -> float:
    return max(ind["highs"][i] - ind["lows"][i], 1e-9)


# ── Ported from strategies/patterns.py (daily -> streaming) ──────────────────

class BullishEngulfing(LivePatternStrategy):
    name = "bull_engulf"
    description = "Bullish engulfing after a decline with RSI<45"
    direction = "long"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_bars = 45

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 5:
            return None
        fell = ind["closes"][i - 1] < ind["closes"][i - 4]
        prev_red = _body(ind, i - 1) < 0
        now_green = _body(ind, i) > 0
        engulfs = (ind["opens"][i] <= ind["closes"][i - 1] and ind["closes"][i] >= ind["opens"][i - 1])
        washed = ind["rsi"][i] < 45
        if fell and prev_red and now_green and engulfs and washed:
            strength = abs(_body(ind, i)) / _range(ind, i)
            return {"confidence": round(min(1.0, 0.5 + strength / 2), 2),
                    "reason": f"bullish engulfing after decline (RSI {ind['rsi'][i]:.0f})"}
        return None


class HammerAtSupport(LivePatternStrategy):
    name = "hammer"
    description = "Hammer (long lower wick, close in top third) at the 20-bar low"
    direction = "long"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_bars = 45

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
                    "reason": "hammer rejection at 20-bar support"}
        return None


class InsideBarBreakout(LivePatternStrategy):
    name = "inside_break"
    description = "Inside bar then breakout above the mother bar high on volume"
    direction = "long"
    stop_mult = 1.8
    target_mult = 3.5
    max_hold_bars = 60

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 25:
            return None
        inside = (ind["highs"][i - 1] <= ind["highs"][i - 2] and ind["lows"][i - 1] >= ind["lows"][i - 2])
        breaks_up = ind["closes"][i] > ind["highs"][i - 2]
        vol_ok = ind["volumes"][i] >= 1.2 * ind["vol_avg_20"][i]
        uptrend = ind["ema20"][i] > ind["ema50"][i]
        if inside and breaks_up and vol_ok and uptrend:
            return {"confidence": 0.65, "reason": "inside-bar squeeze broke out upward on volume"}
        return None


class BearishEngulfing(LivePatternStrategy):
    name = "bear_engulf"
    description = "SHORT: bearish engulfing after a rally with RSI>60"
    direction = "short"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_bars = 45

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 5:
            return None
        rose = ind["closes"][i - 1] > ind["closes"][i - 4]
        prev_green = _body(ind, i - 1) > 0
        now_red = _body(ind, i) < 0
        engulfs = (ind["opens"][i] >= ind["closes"][i - 1] and ind["closes"][i] <= ind["opens"][i - 1])
        stretched = ind["rsi"][i] > 60
        if rose and prev_green and now_red and engulfs and stretched:
            strength = abs(_body(ind, i)) / _range(ind, i)
            return {"confidence": round(min(1.0, 0.5 + strength / 2), 2),
                    "reason": f"bearish engulfing after rally (RSI {ind['rsi'][i]:.0f})"}
        return None


class ShootingStar(LivePatternStrategy):
    name = "shooting_star"
    description = "SHORT: shooting star (long upper wick) at the 20-bar high"
    direction = "short"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_bars = 45

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
                    "reason": "shooting star rejection at 20-bar high"}
        return None


class Breakdown(LivePatternStrategy):
    name = "breakdown"
    description = "SHORT: close below the 20-bar low on >=1.5x volume in a downtrend"
    direction = "short"
    stop_mult = 2.0
    target_mult = 4.0
    max_hold_bars = 90

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 60:
            return None
        new_low = ind["closes"][i] < ind["low_20"][i]
        vol_ratio = ind["volumes"][i] / (ind["vol_avg_20"][i] + 1e-9)
        downtrend = ind["ema20"][i] < ind["ema50"][i]
        if new_low and vol_ratio >= 1.5 and downtrend:
            return {"confidence": round(min(1.0, 0.5 + vol_ratio / 6), 2),
                    "reason": f"20-bar low breakdown on {vol_ratio:.1f}x volume"}
        return None


# ── New patterns added per plan research ──────────────────────────────────────

class DojiAtSupport(LivePatternStrategy):
    name = "doji_support"
    description = "Doji (indecision) printed at the 20-bar low"
    direction = "long"
    stop_mult = 1.3
    target_mult = 2.5
    max_hold_bars = 30

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 25:
            return None
        rng = _range(ind, i)
        is_doji = abs(_body(ind, i)) <= 0.1 * rng
        at_low = ind["lows"][i] <= ind["low_20"][i] * 1.01
        if is_doji and at_low:
            return {"confidence": 0.55, "reason": "doji indecision at 20-bar support"}
        return None


class DojiAtResistance(LivePatternStrategy):
    name = "doji_resistance"
    description = "Doji (indecision) printed at the 20-bar high"
    direction = "short"
    stop_mult = 1.3
    target_mult = 2.5
    max_hold_bars = 30

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 25:
            return None
        rng = _range(ind, i)
        is_doji = abs(_body(ind, i)) <= 0.1 * rng
        at_high = ind["highs"][i] >= ind["high_20"][i] * 0.99
        if is_doji and at_high:
            return {"confidence": 0.55, "reason": "doji indecision at 20-bar resistance"}
        return None


class MorningStar(LivePatternStrategy):
    name = "morning_star"
    description = "3-bar bullish reversal: big red, small indecisive gap-down, big green closing above candle-1 midpoint"
    direction = "long"
    stop_mult = 1.6
    target_mult = 3.2
    max_hold_bars = 45

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 2:
            return None
        r1, r2, r3 = _range(ind, i - 2), _range(ind, i - 1), _range(ind, i)
        big_red = _body(ind, i - 2) < 0 and abs(_body(ind, i - 2)) >= 0.6 * r1
        small_mid = abs(_body(ind, i - 1)) <= 0.3 * r2
        gaps_down = max(ind["opens"][i - 1], ind["closes"][i - 1]) < ind["closes"][i - 2]
        big_green = _body(ind, i) > 0 and abs(_body(ind, i)) >= 0.6 * r3
        midpoint_1 = (ind["opens"][i - 2] + ind["closes"][i - 2]) / 2
        closes_above_mid = ind["closes"][i] > midpoint_1
        if big_red and small_mid and gaps_down and big_green and closes_above_mid:
            return {"confidence": 0.7, "reason": "morning star 3-bar reversal"}
        return None


class EveningStar(LivePatternStrategy):
    name = "evening_star"
    description = "3-bar bearish reversal: big green, small indecisive gap-up, big red closing below candle-1 midpoint"
    direction = "short"
    stop_mult = 1.6
    target_mult = 3.2
    max_hold_bars = 45

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 2:
            return None
        r1, r2, r3 = _range(ind, i - 2), _range(ind, i - 1), _range(ind, i)
        big_green = _body(ind, i - 2) > 0 and abs(_body(ind, i - 2)) >= 0.6 * r1
        small_mid = abs(_body(ind, i - 1)) <= 0.3 * r2
        gaps_up = min(ind["opens"][i - 1], ind["closes"][i - 1]) > ind["closes"][i - 2]
        big_red = _body(ind, i) < 0 and abs(_body(ind, i)) >= 0.6 * r3
        midpoint_1 = (ind["opens"][i - 2] + ind["closes"][i - 2]) / 2
        closes_below_mid = ind["closes"][i] < midpoint_1
        if big_green and small_mid and gaps_up and big_red and closes_below_mid:
            return {"confidence": 0.7, "reason": "evening star 3-bar reversal"}
        return None


class PiercingLine(LivePatternStrategy):
    name = "piercing_line"
    description = "2-bar bullish reversal: gap-down open, closes above prior body midpoint"
    direction = "long"
    stop_mult = 1.4
    target_mult = 2.8
    max_hold_bars = 40

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 1:
            return None
        prev_red_big = _body(ind, i - 1) < 0 and abs(_body(ind, i - 1)) >= 0.5 * _range(ind, i - 1)
        gaps_down = ind["opens"][i] < ind["lows"][i - 1]
        midpoint = (ind["opens"][i - 1] + ind["closes"][i - 1]) / 2
        pierces = _body(ind, i) > 0 and ind["closes"][i] > midpoint and ind["closes"][i] < ind["opens"][i - 1]
        if prev_red_big and gaps_down and pierces:
            return {"confidence": 0.62, "reason": "piercing line reversal"}
        return None


class DarkCloudCover(LivePatternStrategy):
    name = "dark_cloud_cover"
    description = "2-bar bearish reversal: gap-up open, closes below prior body midpoint"
    direction = "short"
    stop_mult = 1.4
    target_mult = 2.8
    max_hold_bars = 40

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 1:
            return None
        prev_green_big = _body(ind, i - 1) > 0 and abs(_body(ind, i - 1)) >= 0.5 * _range(ind, i - 1)
        gaps_up = ind["opens"][i] > ind["highs"][i - 1]
        midpoint = (ind["opens"][i - 1] + ind["closes"][i - 1]) / 2
        covers = _body(ind, i) < 0 and ind["closes"][i] < midpoint and ind["closes"][i] > ind["opens"][i - 1]
        if prev_green_big and gaps_up and covers:
            return {"confidence": 0.62, "reason": "dark cloud cover reversal"}
        return None


class ThreeWhiteSoldiers(LivePatternStrategy):
    name = "three_white_soldiers"
    description = "3 consecutive rising green candles with small upper wicks"
    direction = "long"
    stop_mult = 1.8
    target_mult = 3.5
    max_hold_bars = 60

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 2:
            return None
        all_green = all(_body(ind, j) > 0 for j in (i - 2, i - 1, i))
        rising = ind["closes"][i - 2] < ind["closes"][i - 1] < ind["closes"][i]
        small_wicks = all(
            (ind["highs"][j] - ind["closes"][j]) <= 0.25 * _range(ind, j) for j in (i - 2, i - 1, i)
        )
        if all_green and rising and small_wicks:
            return {"confidence": 0.68, "reason": "three white soldiers continuation"}
        return None


class ThreeBlackCrows(LivePatternStrategy):
    name = "three_black_crows"
    description = "3 consecutive falling red candles with small lower wicks"
    direction = "short"
    stop_mult = 1.8
    target_mult = 3.5
    max_hold_bars = 60

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 2:
            return None
        all_red = all(_body(ind, j) < 0 for j in (i - 2, i - 1, i))
        falling = ind["closes"][i - 2] > ind["closes"][i - 1] > ind["closes"][i]
        small_wicks = all(
            (ind["closes"][j] - ind["lows"][j]) <= 0.25 * _range(ind, j) for j in (i - 2, i - 1, i)
        )
        if all_red and falling and small_wicks:
            return {"confidence": 0.68, "reason": "three black crows continuation"}
        return None


class BullishMarubozu(LivePatternStrategy):
    name = "bullish_marubozu"
    description = "Strong green candle with virtually no wicks — momentum continuation"
    direction = "long"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_bars = 40

    def fires(self, ind, i) -> Optional[Dict]:
        rng = _range(ind, i)
        body = _body(ind, i)
        no_lower_wick = (ind["opens"][i] - ind["lows"][i]) <= 0.05 * rng
        no_upper_wick = (ind["highs"][i] - ind["closes"][i]) <= 0.05 * rng
        strong_body = body > 0 and body >= 0.8 * rng
        if no_lower_wick and no_upper_wick and strong_body:
            return {"confidence": 0.6, "reason": "bullish marubozu momentum candle"}
        return None


class BearishMarubozu(LivePatternStrategy):
    name = "bearish_marubozu"
    description = "Strong red candle with virtually no wicks — momentum continuation"
    direction = "short"
    stop_mult = 1.5
    target_mult = 3.0
    max_hold_bars = 40

    def fires(self, ind, i) -> Optional[Dict]:
        rng = _range(ind, i)
        body = _body(ind, i)
        no_upper_wick = (ind["highs"][i] - ind["opens"][i]) <= 0.05 * rng
        no_lower_wick = (ind["closes"][i] - ind["lows"][i]) <= 0.05 * rng
        strong_body = body < 0 and abs(body) >= 0.8 * rng
        if no_upper_wick and no_lower_wick and strong_body:
            return {"confidence": 0.6, "reason": "bearish marubozu momentum candle"}
        return None


CANDLESTICK_PATTERNS = [
    BullishEngulfing(), HammerAtSupport(), InsideBarBreakout(),
    BearishEngulfing(), ShootingStar(), Breakdown(),
    DojiAtSupport(), DojiAtResistance(), MorningStar(), EveningStar(),
    PiercingLine(), DarkCloudCover(), ThreeWhiteSoldiers(), ThreeBlackCrows(),
    BullishMarubozu(), BearishMarubozu(),
]
