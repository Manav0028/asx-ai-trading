"""
Layer 05 · Execution — Stop-Loss, Trailing Stop & Position Management
- Hard stop: -7% from entry (configurable)
- Trailing stop: locks in gains when stock rises >5%, trails at -5% from peak
- Target exit: auto-sell at ATR-based target
- Stale exit: closes positions stuck >45 days with <2% move
"""
import logging
from datetime import date
from typing import Dict, List, Tuple

from config.settings import STOP_LOSS_PCT
from signals.watchlist import get_active_watchlist, update_watchlist_prices
from execution.paper_trader import execute_sell
from storage.cache import get_value, set_value
from alerts.telegram_bot import send_stop_loss_alert, send_target_alert, send_stale_exit_alert

logger = logging.getLogger(__name__)

TRAIL_ACTIVATE_PCT = 0.05   # Start trailing after 5% gain
TRAIL_DISTANCE_PCT = 0.05   # Trail 5% below the peak price
STALE_DAYS         = 45     # Exit if stuck this many days
STALE_MIN_MOVE_PCT = 2.0    # Only exit if move was <2% either way


def _get_peak(ticker: str, current: float) -> float:
    """Retrieve or initialise the peak price for trailing stop."""
    key = f"trail_peak:{ticker}"
    peak = get_value(key)
    if peak is None or current > peak:
        set_value(key, current, ttl=3600 * 24 * 90)
        return current
    return float(peak)


def _clear_peak(ticker: str) -> None:
    from storage.cache import delete_key
    delete_key(f"trail_peak:{ticker}")


def evaluate_exits() -> Tuple[List[Dict], List[Dict]]:
    """
    Evaluate all active positions for exit conditions.
    Returns (stops_triggered, targets_hit).
    """
    update_watchlist_prices()
    positions = get_active_watchlist()

    stops_triggered = []
    targets_hit = []

    for pos in positions:
        ticker     = pos["ticker"]
        current    = pos.get("current_price")
        entry      = pos.get("entry_price")
        stop       = pos.get("stop_loss_price")
        target     = pos.get("target_price")
        days_held  = pos.get("days_held", 0)
        shares     = pos.get("shares", 0)

        if current is None or entry is None:
            continue

        # ── Trailing stop ─────────────────────────────────────────────────────
        gain_pct = (current - entry) / entry
        if gain_pct >= TRAIL_ACTIVATE_PCT:
            peak = _get_peak(ticker, current)
            trail_stop = peak * (1 - TRAIL_DISTANCE_PCT)
            # Update the watchlist stop-loss to the trailing level
            from storage.database import get_session
            from storage.models import WatchlistItem
            with get_session() as session:
                item = session.query(WatchlistItem).filter(
                    WatchlistItem.ticker == ticker,
                    WatchlistItem.is_active == True
                ).first()
                if item and trail_stop > (item.stop_loss_price or 0):
                    item.stop_loss_price = round(trail_stop, 3)
                    stop = trail_stop
                    logger.info(
                        "%s trailing stop updated to $%.3f (peak $%.3f)",
                        ticker, trail_stop, peak
                    )
        else:
            _get_peak(ticker, current)  # initialise peak tracking

        # ── Hard stop-loss ────────────────────────────────────────────────────
        effective_stop = stop or (entry * (1 - STOP_LOSS_PCT))
        if current <= effective_stop:
            loss_pct = (current - entry) / entry * 100
            logger.warning(
                "STOP-LOSS: %s current=$%.3f stop=$%.3f (%.1f%%)",
                ticker, current, effective_stop, loss_pct,
            )
            result = execute_sell(ticker, reason="stop_loss")
            if result:
                _clear_peak(ticker)
                send_stop_loss_alert(
                    ticker, result["fill_price"], result["pnl"],
                    entry_price=entry, days_held=days_held,
                )
                stops_triggered.append({**result, "stop_price": effective_stop})
            continue

        # ── Target hit ────────────────────────────────────────────────────────
        if target and current >= target:
            gain_pct_display = (current - entry) / entry * 100
            logger.info(
                "TARGET HIT: %s current=$%.3f target=$%.3f (+%.1f%%)",
                ticker, current, target, gain_pct_display,
            )
            result = execute_sell(ticker, reason="target")
            if result:
                _clear_peak(ticker)
                send_target_alert(
                    ticker, result["fill_price"], result["pnl"],
                    entry_price=entry, days_held=days_held,
                )
                targets_hit.append({**result, "target_price": target})

    return stops_triggered, targets_hit


def check_stale_positions() -> List[Dict]:
    """Exit positions that have gone nowhere after STALE_DAYS days."""
    positions = get_active_watchlist()
    exited = []
    for pos in positions:
        if pos["days_held"] < STALE_DAYS:
            continue
        move_pct = abs(pos.get("unrealised_pnl_pct") or 0)
        if move_pct < STALE_MIN_MOVE_PCT:
            ticker = pos["ticker"]
            logger.info(
                "Stale exit: %s held %d days, move only %.1f%%",
                ticker, pos["days_held"], move_pct,
            )
            result = execute_sell(ticker, reason="stale")
            if result:
                send_stale_exit_alert(
                    ticker, result["fill_price"], result["pnl"], pos["days_held"]
                )
                exited.append(result)
    return exited
