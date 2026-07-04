"""
Multi-timeframe confluence gate — a 1-min pattern only becomes "confirmed"
(eligible for auto-trading) if the higher-timeframe bias agrees. Research
cited in the plan doc found multi-timeframe agreement measurably improves
signal quality (40-50% cited success-rate improvement vs single-timeframe).
"""
from typing import Dict, Optional


def bias_for(ind: Optional[Dict]) -> str:
    """'bullish' | 'bearish' | 'neutral' for one timeframe's indicator snapshot."""
    if not ind or not ind.get("ema20") or not ind.get("ema50"):
        return "neutral"
    ema20, ema50, price = ind["ema20"][-1], ind["ema50"][-1], ind["closes"][-1]
    if ema20 > ema50 and price > ema20:
        return "bullish"
    if ema20 < ema50 and price < ema20:
        return "bearish"
    return "neutral"


def check_confluence(direction: str, biases: Dict[str, str]) -> Dict:
    """direction: 'long' | 'short'. biases: {'5m': ..., '15m': ...}.
    Returns {'confirmed': bool, 'bonus': 0-100, 'summary': str} — bonus feeds
    the mtf_confluence_bonus term of the composite score (plan §7)."""
    expected = "bullish" if direction == "long" else "bearish"
    bias_5m = biases.get("5m", "neutral")
    bias_15m = biases.get("15m", "neutral")

    if bias_5m == expected:
        confirmed = True
        bonus = 100.0 if bias_15m == expected else 50.0
    elif bias_5m == "neutral":
        confirmed = False
        bonus = 50.0
    else:
        confirmed = False
        bonus = 0.0

    return {
        "confirmed": confirmed,
        "bonus": bonus,
        "summary": f"5m={bias_5m}, 15m={bias_15m} (expected {expected})",
    }
