"""
Layer 05 · Execution — Paper Trading Engine
Simulates order fills with 0.1% slippage and $9.95 brokerage.
Logs all trades to the DB and updates the watchlist.
"""
import logging
from datetime import date
from typing import Dict, List, Optional

from config.settings import (
    PAPER_BROKERAGE,
    PAPER_SLIPPAGE,
    SIGNAL_THRESHOLD,
    STOP_LOSS_PCT,
)
from data_ingestion.price_fetcher import get_latest_price
from signals.kelly_sizer import compute_shares
from signals.watchlist import (
    add_to_watchlist,
    get_active_watchlist,
    remove_from_watchlist,
    update_watchlist_prices,
)
from storage.database import get_session
from storage.models import Trade

logger = logging.getLogger(__name__)


def _simulate_fill(price: float, side: str) -> float:
    """Apply slippage: buys fill slightly higher, sells slightly lower."""
    slip = PAPER_SLIPPAGE
    return price * (1 + slip) if side == "buy" else price * (1 - slip)


def _record_trade(
    ticker: str,
    trade_type: str,
    entry_price: float,
    exit_price: Optional[float],
    shares: float,
    entry_date: date,
    exit_date: Optional[date],
    exit_reason: str,
    signal_score: float,
) -> None:
    gross = (exit_price - entry_price) * shares if exit_price else 0.0
    net = gross - PAPER_BROKERAGE * (2 if exit_price else 1)
    with get_session() as session:
        session.add(Trade(
            ticker=ticker,
            trade_type=trade_type,
            mode="paper",
            entry_date=entry_date,
            exit_date=exit_date,
            entry_price=entry_price,
            exit_price=exit_price,
            shares=shares,
            gross_pnl=round(gross, 2),
            net_pnl=round(net, 2),
            brokerage=PAPER_BROKERAGE * (2 if exit_price else 1),
            exit_reason=exit_reason,
            signal_score=signal_score,
        ))


def execute_buy(signal: Dict) -> Optional[Dict]:
    """
    Open a paper position (long or short) for an actionable signal.
    Longs need composite ≥ threshold; shorts need the bearish composite
    (100 − score) ≥ threshold. Returns fill details or None if skipped.
    """
    ticker = signal["ticker"]
    score = signal["composite_score"]
    direction = signal.get("direction") or "long"
    short = direction == "short"

    effective_score = (100 - score) if short else score
    if effective_score < SIGNAL_THRESHOLD:
        logger.debug("Skipping %s — %s score %.1f below threshold",
                     ticker, direction, effective_score)
        return None

    # Strategy gate: non-actionable signals (no validated strategy, or the
    # strategy didn't fire today) carry position_size_aud=0 — never buy them.
    position_aud = signal.get("position_size_aud") or 0
    if position_aud <= 0:
        logger.info(
            "Skipping %s — score %.1f but no validated strategy entry (strategy=%s)",
            ticker, score, signal.get("strategy_name") or "unassigned",
        )
        return None

    raw_price = signal.get("entry_price") or get_latest_price(ticker)
    if not raw_price:
        logger.warning("No price for %s — cannot place order", ticker)
        return None

    # Shorts sell to open — slippage works against you in both directions
    fill_price = _simulate_fill(raw_price, "sell" if short else "buy")
    shares = compute_shares(position_aud, fill_price)

    if shares <= 0:
        logger.warning("Position size too small for %s", ticker)
        return None

    actual_cost = shares * fill_price + PAPER_BROKERAGE
    if short:
        stop_loss = signal.get("stop_loss_price") or round(fill_price * (1 + STOP_LOSS_PCT), 3)
        target = signal.get("target_price") or round(fill_price * 0.90, 3)
    else:
        stop_loss = signal.get("stop_loss_price") or round(fill_price * (1 - STOP_LOSS_PCT), 3)
        target = signal.get("target_price") or round(fill_price * 1.10, 3)

    add_to_watchlist(
        ticker=ticker,
        entry_price=fill_price,
        target_price=target,
        stop_loss_price=stop_loss,
        shares=shares,
        position_size_aud=actual_cost,
        signal_score=score,
        direction=direction,
    )

    _record_trade(
        ticker=ticker,
        trade_type="short" if short else "buy",
        entry_price=fill_price,
        exit_price=None,
        shares=shares,
        entry_date=date.today(),
        exit_date=None,
        exit_reason="open",
        signal_score=score,
    )

    logger.info(
        "PAPER %s: %s  %d shares @ $%.3f  stop=$%.3f  target=$%.3f  notional=$%.2f",
        "SHORT" if short else "BUY",
        ticker, shares, fill_price, stop_loss, target, actual_cost,
    )
    return {"ticker": ticker, "shares": shares, "fill_price": fill_price,
            "cost": actual_cost, "direction": direction}


def execute_sell(ticker: str, reason: str = "manual",
                 trading_mode: str = None) -> Optional[Dict]:
    """
    Close a paper position.
    trading_mode: if provided, look up the position in that specific mode;
                  if None, search all active modes so legacy 'paper' positions
                  are found even when TRADING_PHASE has moved to 2+.
    """
    raw_price = get_latest_price(ticker)
    if not raw_price:
        logger.warning("No price to sell %s", ticker)
        return None

    # Search all modes so legacy 'paper' positions are found under phase 2+
    watchlist = get_active_watchlist(all_modes=True)
    position = next((p for p in watchlist if p["ticker"] == ticker
                     and (trading_mode is None or p.get("trading_mode") == trading_mode)), None)
    if not position:
        logger.warning("No active position for %s (mode=%s)", ticker, trading_mode or "any")
        return None

    short = (position.get("direction") or "long") == "short"
    # Covering a short means buying — slippage fills higher
    fill_price = _simulate_fill(raw_price, "buy" if short else "sell")

    pos_trading_mode = position.get("trading_mode", "paper")
    if short:
        pnl = (position["entry_price"] - fill_price) * position["shares"] - PAPER_BROKERAGE * 2
    else:
        pnl = (fill_price - position["entry_price"]) * position["shares"] - PAPER_BROKERAGE * 2
    remove_from_watchlist(ticker, reason=reason, trading_mode=pos_trading_mode)

    _record_trade(
        ticker=ticker,
        trade_type="cover" if short else "sell",
        entry_price=position["entry_price"],
        exit_price=fill_price,
        shares=position["shares"],
        entry_date=position["entry_date"],
        exit_date=date.today(),
        exit_reason=reason,
        signal_score=position["signal_score"],
    )

    logger.info(
        "PAPER SELL: %s  %d shares @ $%.3f  P&L=$%.2f  reason=%s",
        ticker, position["shares"], fill_price, pnl, reason,
    )
    return {"ticker": ticker, "fill_price": fill_price, "pnl": round(pnl, 2)}


def process_new_signals(signals: List[Dict]) -> List[Dict]:
    """Attempt to buy any signal above threshold not already in watchlist."""
    active_tickers = {p["ticker"] for p in get_active_watchlist()}
    fills = []
    for sig in signals:
        if sig["ticker"] not in active_tickers:
            fill = execute_buy(sig)
            if fill:
                fills.append(fill)
    return fills
