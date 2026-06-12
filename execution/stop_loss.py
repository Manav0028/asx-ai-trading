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

from config.settings import STOP_LOSS_PCT, IBKR_PAPER_ENABLED
from signals.watchlist import get_active_watchlist, update_watchlist_prices
from storage.cache import get_value, set_value
from alerts.telegram_bot import send_stop_loss_alert, send_target_alert, send_stale_exit_alert


def _execute_sell(ticker: str, reason: str, trading_mode: str = None):
    """
    Route sell to the correct executor based on the position's own trading_mode.
    - 'ibkr_paper' / 'live' → IBKR (requires IBKR_PAPER_ENABLED)
    - 'paper' / anything else → internal paper trader

    trading_mode should come from the watchlist position dict so we don't
    misroute legacy 'paper' positions when TRADING_PHASE has moved to 2+.
    """
    mode = trading_mode or "paper"
    if mode in ("ibkr_paper", "live") and IBKR_PAPER_ENABLED:
        from execution.ibkr_paper_trader import ibkr_execute_sell
        return ibkr_execute_sell(ticker, reason=reason)
    from execution.paper_trader import execute_sell
    return execute_sell(ticker, reason=reason)

logger = logging.getLogger(__name__)

# Static fallback constants (used when ATR/ADX data is unavailable)
TRAIL_ACTIVATE_PCT = 0.05   # Start trailing after 5% gain
TRAIL_DISTANCE_PCT = 0.05   # Trail 5% below the peak price
STALE_DAYS         = 45     # Exit if stuck this many days
STALE_MIN_MOVE_PCT = 2.0    # Only exit if move was <2% either way


def _get_trail_params(ticker: str, entry_price: float) -> tuple:
    """
    Return (activate_pct, distance_pct) for trailing stop.
    Pulls ATR from the technical engine for per-ticker calibration.
    Falls back to static defaults if ATR unavailable.
    """
    try:
        from ai_engine.technical_engine import get_technical_meta
        from signals.risk_params import compute_trail_params
        meta = get_technical_meta(ticker)
        atr  = meta.get("atr")
        if atr and entry_price:
            params = compute_trail_params(entry_price, atr)
            return params["trail_activate_pct"], params["trail_distance_pct"]
    except Exception:
        pass
    return TRAIL_ACTIVATE_PCT, TRAIL_DISTANCE_PCT


def _get_stale_days(ticker: str) -> int:
    """
    Return ADX-adjusted stale-exit threshold for a ticker.
    Trending stocks get more patience; choppy stocks exit sooner.
    """
    try:
        from ai_engine.technical_engine import get_technical_meta
        from signals.risk_params import compute_stale_days
        meta = get_technical_meta(ticker)
        return compute_stale_days(meta.get("adx"))
    except Exception:
        return STALE_DAYS


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
    Uses all_modes=True so legacy 'paper' positions are evaluated alongside
    'ibkr_paper' positions when TRADING_PHASE=2.
    """
    update_watchlist_prices()
    positions = get_active_watchlist(all_modes=True)

    stops_triggered = []
    targets_hit = []

    for pos in positions:
        ticker       = pos["ticker"]
        current      = pos.get("current_price")
        entry        = pos.get("entry_price")
        stop         = pos.get("stop_loss_price")
        target       = pos.get("target_price")
        days_held    = pos.get("days_held", 0)
        shares       = pos.get("shares", 0)
        pos_mode     = pos.get("trading_mode", "paper")   # route sell correctly
        short        = (pos.get("direction") or "long") == "short"

        if current is None or entry is None:
            continue

        if short:
            # Shorts: stop sits ABOVE entry, target BELOW. No trailing (yet).
            effective_stop = stop or (entry * (1 + STOP_LOSS_PCT))
            if current >= effective_stop:
                logger.warning(
                    "SHORT STOP: %s current=$%.3f stop=$%.3f",
                    ticker, current, effective_stop,
                )
                result = _execute_sell(ticker, reason="stop_loss", trading_mode=pos_mode)
                if result:
                    send_stop_loss_alert(
                        ticker, result["fill_price"], result["pnl"],
                        entry_price=entry, days_held=days_held,
                    )
                    stops_triggered.append({**result, "stop_price": effective_stop})
            elif target and current <= target:
                logger.info(
                    "SHORT TARGET: %s current=$%.3f target=$%.3f",
                    ticker, current, target,
                )
                result = _execute_sell(ticker, reason="target", trading_mode=pos_mode)
                if result:
                    send_target_alert(
                        ticker, result["fill_price"], result["pnl"],
                        entry_price=entry, days_held=days_held,
                    )
                    targets_hit.append({**result, "target_price": target})
            continue

        # ── Trailing stop (ATR-calibrated per ticker) ─────────────────────────
        trail_act, trail_dist = _get_trail_params(ticker, entry)
        gain_pct = (current - entry) / entry
        if gain_pct >= trail_act:
            peak = _get_peak(ticker, current)
            trail_stop = peak * (1 - trail_dist)
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
            result = _execute_sell(ticker, reason="stop_loss", trading_mode=pos_mode)
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
            result = _execute_sell(ticker, reason="target", trading_mode=pos_mode)
            if result:
                _clear_peak(ticker)
                send_target_alert(
                    ticker, result["fill_price"], result["pnl"],
                    entry_price=entry, days_held=days_held,
                )
                targets_hit.append({**result, "target_price": target})

    return stops_triggered, targets_hit


def intraday_evaluate_exits(live_prices: Dict[str, float]) -> Tuple[List[Dict], List[Dict]]:
    """
    Check stop-loss and target exits using live intraday prices.
    Called every 30 minutes during market hours by job_intraday_check().

    Differences from evaluate_exits():
    - Uses caller-supplied live prices instead of DB prices
    - Skips trailing stop updates (EOD-only concern)
    - Uses dedicated intraday Telegram alerts
    - No watchlist price refresh (prices come in from yfinance directly)
    """
    from alerts.telegram_bot import send_intraday_stop_alert, send_intraday_target_alert

    positions = get_active_watchlist(all_modes=True)
    stops_triggered: List[Dict] = []
    targets_hit:     List[Dict] = []

    for pos in positions:
        ticker    = pos["ticker"]
        current   = live_prices.get(ticker)
        entry     = pos.get("entry_price")
        stop      = pos.get("stop_loss_price")
        target    = pos.get("target_price")
        days_held = pos.get("days_held", 0)
        pos_mode  = pos.get("trading_mode", "paper")   # route sell correctly
        short     = (pos.get("direction") or "long") == "short"

        if current is None or entry is None:
            continue

        if short:
            effective_stop = stop or (entry * (1 + STOP_LOSS_PCT))
            if current >= effective_stop:
                result = _execute_sell(ticker, reason="intraday_stop", trading_mode=pos_mode)
                if result:
                    send_intraday_stop_alert(
                        ticker, current, effective_stop, result["pnl"],
                        entry_price=entry, days_held=days_held,
                    )
                    stops_triggered.append({**result, "stop_price": effective_stop})
            elif target and current <= target:
                result = _execute_sell(ticker, reason="intraday_target", trading_mode=pos_mode)
                if result:
                    send_intraday_target_alert(
                        ticker, current, target, result["pnl"],
                        entry_price=entry, days_held=days_held,
                    )
                    targets_hit.append({**result, "target_price": target})
            continue

        # ── Hard stop-loss ────────────────────────────────────────────────────
        effective_stop = stop or (entry * (1 - STOP_LOSS_PCT))
        if current <= effective_stop:
            logger.warning(
                "INTRADAY STOP: %s live=$%.3f stop=$%.3f",
                ticker, current, effective_stop,
            )
            result = _execute_sell(ticker, reason="intraday_stop", trading_mode=pos_mode)
            if result:
                _clear_peak(ticker)
                send_intraday_stop_alert(
                    ticker, current, effective_stop, result["pnl"],
                    entry_price=entry, days_held=days_held,
                )
                stops_triggered.append({**result, "stop_price": effective_stop})
            continue

        # ── Target hit ────────────────────────────────────────────────────────
        if target and current >= target:
            logger.info(
                "INTRADAY TARGET: %s live=$%.3f target=$%.3f",
                ticker, current, target,
            )
            result = _execute_sell(ticker, reason="intraday_target", trading_mode=pos_mode)
            if result:
                _clear_peak(ticker)
                send_intraday_target_alert(
                    ticker, current, target, result["pnl"],
                    entry_price=entry, days_held=days_held,
                )
                targets_hit.append({**result, "target_price": target})

    if stops_triggered or targets_hit:
        logger.info(
            "Intraday check: %d stop(s) + %d target(s) triggered",
            len(stops_triggered), len(targets_hit),
        )
    return stops_triggered, targets_hit


def check_stale_positions() -> List[Dict]:
    """Exit positions that have gone nowhere after the ADX-adjusted stale threshold."""
    positions = get_active_watchlist(all_modes=True)
    exited = []
    for pos in positions:
        stale_threshold = _get_stale_days(pos["ticker"])
        if pos["days_held"] < stale_threshold:
            continue
        move_pct = abs(pos.get("unrealised_pnl_pct") or 0)
        if move_pct < STALE_MIN_MOVE_PCT:
            ticker   = pos["ticker"]
            pos_mode = pos.get("trading_mode", "paper")
            logger.info(
                "Stale exit: %s held %d days, move only %.1f%%",
                ticker, pos["days_held"], move_pct,
            )
            result = _execute_sell(ticker, reason="stale", trading_mode=pos_mode)
            if result:
                send_stale_exit_alert(
                    ticker, result["fill_price"], result["pnl"], pos["days_held"]
                )
                exited.append(result)
    return exited
