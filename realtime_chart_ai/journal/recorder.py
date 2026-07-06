"""
The journal write path — every function here is a thin, synchronous DB write.
Called from the signal engine and data-source manager so that "keep track of
everything" is enforced at the source, not bolted on later.
"""
import logging
from typing import Dict, List, Optional

from journal.db import get_session
from journal.models import (
    RtcBar, RtcChartInterpretation, RtcEvent, RtcOpenPosition, RtcTradeAction, RtcTradeOutcome,
)

logger = logging.getLogger(__name__)


def log_bar(ticker: str, timeframe: str, ind: Dict) -> None:
    if not ind.get("closes"):
        return
    i = len(ind["closes"]) - 1
    with get_session() as session:
        session.add(RtcBar(
            ticker=ticker, timeframe=timeframe, bar_ts=ind["timestamps"][i],
            open=ind["opens"][i], high=ind["highs"][i], low=ind["lows"][i],
            close=ind["closes"][i], volume=ind["volumes"][i],
            source=ind["sources"][i] if ind.get("sources") else "unknown",
            delayed=ind["delayed"][i] if ind.get("delayed") else False,
        ))


def log_event(event_type: str, source: Optional[str] = None, ticker: Optional[str] = None,
              detail: Optional[str] = None) -> None:
    try:
        with get_session() as session:
            session.add(RtcEvent(event_type=event_type, source=source, ticker=ticker, detail=detail))
    except Exception:
        logger.exception("Failed to write rtc_events row (event_type=%s)", event_type)


def write_interpretation(signal: Dict) -> int:
    """signal is expected to carry: ticker, bar_ts, timeframe, data_source,
    pattern_name, pattern_type, direction, confidence, composite_score,
    rule_reason, mtf_confluence, mtf_summary, smc_zone, smc_context,
    claude_rationale, claude_model, price_at_signal."""
    with get_session() as session:
        row = RtcChartInterpretation(**signal)
        session.add(row)
        session.flush()
        return row.id


def record_action(interpretation_id: int, action_type: str, mode: str,
                   entry_price: Optional[float] = None, shares: Optional[float] = None,
                   order_id: Optional[str] = None, stop_price: Optional[float] = None,
                   target_price: Optional[float] = None, composite_score_at_entry: Optional[float] = None,
                   dollar_risk: Optional[float] = None, score_multiplier: Optional[float] = None,
                   atr_at_entry: Optional[float] = None) -> int:
    with get_session() as session:
        row = RtcTradeAction(
            interpretation_id=interpretation_id, action_type=action_type, mode=mode,
            entry_price=entry_price, shares=shares, order_id=order_id,
            stop_price=stop_price, target_price=target_price,
            composite_score_at_entry=composite_score_at_entry, dollar_risk=dollar_risk,
            score_multiplier=score_multiplier, atr_at_entry=atr_at_entry,
        )
        session.add(row)
        session.flush()
        return row.id


def record_outcome(trade_action_id: int, exit_price: float, exit_reason: str,
                    gross_pnl: Optional[float] = None, net_pnl: Optional[float] = None,
                    bars_held: Optional[int] = None) -> None:
    from datetime import datetime
    with get_session() as session:
        session.add(RtcTradeOutcome(
            trade_action_id=trade_action_id, exit_price=exit_price, exit_ts=datetime.utcnow(),
            exit_reason=exit_reason, gross_pnl=gross_pnl, net_pnl=net_pnl, bars_held=bars_held,
        ))


def open_position_row(ticker: str, trade_action_id: int, direction: str, entry_price: float,
                       shares: float, stop_price: float, target_price: float, peak_price: float,
                       atr_at_entry: float, trail_activate_pct: float, trail_distance_pct: float,
                       max_hold_bars: int) -> int:
    with get_session() as session:
        row = RtcOpenPosition(
            ticker=ticker, trade_action_id=trade_action_id, direction=direction,
            entry_price=entry_price, shares=shares, stop_price=stop_price, target_price=target_price,
            peak_price=peak_price, atr_at_entry=atr_at_entry, trail_activate_pct=trail_activate_pct,
            trail_distance_pct=trail_distance_pct, max_hold_bars=max_hold_bars, bars_held=0, status="open",
        )
        session.add(row)
        session.flush()
        return row.id


def update_open_position(position_id: int, stop_price: Optional[float] = None,
                          peak_price: Optional[float] = None, bars_held: Optional[int] = None,
                          target_price: Optional[float] = None, shares: Optional[float] = None) -> None:
    with get_session() as session:
        row = session.get(RtcOpenPosition, position_id)
        if row is None:
            return
        if stop_price is not None:
            row.stop_price = stop_price
        if peak_price is not None:
            row.peak_price = peak_price
        if bars_held is not None:
            row.bars_held = bars_held
        # target_price/shares only ever change via a manual override (the
        # automated exit-check path never touches either) — added here
        # rather than a separate function so both paths write through the
        # same row-update helper.
        if target_price is not None:
            row.target_price = target_price
        if shares is not None:
            row.shares = shares


def close_open_position(position_id: int) -> None:
    with get_session() as session:
        row = session.get(RtcOpenPosition, position_id)
        if row is not None:
            row.status = "closed"


def get_open_positions(ticker: Optional[str] = None) -> List[Dict]:
    with get_session() as session:
        q = session.query(RtcOpenPosition).filter(RtcOpenPosition.status == "open")
        if ticker:
            q = q.filter(RtcOpenPosition.ticker == ticker)
        return [{
            "id": r.id, "ticker": r.ticker, "trade_action_id": r.trade_action_id,
            "direction": r.direction, "entry_price": r.entry_price, "shares": r.shares,
            "stop_price": r.stop_price, "target_price": r.target_price, "peak_price": r.peak_price,
            "atr_at_entry": r.atr_at_entry, "trail_activate_pct": r.trail_activate_pct,
            "trail_distance_pct": r.trail_distance_pct, "max_hold_bars": r.max_hold_bars,
            "bars_held": r.bars_held, "opened_at": r.opened_at.isoformat(),
        } for r in q.all()]


def query_history(ticker: Optional[str] = None, limit: int = 50,
                   start=None, end=None) -> List[Dict]:
    """`start`/`end` are datetimes (inclusive), filtered against bar_ts — for
    the frontend's global Trades view, which needs a date-range filter across
    every ticker rather than just the currently-selected one."""
    with get_session() as session:
        q = session.query(RtcChartInterpretation).order_by(RtcChartInterpretation.created_at.desc())
        if ticker:
            q = q.filter(RtcChartInterpretation.ticker == ticker)
        if start is not None:
            q = q.filter(RtcChartInterpretation.bar_ts >= start)
        if end is not None:
            q = q.filter(RtcChartInterpretation.bar_ts <= end)
        rows = q.limit(limit).all()
        if not rows:
            return []

        # Batched instead of one query per row (2 extra round trips per row,
        # e.g. up to 1000 for limit=500) — fine at limit=50 scoped to a
        # single ticker, but against a remote Postgres this made the
        # unfiltered global Trades-tab query (limit=500, no ticker) hang for
        # a minute+ rather than returning. Three queries total regardless of
        # `limit` instead of up to 2*limit+1.
        interp_ids = [row.id for row in rows]
        actions = (
            session.query(RtcTradeAction)
            .filter(RtcTradeAction.interpretation_id.in_(interp_ids))
            .all()
        )
        actions_by_interp = {a.interpretation_id: a for a in actions}
        action_ids = [a.id for a in actions]
        outcomes = (
            session.query(RtcTradeOutcome).filter(RtcTradeOutcome.trade_action_id.in_(action_ids)).all()
            if action_ids else []
        )
        outcomes_by_action = {o.trade_action_id: o for o in outcomes}

        results = []
        for row in rows:
            action = actions_by_interp.get(row.id)
            outcome = outcomes_by_action.get(action.id) if action else None
            results.append({
                "id": row.id, "ticker": row.ticker, "bar_ts": row.bar_ts.isoformat(),
                "pattern_name": row.pattern_name, "pattern_type": row.pattern_type,
                "direction": row.direction, "confidence": row.confidence,
                "composite_score": row.composite_score, "rule_reason": row.rule_reason,
                "smc_zone": row.smc_zone, "claude_rationale": row.claude_rationale,
                "action": {"action_type": action.action_type, "mode": action.mode,
                           "entry_price": action.entry_price, "shares": action.shares,
                           "stop_price": action.stop_price, "target_price": action.target_price} if action else None,
                "outcome": {"exit_price": outcome.exit_price, "exit_reason": outcome.exit_reason,
                            "gross_pnl": outcome.gross_pnl, "net_pnl": outcome.net_pnl,
                            "bars_held": outcome.bars_held} if outcome else None,
            })
        return results
