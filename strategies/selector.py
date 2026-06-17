"""
Strategy Engine — Per-Stock Strategy Selector
Backtests every strategy in the library against each ticker's own history,
validates on the out-of-sample forward window, and assigns the best-performing
validated strategy to that ticker. Assignments are persisted so the signal
pipeline and order placement can gate on them.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy.dialects.postgresql import insert

from storage.database import get_session
from storage.models import Price, StrategyAssignment
from strategies.backtest import is_validated, rank_score, run_strategy_backtest
from strategies.indicators import precompute
from strategies.library import ALL_STRATEGIES, STRATEGY_BY_NAME

logger = logging.getLogger(__name__)

MIN_BARS = 120              # need enough history for a meaningful 70/30 split
ASSIGNMENT_MAX_AGE_DAYS = 21  # re-select if older (weekly job keeps these fresh)


def _load_ohlcv(ticker: str, days: int = 760) -> Optional[Dict[str, np.ndarray]]:
    with get_session() as session:
        rows = (
            session.query(Price.date, Price.open, Price.high, Price.low, Price.close, Price.volume)
            .filter(Price.ticker == ticker)
            .order_by(Price.date.desc())
            .limit(days)
            .all()
        )
    if len(rows) < MIN_BARS:
        return None
    rows = list(reversed(rows))  # oldest → newest
    return {
        "opens":   np.array([r.open or r.close for r in rows], dtype=float),
        "highs":   np.array([r.high or r.close for r in rows], dtype=float),
        "lows":    np.array([r.low or r.close for r in rows], dtype=float),
        "closes":  np.array([r.close for r in rows], dtype=float),
        "volumes": np.array([r.volume or 0 for r in rows], dtype=float),
    }


def select_for_ticker(ticker: str) -> Optional[Dict]:
    """
    Run all strategies through backtest + forward test on this ticker.
    Persists and returns the assignment (best validated strategy, or the
    top-ranked one flagged validated=False when nothing passes the gates).
    """
    ohlcv = _load_ohlcv(ticker)
    if ohlcv is None:
        logger.debug("%s: insufficient price history for strategy selection", ticker)
        return None

    ind = precompute(ohlcv)
    candidates = []
    for strat in ALL_STRATEGIES:
        result = run_strategy_backtest(strat, ind)
        candidates.append({
            "strategy": strat.name,
            "validated": is_validated(result),
            "rank": rank_score(result),
            **result,
        })

    validated = [c for c in candidates if c["validated"]]
    pool = validated or candidates
    best = max(pool, key=lambda c: (c["rank"], c["backtest"]["num_trades"]))

    row = {
        "ticker": ticker,
        "strategy_name": best["strategy"],
        "direction": getattr(STRATEGY_BY_NAME.get(best["strategy"]), "direction", "long"),
        "validated": best["validated"],
        "bt_trades": best["backtest"]["num_trades"],
        "bt_win_rate": best["backtest"]["win_rate"],
        "bt_profit_factor": best["backtest"]["profit_factor"],
        "bt_avg_return_pct": best["backtest"]["avg_return_pct"],
        "bt_max_drawdown_pct": best["backtest"]["max_drawdown_pct"],
        "fw_trades": best["forward"]["num_trades"],
        "fw_win_rate": best["forward"]["win_rate"],
        "fw_profit_factor": best["forward"]["profit_factor"],
        "fw_total_return_pct": best["forward"]["total_return_pct"],
        "rank_score": best["rank"],
        "assigned_at": datetime.utcnow(),
    }

    with get_session() as session:
        stmt = insert(StrategyAssignment).values(**row).on_conflict_do_update(
            index_elements=["ticker"],
            set_={k: v for k, v in row.items() if k != "ticker"},
        )
        session.execute(stmt)

    logger.info(
        "%s → %s %s (bt: %d trades pf=%.2f wr=%.0f%% | fw: %d trades pf=%.2f)",
        ticker, best["strategy"], "VALIDATED" if best["validated"] else "unvalidated",
        row["bt_trades"], row["bt_profit_factor"], row["bt_win_rate"] * 100,
        row["fw_trades"], row["fw_profit_factor"],
    )
    return row


def run_strategy_selection(tickers: List[str]) -> Dict:
    """Batch selection across the universe. Returns summary counts."""
    total = validated = skipped = 0
    by_strategy: Dict[str, int] = {}
    for ticker in tickers:
        try:
            row = select_for_ticker(ticker)
        except Exception as e:
            logger.warning("Strategy selection failed for %s: %s", ticker, e)
            continue
        if row is None:
            skipped += 1
            continue
        total += 1
        if row["validated"]:
            validated += 1
            by_strategy[row["strategy_name"]] = by_strategy.get(row["strategy_name"], 0) + 1

    logger.info(
        "Strategy selection complete: %d assigned, %d validated, %d skipped | mix: %s",
        total, validated, skipped,
        ", ".join(f"{k}={v}" for k, v in sorted(by_strategy.items())) or "none",
    )
    return {"total": total, "validated": validated, "skipped": skipped, "mix": by_strategy}


def get_assignment(ticker: str) -> Optional[Dict]:
    """Return the persisted assignment for a ticker, or None if missing/stale."""
    with get_session() as session:
        row = (
            session.query(StrategyAssignment)
            .filter(StrategyAssignment.ticker == ticker)
            .first()
        )
        if row is None:
            return None
        if row.assigned_at and row.assigned_at < datetime.utcnow() - timedelta(days=ASSIGNMENT_MAX_AGE_DAYS):
            return None  # stale — treat as unassigned until the weekly job refreshes it
        return {
            "ticker": row.ticker,
            "strategy_name": row.strategy_name,
            "validated": bool(row.validated),
            "bt_profit_factor": row.bt_profit_factor,
            "fw_profit_factor": row.fw_profit_factor,
            "rank_score": row.rank_score,
        }


def get_strategy_signal(ticker: str) -> Optional[Dict]:
    """
    Evaluate whether ANY validated strategy fires for this ticker today.

    Priority order:
      1. Assigned+validated strategy fires → use it (original behaviour)
      2. Assigned+validated strategy silent → scan all strategies, take
         the first alternative that (a) fires today AND (b) passes inline
         backtest validation. This prevents a ticker being blocked simply
         because its primary pattern isn't set up today when another edge is.
      3. Assigned+unvalidated → block (no proven edge on this stock)
      4. No assignment → return None (caller uses composite-only path)
    """
    assignment = get_assignment(ticker)
    if assignment is None:
        return None

    primary_strat = STRATEGY_BY_NAME.get(assignment["strategy_name"])
    if primary_strat is None:
        return None

    base_result = {
        "strategy": primary_strat.name,
        "direction": getattr(primary_strat, "direction", "long"),
        "validated": assignment["validated"],
        "fires": False,
        "stop_mult": primary_strat.stop_mult,
        "target_mult": primary_strat.target_mult,
        "max_hold_days": primary_strat.max_hold_days,
        "confidence": 0.0,
        "reason": "no entry condition today",
    }
    if not assignment["validated"]:
        base_result["reason"] = "strategy not validated by backtest/forward test"
        return base_result

    # 400 bars: enough for 260-bar warmup + 70/30 split validation
    ohlcv = _load_ohlcv(ticker, days=400)
    if ohlcv is None:
        return base_result

    ind = precompute(ohlcv)

    # 1. Try the assigned strategy first
    try:
        fired = primary_strat.evaluate_latest(ind)
        if fired:
            base_result.update({"fires": True, **fired})
            return base_result
    except Exception as e:
        logger.debug("Primary strategy evaluate failed for %s: %s", ticker, e)

    # 2. Scan all alternatives — take first that fires AND passes inline validation
    for alt in ALL_STRATEGIES:
        if alt.name == primary_strat.name:
            continue
        try:
            fired = alt.evaluate_latest(ind)
            if not fired:
                continue
            result = run_strategy_backtest(alt, ind)
            if is_validated(result):
                logger.info(
                    "%s: primary strategy silent; firing alternative %s (%s)",
                    ticker, alt.name, fired.get("reason", ""),
                )
                return {
                    "strategy": alt.name,
                    "direction": getattr(alt, "direction", "long"),
                    "validated": True,
                    "fires": True,
                    "stop_mult": alt.stop_mult,
                    "target_mult": alt.target_mult,
                    "max_hold_days": alt.max_hold_days,
                    **fired,
                }
        except Exception as e:
            logger.debug("Alt strategy %s failed for %s: %s", alt.name, ticker, e)

    return base_result
