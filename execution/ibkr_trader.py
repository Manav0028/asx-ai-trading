"""
Layer 05 · Execution — IBKR Live Trading (Phase 3 only)
Uses ib_insync library. Only activates when TRADING_PHASE >= 2.

Resilient connection handling:
  - Retries with exponential backoff (3 attempts, 2s → 4s → 8s)
  - Sends Telegram alert when TWS is unreachable
  - Callers should handle None return gracefully (fallback to paper)

Supported exchanges via IBKR:
  - ASX (Australia): STK on ASX exchange, currency AUD
  - NSE (India):     STK on NSE exchange, currency INR

The active exchange is read from config.get_active_exchange() so no
code changes are needed when switching between ASX and NSE.
"""
import logging
import time
from typing import Dict, Optional

from config import get_active_exchange
from config.settings import IBKR_CLIENT_ID, IBKR_HOST, IBKR_PORT, IBKR_PAPER_ENABLED, LIVE_TRADING_ENABLED

logger = logging.getLogger(__name__)

# ── Connection resilience settings ───────────────────────────────────────────
_MAX_RETRIES     = 3        # number of connection attempts
_RETRY_BASE_WAIT = 2        # seconds: 2, 4, 8
_CONNECT_TIMEOUT = 15       # per-attempt timeout
_CLIENT_ID_RANGE = (1, 9)   # rotate client IDs to avoid stale socket locks

# Track consecutive failures to avoid spamming alerts
_consecutive_failures = 0
_ALERT_EVERY_N = 3          # send Telegram alert every N consecutive failures


def _send_connection_alert(error_msg: str) -> None:
    """Send Telegram alert when TWS connection fails repeatedly."""
    try:
        from alerts.telegram_bot import _send, _exchange_badge
        badge = _exchange_badge()
        text = (
            f"🔴 *{badge} — TWS Connection Lost*\n\n"
            f"IBKR TWS is unreachable after {_MAX_RETRIES} retries.\n"
            f"Error: `{error_msg[:100]}`\n\n"
            f"⚠️ Orders are falling back to internal paper trader.\n"
            f"Fix: Check TWS is running → API enabled → port {IBKR_PORT}"
        )
        _send(text)
    except Exception:
        logger.debug("Could not send TWS connection alert via Telegram")


def _send_reconnect_alert() -> None:
    """Notify that TWS connection has recovered."""
    try:
        from alerts.telegram_bot import _send, _exchange_badge
        badge = _exchange_badge()
        _send(f"🟢 *{badge} — TWS Reconnected*\nIBKR connection restored. Orders routing via IBKR.")
    except Exception:
        pass


def _get_ib():
    """
    Connect to TWS/IB Gateway with retry + exponential backoff.
    Works for both paper (port 7497) and live (port 7496).
    Raises ConnectionError after all retries exhausted.
    """
    global _consecutive_failures

    if not IBKR_PAPER_ENABLED:
        raise RuntimeError("IBKR not enabled (set TRADING_PHASE >= 2 in .env)")

    import asyncio
    # APScheduler runs jobs in a ThreadPoolExecutor which has no event loop.
    # Create one for this thread so ib_insync can function properly.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    from ib_insync import IB

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            ib = IB()
            # Rotate client ID to avoid "already connected" socket locks
            client_id = IBKR_CLIENT_ID + ((attempt - 1) % (_CLIENT_ID_RANGE[1] - _CLIENT_ID_RANGE[0]))
            ib.connect(IBKR_HOST, IBKR_PORT, clientId=client_id, timeout=_CONNECT_TIMEOUT)
            mode = "PAPER" if not LIVE_TRADING_ENABLED else "LIVE"

            # Connection succeeded — reset failure counter
            if _consecutive_failures > 0:
                logger.info("TWS reconnected after %d consecutive failures", _consecutive_failures)
                _send_reconnect_alert()
            _consecutive_failures = 0

            logger.info("Connected to IBKR %s at %s:%s (attempt %d, clientId %d)",
                        mode, IBKR_HOST, IBKR_PORT, attempt, client_id)
            return ib

        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))  # 2s, 4s, 8s
                logger.warning(
                    "TWS connection attempt %d/%d failed: %s — retrying in %ds",
                    attempt, _MAX_RETRIES, e, wait,
                )
                time.sleep(wait)
            else:
                logger.error("TWS connection FAILED after %d attempts: %s", _MAX_RETRIES, e)

    # All retries exhausted
    _consecutive_failures += 1
    if _consecutive_failures % _ALERT_EVERY_N == 1:
        _send_connection_alert(str(last_error))

    raise ConnectionError(f"TWS unreachable after {_MAX_RETRIES} attempts: {last_error}")


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
