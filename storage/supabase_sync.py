"""
Phase 2 · Storage — Supabase Cloud Sync
Mirrors local PostgreSQL data to Supabase after each pipeline stage.

Uses the Supabase REST API directly via requests — no supabase-py dependency.
This avoids the pyiceberg/pydantic version conflicts in the conda environment.

Design principles:
- Fire-and-forget: sync failures NEVER affect the local scheduler
- Lazy init: REST session only created when SUPABASE_URL is configured
- Exchange-aware: adds 'exchange' column absent from local PG tables
- Graceful no-op: returns False silently when not configured

Sync targets:
  signals        → after job_signal_scan()
  regime         → after job_signal_scan()   (computed by job_technical_regime)
  watchlist      → after job_place_orders() + job_market_close()
  trades         → after job_market_close()
  backtest_cache → after job_weekly_sunday()
"""

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── REST client helpers ───────────────────────────────────────────────────────

def _get_config():
    """Return (url, key) from env, or (None, None) if not configured."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")

    # Fall back to config.settings (loads dotenv) if not set in env directly
    if not url or not key:
        try:
            from config.settings import SUPABASE_URL, SUPABASE_KEY
            url = url or SUPABASE_URL
            key = key or SUPABASE_KEY
        except Exception:
            pass

    if url and key:
        return url.rstrip("/"), key
    return None, None


def _headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",  # upsert semantics
    }


def _upsert(url: str, key: str, table: str, rows: list) -> bool:
    """POST rows to Supabase table with upsert semantics (merge-duplicates)."""
    import requests
    resp = requests.post(
        f"{url}/rest/v1/{table}",
        headers=_headers(key),
        data=json.dumps(rows, default=str),  # default=str handles date serialisation
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        logger.warning("Supabase upsert to %s failed: %s %s", table, resp.status_code, resp.text[:200])
        return False
    return True


def _delete(url: str, key: str, table: str, filters: dict) -> bool:
    """DELETE rows matching filters from a Supabase table."""
    import requests
    params = {k: f"eq.{v}" for k, v in filters.items()}
    resp = requests.delete(
        f"{url}/rest/v1/{table}",
        headers=_headers(key),
        params=params,
        timeout=30,
    )
    if resp.status_code not in (200, 204):
        logger.warning("Supabase delete from %s failed: %s %s", table, resp.status_code, resp.text[:200])
        return False
    return True


def _get_exchange_id() -> str:
    """Active exchange id from env — matches logic in config/__init__.py."""
    return os.environ.get("EXCHANGE", "asx").lower()


def _ticker_suffix(exchange_id: str) -> str:
    return ".AX" if exchange_id == "asx" else ".NS"


# ── Public sync functions ─────────────────────────────────────────────────────

def sync_signals_to_supabase(signal_date: date = None) -> bool:
    """Upsert today's signals for the active exchange to Supabase."""
    url, key = _get_config()
    if not url:
        return False

    signal_date = signal_date or date.today()
    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)

    try:
        from storage.database import get_session
        from storage.models import Signal

        with get_session() as session:
            rows_orm = (
                session.query(Signal)
                .filter(Signal.date == signal_date, Signal.ticker.endswith(suffix))
                .all()
            )
            payload = [
                {
                    "ticker": r.ticker,
                    "date": str(r.date),
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
                for r in rows_orm
            ]

        if not payload:
            logger.info("No signals to sync for %s on %s", exchange_id.upper(), signal_date)
            return True

        ok = _upsert(url, key, "signals", payload)
        if ok:
            logger.info("Synced %d signals to Supabase (%s)", len(payload), exchange_id.upper())
        return ok

    except Exception as e:
        logger.warning("sync_signals_to_supabase failed: %s", e)
        return False


def sync_regime_to_supabase() -> bool:
    """Upsert current regime status to Supabase 'regime' table."""
    url, key = _get_config()
    if not url:
        return False

    exchange_id = _get_exchange_id()

    try:
        from ai_engine.regime_filter import get_regime_summary
        regime = get_regime_summary()

        payload = [
            {
                "exchange": exchange_id,
                "regime_ok": regime.get("regime_ok"),
                "index_val": regime.get("index"),
                "index_name": regime.get("index_name"),
                "ema200": regime.get("ema200"),
                "pct_above": regime.get("pct_above"),
            }
        ]

        ok = _upsert(url, key, "regime", payload)
        if ok:
            logger.info(
                "Synced regime to Supabase (%s): %s",
                exchange_id.upper(),
                "RISK-ON" if regime.get("regime_ok") else "RISK-OFF",
            )
        return ok

    except Exception as e:
        logger.warning("sync_regime_to_supabase failed: %s", e)
        return False


def sync_watchlist_to_supabase() -> bool:
    """Replace active watchlist positions for the active exchange in Supabase."""
    url, key = _get_config()
    if not url:
        return False

    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)

    try:
        from storage.database import get_session
        from storage.models import WatchlistItem

        # Build payload inside the session to avoid detached-instance errors
        with get_session() as session:
            items = (
                session.query(WatchlistItem)
                .filter(
                    WatchlistItem.is_active == True,
                    WatchlistItem.ticker.endswith(suffix),
                )
                .all()
            )
            payload = [
                {
                    "ticker": i.ticker,
                    "exchange": exchange_id,
                    "trading_mode": i.trading_mode or "paper",
                    "entry_date": str(i.entry_date) if i.entry_date else None,
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

        # Delete all rows for this exchange, then re-insert active ones
        _delete(url, key, "watchlist", {"exchange": exchange_id})

        if not payload:
            logger.info("Watchlist empty for %s — cleared Supabase rows", exchange_id.upper())
            return True

        # Try with trading_mode first; fall back without it if column not yet migrated
        ok = _upsert(url, key, "watchlist", payload)
        if not ok:
            payload_no_mode = [{k: v for k, v in row.items() if k != "trading_mode"} for row in payload]
            ok = _upsert(url, key, "watchlist", payload_no_mode)
            if ok:
                logger.warning("Synced watchlist WITHOUT trading_mode — run ALTER TABLE migration in Supabase SQL Editor")

        if ok:
            logger.info("Synced %d positions to Supabase (%s)", len(payload), exchange_id.upper())
        return ok

    except Exception as e:
        logger.warning("sync_watchlist_to_supabase failed: %s", e)
        return False


def sync_trades_to_supabase(days: int = 90) -> bool:
    """Upsert closed trades from the last N days for the active exchange."""
    url, key = _get_config()
    if not url:
        return False

    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)
    cutoff = date.today() - timedelta(days=days)

    try:
        from storage.database import get_session
        from storage.models import Trade

        with get_session() as session:
            rows_orm = (
                session.query(Trade)
                .filter(
                    Trade.exit_date != None,
                    Trade.exit_date >= cutoff,
                    Trade.ticker.endswith(suffix),
                )
                .all()
            )
            payload = [
                {
                    "ticker": r.ticker,
                    "exchange": exchange_id,
                    "trade_type": r.trade_type,
                    "mode": r.mode,
                    "entry_date": str(r.entry_date) if r.entry_date else None,
                    "exit_date": str(r.exit_date) if r.exit_date else None,
                    "entry_price": r.entry_price,
                    "exit_price": r.exit_price,
                    "shares": r.shares,
                    "gross_pnl": r.gross_pnl,
                    "net_pnl": r.net_pnl,
                    "brokerage": r.brokerage,
                    "exit_reason": r.exit_reason,
                    "signal_score": r.signal_score,
                }
                for r in rows_orm
            ]

        if not payload:
            logger.info("No closed trades to sync for %s", exchange_id.upper())
            return True

        ok = _upsert(url, key, "trades", payload)
        if ok:
            logger.info("Synced %d trades to Supabase (%s)", len(payload), exchange_id.upper())
        return ok

    except Exception as e:
        logger.warning("sync_trades_to_supabase failed: %s", e)
        return False


def sync_backtest_to_supabase(results: dict) -> bool:
    """Store walk-forward backtest results as a JSON snapshot in Supabase."""
    url, key = _get_config()
    if not url:
        return False

    exchange_id = _get_exchange_id()

    try:
        payload = [
            {
                "exchange": exchange_id,
                "results_json": json.dumps(results),
            }
        ]
        # Use insert (not upsert) — each Sunday creates a new snapshot
        import requests
        headers = _headers(key)
        headers["Prefer"] = "return=minimal"  # override to insert, not upsert
        resp = requests.post(
            f"{url}/rest/v1/backtest_cache",
            headers=headers,
            data=json.dumps(payload),
            timeout=30,
        )
        ok = resp.status_code in (200, 201)
        if ok:
            logger.info("Synced backtest results to Supabase (%s): %d tickers",
                        exchange_id.upper(), len(results))
        else:
            logger.warning("Backtest sync failed: %s %s", resp.status_code, resp.text[:200])
        return ok

    except Exception as e:
        logger.warning("sync_backtest_to_supabase failed: %s", e)
        return False
