"""
Layer 05 · Execution — IBKR Live Trading (Phase 3 only)
Uses ib_insync library. Only activates when TRADING_PHASE >= 3.

Supported exchanges via IBKR:
  - ASX (Australia): STK on ASX exchange, currency AUD
  - NSE (India):     STK on NSE exchange, currency INR
    Note: IBKR supports NSE for institutional/NRI accounts.
          Indian retail investors may need Zerodha/Upstox instead
          (see execution/zerodha_broker.py stub).

The active exchange is read from config.get_active_exchange() so no
code changes are needed when switching between ASX and NSE.
"""
import logging
from typing import Dict, Optional

from config import get_active_exchange
from config.settings import IBKR_CLIENT_ID, IBKR_HOST, IBKR_PORT, IBKR_PAPER_ENABLED, LIVE_TRADING_ENABLED

logger = logging.getLogger(__name__)


def _get_ib():
    """Connect to TWS/IB Gateway. Works for both paper (port 7497) and live (port 7496)."""
    if not IBKR_PAPER_ENABLED:
        raise RuntimeError("IBKR not enabled (set TRADING_PHASE >= 2 in .env)")
    try:
        from ib_insync import IB, util
        util.startLoop()          # required outside Jupyter
        ib = IB()
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=10)
        mode = "PAPER" if not LIVE_TRADING_ENABLED else "LIVE"
        logger.info("Connected to IBKR %s at %s:%s", mode, IBKR_HOST, IBKR_PORT)
        return ib
    except ImportError:
        raise ImportError("ib_insync not installed — run: pip install ib_insync")


def _build_contract(ticker: str):
    """
    Build the correct ib_insync contract for the active exchange.
    ASX: Stock("BHP", "ASX", "AUD")
    NSE: Stock("RELIANCE", "NSE", "INR")
    """
    from ib_insync import Stock
    exchange = get_active_exchange()

    if exchange.id == "asx":
        symbol = ticker.replace(".AX", "")
        return Stock(symbol, "ASX", "AUD")

    elif exchange.id == "nse":
        symbol = ticker.replace(".NS", "")
        # IBKR uses "NSE" for the National Stock Exchange of India
        return Stock(symbol, "NSE", "INR")

    else:
        # Generic fallback: strip the suffix and use exchange id uppercased
        suffix = f".{ticker.split('.')[-1]}" if "." in ticker else ""
        symbol = ticker.replace(suffix, "")
        currency = exchange.currency_code
        return Stock(symbol, exchange.id.upper(), currency)


def place_market_buy(ticker: str, shares: int) -> Optional[Dict]:
    """Place a live market buy order via IBKR."""
    if not IBKR_PAPER_ENABLED:
        logger.warning("Live trading not enabled — use paper_trader instead")
        return None

    ib = _get_ib()
    try:
        from ib_insync import MarketOrder
        contract = _build_contract(ticker)
        ib.qualifyContracts(contract)
        order = MarketOrder("BUY", shares)
        trade = ib.placeOrder(contract, order)
        ib.sleep(2)
        logger.info(
            "LIVE BUY: %s %d shares — status: %s",
            ticker, shares, trade.orderStatus.status,
        )
        return {
            "ticker": ticker,
            "shares": shares,
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
        }
    finally:
        ib.disconnect()


def place_stop_loss_order(ticker: str, shares: int, stop_price: float) -> Optional[Dict]:
    """Place a conditional stop-loss sell order via IBKR."""
    if not IBKR_PAPER_ENABLED:
        return None

    ib = _get_ib()
    try:
        from ib_insync import StopOrder
        contract = _build_contract(ticker)
        ib.qualifyContracts(contract)
        order = StopOrder("SELL", shares, stop_price)
        trade = ib.placeOrder(contract, order)
        ib.sleep(1)
        logger.info(
            "LIVE STOP: %s %d shares @ %.3f — status: %s",
            ticker, shares, stop_price, trade.orderStatus.status,
        )
        return {
            "ticker": ticker,
            "stop_price": stop_price,
            "order_id": trade.order.orderId,
        }
    finally:
        ib.disconnect()


def place_market_sell(ticker: str, shares: int) -> Optional[Dict]:
    """Place a live market sell order via IBKR."""
    if not IBKR_PAPER_ENABLED:
        return None

    ib = _get_ib()
    try:
        from ib_insync import MarketOrder
        contract = _build_contract(ticker)
        ib.qualifyContracts(contract)
        order = MarketOrder("SELL", shares)
        trade = ib.placeOrder(contract, order)
        ib.sleep(2)
        logger.info(
            "LIVE SELL: %s %d shares — status: %s",
            ticker, shares, trade.orderStatus.status,
        )
        return {
            "ticker": ticker,
            "shares": shares,
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
        }
    finally:
        ib.disconnect()


def get_account_summary() -> Optional[Dict]:
    """Fetch IBKR account balance and open positions."""
    if not IBKR_PAPER_ENABLED:
        return None
    ib = _get_ib()
    try:
        return {item.tag: item.value for item in ib.accountSummary()}
    finally:
        ib.disconnect()
