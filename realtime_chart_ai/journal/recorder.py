"""
The journal write path — every function here is a thin, synchronous DB write.
Called from the signal engine and data-source manager so that "keep track of
everything" is enforced at the source, not bolted on later.
"""
import logging
from typing import Dict, List, Optional

from journal.db import get_session
from journal.models import RtcBar, RtcChartInterpretation, RtcEvent, RtcTradeAction, RtcTradeOutcome

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
            source="ibkr", delayed=False,
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
                   order_id: Optional[str] = None) -> int:
    with get_session() as session:
        row = RtcTradeAction(
            interpretation_id=interpretation_id, action_type=action_type, mode=mode,
            entry_price=entry_price, shares=shares, order_id=order_id,
        )
        session.add(row)
        session.flush()
        return row.id


def record_outcome(trade_action_id: int, exit_price: float, exit_reason: str,
                    gross_pnl: Optional[float] = None, net_pnl: Optional[float] = None) -> None:
    from datetime import datetime
    with get_session() as session:
        session.add(RtcTradeOutcome(
            trade_action_id=trade_action_id, exit_price=exit_price, exit_ts=datetime.utcnow(),
            exit_reason=exit_reason, gross_pnl=gross_pnl, net_pnl=net_pnl,
        ))


def query_history(ticker: Optional[str] = None, limit: int = 50) -> List[Dict]:
    with get_session() as session:
        q = session.query(RtcChartInterpretation).order_by(RtcChartInterpretation.created_at.desc())
        if ticker:
            q = q.filter(RtcChartInterpretation.ticker == ticker)
        rows = q.limit(limit).all()
        results = []
        for row in rows:
            action = (
                session.query(RtcTradeAction)
                .filter(RtcTradeAction.interpretation_id == row.id)
                .first()
            )
            outcome = None
            if action:
                outcome = (
                    session.query(RtcTradeOutcome)
                    .filter(RtcTradeOutcome.trade_action_id == action.id)
                    .first()
                )
            results.append({
                "id": row.id, "ticker": row.ticker, "bar_ts": row.bar_ts.isoformat(),
                "pattern_name": row.pattern_name, "pattern_type": row.pattern_type,
                "direction": row.direction, "confidence": row.confidence,
                "composite_score": row.composite_score, "rule_reason": row.rule_reason,
                "smc_zone": row.smc_zone, "claude_rationale": row.claude_rationale,
                "action": {"action_type": action.action_type, "mode": action.mode,
                           "entry_price": action.entry_price} if action else None,
                "outcome": {"exit_price": outcome.exit_price, "exit_reason": outcome.exit_reason,
                            "net_pnl": outcome.net_pnl} if outcome else None,
            })
        return results
