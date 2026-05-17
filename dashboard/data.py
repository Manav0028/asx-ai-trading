"""
Phase 2 · Dashboard — Dual-Backend Data Layer

Automatically switches between:
  • Supabase  — when SUPABASE_URL env var is set (Streamlit Cloud deployment)
  • Local PG  — when SUPABASE_URL is absent (local development on Mac)

All public functions return plain Python dicts/lists so Streamlit's
@st.cache_data can hash them without issues.

Exchange filtering:
  Supabase path → filter by .eq("exchange", exchange)
  Local PG path → filter by ticker suffix (.AX / .NS)
"""

import os
from datetime import date, timedelta
from typing import Dict, List, Optional


# ── Backend helpers ───────────────────────────────────────────────────────────

def _use_supabase() -> bool:
    return bool(os.getenv("SUPABASE_URL", ""))


def _supabase_client():
    """Module-level singleton Supabase client."""
    if not hasattr(_supabase_client, "_instance"):
        from supabase import create_client
        _supabase_client._instance = create_client(
            os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
        )
    return _supabase_client._instance


def _ticker_suffix(exchange: str) -> str:
    return ".AX" if exchange == "asx" else ".NS"


def _signal_row_to_dict(r) -> Dict:
    """SQLAlchemy Signal ORM row → plain dict."""
    return {
        "ticker": r.ticker,
        "date": str(r.date) if r.date else None,
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


def _watchlist_row_to_dict(i) -> Dict:
    """SQLAlchemy WatchlistItem ORM row → plain dict."""
    return {
        "ticker": i.ticker,
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
    }


def _trade_row_to_dict(r) -> Dict:
    """SQLAlchemy Trade ORM row → plain dict."""
    return {
        "ticker": r.ticker,
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


# ── Signals ───────────────────────────────────────────────────────────────────

def get_signals(exchange: str, signal_date: date = None, n: int = 10) -> List[Dict]:
    """
    Top-N signals for the exchange on the given date.
    Falls back up to 3 days back to handle weekends / holidays.
    """
    signal_date = signal_date or date.today()
    if _use_supabase():
        return _signals_supabase(exchange, signal_date, n)
    return _signals_local(exchange, signal_date, n)


def _signals_supabase(exchange: str, signal_date: date, n: int) -> List[Dict]:
    client = _supabase_client()
    for attempt in range(3):
        d = signal_date - timedelta(days=attempt)
        resp = (
            client.table("signals")
            .select("*")
            .eq("exchange", exchange)
            .eq("date", str(d))
            .order("composite_score", desc=True)
            .limit(n)
            .execute()
        )
        if resp.data:
            return resp.data
    return []


def _signals_local(exchange: str, signal_date: date, n: int) -> List[Dict]:
    from storage.database import get_session
    from storage.models import Signal
    suffix = _ticker_suffix(exchange)
    for attempt in range(3):
        d = signal_date - timedelta(days=attempt)
        with get_session() as session:
            rows = (
                session.query(Signal)
                .filter(Signal.date == d, Signal.ticker.endswith(suffix))
                .order_by(Signal.composite_score.desc())
                .limit(n)
                .all()
            )
            if rows:
                return [_signal_row_to_dict(r) for r in rows]
    return []


# ── Portfolio (open positions) ─────────────────────────────────────────────────

def get_portfolio(exchange: str) -> Dict:
    """
    Returns watchlist summary for the given exchange:
    {total_positions, total_unrealised_pnl, winners, losers, positions: List[Dict]}
    """
    if _use_supabase():
        positions = _portfolio_supabase(exchange)
    else:
        positions = _portfolio_local(exchange)

    total_pnl = sum(p.get("unrealised_pnl") or 0 for p in positions)
    winners = sum(1 for p in positions if (p.get("unrealised_pnl") or 0) > 0)
    return {
        "total_positions": len(positions),
        "total_unrealised_pnl": round(total_pnl, 2),
        "winners": winners,
        "losers": len(positions) - winners,
        "positions": positions,
    }


def _portfolio_supabase(exchange: str) -> List[Dict]:
    client = _supabase_client()
    resp = (
        client.table("watchlist")
        .select("*")
        .eq("exchange", exchange)
        .eq("is_active", True)
        .order("unrealised_pnl_pct", desc=True)
        .execute()
    )
    return resp.data or []


def _portfolio_local(exchange: str) -> List[Dict]:
    from storage.database import get_session
    from storage.models import WatchlistItem
    suffix = _ticker_suffix(exchange)
    with get_session() as session:
        items = (
            session.query(WatchlistItem)
            .filter(WatchlistItem.is_active == True, WatchlistItem.ticker.endswith(suffix))
            .order_by(WatchlistItem.unrealised_pnl_pct.desc())
            .all()
        )
        return [_watchlist_row_to_dict(i) for i in items]


# ── Closed Trades ─────────────────────────────────────────────────────────────

def get_trades(exchange: str, days: int = 90) -> List[Dict]:
    """Closed trades for the exchange over the last N days, newest first."""
    cutoff = date.today() - timedelta(days=days)
    if _use_supabase():
        return _trades_supabase(exchange, cutoff)
    return _trades_local(exchange, cutoff)


def _trades_supabase(exchange: str, cutoff: date) -> List[Dict]:
    client = _supabase_client()
    resp = (
        client.table("trades")
        .select("*")
        .eq("exchange", exchange)
        .gte("exit_date", str(cutoff))
        .not_.is_("exit_date", "null")
        .order("exit_date", desc=True)
        .execute()
    )
    return resp.data or []


def _trades_local(exchange: str, cutoff: date) -> List[Dict]:
    from storage.database import get_session
    from storage.models import Trade
    suffix = _ticker_suffix(exchange)
    with get_session() as session:
        rows = (
            session.query(Trade)
            .filter(
                Trade.exit_date != None,
                Trade.exit_date >= cutoff,
                Trade.ticker.endswith(suffix),
            )
            .order_by(Trade.exit_date.desc())
            .all()
        )
        return [_trade_row_to_dict(r) for r in rows]


# ── Market Regime ─────────────────────────────────────────────────────────────

def get_regime(exchange: str) -> Dict:
    """
    Returns regime dict: {regime_ok, index, index_name, ema200, pct_above}
    Supabase path reads from the 'regime' table (synced by scheduler).
    Local PG path calls get_regime_summary() directly.
    """
    if _use_supabase():
        return _regime_supabase(exchange)
    return _regime_local(exchange)


def _regime_supabase(exchange: str) -> Dict:
    client = _supabase_client()
    try:
        resp = (
            client.table("regime")
            .select("*")
            .eq("exchange", exchange)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return {
                "regime_ok": row.get("regime_ok"),
                "index": row.get("index_val"),
                "index_name": row.get("index_name", "Index"),
                "ema200": row.get("ema200"),
                "pct_above": row.get("pct_above"),
            }
    except Exception:
        pass
    return {"regime_ok": None, "index": None, "index_name": "Index", "ema200": None, "pct_above": None}


def _regime_local(exchange: str) -> Dict:
    try:
        # Temporarily set EXCHANGE so regime_filter reads the right index
        old = os.environ.get("EXCHANGE")
        os.environ["EXCHANGE"] = exchange
        from ai_engine.regime_filter import get_regime_summary
        result = get_regime_summary()
        if old is None:
            os.environ.pop("EXCHANGE", None)
        else:
            os.environ["EXCHANGE"] = old
        return result
    except Exception:
        return {"regime_ok": None, "index": None, "index_name": "Index", "ema200": None, "pct_above": None}


# ── Cumulative P&L time series ─────────────────────────────────────────────────

def get_cumulative_pnl(exchange: str, days: int = 90) -> List[Dict]:
    """
    Daily and cumulative net P&L from closed trades.
    Returns: [{date, daily_pnl, cumulative_pnl}] sorted ascending by date.
    Computed from get_trades() output — no extra DB query.
    """
    trades = get_trades(exchange, days=days)
    if not trades:
        return []

    daily: Dict[str, float] = {}
    for t in trades:
        d = t.get("exit_date") or ""
        if d:
            daily[d] = daily.get(d, 0.0) + (t.get("net_pnl") or 0.0)

    cumulative = 0.0
    result = []
    for d in sorted(daily.keys()):
        cumulative += daily[d]
        result.append({
            "date": d,
            "daily_pnl": round(daily[d], 2),
            "cumulative_pnl": round(cumulative, 2),
        })
    return result


# ── Score history for a single ticker ────────────────────────────────────────

def get_score_history(ticker: str, days: int = 30) -> List[Dict]:
    """Composite + component score history for one ticker over last N days."""
    cutoff = date.today() - timedelta(days=days)
    if _use_supabase():
        return _score_history_supabase(ticker, cutoff)
    return _score_history_local(ticker, cutoff)


def _score_history_supabase(ticker: str, cutoff: date) -> List[Dict]:
    client = _supabase_client()
    resp = (
        client.table("signals")
        .select("date,composite_score,sentiment_score,fundamental_score,technical_score,insider_score")
        .eq("ticker", ticker)
        .gte("date", str(cutoff))
        .order("date")
        .execute()
    )
    return resp.data or []


def _score_history_local(ticker: str, cutoff: date) -> List[Dict]:
    from storage.database import get_session
    from storage.models import Signal
    with get_session() as session:
        rows = (
            session.query(Signal)
            .filter(Signal.ticker == ticker, Signal.date >= cutoff)
            .order_by(Signal.date)
            .all()
        )
        return [
            {
                "date": str(r.date),
                "composite_score": r.composite_score,
                "sentiment_score": r.sentiment_score,
                "fundamental_score": r.fundamental_score,
                "technical_score": r.technical_score,
                "insider_score": r.insider_score,
            }
            for r in rows
        ]


# ── Backtest results ──────────────────────────────────────────────────────────

def get_backtest_results(exchange: str) -> Dict:
    """
    Most recent backtest results for the exchange.
    Supabase: read from backtest_cache table (written by Sunday scheduler).
    Local PG: return {} — backtest is too slow to run on-demand in the dashboard.
    """
    if _use_supabase():
        return _backtest_supabase(exchange)
    return {}


def _backtest_supabase(exchange: str) -> Dict:
    client = _supabase_client()
    try:
        resp = (
            client.table("backtest_cache")
            .select("results_json,computed_at")
            .eq("exchange", exchange)
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            import json
            return json.loads(resp.data[0]["results_json"])
    except Exception:
        pass
    return {}
