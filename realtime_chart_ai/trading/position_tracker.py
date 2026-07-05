"""
The stateful core of automated trading — owns the open-position lifecycle:
entry sizing/stop-target computation, per-bar exit checking (stop / target /
max-hold, with a favorably-ratcheting trailing stop), simulated fill P&L, and
all journal writes for the trade lifecycle.

Per the plan doc's feedback round: open-position state must be trackable and
retrievable, not just held in a Python dict that dies with the process. The
in-memory `{ticker: OpenPosition}` dict here is a working-set CACHE — the
`rtc_open_positions` table (via journal/recorder.py) is the actual source of
truth, written through on every mutation, and `load_open_positions()` rebuilds
the cache from it exactly on startup.
"""
import logging
from dataclasses import dataclass
from typing import Dict, Optional

from journal.recorder import (
    close_open_position, get_open_positions, log_event, open_position_row,
    record_action, record_outcome, update_open_position,
)
from trading import pnl, sizing, stops

logger = logging.getLogger(__name__)


@dataclass
class OpenPosition:
    ticker: str
    position_id: int
    trade_action_id: int
    direction: str
    entry_price: float
    shares: float
    stop_price: float
    target_price: float
    peak_price: float
    trail_activate_pct: float
    trail_distance_pct: float
    max_hold_bars: int
    bars_held: int = 0


class PositionTracker:
    def __init__(self):
        self._positions: Dict[str, OpenPosition] = {}

    def has_open_position(self, ticker: str) -> bool:
        return ticker in self._positions

    def load_open_positions(self) -> None:
        """Rebuild the in-memory cache from rtc_open_positions — called once
        at server startup so a restart doesn't lose track of what's open."""
        rows = get_open_positions()
        for row in rows:
            self._positions[row["ticker"]] = OpenPosition(
                ticker=row["ticker"], position_id=row["id"], trade_action_id=row["trade_action_id"],
                direction=row["direction"], entry_price=row["entry_price"], shares=row["shares"],
                stop_price=row["stop_price"], target_price=row["target_price"], peak_price=row["peak_price"],
                trail_activate_pct=row["trail_activate_pct"], trail_distance_pct=row["trail_distance_pct"],
                max_hold_bars=row["max_hold_bars"], bars_held=row["bars_held"],
            )
        if rows:
            logger.info("Recovered %d open position(s) from rtc_open_positions: %s",
                        len(rows), [r["ticker"] for r in rows])

    def open_position(self, interpretation_id: int, ticker: str, direction: str, price: float,
                       atr: float, composite_score: float, stop_mult: float, target_mult: float,
                       max_hold_bars: int) -> Optional[Dict]:
        """This tracker is exclusively the 'paper' (simulated-fill) backend —
        mode dispatch/gating happens one layer up in paper_or_live_bridge.py."""
        st = stops.compute_stop_target(price, atr, direction, stop_mult, target_mult)
        trail = stops.compute_trail_params(price, atr)
        pos = sizing.compute_position(price, st["stop_price"], composite_score)

        trade_action_id = record_action(
            interpretation_id, action_type="entry", mode="paper",
            entry_price=price, shares=pos["shares"], stop_price=st["stop_price"],
            target_price=st["target_price"], composite_score_at_entry=composite_score,
            dollar_risk=pos["dollar_risk"], score_multiplier=pos["multiplier"], atr_at_entry=atr,
        )
        position_id = open_position_row(
            ticker=ticker, trade_action_id=trade_action_id, direction=direction, entry_price=price,
            shares=pos["shares"], stop_price=st["stop_price"], target_price=st["target_price"],
            peak_price=price, atr_at_entry=atr, trail_activate_pct=trail["activate_pct"],
            trail_distance_pct=trail["distance_pct"], max_hold_bars=max_hold_bars,
        )
        self._positions[ticker] = OpenPosition(
            ticker=ticker, position_id=position_id, trade_action_id=trade_action_id,
            direction=direction, entry_price=price, shares=pos["shares"],
            stop_price=st["stop_price"], target_price=st["target_price"], peak_price=price,
            trail_activate_pct=trail["activate_pct"], trail_distance_pct=trail["distance_pct"],
            max_hold_bars=max_hold_bars,
        )
        logger.info("Opened paper position: %s %s @ %.3f, shares=%.2f, stop=%.3f, target=%.3f",
                    direction, ticker, price, pos["shares"], st["stop_price"], st["target_price"])
        return {
            "trade_action_id": trade_action_id, "entry_price": price, "shares": pos["shares"],
            "stop_price": st["stop_price"], "target_price": st["target_price"],
            "dollar_risk": pos["dollar_risk"], "score_multiplier": pos["multiplier"],
        }

    def check_exit(self, ticker: str, ind: Dict, i: int) -> Optional[Dict]:
        position = self._positions.get(ticker)
        if position is None:
            return None

        close, high, low = ind["closes"][i], ind["highs"][i], ind["lows"][i]
        position.bars_held += 1

        trail = stops.update_trailing_stop(
            position.direction, position.entry_price, close, position.peak_price,
            position.stop_price, position.trail_activate_pct, position.trail_distance_pct,
        )
        if trail["new_stop"] != position.stop_price:
            log_event("trailing_stop_updated", ticker=ticker,
                       detail=f"stop {position.stop_price:.4f} -> {trail['new_stop']:.4f} "
                              f"at bar {position.bars_held}")
            position.stop_price = trail["new_stop"]
        position.peak_price = trail["new_peak"]

        update_open_position(position.position_id, stop_price=position.stop_price,
                              peak_price=position.peak_price, bars_held=position.bars_held)

        exit_reason = None
        exit_price_raw = None
        if position.direction == "long":
            if low <= position.stop_price:
                exit_reason, exit_price_raw = "stop_loss", position.stop_price
            elif high >= position.target_price:
                exit_reason, exit_price_raw = "target", position.target_price
        else:
            if high >= position.stop_price:
                exit_reason, exit_price_raw = "stop_loss", position.stop_price
            elif low <= position.target_price:
                exit_reason, exit_price_raw = "target", position.target_price
        if exit_reason is None and position.bars_held >= position.max_hold_bars:
            exit_reason, exit_price_raw = "max_hold", close

        if exit_reason is None:
            return None

        pnl_result = pnl.compute_pnl(position.direction, position.entry_price, exit_price_raw, position.shares)
        record_outcome(
            position.trade_action_id, exit_price=exit_price_raw, exit_reason=exit_reason,
            gross_pnl=pnl_result["gross_pnl"], net_pnl=pnl_result["net_pnl"], bars_held=position.bars_held,
        )
        close_open_position(position.position_id)
        del self._positions[ticker]

        logger.info("Closed paper position: %s %s exit=%.3f reason=%s net_pnl=%.2f",
                    position.direction, ticker, exit_price_raw, exit_reason, pnl_result["net_pnl"])
        return {
            "type": "trade_exit", "ticker": ticker, "direction": position.direction,
            "entry_price": position.entry_price, "exit_price": exit_price_raw, "exit_reason": exit_reason,
            "shares": position.shares, "gross_pnl": pnl_result["gross_pnl"], "net_pnl": pnl_result["net_pnl"],
            "bars_held": position.bars_held,
        }


tracker = PositionTracker()
