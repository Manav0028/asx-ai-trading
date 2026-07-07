"""
Multi-timeframe confluence gate — a 1-min pattern only becomes "confirmed"
(eligible for auto-trading) if the higher-timeframe bias agrees. Research
cited in the plan doc found multi-timeframe agreement measurably improves
signal quality (40-50% cited success-rate improvement vs single-timeframe).

Originally this was the ONLY place higher timeframes (5m/15m) mattered at
all — every actual pattern detector (candlestick/chart/SMC) only ever ran
against 1-minute bars, so "bias" here meant nothing more than an EMA20/50
crossover on that timeframe. engine/signal_engine.py now also runs the same
pattern detectors against 5m/15m/1d bars directly (see its
_handle_context_bar), so bias_for() takes an optional `recent_pattern`
argument: if a real pattern actually fired on that timeframe recently (not
just "price happens to be above its 20-EMA"), that's a stronger and more
specific signal than the EMA-crossover fallback, and takes priority over it.
"""
from typing import Dict, Optional


def bias_for(ind: Optional[Dict], recent_pattern_direction: Optional[str] = None) -> str:
    """'bullish' | 'bearish' | 'neutral' for one timeframe. `recent_pattern_direction`
    ('long'/'short'/None) comes from that timeframe's own pattern engines having
    actually fired within the last few bars (see RECENT_PATTERN_DECAY_BARS in
    signal_engine.py) — when present, it's used ahead of the EMA-crossover
    fallback, since an actual confirmed pattern is a more specific claim than
    "price is on the right side of its moving averages."""
    if recent_pattern_direction == "long":
        return "bullish"
    if recent_pattern_direction == "short":
        return "bearish"
    if not ind or not ind.get("ema20") or not ind.get("ema50"):
        return "neutral"
    ema20, ema50, price = ind["ema20"][-1], ind["ema50"][-1], ind["closes"][-1]
    if ema20 > ema50 and price > ema20:
        return "bullish"
    if ema20 < ema50 and price < ema20:
        return "bearish"
    return "neutral"


def check_confluence(direction: str, biases: Dict[str, str]) -> Dict:
    """direction: 'long' | 'short'. biases: {'5m': ..., '15m': ..., '1d': ...}
    (any subset — missing keys default to 'neutral'). Returns {'confirmed':
    bool, 'bonus': 0-100, 'summary': str} — bonus feeds the mtf_confluence_bonus
    term of the composite score (plan §7). 5m is still the primary gate (it's
    the closest higher timeframe to the 1m execution timeframe); 15m and 1d
    each add an equal share of bonus on top when they also agree, so a signal
    with all three timeframes aligned scores meaningfully higher than one
    where only 5m agrees."""
    expected = "bullish" if direction == "long" else "bearish"
    bias_5m = biases.get("5m", "neutral")
    bias_15m = biases.get("15m", "neutral")
    bias_1d = biases.get("1d", "neutral")

    if bias_5m == expected:
        confirmed = True
        agree_count = sum(1 for b in (bias_15m, bias_1d) if b == expected)
        bonus = 50.0 + 25.0 * agree_count
    elif bias_5m == "neutral":
        confirmed = False
        bonus = 50.0
    else:
        confirmed = False
        bonus = 0.0

    return {
        "confirmed": confirmed,
        "bonus": bonus,
        "summary": f"5m={bias_5m}, 15m={bias_15m}, 1d={bias_1d} (expected {expected})",
    }
