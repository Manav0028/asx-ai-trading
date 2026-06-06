"""
Phase 2 · Execution — IBKR Paper Trading Bridge
Routes orders through IBKR's paper trading account (TWS port 7497)
while keeping the local PostgreSQL database fully in sync.

Flow for each signal:
  1. Place MarketOrder via IBKR paper account
  2. Wait up to 10 s for fill confirmation
  3. Use actual IBKR fill price (or last market price as fallback)
  4. Record to watchlist + trades table (same as internal paper_trader)
  5. Trigger Telegram alert

This gives the realism of IBKR's paper account (real bid/ask, proper fills,
IBKR portfolio tracking) while still maintaining our own DB for the dashboard.

Prerequisites (TWS setup):
  - TWS running, logged into paper trading account
  - API enabled: TWS → Edit → Global Configuration → API → Settings
      ✅ Enable ActiveX and Socket Clients
      Port: 7497
      Master API client ID: 0
  - Trusted IPs: 127.0.0.1
  - Allow connections from localhost checked
"""
import logging
from datetime import date
from typing import Dict, List, Optional

from config.settings import (
    IBKR_PAPER_ENABLED, PAPER_BROKERAGE, PAPER_SLIPPAGE, SIGNAL_THRESHOLD
)
from signals.watchlist import add_to_watchlist, remove_from_watchlist, get_active_watchlist

logger = logging.getLogger(__name__)

_FILL_TIMEOUT = 10    # seconds to wait for an IBKR fill


# ── Fallback: internal paper trader when TWS is down ─────────────────────────

def _fallback_paper_buy(signal: Dict) -> Optional[Dict]:
    """Route buy through internal paper trader when IBKR is unreachable."""
    from execution.paper_trader import execute_buy
    logger.info("FALLBACK BUY: routing %s through internal paper trader", signal["ticker"])
    return execute_buy(signal)


def _fallback_paper_sell(ticker: str, reason: str) -> Optional[Dict]:
    """Route sell through internal paper trader when IBKR is unreachable."""
    from execution.paper_trader import execute_sell
    logger.info("FALLBACK SELL: routing %s through internal paper trader", ticker)
    return execute_sell(ticker, reason=reason)


def _wait_for_fill(ib, trade) -> Optional[float]:
    """
    Wait up to _FILL_TIMEOUT seconds for an IBKR trade to fill.
    Returns the average fill price, or None if not filled in time.
    """
    from ib_insync import OrderStatus
    deadline = ib.loop.time() + _FILL_TIMEOUT
    while ib.loop.time() < deadline:
        ib.sleep(0.5)
        if trade.orderStatus.status in (
            OrderStatus.Filled, OrderStatus.PartiallyFilled, "Filled", "PartiallyFilled"
        ):
            avg_fill = trade.orderStatus.avgFillPrice
            return float(avg_fill) if avg_fill else None
    return None


def _record_buy(ticker: str, fill_price: float, shares: int,
                signal: Dict) -> Optional[Dict]:
    """Write the buy to watchlist and trade tables."""
    from storage.database import get_session
    from storage.models import Trade

    cost = round(fill_price * shares + PAPER_BROKERAGE, 2)
    target = signal.get("target_price") or round(fill_price * 1.10, 3)
    stop   = signal.get("stop_loss_price") or round(fill_price * 0.93, 3)
    score  = signal.get("composite_score", 0)

    # Add to watchlist (tagged ibkr_paper so it doesn't mix with internal paper)
    add_to_watchlist(
        ticker=ticker,
        entry_price=fill_price,
        target_price=target,
        stop_loss_price=stop,
        shares=shares,
        position_size_aud=cost,
        signal_score=score,
        trading_mode="ibkr_paper",
    )

    # Record as open trade
    with get_session() as session:
        trade = Trade(
            ticker=ticker,
            trade_type="buy",
            mode="ibkr_paper",
            entry_date=date.today(),
            entry_price=fill_price,
            shares=shares,
            brokerage=PAPER_BROKERAGE,
            signal_score=score,
        )
        session.add(trade)

    logger.info(
        "IBKR PAPER BUY recorded: %s × %d shares @ %.3f (cost %.2f)",
        ticker, shares, fill_price, cost,
    )
    return {"ticker": ticker, "shares": shares, "fill_price": fill_price, "cost": cost}


def _record_sell(ticker: str, fill_price: float, reason: str) -> Optional[Dict]:
    """Write the sell to the trades table and deactivate watchlist entry."""
    from storage.database import get_session
    from storage.models import Trade, WatchlistItem

    with get_session() as session:
        item = (
            session.query(WatchlistItem)
            .filter(
                WatchlistItem.ticker == ticker,
                WatchlistItem.trading_mode == "ibkr_paper",
                WatchlistItem.is_active == True,
            )
            .first()
        )
        if not item:
            logger.warning("IBKR PAPER SELL: %s not in watchlist", ticker)
            return None

        shares     = item.shares
        entry      = item.entry_price
        gross_pnl  = round((fill_price - entry) * shares, 2)
        net_pnl    = round(gross_pnl - PAPER_BROKERAGE * 2, 2)

        # Close the open trade
        open_trade = (
            session.query(Trade)
            .filter(Trade.ticker == ticker, Trade.trade_type == "buy", Trade.exit_date == None)
            .order_by(Trade.entry_date.desc())
            .first()
        )
        if open_trade:
            open_trade.exit_date  = date.today()
            open_trade.exit_price = fill_price
            open_trade.gross_pnl  = gross_pnl
            open_trade.net_pnl    = net_pnl
            open_trade.brokerage  = PAPER_BROKERAGE * 2
            open_trade.exit_reason = reason

        item.is_active = False

    logger.info(
        "IBKR PAPER SELL recorded: %s × %.0f shares @ %.3f | P&L %.2f (%s)",
        ticker, shares, fill_price, net_pnl, reason,
    )
    return {"ticker": ticker, "fill_price": fill_price, "pnl": net_pnl}


# ── Public API ────────────────────────────────────────────────────────────────

def ibkr_execute_buy(signal: Dict) -> Optional[Dict]:
    """
    Place a paper buy order via IBKR for a single signal.
    Falls back to internal paper trader if TWS is unreachable.
    Returns fill dict or None if not filled.
    """
    if not IBKR_PAPER_ENABLED:
        return None

    ticker    = signal["ticker"]
    pos_size  = signal.get("position_size_aud", 0)
    entry_est = signal.get("entry_price", 0)

    if not entry_est or not pos_size:
        logger.warning("No price/size for %s — skipping", ticker)
        return None

    from signals.kelly_sizer import compute_shares
    shares = compute_shares(pos_size, entry_est)
    if shares <= 0:
        logger.info("Computed 0 shares for %s — skipping", ticker)
        return None

    # Check not already in ibkr_paper watchlist
    active = {p["ticker"] for p in get_active_watchlist(trading_mode="ibkr_paper")}
    if ticker in active:
        logger.info("%s already held — skipping duplicate buy", ticker)
        return None

    from execution.ibkr_trader import _build_contract, _get_ib
    ib = None
    try:
        from ib_insync import MarketOrder
        ib = _get_ib()
        contract = _build_contract(ticker)
        ib.qualifyContracts(contract)

        order = MarketOrder("BUY", shares)
        trade = ib.placeOrder(contract, order)
        logger.info("IBKR PAPER: placed BUY %s × %d — waiting for fill...", ticker, shares)

        fill_price = _wait_for_fill(ib, trade)
        if fill_price is None:
            # Fallback: use estimated entry price (happens if market closed)
            fill_price = round(entry_est * (1 + PAPER_SLIPPAGE), 4)
            logger.warning(
                "%s fill timed out — using estimated price %.3f", ticker, fill_price
            )

        return _record_buy(ticker, fill_price, shares, signal)

    except ConnectionError:
        # TWS is down — fall back to internal paper trader
        logger.warning("TWS unreachable — falling back to internal paper trader for BUY %s", ticker)
        return _fallback_paper_buy(signal)
    except Exception as e:
        logger.error("IBKR paper buy failed for %s: %s", ticker, e)
        # Also fall back so the signal isn't lost
        logger.info("Falling back to internal paper trader for %s", ticker)
        return _fallback_paper_buy(signal)
    finally:
        if ib and ib.isConnected():
            ib.disconnect()


def ibkr_execute_sell(ticker: str, reason: str = "manual") -> Optional[Dict]:
    """
    Place a paper sell order via IBKR for a held position.
    Falls back to internal paper trader if TWS is unreachable.
    Returns sell dict or None if failed.
    """
    if not IBKR_PAPER_ENABLED:
        return None

    positions = get_active_watchlist(trading_mode="ibkr_paper")
    pos = next((p for p in positions if p["ticker"] == ticker), None)
    if not pos:
        logger.warning("IBKR paper sell: %s not in active watchlist", ticker)
        return None

    shares    = int(pos.get("shares") or 0)
    price_est = pos.get("current_price") or pos.get("entry_price") or 0

    if shares <= 0:
        return None

    from execution.ibkr_trader import _build_contract, _get_ib
    ib = None
    try:
        from ib_insync import MarketOrder
        ib = _get_ib()
        contract = _build_contract(ticker)
        ib.qualifyContracts(contract)

        order = MarketOrder("SELL", shares)
        trade = ib.placeOrder(contract, order)
        logger.info("IBKR PAPER: placed SELL %s × %d — waiting for fill...", ticker, shares)

        fill_price = _wait_for_fill(ib, trade)
        if fill_price is None:
            fill_price = round(price_est * (1 - PAPER_SLIPPAGE), 4)
            logger.warning(
                "%s sell fill timed out — using estimated price %.3f", ticker, fill_price
            )

        return _record_sell(ticker, fill_price, reason)

    except ConnectionError:
        # TWS is down — fall back to internal paper trader for the sell
        logger.warning("TWS unreachable — falling back to internal paper trader for SELL %s", ticker)
        return _fallback_paper_sell(ticker, reason)
    except Exception as e:
        logger.error("IBKR paper sell failed for %s: %s", ticker, e)
        logger.info("Falling back to internal paper trader for SELL %s", ticker)
        return _fallback_paper_sell(ticker, reason)
    finally:
        if ib and ib.isConnected():
            ib.disconnect()


def ibkr_process_new_signals(signals: List[Dict]) -> List[Dict]:
    """
    Process a list of signals: place IBKR paper buy orders for all qualifying signals.
    Mirrors paper_trader.process_new_signals() but uses IBKR.
    Returns list of successful fill dicts.
    """
    fills = []
    for sig in signals:
        if sig.get("composite_score", 0) < SIGNAL_THRESHOLD:
            continue
        result = ibkr_execute_buy(sig)
        if result:
            fills.append(result)
    return fills


def get_ibkr_account_summary() -> Optional[Dict]:
    """
    Fetch the IBKR paper account balance and positions.
    Useful for verifying connection and paper P&L.
    """
    if not IBKR_PAPER_ENABLED:
        return None
    from execution.ibkr_trader import _get_ib
    ib = None
    try:
        ib = _get_ib()
        summary = {item.tag: item.value for item in ib.accountSummary()}
        positions = [
            {
                "symbol":   p.contract.symbol,
                "position": p.position,
                "avg_cost": p.avgCost,
                "market_val": p.marketValue,
                "unrealised_pnl": p.unrealizedPNL,
            }
            for p in ib.portfolio()
        ]
        return {"account": summary, "positions": positions}
    except Exception as e:
        logger.error("Failed to fetch IBKR account summary: %s", e)
        return None
    finally:
        if ib and ib.isConnected():
            ib.disconnect()


def check_ibkr_health() -> Dict:
    """
    Quick health check for TWS connectivity.
    Returns {"connected": bool, "error": str|None, "account": str|None}.
    Used by the scheduler to verify TWS before market open.
    """
    if not IBKR_PAPER_ENABLED:
        return {"connected": False, "error": "IBKR not enabled (TRADING_PHASE < 2)"}

    from execution.ibkr_trader import _get_ib
    ib = None
    try:
        ib = _get_ib()
        # Quick account query to verify the connection is actually working
        acct = ib.managedAccounts()
        return {"connected": True, "error": None, "account": acct[0] if acct else None}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    finally:
        if ib and ib.isConnected():
            ib.disconnect()
