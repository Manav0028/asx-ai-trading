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

# Positions/trades entered before this date are not synced to the new DB.
# Treat the new DB as a fresh account starting from this date.
NEW_DB_EPOCH = date(2026, 6, 19)

# ── REST client helpers ───────────────────────────────────────────────────────

def _get_config(db: str = "primary"):
    """Return (url, key) for the requested DB instance, or (None, None)."""
    if db == "new":
        url = os.environ.get("SUPABASE_URL_B", "")
        key = os.environ.get("SUPABASE_KEY_B", "")
        if not url or not key:
            try:
                from config.settings import SUPABASE_URL_B, SUPABASE_KEY_B
                url = url or SUPABASE_URL_B
                key = key or SUPABASE_KEY_B
            except Exception:
                pass
        return (url.rstrip("/"), key) if url and key else (None, None)

    # primary
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        try:
            from config.settings import SUPABASE_URL, SUPABASE_KEY
            url = url or SUPABASE_URL
            key = key or SUPABASE_KEY
        except Exception:
            pass
    return (url.rstrip("/"), key) if url and key else (None, None)


def _all_db_configs():
    """Yield (url, key, label) for every configured Supabase instance."""
    for label in ("primary", "new"):
        url, key = _get_config(label)
        if url:
            yield url, key, label


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
    """Upsert today's signals to all configured Supabase instances."""
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
                    "strategy_name": getattr(r, "strategy_name", None),
                    "direction": getattr(r, "direction", None) or "long",
                    "strategy_fires": bool(getattr(r, "strategy_fires", False)),
                }
                for r in rows_orm
            ]

        if not payload:
            logger.info("No signals to sync for %s on %s", exchange_id.upper(), signal_date)
            return True

        ok = False
        for url, key, label in _all_db_configs():
            result = _upsert(url, key, "signals", payload)
            if result:
                logger.info("Synced %d signals → %s DB (%s)", len(payload), label, exchange_id.upper())
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_signals_to_supabase failed: %s", e)
        return False


def sync_regime_to_supabase() -> bool:
    """Upsert current regime status to all configured Supabase instances."""
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

        ok = False
        for url, key, label in _all_db_configs():
            result = _upsert(url, key, "regime", payload)
            if result:
                logger.info("Synced regime → %s DB (%s): %s", label, exchange_id.upper(),
                            "RISK-ON" if regime.get("regime_ok") else "RISK-OFF")
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_regime_to_supabase failed: %s", e)
        return False


def sync_watchlist_to_supabase() -> bool:
    """Replace active watchlist positions in all configured Supabase instances."""
    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)

    try:
        from storage.database import get_session
        from storage.models import WatchlistItem

        from storage.models import Price

        with get_session() as session:
            items = (
                session.query(WatchlistItem)
                .filter(
                    WatchlistItem.is_active == True,
                    WatchlistItem.ticker.endswith(suffix),
                )
                .all()
            )

            # Fetch yesterday's close for each position to compute day P&L
            def _prev_close(ticker: str) -> float:
                row = (
                    session.query(Price.close)
                    .filter(Price.ticker == ticker, Price.date < date.today())
                    .order_by(Price.date.desc())
                    .first()
                )
                return row[0] if row else None

            payload = []
            for i in items:
                current   = i.current_price or i.entry_price
                prev      = _prev_close(i.ticker)
                sign      = -1 if (getattr(i, "direction", None) or "long") == "short" else 1
                day_pnl   = round(sign * (current - prev) * (i.shares or 0), 2) if prev else None
                payload.append({
                    "ticker":           i.ticker,
                    "exchange":         exchange_id,
                    "trading_mode":     i.trading_mode or "paper",
                    "entry_date":       str(i.entry_date) if i.entry_date else None,
                    "entry_price":      i.entry_price,
                    "current_price":    current,
                    "prev_close":       prev,
                    "day_pnl":          day_pnl,
                    "target_price":     i.target_price,
                    "stop_loss_price":  i.stop_loss_price,
                    "shares":           i.shares,
                    "position_size_aud": i.position_size_aud,
                    "unrealised_pnl":   i.unrealised_pnl,
                    "unrealised_pnl_pct": i.unrealised_pnl_pct,
                    "days_held":        i.days_held,
                    "signal_score":     i.signal_score,
                    "is_active":        True,
                    "strategy_name":    getattr(i, "strategy_name", None),
                    "direction":        getattr(i, "direction", None) or "long",
                    "source":           getattr(i, "source", "morning") or "morning",
                })

        ok = False
        for url, key, label in _all_db_configs():
            # New DB is a fresh account — exclude positions opened before the epoch
            rows = payload
            if label == "new":
                rows = [r for r in payload if (r.get("entry_date") or "") >= str(NEW_DB_EPOCH)]

            _delete(url, key, "watchlist", {"exchange": exchange_id})
            if not rows:
                logger.info("Watchlist empty for %s — cleared %s DB", exchange_id.upper(), label)
                ok = True
                continue
            result = _upsert(url, key, "watchlist", rows)
            if not result:
                # Fallback: strip trading_mode for older schemas
                rows_nm = [{k: v for k, v in row.items() if k != "trading_mode"} for row in rows]
                result = _upsert(url, key, "watchlist", rows_nm)
                if result:
                    logger.warning("Synced watchlist → %s DB without trading_mode column", label)
            if result:
                logger.info("Synced %d positions → %s DB (%s)", len(rows), label, exchange_id.upper())
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_watchlist_to_supabase failed: %s", e)
        return False


def sync_trades_to_supabase(days: int = 90) -> bool:
    """Upsert closed trades from the last N days to all configured Supabase instances."""
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
                    "source": getattr(r, "source", "morning") or "morning",
                }
                for r in rows_orm
            ]

        if not payload:
            logger.info("No closed trades to sync for %s", exchange_id.upper())
            return True

        ok = False
        for url, key, label in _all_db_configs():
            # New DB is a fresh account — only include trades entered on or after epoch
            rows = payload
            if label == "new":
                rows = [r for r in payload if (r.get("entry_date") or "") >= str(NEW_DB_EPOCH)]
            if not rows:
                logger.info("No new-epoch trades to sync for %s → %s DB", exchange_id.upper(), label)
                ok = True
                continue
            result = _upsert(url, key, "trades", rows)
            if result:
                logger.info("Synced %d trades → %s DB (%s)", len(rows), label, exchange_id.upper())
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_trades_to_supabase failed: %s", e)
        return False


def sync_strategy_assignments_to_supabase() -> bool:
    """Upsert per-stock strategy assignments for the active exchange to all configured Supabase instances."""
    exchange_id = _get_exchange_id()
    suffix = _ticker_suffix(exchange_id)

    try:
        from storage.database import get_session
        from storage.models import StrategyAssignment

        with get_session() as session:
            rows_orm = (
                session.query(StrategyAssignment)
                .filter(StrategyAssignment.ticker.endswith(suffix))
                .all()
            )
            payload = [
                {
                    "ticker": r.ticker,
                    "exchange": exchange_id,
                    "strategy_name": r.strategy_name,
                    "direction": getattr(r, "direction", None) or "long",
                    "validated": bool(r.validated),
                    "bt_trades": r.bt_trades,
                    "bt_win_rate": r.bt_win_rate,
                    "bt_profit_factor": r.bt_profit_factor,
                    "fw_trades": r.fw_trades,
                    "fw_win_rate": r.fw_win_rate,
                    "fw_profit_factor": r.fw_profit_factor,
                    "fw_total_return_pct": r.fw_total_return_pct,
                    "rank_score": r.rank_score,
                }
                for r in rows_orm
            ]

        if not payload:
            logger.info("No strategy assignments to sync for %s", exchange_id.upper())
            return True

        ok = False
        for url, key, label in _all_db_configs():
            result = _upsert(url, key, "strategy_assignments", payload)
            if result:
                logger.info("Synced %d strategy assignments → %s DB (%s)", len(payload), label, exchange_id.upper())
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_strategy_assignments_to_supabase failed: %s", e)
        return False


def sync_backtest_to_supabase(results: dict) -> bool:
    """Store walk-forward backtest results as a JSON snapshot in all configured Supabase instances."""
    exchange_id = _get_exchange_id()

    try:
        payload = [
            {
                "exchange": exchange_id,
                "results_json": json.dumps(results),
            }
        ]
        import requests

        ok = False
        for url, key, label in _all_db_configs():
            headers = _headers(key)
            headers["Prefer"] = "return=minimal"
            resp = requests.post(
                f"{url}/rest/v1/backtest_cache",
                headers=headers,
                data=json.dumps(payload),
                timeout=30,
            )
            result = resp.status_code in (200, 201)
            if result:
                logger.info("Synced backtest results → %s DB (%s): %d tickers",
                            label, exchange_id.upper(), len(results))
            else:
                logger.warning("Backtest sync failed on %s DB: %s %s", label, resp.status_code, resp.text[:200])
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_backtest_to_supabase failed: %s", e)
        return False


def sync_daily_pnl_to_supabase() -> bool:
    """
    Upsert today's P&L snapshot into the daily_pnl table.
    Called at market close to build a day-by-day performance history.

    Rows:  date, exchange, day_pnl (intraday open move),
           realised_today (closed trades today), total_day_pnl, portfolio_value.
    """
    exchange_id = _get_exchange_id()
    suffix      = _ticker_suffix(exchange_id)
    today       = date.today()

    try:
        from storage.database import get_session
        from storage.models import WatchlistItem, Trade, Price

        with get_session() as session:
            # Intraday move on open positions (current vs prev close)
            items = (
                session.query(WatchlistItem)
                .filter(WatchlistItem.is_active == True, WatchlistItem.ticker.endswith(suffix))
                .all()
            )
            day_pnl = 0.0
            portfolio_value = 0.0
            for i in items:
                current = i.current_price or i.entry_price or 0
                portfolio_value += current * (i.shares or 0)
                prev_row = (
                    session.query(Price.close)
                    .filter(Price.ticker == i.ticker, Price.date < today)
                    .order_by(Price.date.desc())
                    .first()
                )
                if prev_row:
                    sign = -1 if (getattr(i, "direction", None) or "long") == "short" else 1
                    day_pnl += sign * (current - prev_row[0]) * (i.shares or 0)

            # Realised P&L from trades closed today
            closed_today = (
                session.query(Trade)
                .filter(Trade.exit_date == today, Trade.ticker.endswith(suffix))
                .all()
            )
            realised_today = sum(t.net_pnl or 0 for t in closed_today)

        payload = [{
            "date":            str(today),
            "exchange":        exchange_id,
            "day_pnl":         round(day_pnl, 2),
            "realised_today":  round(realised_today, 2),
            "total_day_pnl":   round(day_pnl + realised_today, 2),
            "portfolio_value": round(portfolio_value, 2),
            "positions_count": len(items),
        }]

        ok = False
        for url, key, label in _all_db_configs():
            if label == "new" and str(today) < str(NEW_DB_EPOCH):
                continue
            result = _upsert(url, key, "daily_pnl", payload)
            if result:
                logger.info(
                    "Synced daily P&L → %s DB (%s): day=%+.2f realised=%+.2f",
                    label, exchange_id.upper(), day_pnl, realised_today,
                )
            ok = ok or result
        return ok

    except Exception as e:
        logger.warning("sync_daily_pnl_to_supabase failed: %s", e)
        return False
