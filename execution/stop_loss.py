"""
Layer 05 · Execution — Stop-Loss & Target Engine
Runs at 4:00 PM after market close.
Evaluates all watchlist positions and triggers exits.
"""
import logging
from typing import Dict, List, Tuple

from signals.watchlist import get_active_watchlist, update_watchlist_prices
from execution.paper_trader import execute_sell

logger = logging.getLogger(__name__)


def evaluate_exits() -> Tuple[List[Dict], List[Dict]]:
    """
    Check all active positions for stop-loss or target hits.
    Returns (stop_losses_triggered, targets_hit).
    """
    update_watchlist_prices()
    positions = get_active_watchlist()

    stops_triggered = []
    targets_hit = []

    for pos in positions:
        ticker = pos["ticker"]
        current = pos["current_price"]
        stop = pos["stop_loss_price"]
        target = pos["target_price"]
        entry = pos["entry_price"]

        if current is None:
            continue

        if current <= stop:
            loss_pct = (current - entry) / entry * 100
            logger.warning(
                "STOP-LOSS triggered: %s current=$%.3f stop=$%.3f (%.1f%%)",
                ticker, current, stop, loss_pct,
            )
            result = execute_sell(ticker, reason="stop_loss")
            if result:
                stops_triggered.append({**result, "stop_price": stop})

        elif current >= target:
            gain_pct = (current - entry) / entry * 100
            logger.info(
                "TARGET HIT: %s current=$%.3f target=$%.3f (+%.1f%%)",
                ticker, current, target, gain_pct,
            )
            result = execute_sell(ticker, reason="target")
            if result:
                targets_hit.append({**result, "target_price": target})

    if stops_triggered:
        logger.info("%d stop-loss exits executed", len(stops_triggered))
    if targets_hit:
        logger.info("%d target exits executed", len(targets_hit))

    return stops_triggered, targets_hit


def check_stale_positions(max_days: int = 60) -> List[Dict]:
    """Exit positions held longer than max_days with no meaningful move."""
    positions = get_active_watchlist()
    exited = []
    for pos in positions:
        if pos["days_held"] >= max_days:
            pnl_pct = pos["unrealised_pnl_pct"] or 0
            if abs(pnl_pct) < 3:  # no meaningful move after 60 days
                logger.info(
                    "Exiting stale position: %s held %d days, P&L=%.1f%%",
                    pos["ticker"], pos["days_held"], pnl_pct,
                )
                result = execute_sell(pos["ticker"], reason="stale")
                if result:
                    exited.append(result)
    return exited
