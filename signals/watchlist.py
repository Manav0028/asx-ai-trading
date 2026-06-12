"""
Layer 04 · Signal Intelligence — Watchlist Manager
Tracks active positions: entry, target, stop-loss, P&L, days held.

Trading mode segregation:
  trading_mode = 'paper'       → internal simulation (TRADING_PHASE 1)
  trading_mode = 'ibkr_paper'  → IBKR paper account  (TRADING_PHASE 2)
  trading_mode = 'live'        → IBKR live account    (TRADING_PHASE 3)

All queries filter by the CURRENT trading mode so the two datasets
never mix — historical internal-paper positions stay visible when
TRADING_PHASE=2, but only as read-only history.
"""
import logging
import os
from datetime import date
from typing import Dict, List, Optional

from storage.database import get_session
from storage.models import WatchlistItem
from data_ingestion.price_fetcher import get_latest_price

logger = logging.getLogger(__name__)


# ── Current trading mode ──────────────────────────────────────────────────────

def _current_trading_mode() -> str:
    """Derive trading_mode string from TRADING_PHASE env var."""
    phase = int(os.environ.get("TRADING_PHASE", "1"))
    if phase >= 3:
        return "live"
    if phase == 2:
        return "ibkr_paper"
    return "paper"


def _active_ticker_suffix() -> Optional[str]:
    """Return the ticker suffix for the active exchange (e.g. '.AX' or '.NS').
    Used to segregate positions by exchange without an exchange column in the DB."""
    try:
        from config import get_active_exchange
        tickers = get_active_exchange().tickers
        if tickers:
            t = tickers[0]
            dot = t.rfind(".")
            return t[dot:] if dot >= 0 else None
    except Exception:
        pass
    return None


# ── Write operations ──────────────────────────────────────────────────────────

def add_to_watchlist(
    ticker: str,
    entry_price: float,
    target_price: float,
    stop_loss_price: float,
    shares: int,
    position_size_aud: float,
    signal_score: float,
    trading_mode: str = None,          # defaults to current phase mode
    direction: str = "long",           # 'long' | 'short'
) -> WatchlistItem:
    mode = trading_mode or _current_trading_mode()

    with get_session() as session:
        # Only block duplicate if same mode is already active
        existing = (
            session.query(WatchlistItem)
            .filter(
                WatchlistItem.ticker == ticker,
                WatchlistItem.trading_mode == mode,
                WatchlistItem.is_active == True,
            )
            .first()
        )
        if existing:
            logger.info("%s already in %s watchlist", ticker, mode)
            return existing

        item = WatchlistItem(
            ticker=ticker,
            entry_date=date.today(),
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            shares=shares,
            position_size_aud=position_size_aud,
            current_price=entry_price,
            unrealised_pnl=0.0,
            unrealised_pnl_pct=0.0,
            days_held=0,
            signal_score=signal_score,
            trading_mode=mode,
            direction=direction,
            is_active=True,
        )
        session.add(item)
        logger.info("Added %s to %s watchlist at $%.3f", ticker, mode, entry_price)
        return item


def update_watchlist_prices() -> List[Dict]:
    """Refresh current prices and P&L for all active watchlist items (all modes)."""
    updated = []
    with get_session() as session:
        items = session.query(WatchlistItem).filter(WatchlistItem.is_active == True).all()
        for item in items:
            current = get_latest_price(item.ticker)
            if current is None:
                continue
            item.current_price = current
            sign = -1 if (getattr(item, "direction", None) or "long") == "short" else 1
            pnl = sign * (current - item.entry_price) * item.shares
            item.unrealised_pnl = round(pnl, 2)
            item.unrealised_pnl_pct = round(
                sign * (current - item.entry_price) / item.entry_price * 100, 2
            )
            item.days_held = (date.today() - item.entry_date).days
            updated.append({
                "ticker": item.ticker,
                "entry_price": item.entry_price,
                "current_price": current,
                "unrealised_pnl": item.unrealised_pnl,
                "unrealised_pnl_pct": item.unrealised_pnl_pct,
                "days_held": item.days_held,
                "target_price": item.target_price,
                "stop_loss_price": item.stop_loss_price,
                "trading_mode": item.trading_mode,
            })
    return updated


def remove_from_watchlist(ticker: str, reason: str = "manual",
                          trading_mode: str = None) -> None:
    mode = trading_mode or _current_trading_mode()
    with get_session() as session:
        item = (
            session.query(WatchlistItem)
            .filter(
                WatchlistItem.ticker == ticker,
                WatchlistItem.trading_mode == mode,
                WatchlistItem.is_active == True,
            )
            .first()
        )
        if item:
            item.is_active = False
            logger.info("Removed %s from %s watchlist (reason: %s)", ticker, mode, reason)


# ── Read operations ───────────────────────────────────────────────────────────

def get_active_watchlist(trading_mode: str = None,
                         all_modes: bool = False) -> List[Dict]:
    """
    Return active positions.

    trading_mode=None  → filter by current TRADING_PHASE mode (default)
    trading_mode='...' → filter by explicit mode
    all_modes=True     → return all modes (used by dashboard history view)
    """
    mode = trading_mode or _current_trading_mode()
    suffix = _active_ticker_suffix()

    with get_session() as session:
        q = session.query(WatchlistItem).filter(WatchlistItem.is_active == True)
        if not all_modes:
            q = q.filter(WatchlistItem.trading_mode == mode)
        items = q.order_by(WatchlistItem.unrealised_pnl_pct.desc()).all()

        return [
            {
                "ticker":           i.ticker,
                "entry_date":       i.entry_date,
                "entry_price":      i.entry_price,
                "current_price":    i.current_price,
                "target_price":     i.target_price,
                "stop_loss_price":  i.stop_loss_price,
                "shares":           i.shares,
                "position_size_aud": i.position_size_aud,
                "unrealised_pnl":   i.unrealised_pnl,
                "unrealised_pnl_pct": i.unrealised_pnl_pct,
                "days_held":        i.days_held,
                "signal_score":     i.signal_score,
                "trading_mode":     i.trading_mode,
                "direction":        getattr(i, "direction", None) or "long",
            }
            for i in items
            if suffix is None or i.ticker.endswith(suffix)
        ]


def get_watchlist_summary(trading_mode: str = None) -> Dict:
    positions = get_active_watchlist(trading_mode=trading_mode)
    total_pnl = sum(p["unrealised_pnl"] or 0 for p in positions)
    winners   = sum(1 for p in positions if (p["unrealised_pnl"] or 0) > 0)
    return {
        "total_positions":       len(positions),
        "total_unrealised_pnl":  round(total_pnl, 2),
        "winners":               winners,
        "losers":                len(positions) - winners,
        "positions":             positions,
        "trading_mode":          trading_mode or _current_trading_mode(),
    }
