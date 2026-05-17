"""
Phase 2 · Storage — Supabase Cloud Sync
Mirrors local PostgreSQL data to Supabase after each pipeline stage.

Design principles:
- Fire-and-forget: sync failures NEVER affect the local scheduler
- Lazy init: Supabase client only created when SUPABASE_URL is configured
- Exchange-aware: adds an 'exchange' column absent from local PG tables
- Graceful no-op: returns False silently when not configured

Sync targets:
  signals       → after job_signal_scan()
  regime        → after job_signal_scan()   (computed by job_technical_regime)
  watchlist     → after job_place_orders() + job_market_close()
  trades        → after job_market_close()
  backtest_cache → after job_weekly_sunday()
"""

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ── Lazy Supabase client ──────────────────────────────────────────────────────

_client_cache = None


def _get_client():
    """Return a Supabase Client if credentials are configured, else None."""
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    # Check env directly first — avoids importing config (which loads dotenv) when not needed
    url = os.environ.get("SUPABASE_URL") or ""
    key = os.environ.get("SUPABASE_KEY") or ""

    # Fall back to config.settings if env vars not directly set (e.g. loaded via dotenv)
    if not url or not key:
        try:
            from config.settings import SUPABASE_URL, SUPABASE_KEY
            url = SUPABASE_URL or url
            key = SUPABASE_KEY or key
        except Exception:
            pass

    if not url or not key:
        return None

    try:
        from supabase import create_client
        _client_cache = create_client(url, key)
        logger.info("Supabase client initialised (%s)", url[:40])
        return _client_cache
    except ImportError:
        logger.warning("supabase-py not installed — cloud sync disabled")
        return None
    except Exception as e:
        logger.warning("Supabase client init failed: %s", e)
        return None


def _get_exchange_id() -> str:
    """Active exchange id from env — matches logic in config/__init__.py."""
    return os.environ.get("EXCHANGE", "asx").lower()


def _ticker_suffix(exchange_id: str) -> str:
    return ".AX" if exchange_id == "asx" else ".NS"


def _to_str(val) -> Optional[str]:
    """Convert date/datetime to ISO string for JSON serialisation."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


# ── Public sync functions ─────────────────────────────────────────────────────

def sync_signals_to_supabase(signal_date: date = None) -> bool:
    """
    Upsert today's signals for the active exchange to Supabase.
    Called after job_signal_scan() completes.
    """
    client = _get_client()
    if client is None:
        return False

    signal_date = signal_date or date.today()
    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)

    try:
        from storage.database import get_session
        from storage.models import Signal

        with get_session() as session:
            rows = (
                session.query(Signal)
                .filter(Signal.date == signal_date, Signal.ticker.endswith(suffix))
                .all()
            )

        if not rows:
            logger.info("No signals to sync for %s on %s", exchange_id.upper(), signal_date)
            return True

        payload = [
            {
                "ticker": r.ticker,
                "date": _to_str(r.date),
                "exchange": exchange_id,
                "composite_score": r.composite_score,
                "sentiment_score": r.sentiment_score,
                "fundamental_score": r.fundamental_score,
                "technical_score": r.technical_score,
                "insider_score": r.insider_score,
                "regime_ok": r.regime_ok,
                "position_size_aud": r.position_size_aud,
                "entry_price": r.entry_price,
                "target_price": r.target_price,
                "stop_loss_price": r.stop_loss_price,
            }
            for r in rows
        ]

        client.table("signals").upsert(payload, on_conflict="ticker,date").execute()
        logger.info("Synced %d signals to Supabase (%s)", len(payload), exchange_id.upper())
        return True

    except Exception as e:
        logger.warning("sync_signals_to_supabase failed: %s", e)
        return False


def sync_regime_to_supabase() -> bool:
    """
    Upsert current regime status to Supabase.
    Called after job_signal_scan() (regime computed in job_technical_regime just before).
    """
    client = _get_client()
    if client is None:
        return False

    exchange_id = _get_exchange_id()

    try:
        from ai_engine.regime_filter import get_regime_summary
        regime = get_regime_summary()

        payload = {
            "exchange": exchange_id,
            "regime_ok": regime.get("regime_ok"),
            "index_val": regime.get("index"),
            "index_name": regime.get("index_name"),
            "ema200": regime.get("ema200"),
            "pct_above": regime.get("pct_above"),
        }

        client.table("regime").upsert([payload], on_conflict="exchange").execute()
        logger.info(
            "Synced regime to Supabase (%s): %s",
            exchange_id.upper(),
            "RISK-ON" if regime.get("regime_ok") else "RISK-OFF",
        )
        return True

    except Exception as e:
        logger.warning("sync_regime_to_supabase failed: %s", e)
        return False


def sync_watchlist_to_supabase() -> bool:
    """
    Replace active watchlist positions for the active exchange in Supabase.
    Uses delete-then-insert to correctly handle closed positions.
    Called after job_place_orders() and job_market_close().
    """
    client = _get_client()
    if client is None:
        return False

    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)

    try:
        from storage.database import get_session
        from storage.models import WatchlistItem

        with get_session() as session:
            items = (
                session.query(WatchlistItem)
                .filter(
                    WatchlistItem.is_active == True,
                    WatchlistItem.ticker.endswith(suffix),
                )
                .all()
            )

        # Delete all existing rows for this exchange, then re-insert
        client.table("watchlist").delete().eq("exchange", exchange_id).execute()

        if not items:
            logger.info("Watchlist empty for %s — cleared Supabase rows", exchange_id.upper())
            return True

        payload = [
            {
                "ticker": i.ticker,
                "exchange": exchange_id,
                "entry_date": _to_str(i.entry_date),
                "entry_price": i.entry_price,
                "current_price": i.current_price,
                "target_price": i.target_price,
                "stop_loss_price": i.stop_loss_price,
                "shares": i.shares,
                "position_size_aud": i.position_size_aud,
                "unrealised_pnl": i.unrealised_pnl,
                "unrealised_pnl_pct": i.unrealised_pnl_pct,
                "days_held": i.days_held,
                "signal_score": i.signal_score,
                "is_active": True,
            }
            for i in items
        ]

        client.table("watchlist").insert(payload).execute()
        logger.info("Synced %d positions to Supabase (%s)", len(payload), exchange_id.upper())
        return True

    except Exception as e:
        logger.warning("sync_watchlist_to_supabase failed: %s", e)
        return False


def sync_trades_to_supabase(days: int = 90) -> bool:
    """
    Upsert closed trades from the last N days for the active exchange.
    Called after job_market_close().
    """
    client = _get_client()
    if client is None:
        return False

    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)
    cutoff = date.today() - timedelta(days=days)

    try:
        from storage.database import get_session
        from storage.models import Trade

        with get_session() as session:
            rows = (
                session.query(Trade)
                .filter(
                    Trade.exit_date != None,
                    Trade.exit_date >= cutoff,
                    Trade.ticker.endswith(suffix),
                )
                .all()
            )

        if not rows:
            logger.info("No closed trades to sync for %s", exchange_id.upper())
            return True

        payload = [
            {
                "ticker": r.ticker,
                "exchange": exchange_id,
                "trade_type": r.trade_type,
                "mode": r.mode,
                "entry_date": _to_str(r.entry_date),
                "exit_date": _to_str(r.exit_date),
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
                "shares": r.shares,
                "gross_pnl": r.gross_pnl,
                "net_pnl": r.net_pnl,
                "brokerage": r.brokerage,
                "exit_reason": r.exit_reason,
                "signal_score": r.signal_score,
            }
            for r in rows
        ]

        client.table("trades").upsert(
            payload, on_conflict="ticker,entry_date,trade_type"
        ).execute()
        logger.info("Synced %d trades to Supabase (%s)", len(payload), exchange_id.upper())
        return True

    except Exception as e:
        logger.warning("sync_trades_to_supabase failed: %s", e)
        return False


def sync_backtest_to_supabase(results: dict) -> bool:
    """
    Store walk-forward backtest results as a JSON snapshot in Supabase.
    Called from job_weekly_sunday() after run_walk_forward() completes.
    """
    client = _get_client()
    if client is None:
        return False

    exchange_id = _get_exchange_id()

    try:
        payload = {
            "exchange": exchange_id,
            "results_json": json.dumps(results),
        }
        client.table("backtest_cache").insert(payload).execute()
        logger.info(
            "Synced backtest results to Supabase (%s): %d tickers",
            exchange_id.upper(), len(results),
        )
        return True

    except Exception as e:
        logger.warning("sync_backtest_to_supabase failed: %s", e)
        return False
