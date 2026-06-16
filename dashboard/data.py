"""
Phase 2 · Dashboard — Dual-Backend Data Layer

Automatically switches between:
  • Supabase  — when SUPABASE_URL env var is set (Streamlit Cloud deployment)
  • Local PG  — when SUPABASE_URL is absent (local development on Mac)

Uses the Supabase REST API directly via requests — no supabase-py dependency.
This avoids the pyiceberg/pydantic version conflicts in the conda environment.

All public functions return plain Python dicts/lists so Streamlit's
@st.cache_data can hash them without issues.

Exchange filtering:
  Supabase path → filter by exchange= query param
  Local PG path → filter by ticker suffix (.AX / .NS)
"""

import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


# ── Market hours ──────────────────────────────────────────────────────────────

_EXCHANGE_TZ = {
    "asx": ("Australia/Sydney", 10,  0, 16,  0),   # open 10:00, close 16:00
    "nse": ("Asia/Kolkata",      9, 15, 15, 30),   # open  9:15, close 15:30
}


def is_market_open(exchange: str) -> bool:
    """Return True if the exchange is currently within trading hours (weekdays only)."""
    try:
        tz_name, oh, om, ch, cm = _EXCHANGE_TZ.get(exchange, _EXCHANGE_TZ["asx"])
        now = datetime.now(ZoneInfo(tz_name))
        if now.weekday() >= 5:          # Saturday / Sunday
            return False
        open_t  = now.replace(hour=oh, minute=om,  second=0, microsecond=0)
        close_t = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
        return open_t <= now <= close_t
    except Exception:
        return False


def market_status(exchange: str) -> dict:
    """Return {open: bool, label: str, local_time: str} for the exchange."""
    try:
        tz_name, oh, om, ch, cm = _EXCHANGE_TZ.get(exchange, _EXCHANGE_TZ["asx"])
        now   = datetime.now(ZoneInfo(tz_name))
        open_ = is_market_open(exchange)
        return {
            "open":       open_,
            "label":      "🟢 Market Open" if open_ else "🔴 Market Closed",
            "local_time": now.strftime("%H:%M %Z %a"),
        }
    except Exception:
        return {"open": False, "label": "—", "local_time": ""}


def get_live_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Fetch the latest trade price for each ticker from yfinance.
    Returns {ticker: price}. Silently skips failed tickers.
    Called only when the market is open.
    """
    if not tickers:
        return {}
    try:
        import yfinance as yf
        prices: Dict[str, float] = {}
        # download with 1-minute bars for today; take the last close
        raw = yf.download(
            tickers, period="1d", interval="1m",
            progress=False, auto_adjust=True,
        )
        if raw.empty:
            return prices
        close = raw["Close"] if "Close" in raw.columns else raw.get("close", raw)
        if len(tickers) == 1:
            val = close.dropna().iloc[-1]
            prices[tickers[0]] = float(val)
        else:
            for t in tickers:
                try:
                    prices[t] = float(close[t].dropna().iloc[-1])
                except Exception:
                    pass
        return prices
    except Exception:
        return {}


# ── Backend helpers ───────────────────────────────────────────────────────────

def _use_supabase() -> bool:
    return bool(os.getenv("SUPABASE_URL", ""))


def _sb_config():
    """Return (url, key) for Supabase REST calls."""
    return os.getenv("SUPABASE_URL", "").rstrip("/"), os.getenv("SUPABASE_KEY", "")


def _sb_headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _sb_get(table: str, params: dict) -> list:
    """GET rows from a Supabase table using PostgREST query params."""
    import requests
    url, key = _sb_config()
    resp = requests.get(
        f"{url}/rest/v1/{table}",
        headers=_sb_headers(key),
        params=params,
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json() or []
    return []


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
        "strategy_name": getattr(r, "strategy_name", None),
        "direction": getattr(r, "direction", None) or "long",
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
        # trading_mode added in Phase 2 — default to 'paper' for older rows
        "trading_mode": getattr(i, "trading_mode", None) or "paper",
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
    for attempt in range(3):
        d = signal_date - timedelta(days=attempt)
        rows = _sb_get("signals", {
            "exchange": f"eq.{exchange}",
            "date": f"eq.{d}",
            "order": "composite_score.desc",
            "limit": n,
            "select": "*",
        })
        if rows:
            return rows
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

def _get_prev_closes(tickers: List[str]) -> Dict[str, float]:
    """Get the previous trading day's close price for each ticker from the Price table."""
    result: Dict[str, float] = {}
    if not tickers:
        return result
    try:
        if _use_supabase():
            for t in tickers:
                rows = _sb_get("prices", {
                    "ticker": f"eq.{t}",
                    "order": "date.desc",
                    "limit": 2,
                    "select": "close",
                })
                if len(rows) >= 2:
                    result[t] = float(rows[1]["close"])
                elif rows:
                    result[t] = float(rows[0]["close"])
        else:
            from storage.database import get_session
            from storage.models import Price
            with get_session() as session:
                for t in tickers:
                    rows = (
                        session.query(Price.close)
                        .filter(Price.ticker == t)
                        .order_by(Price.date.desc())
                        .limit(2)
                        .all()
                    )
                    if len(rows) >= 2:
                        result[t] = float(rows[1].close)
                    elif rows:
                        result[t] = float(rows[0].close)
    except Exception:
        pass
    return result


def get_portfolio(exchange: str, live: bool = False) -> Dict:
    """
    Returns watchlist summary for the given exchange.
    When live=True AND the market is open, overlays real-time prices
    from yfinance on top of the Supabase/PG base data.
    """
    if _use_supabase():
        positions = _portfolio_supabase(exchange)
    else:
        positions = _portfolio_local(exchange)

    # ── Optional: overlay live prices ────────────────────────────────────
    live_prices: Dict[str, float] = {}
    if live and positions and is_market_open(exchange):
        tickers = [p["ticker"] for p in positions]
        live_prices = get_live_prices(tickers)

    # ── Fetch previous close for day's P&L ────────────────────────────────
    prev_closes: Dict[str, float] = {}
    if positions:
        prev_closes = _get_prev_closes([p.get("ticker", "") for p in positions])

    # ── Per-position derived fields ───────────────────────────────────────
    for p in positions:
        ticker   = p.get("ticker", "")
        shares   = p.get("shares") or 0
        entry    = p.get("entry_price") or 0
        invested = p.get("position_size_aud") or 0

        # Override current_price with live quote when available
        if ticker in live_prices:
            cp = live_prices[ticker]
            p["current_price"]     = round(cp, 4)
            p["unrealised_pnl"]    = round((cp - entry) * shares, 2)
            p["unrealised_pnl_pct"] = round((cp - entry) / entry * 100, 2) if entry else 0
        else:
            cp = p.get("current_price") or 0

        p["invested"]      = round(invested, 2)
        p["current_value"] = round(cp * shares, 2)
        p["is_live"]       = ticker in live_prices

        prev_close = prev_closes.get(ticker)
        if prev_close is not None and prev_close != cp:
            p["day_pnl"]     = round((cp - prev_close) * shares, 2)
            p["day_pnl_pct"] = round((cp - prev_close) / prev_close * 100, 2) if prev_close else 0
        else:
            # No prev-close available (price history missing) — show 0 rather than
            # falling back to entry price which makes Day P&L equal Unrealised P&L.
            p["day_pnl"]     = 0
            p["day_pnl_pct"] = 0

    total_unrealised_pnl = sum(p.get("unrealised_pnl")   or 0 for p in positions)
    total_invested       = sum(p.get("invested")          or 0 for p in positions)
    total_current_value  = sum(p.get("current_value")     or 0 for p in positions)
    open_day_pnl         = sum(p.get("day_pnl")           or 0 for p in positions)
    winners = sum(1 for p in positions if (p.get("unrealised_pnl") or 0) > 0)

    # Cumulative realised P&L from all closed trades, plus today's realised P&L,
    # so "Total P&L" reflects every day's results, not just open positions.
    realised_all_time, realised_today = _realised_pnl_totals(exchange)
    total_pnl     = total_unrealised_pnl + realised_all_time
    total_day_pnl = open_day_pnl + realised_today

    return {
        "total_positions":      len(positions),
        "total_invested":       round(total_invested, 2),
        "total_current_value":  round(total_current_value, 2),
        "total_unrealised_pnl": round(total_pnl, 2),
        "total_day_pnl":        round(total_day_pnl, 2),
        "winners":    winners,
        "losers":     len(positions) - winners,
        "positions":  positions,
        "prices_live": bool(live_prices),
    }


def _portfolio_supabase(exchange: str) -> List[Dict]:
    return _sb_get("watchlist", {
        "exchange":     f"eq.{exchange}",
        "is_active":    "eq.true",
        "order":        "unrealised_pnl_pct.desc",
        "select":       "*",          # includes trading_mode column
    })


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

def _realised_pnl_totals(exchange: str) -> tuple:
    """Returns (all_time_realised_pnl, today_realised_pnl) from closed trades."""
    if _use_supabase():
        rows = _sb_get("trades", {
            "exchange": f"eq.{exchange}",
            "select": "net_pnl,exit_date",
        })
    else:
        from storage.database import get_session
        from storage.models import Trade
        suffix = _ticker_suffix(exchange)
        with get_session() as session:
            trade_rows = (
                session.query(Trade)
                .filter(Trade.exit_date != None, Trade.ticker.endswith(suffix))
                .all()
            )
            rows = [{"net_pnl": r.net_pnl, "exit_date": str(r.exit_date)} for r in trade_rows]

    today_str = str(date.today())
    all_time = sum(r.get("net_pnl") or 0 for r in rows)
    today = sum(r.get("net_pnl") or 0 for r in rows if str(r.get("exit_date")) == today_str)
    return all_time, today


def get_trades(exchange: str, days: int = 90) -> List[Dict]:
    """Closed trades for the exchange over the last N days, newest first."""
    cutoff = date.today() - timedelta(days=days)
    if _use_supabase():
        return _trades_supabase(exchange, cutoff)
    return _trades_local(exchange, cutoff)


def _trades_supabase(exchange: str, cutoff: date) -> List[Dict]:
    return _sb_get("trades", {
        "exchange": f"eq.{exchange}",
        "exit_date": f"gte.{cutoff}",
        "order": "exit_date.desc",
        "select": "*",
    })


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
    try:
        rows = _sb_get("regime", {"exchange": f"eq.{exchange}", "select": "*"})
        if rows:
            row = rows[0]
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
    return _sb_get("signals", {
        "ticker": f"eq.{ticker}",
        "date": f"gte.{cutoff}",
        "order": "date.asc",
        "select": "date,composite_score,sentiment_score,fundamental_score,technical_score,insider_score",
    })


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

def get_todays_scores(tickers: List[str], exchange: str) -> Dict[str, float]:
    """
    Bulk-fetch today's composite score for a list of tickers.
    Used by the Positions page to show signal strength at time of check.
    Returns {ticker: composite_score}.
    """
    if not tickers:
        return {}
    try:
        tz = "Australia/Sydney" if exchange == "asx" else "Asia/Kolkata"
        today_str = str(datetime.now(ZoneInfo(tz)).date())
    except Exception:
        today_str = str(date.today())

    if _use_supabase():
        # Fetch all tickers in one request using 'in' filter
        ticker_csv = ",".join(tickers)
        rows = _sb_get("signals", {
            "ticker": f"in.({ticker_csv})",
            "date": f"eq.{today_str}",
            "select": "ticker,composite_score",
        })
        return {r["ticker"]: r["composite_score"] for r in rows if r.get("composite_score")}
    else:
        try:
            from storage.database import get_session
            from storage.models import Signal
            from datetime import datetime
            today_date = datetime.strptime(today_str, "%Y-%m-%d").date()
            with get_session() as session:
                rows = (
                    session.query(Signal.ticker, Signal.composite_score)
                    .filter(Signal.date == today_date, Signal.ticker.in_(tickers))
                    .all()
                )
                return {r.ticker: r.composite_score for r in rows if r.composite_score}
        except Exception:
            return {}


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
    try:
        rows = _sb_get("backtest_cache", {
            "exchange": f"eq.{exchange}",
            "order": "computed_at.desc",
            "limit": 1,
            "select": "results_json,computed_at",
        })
        if rows:
            raw = rows[0]["results_json"]
            return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass
    return {}


# ── Price history & sparkline helpers ─────────────────────────────────────────

def _flatten_yf(raw):
    """
    yfinance ≥0.2 returns a MultiIndex column like ('Close','BHP.AX').
    Flatten to simple column names ('Close','High',...) for single-ticker frames,
    or keep the ticker-level accessible for multi-ticker frames.
    Returns (df_flat, is_multi) where df_flat has simple string columns.
    """
    import pandas as pd
    if isinstance(raw.columns, pd.MultiIndex):
        # Single ticker: columns are ('Close','BHP.AX') — drop ticker level
        if len(raw.columns.get_level_values(1).unique()) == 1:
            raw = raw.droplevel(1, axis=1)
            return raw, False
        # Multi-ticker: keep multi-index, caller accesses via raw["Close"][ticker]
        return raw, True
    return raw, False


def get_price_history(ticker: str, days: int = 60) -> List[Dict]:
    """
    Fetch OHLCV candles for candlestick charts.
    Returns [{date, open, high, low, close, volume}] sorted ascending.
    """
    try:
        import yfinance as yf
        raw = yf.download(ticker, period=f"{days}d", interval="1d",
                          progress=False, auto_adjust=True)
        if raw.empty:
            return []
        raw, _ = _flatten_yf(raw)
        result = []
        for dt, row in raw.iterrows():
            try:
                result.append({
                    "date":   str(dt.date()),
                    "open":   float(row["Open"]),
                    "high":   float(row["High"]),
                    "low":    float(row["Low"]),
                    "close":  float(row["Close"]),
                    "volume": float(row.get("Volume", 0)),
                })
            except Exception:
                pass
        return result
    except Exception:
        return []


def get_multi_close(tickers: List[str], days: int = 20) -> Dict[str, List[Dict]]:
    """
    Batch fetch daily close prices for multiple tickers (sparklines).
    Returns {ticker: [{date, close}]} sorted ascending.
    """
    if not tickers:
        return {}
    try:
        import yfinance as yf
        raw = yf.download(tickers, period=f"{days}d", interval="1d",
                          progress=False, auto_adjust=True)
        if raw.empty:
            return {}
        raw, is_multi = _flatten_yf(raw)
        result: Dict[str, List[Dict]] = {}
        if not is_multi:
            # Single ticker case (already flattened)
            t = tickers[0]
            col = raw["Close"].dropna()
            result[t] = [{"date": str(d.date()), "close": float(v)}
                         for d, v in col.items()]
        else:
            closes = raw["Close"]
            for t in tickers:
                try:
                    col = closes[t].dropna()
                    result[t] = [{"date": str(d.date()), "close": float(v)}
                                 for d, v in col.items()]
                except Exception:
                    pass
        return result
    except Exception:
        return {}


def get_strategy_assignments(exchange: str) -> List[Dict]:
    """Per-stock strategy assignments — written by the weekly selection job."""
    if _use_supabase():
        return _strategy_assignments_supabase(exchange)
    return _strategy_assignments_local(exchange)


def _strategy_assignments_supabase(exchange: str) -> List[Dict]:
    rows = _sb_get("strategy_assignments", {
        "exchange": f"eq.{exchange}",
        "order": "validated.desc,rank_score.desc",
        "select": "*",
    })
    for r in rows:
        r["direction"] = r.get("direction") or "long"
    return rows


def _strategy_assignments_local(exchange: str) -> List[Dict]:
    try:
        from storage.database import get_session
        from storage.models import StrategyAssignment
        suffix = _ticker_suffix(exchange)
        with get_session() as session:
            rows = (
                session.query(StrategyAssignment)
                .filter(StrategyAssignment.ticker.endswith(suffix))
                .order_by(StrategyAssignment.validated.desc(),
                          StrategyAssignment.rank_score.desc())
                .all()
            )
            return [
                {
                    "ticker": r.ticker,
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
                for r in rows
            ]
    except Exception:
        return []


def get_strategy_radar(exchange: str) -> List[Dict]:
    """Live Strategy Radar: every assignment joined with today's signal so the
    dashboard can show which validated strategies are firing right now."""
    if _use_supabase():
        return _strategy_radar_supabase(exchange)
    return _strategy_radar_local(exchange)


def _strategy_radar_supabase(exchange: str) -> List[Dict]:
    try:
        assignments = _sb_get("strategy_assignments", {
            "exchange": f"eq.{exchange}",
            "select": "*",
        })
        today_str = str(date.today())
        sig_rows = _sb_get("signals", {
            "exchange": f"eq.{exchange}",
            "date": f"eq.{today_str}",
            "select": "*",
        })
        sig_by_ticker = {s["ticker"]: s for s in sig_rows}
        out = []
        for a in assignments:
            s = sig_by_ticker.get(a["ticker"])
            firing = bool(s and (s.get("position_size_aud") or 0) > 0)
            strategy_fires = bool(s and s.get("strategy_fires"))
            near_miss = strategy_fires and not firing
            out.append({
                "ticker": a["ticker"],
                "strategy_name": a.get("strategy_name"),
                "direction": a.get("direction") or "long",
                "validated": bool(a.get("validated")),
                "firing": firing,
                "near_miss": near_miss,
                "composite_score": s.get("composite_score") if s else None,
                "entry_price": s.get("entry_price") if s else None,
                "target_price": s.get("target_price") if s else None,
                "stop_loss_price": s.get("stop_loss_price") if s else None,
                "fw_profit_factor": a.get("fw_profit_factor"),
                "fw_win_rate": a.get("fw_win_rate"),
                "rank_score": a.get("rank_score"),
                "bt_trades": a.get("bt_trades"),
                "bt_win_rate": a.get("bt_win_rate"),
                "bt_profit_factor": a.get("bt_profit_factor"),
                "bt_avg_return_pct": a.get("bt_avg_return_pct"),
                "fw_trades": a.get("fw_trades"),
                "fw_total_return_pct": a.get("fw_total_return_pct"),
                "sentiment_score": s.get("sentiment_score") if s else None,
                "fundamental_score": s.get("fundamental_score") if s else None,
                "technical_score": s.get("technical_score") if s else None,
                "insider_score": s.get("insider_score") if s else None,
                "regime_ok": s.get("regime_ok") if s else None,
                "strategy_fires": strategy_fires,
            })
        out.sort(key=lambda r: (not r["firing"], not r["near_miss"], not r["validated"], -(r["rank_score"] or 0)))
        return out
    except Exception:
        return []


def _strategy_radar_local(exchange: str) -> List[Dict]:
    try:
        from datetime import date as _date
        from storage.database import get_session
        from storage.models import Signal, StrategyAssignment
        suffix = _ticker_suffix(exchange)
        with get_session() as session:
            assignments = (
                session.query(StrategyAssignment)
                .filter(StrategyAssignment.ticker.endswith(suffix))
                .all()
            )
            sig_rows = (
                session.query(Signal)
                .filter(Signal.date == _date.today(), Signal.ticker.endswith(suffix))
                .all()
            )
            sig_by_ticker = {s.ticker: s for s in sig_rows}
            out = []
            for a in assignments:
                s = sig_by_ticker.get(a.ticker)
                firing = bool(s and (s.position_size_aud or 0) > 0)
                strategy_fires = bool(s and getattr(s, "strategy_fires", False))
                near_miss = strategy_fires and not firing
                out.append({
                    "ticker": a.ticker,
                    "strategy_name": a.strategy_name,
                    "direction": getattr(a, "direction", None) or "long",
                    "validated": bool(a.validated),
                    "firing": firing,
                    "near_miss": near_miss,
                    "composite_score": s.composite_score if s else None,
                    "entry_price": s.entry_price if s else None,
                    "target_price": s.target_price if s else None,
                    "stop_loss_price": s.stop_loss_price if s else None,
                    "fw_profit_factor": a.fw_profit_factor,
                    "fw_win_rate": a.fw_win_rate,
                    "rank_score": a.rank_score,
                    "bt_trades": a.bt_trades,
                    "bt_win_rate": a.bt_win_rate,
                    "bt_profit_factor": a.bt_profit_factor,
                    "bt_avg_return_pct": a.bt_avg_return_pct,
                    "fw_trades": a.fw_trades,
                    "fw_total_return_pct": a.fw_total_return_pct,
                    "sentiment_score": s.sentiment_score if s else None,
                    "fundamental_score": s.fundamental_score if s else None,
                    "technical_score": s.technical_score if s else None,
                    "insider_score": s.insider_score if s else None,
                    "regime_ok": s.regime_ok if s else None,
                    "strategy_fires": strategy_fires,
                })
            # firing first, then near-miss, then validated by rank
            out.sort(key=lambda r: (not r["firing"], not r["near_miss"], not r["validated"], -(r["rank_score"] or 0)))
            return out
    except Exception:
        return []


def ticker_tv_url(ticker: str) -> str:
    """TradingView chart URL for a ticker."""
    if ticker.endswith(".AX"):
        sym = f"ASX:{ticker[:-3]}"
    elif ticker.endswith(".NS"):
        sym = f"NSE:{ticker[:-3]}"
    else:
        sym = ticker
    return f"https://www.tradingview.com/chart/?symbol={sym}"


def ticker_yahoo_url(ticker: str) -> str:
    """Yahoo Finance quote URL."""
    return f"https://finance.yahoo.com/quote/{ticker}"
