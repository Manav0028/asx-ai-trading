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
from datetime import datetime
from typing import Dict, List, Optional

from journal.recorder import (
    close_open_position, get_open_positions, log_event, open_position_row,
    record_action, record_outcome, update_open_position, write_interpretation,
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

    def open_tickers(self) -> List[str]:
        """Every ticker with a currently-open position — fed into the data
        source's priority-refresh set (see server/app.py) so a held
        position's price/P&L keeps updating fast regardless of where it
        sits in the full-watchlist round robin."""
        return list(self._positions.keys())

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

    def manual_open(self, ticker: str, direction: str, price: float, shares: float,
                     stop_price: float, target_price: float, atr: float = 0.0,
                     max_hold_bars: int = 60) -> Optional[Dict]:
        """User-initiated entry, bypassing the composite-score gate entirely
        — still goes through the same journal/position-lifecycle plumbing as
        an automated entry (one open position per ticker, trailing stop,
        DB-backed recovery) so it's indistinguishable from an automatic trade
        everywhere except the journal's pattern_name/rule_reason, which
        record that a human made the call."""
        if self.has_open_position(ticker):
            return None
        from engine.timeframe_store import EXECUTION_TIMEFRAME
        trail = stops.compute_trail_params(price, atr)
        interpretation_id = write_interpretation({
            "ticker": ticker, "bar_ts": datetime.utcnow(), "timeframe": EXECUTION_TIMEFRAME,
            "data_source": "manual", "pattern_name": "manual_entry", "pattern_type": "manual",
            "direction": direction, "confidence": None, "composite_score": None,
            "rule_reason": "Manually opened by user", "mtf_confluence": None, "mtf_summary": None,
            "smc_zone": None, "smc_context": None, "claude_rationale": None, "claude_model": None,
            "price_at_signal": price,
        })
        trade_action_id = record_action(
            interpretation_id, action_type="entry", mode="paper", entry_price=price, shares=shares,
            stop_price=stop_price, target_price=target_price, composite_score_at_entry=None,
            dollar_risk=None, score_multiplier=None, atr_at_entry=atr,
        )
        position_id = open_position_row(
            ticker=ticker, trade_action_id=trade_action_id, direction=direction, entry_price=price,
            shares=shares, stop_price=stop_price, target_price=target_price, peak_price=price,
            atr_at_entry=atr, trail_activate_pct=trail["activate_pct"], trail_distance_pct=trail["distance_pct"],
            max_hold_bars=max_hold_bars,
        )
        self._positions[ticker] = OpenPosition(
            ticker=ticker, position_id=position_id, trade_action_id=trade_action_id,
            direction=direction, entry_price=price, shares=shares,
            stop_price=stop_price, target_price=target_price, peak_price=price,
            trail_activate_pct=trail["activate_pct"], trail_distance_pct=trail["distance_pct"],
            max_hold_bars=max_hold_bars,
        )
        log_event("manual_entry", ticker=ticker,
                   detail=f"{direction} {shares:.2f} sh @ {price:.3f}, stop={stop_price:.3f}, target={target_price:.3f}")
        logger.info("Opened MANUAL paper position: %s %s @ %.3f, shares=%.2f", direction, ticker, price, shares)
        return {
            "trade_action_id": trade_action_id, "entry_price": price, "shares": shares,
            "stop_price": stop_price, "target_price": target_price,
        }

    def manual_exit(self, ticker: str, price: float) -> Optional[Dict]:
        """User-initiated close at the current market price, regardless of
        where price sits relative to the stop/target — same accounting path
        as an automatic exit (check_exit below), just a different trigger
        and exit_reason so the journal distinguishes the two."""
        position = self._positions.get(ticker)
        if position is None:
            return None
        pnl_result = pnl.compute_pnl(position.direction, position.entry_price, price, position.shares)
        record_outcome(
            position.trade_action_id, exit_price=price, exit_reason="manual",
            gross_pnl=pnl_result["gross_pnl"], net_pnl=pnl_result["net_pnl"], bars_held=position.bars_held,
        )
        close_open_position(position.position_id)
        del self._positions[ticker]
        log_event("manual_exit", ticker=ticker,
                   detail=f"closed manually @ {price:.3f}, net_pnl={pnl_result['net_pnl']:.2f}")
        logger.info("Closed MANUAL paper position: %s %s exit=%.3f net_pnl=%.2f",
                    position.direction, ticker, price, pnl_result["net_pnl"])
        return {
            "type": "trade_exit", "ticker": ticker, "direction": position.direction,
            "entry_price": position.entry_price, "exit_price": price, "exit_reason": "manual",
            "shares": position.shares, "gross_pnl": pnl_result["gross_pnl"], "net_pnl": pnl_result["net_pnl"],
            "bars_held": position.bars_held,
        }

    def update_manual(self, ticker: str, stop_price: Optional[float] = None,
                       target_price: Optional[float] = None, shares: Optional[float] = None) -> Optional[Dict]:
        """User-initiated adjustment of an open position's risk parameters.
        Unlike the trailing stop (which only ever ratchets favorably), a
        manual edit can move the stop/target either direction — that's the
        point of an override."""
        position = self._positions.get(ticker)
        if position is None:
            return None
        if stop_price is not None:
            position.stop_price = stop_price
        if target_price is not None:
            position.target_price = target_price
        if shares is not None:
            position.shares = shares
        update_open_position(
            position.position_id, stop_price=position.stop_price, target_price=position.target_price,
            shares=position.shares, peak_price=position.peak_price, bars_held=position.bars_held,
        )
        log_event("manual_update", ticker=ticker,
                   detail=f"stop={position.stop_price:.3f}, target={position.target_price:.3f}, shares={position.shares:.2f}")
        return {
            "ticker": ticker, "stop_price": position.stop_price,
            "target_price": position.target_price, "shares": position.shares,
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
