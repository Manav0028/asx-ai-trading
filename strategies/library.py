"""
Strategy Engine — Strategy Library
Nine distinct edges — five practitioner patterns plus the four most
academically validated equity anomalies (time-series momentum, 52-week-high
momentum, RSI(2) mean reversion, Donchian trend breakout).
Each stock gets matched to whichever one its own price
history validates — trending stocks get trend strategies, range-bound stocks
get mean reversion, etc.
"""
from typing import Dict, List, Optional

import numpy as np

from strategies.base import Strategy


class TrendFollow(Strategy):
    """Enter when momentum freshly confirms an established uptrend.
    Suits stocks with long directional moves (high ADX)."""
    name = "trend_follow"
    description = "EMA20>EMA50 uptrend + ADX≥25 + fresh MACD bullish turn"
    stop_mult = 2.0
    target_mult = 4.0
    max_hold_days = 45

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 1:
            return None
        uptrend = ind["ema20"][i] > ind["ema50"][i]
        strong = ind["adx"][i] >= 20          # was 25 — let moderate trends qualify
        macd_turn = ind["macd_hist"][i] > 0 and ind["macd_hist"][i - 1] <= 0
        if uptrend and strong and macd_turn:
            conf = min(1.0, 0.6 + ind["adx"][i] / 100)
            return {"confidence": round(conf, 2),
                    "reason": f"trend confirmed (ADX {ind['adx'][i]:.0f}, MACD turned bullish)"}
        return None


class MeanReversion(Strategy):
    """Buy washed-out dips in range-bound stocks and exit quickly.
    Suits choppy/sideways stocks (low ADX)."""
    name = "mean_reversion"
    description = "Range-bound (ADX<25) + RSI<32 + price at lower Bollinger band"
    stop_mult = 1.5
    target_mult = 2.5
    max_hold_days = 15

    def fires(self, ind, i) -> Optional[Dict]:
        ranging = ind["adx"][i] < 28          # was 25 — slightly wider range-bound threshold
        oversold = ind["rsi"][i] < 36         # was 32 — catch shallower dips
        at_lower_band = ind["bb_pct"][i] < 0.22  # was 0.15 — allow near lower band
        if ranging and oversold and at_lower_band:
            conf = min(1.0, 0.5 + (36 - ind["rsi"][i]) / 40)
            return {"confidence": round(conf, 2),
                    "reason": f"oversold in range (RSI {ind['rsi'][i]:.0f}, at lower band)"}
        return None


class Breakout(Strategy):
    """Buy 20-day-high breakouts confirmed by volume.
    Suits stocks that move in volume-driven thrusts."""
    name = "breakout"
    description = "Close above 20-day high on ≥1.5x average volume"
    stop_mult = 2.0
    target_mult = 4.0
    max_hold_days = 30

    def fires(self, ind, i) -> Optional[Dict]:
        new_high = ind["closes"][i] > ind["high_20"][i]
        vol_ratio = ind["volumes"][i] / (ind["vol_avg_20"][i] + 1e-9)
        if new_high and vol_ratio >= 1.25:        # was 1.5 — slightly elevated volume ok
            conf = min(1.0, 0.5 + vol_ratio / 6)
            return {"confidence": round(conf, 2),
                    "reason": f"20-day high breakout on {vol_ratio:.1f}x volume"}
        return None


class MomentumPullback(Strategy):
    """Buy shallow pullbacks to the 20-day EMA inside an uptrend.
    Suits steadily trending stocks that dip to support."""
    name = "momentum_pullback"
    description = "Uptrend + price within 2% of EMA20 + StochRSI<25"
    stop_mult = 1.8
    target_mult = 3.0
    max_hold_days = 25

    def fires(self, ind, i) -> Optional[Dict]:
        uptrend = ind["ema20"][i] > ind["ema50"][i]
        near_ema = abs(ind["closes"][i] - ind["ema20"][i]) / (ind["ema20"][i] + 1e-9) < 0.04  # was 0.02
        momentum_reset = ind["stoch_rsi"][i] < 35  # was 25 — catch earlier resets
        if uptrend and near_ema and momentum_reset:
            conf = min(1.0, 0.55 + (35 - ind["stoch_rsi"][i]) / 60)
            return {"confidence": round(conf, 2),
                    "reason": f"pullback to EMA20 in uptrend (StochRSI {ind['stoch_rsi'][i]:.0f})"}
        return None


class OversoldBounce(Strategy):
    """Buy the moment RSI recovers out of oversold with volume support.
    Suits volatile stocks that snap back hard after panic selling."""
    name = "oversold_bounce"
    description = "RSI crosses back above 30 with at-least-average volume"
    stop_mult = 1.5
    target_mult = 2.5
    max_hold_days = 15

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 1:
            return None
        rsi_cross_up = ind["rsi"][i - 1] < 30 <= ind["rsi"][i]
        vol_ok = ind["volumes"][i] >= ind["vol_avg_20"][i]
        if rsi_cross_up and vol_ok:
            conf = min(1.0, 0.5 + (ind["rsi"][i] - 30) / 30)
            return {"confidence": round(conf, 2),
                    "reason": f"RSI recovered from oversold ({ind['rsi'][i - 1]:.0f}→{ind['rsi'][i]:.0f})"}
        return None


class TimeSeriesMomentum(Strategy):
    """Buy stocks with strong 12-month momentum as they reclaim short-term trend.
    The most replicated anomaly in finance (Moskowitz et al. 2012 — works across
    two centuries and every asset class). Suits persistent long-run trenders."""
    name = "tsmom"
    description = "12-1 month momentum >10% + above 200-day MA + close reclaims EMA20"
    stop_mult = 2.5
    target_mult = 5.0
    max_hold_days = 60

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 260:
            return None
        mom = ind["mom_12_1"][i]
        strong = mom > 0.05            # was 0.10 — 5% annual momentum qualifies
        above_long = ind["closes"][i] > ind["sma200"][i]
        reclaim = ind["closes"][i] > ind["ema20"][i] >= ind["closes"][i - 1]
        if strong and above_long and reclaim:
            conf = min(1.0, 0.55 + mom)
            return {"confidence": round(conf, 2),
                    "reason": f"12-month momentum +{mom * 100:.0f}%, reclaimed EMA20"}
        return None


class FiftyTwoWeekHigh(Strategy):
    """Buy as price pushes into 2% of its 52-week high — the anchoring effect
    (George & Hwang 2004) makes these levels act as launchpads, not ceilings."""
    name = "high_52w"
    description = "Close enters within 2% of 52-week high on at-least-average volume"
    stop_mult = 2.0
    target_mult = 4.0
    max_hold_days = 40

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 260:
            return None
        hi = ind["high_252"][i]
        near_now = ind["closes"][i] >= hi * 0.96   # was 0.98 — within 4% of 52w high
        was_below = ind["closes"][i - 1] < ind["high_252"][i - 1] * 0.97
        vol_ok = ind["volumes"][i] >= ind["vol_avg_20"][i] * 0.9  # near-average volume ok
        if near_now and was_below and vol_ok:
            dist = (hi - ind["closes"][i]) / (hi + 1e-9)
            return {"confidence": round(min(1.0, 0.6 + (0.04 - dist) * 8), 2),
                    "reason": f"pushed within {dist * 100:.1f}% of 52-week high"}
        return None


class ConnorsRSI2(Strategy):
    """Buy 2-period-RSI panic dips in stocks above their 200-day MA and exit
    fast (Connors & Alvarez). One of the best documented short-term equity
    mean-reversion edges. Suits liquid large caps in long-term uptrends."""
    name = "rsi2_dip"
    description = "Above 200-day MA + RSI(2) < 10 — fast snap-back exits"
    stop_mult = 1.5
    target_mult = 2.0
    max_hold_days = 7

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 200:
            return None
        above_long = ind["closes"][i] > ind["sma200"][i]
        panic = ind["rsi2"][i] < 15        # was 10 — catch moderate short-term exhaustion
        if above_long and panic:
            conf = min(1.0, 0.55 + (15 - ind["rsi2"][i]) / 25)
            return {"confidence": round(conf, 2),
                    "reason": f"RSI(2) panic dip ({ind['rsi2'][i]:.0f}) above 200-day MA"}
        return None


class TurtleBreakout(Strategy):
    """Buy 55-day-high breakouts in a confirmed trend — the classic Donchian
    channel system behind the Turtles and the modern CTA industry. Wide target
    lets the live trailing stop ride the winners."""
    name = "turtle_55"
    description = "Close above 55-day high with ADX≥20 trend confirmation"
    stop_mult = 2.0
    target_mult = 6.0
    max_hold_days = 60

    def fires(self, ind, i) -> Optional[Dict]:
        if i < 60:
            return None
        new_high = ind["closes"][i] > ind["high_55"][i]
        trending = ind["adx"][i] >= 15        # was 20 — weaker trends allowed
        if new_high and trending:
            conf = min(1.0, 0.55 + ind["adx"][i] / 80)
            return {"confidence": round(conf, 2),
                    "reason": f"55-day Donchian breakout (ADX {ind['adx'][i]:.0f})"}
        return None


from strategies.patterns import PATTERN_STRATEGIES  # noqa: E402 — avoids circular import

ALL_STRATEGIES: List[Strategy] = [
    TrendFollow(),
    MeanReversion(),
    Breakout(),
    MomentumPullback(),
    OversoldBounce(),
    TimeSeriesMomentum(),
    FiftyTwoWeekHigh(),
    ConnorsRSI2(),
    TurtleBreakout(),
    *PATTERN_STRATEGIES,
]

STRATEGY_BY_NAME: Dict[str, Strategy] = {s.name: s for s in ALL_STRATEGIES}
