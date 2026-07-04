"""
Optional paper-trade recorder — only invoked when AUTO_PAPER_TRADE=true and a
signal's composite score clears RTC_SIGNAL_THRESHOLD. Phase 1: entry-only,
fixed nominal size (this system is a signal/journal engine first; proper
position sizing and exit-condition automation is Phase 2 hardening — see the
plan doc's phased build order).
"""
import logging
from typing import Dict, Optional

from journal.recorder import record_action
from settings import RTC_TRADING_MODE

logger = logging.getLogger(__name__)

_NOMINAL_SHARES = 100  # placeholder size — real sizing deferred to Phase 2


def maybe_enter_trade(interpretation_id: int, ticker: str, direction: str, price: float) -> Optional[Dict]:
    action_id = record_action(
        interpretation_id, action_type="entry", mode=RTC_TRADING_MODE,
        entry_price=price, shares=_NOMINAL_SHARES,
    )
    logger.info("Paper trade recorded: %s %s @ %.3f (action_id=%d)", direction, ticker, price, action_id)
    return {"action_id": action_id, "entry_price": price, "shares": _NOMINAL_SHARES}
