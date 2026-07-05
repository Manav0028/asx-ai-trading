"""
Thin dispatch façade — the stable public API signal_engine.py calls, so the
call site barely changes as trading modes are added. All real logic (sizing,
stops, simulated fill, journal writes) lives in trading/position_tracker.py;
this module only decides which backend handles the trade based on
RTC_TRADING_MODE. Only "paper" (simulated fill) is implemented — ibkr_paper/
live remain documented future extension points (see plan doc).
"""
from typing import Dict, Optional

from settings import RTC_TRADING_MODE
from trading.position_tracker import tracker


def maybe_enter_trade(interpretation_id: int, ticker: str, direction: str, price: float,
                       atr: float, composite_score: float, stop_mult: float, target_mult: float,
                       max_hold_bars: int) -> Optional[Dict]:
    if RTC_TRADING_MODE != "paper":
        raise NotImplementedError(
            f"RTC_TRADING_MODE={RTC_TRADING_MODE!r} is not implemented — only 'paper' (simulated "
            "fill via trading/position_tracker.py) is built. Real IBKR paper/live order routing "
            "is a documented future extension point, not built in this pass."
        )
    return tracker.open_position(
        interpretation_id, ticker, direction, price, atr, composite_score,
        stop_mult, target_mult, max_hold_bars,
    )
