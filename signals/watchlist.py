"""
Layer 04 · Signal Intelligence — Watchlist Manager
Tracks active paper positions: entry, target, stop-loss, P&L, days held.
"""
import logging
from datetime import date
from typing import Dict, List, Optional

from storage.database import get_session
from storage.models import WatchlistItem
from data_ingestion.price_fetcher import get_latest_price

logger = logging.getLogger(__name__)


def add_to_watchlist(
    ticker: str,
    entry_price: float,
    target_price: float,
    stop_loss_price: float,
    shares: int,
    position_size_aud: float,
    signal_score: float,
) -> WatchlistItem:
    with get_session() as session:
        existing = session.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
        if existing and existing.is_active:
            logger.info("%s already in watchlist", ticker)
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
            is_active=True,
        )
        session.merge(item)
        logger.info("Added %s to watchlist at $%.3f", ticker, entry_price)
        return item


def update_watchlist_prices() -> List[Dict]:
    """Refresh current prices and P&L for all active watchlist items."""
    updated = []
    with get_session() as session:
        items = session.query(WatchlistItem).filter(WatchlistItem.is_active == True).all()
        for item in items:
            current = get_latest_price(item.ticker)
            if current is None:
                continue
            item.current_price = current
            pnl = (current - item.entry_price) * item.shares
            item.unrealised_pnl = round(pnl, 2)
            item.unrealised_pnl_pct = round((current - item.entry_price) / item.entry_price * 100, 2)
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
            })
    return updated


def remove_from_watchlist(ticker: str, reason: str = "manual") -> None:
    with get_session() as session:
        item = (
            session.query(WatchlistItem)
            .filter(WatchlistItem.ticker == ticker, WatchlistItem.is_active == True)
            .first()
        )
        if item:
            item.is_active = False
            logger.info("Removed %s from watchlist (reason: %s)", ticker, reason)


def get_active_watchlist() -> List[Dict]:
    with get_session() as session:
        items = (
            session.query(WatchlistItem)
            .filter(WatchlistItem.is_active == True)
            .order_by(WatchlistItem.unrealised_pnl_pct.desc())
            .all()
        )
        return [
            {
                "ticker": i.ticker,
                "entry_date": i.entry_date,
                "entry_price": i.entry_price,
                "current_price": i.current_price,
                "target_price": i.target_price,
                "stop_loss_price": i.stop_loss_price,
                "shares": i.shares,
                "unrealised_pnl": i.unrealised_pnl,
                "unrealised_pnl_pct": i.unrealised_pnl_pct,
                "days_held": i.days_held,
                "signal_score": i.signal_score,
            }
            for i in items
        ]


def get_watchlist_summary() -> Dict:
    positions = get_active_watchlist()
    total_pnl = sum(p["unrealised_pnl"] or 0 for p in positions)
    winners = sum(1 for p in positions if (p["unrealised_pnl"] or 0) > 0)
    return {
        "total_positions": len(positions),
        "total_unrealised_pnl": round(total_pnl, 2),
        "winners": winners,
        "losers": len(positions) - winners,
        "positions": positions,
    }
