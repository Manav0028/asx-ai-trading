"""
stop_mult/target_mult/max_hold_bars defaults for SMC and chart-pattern
signals — candlestick patterns already carry these as class attributes
(engine/candlestick_patterns.py), but engine/smc.py and engine/chart_patterns.py
return plain dicts without them. Applied once in
engine/signal_engine.py's _evaluate_patterns() rather than touching every
`return {...}` literal in both files. Values stay within the same
stop_mult ~1.3-2.0 / target_mult ~2.5-4.0 / max_hold_bars ~30-90 ranges the
candlestick patterns use, scaled by each pattern's structural
reliability/reversal-vs-continuation character (see plan doc).
"""
from typing import Dict, Optional

PATTERN_RISK_DEFAULTS: Dict[str, Dict] = {
    "bullish_ob_retest": {"stop_mult": 1.5, "target_mult": 3.0, "max_hold_bars": 60},
    "bearish_ob_retest": {"stop_mult": 1.5, "target_mult": 3.0, "max_hold_bars": 60},
    "fvg_fill_bullish": {"stop_mult": 1.3, "target_mult": 2.5, "max_hold_bars": 30},
    "fvg_fill_bearish": {"stop_mult": 1.3, "target_mult": 2.5, "max_hold_bars": 30},
    "liquidity_sweep_reversal": {"stop_mult": 1.4, "target_mult": 3.2, "max_hold_bars": 45},
    "break_of_structure": {"stop_mult": 1.8, "target_mult": 3.5, "max_hold_bars": 60},
    "change_of_character": {"stop_mult": 1.6, "target_mult": 3.5, "max_hold_bars": 50},
    "double_top_breakdown": {"stop_mult": 1.7, "target_mult": 3.3, "max_hold_bars": 60},
    "double_bottom_breakout": {"stop_mult": 1.7, "target_mult": 3.3, "max_hold_bars": 60},
    "head_shoulders_breakdown": {"stop_mult": 1.8, "target_mult": 3.8, "max_hold_bars": 75},
    "inv_head_shoulders_breakout": {"stop_mult": 1.8, "target_mult": 3.8, "max_hold_bars": 75},
    "triangle_breakout": {"stop_mult": 1.5, "target_mult": 3.0, "max_hold_bars": 60},
    "triangle_breakdown": {"stop_mult": 1.5, "target_mult": 3.0, "max_hold_bars": 60},
    "flag_breakout": {"stop_mult": 1.4, "target_mult": 2.8, "max_hold_bars": 40},
    "flag_breakdown": {"stop_mult": 1.4, "target_mult": 2.8, "max_hold_bars": 40},
}

_FALLBACK = {"stop_mult": 1.5, "target_mult": 3.0, "max_hold_bars": 50}


def apply_risk_defaults(signal: Dict) -> Dict:
    """No-op if the signal already carries these fields (candlestick
    patterns do); otherwise looks up by pattern_name, falling back to a
    reasonable default for any name not in the table."""
    if "stop_mult" in signal and "target_mult" in signal and "max_hold_bars" in signal:
        return signal
    defaults = PATTERN_RISK_DEFAULTS.get(signal["pattern_name"], _FALLBACK)
    signal.setdefault("stop_mult", defaults["stop_mult"])
    signal.setdefault("target_mult", defaults["target_mult"])
    signal.setdefault("max_hold_bars", defaults["max_hold_bars"])
    return signal
