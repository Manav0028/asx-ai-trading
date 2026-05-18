"""
Phase 2 · AI Trading Dashboard
Streamlit app — 5 pages, auto-refreshes every 5 minutes.

Run locally:   streamlit run dashboard/app.py
Deployed to:   Streamlit Cloud (share.streamlit.io)

Data source:
  • SUPABASE_URL set → reads from Supabase (Streamlit Cloud)
  • Not set         → reads from local PostgreSQL port 5433 (Mac dev)
"""

import sys
import os

# Allow running from repo root: `streamlit run dashboard/app.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import streamlit as st


# ── Formatting helpers ────────────────────────────────────────────────────────

def _delta(val: float, currency: str = "") -> str:
    """
    Format a delta value so Streamlit correctly detects positive/negative.
    Puts the sign BEFORE the currency symbol: -₹682 or +$1,234.
    Streamlit reads the first character to decide green vs red arrow.
    """
    sign = "+" if val >= 0 else "-"
    return f"{sign}{currency}{abs(val):,.0f}"


def _delta_pct(val: float) -> str:
    """Format a percentage delta: +1.34% or -1.34%."""
    return f"{val:+.2f}%"


def _today(exchange: str) -> date:
    """
    Return today's date in the exchange's local timezone.
    Streamlit Cloud runs in UTC — without this, ASX shows yesterday
    because 8 AM Sydney = previous day in UTC.
    """
    try:
        from datetime import datetime
        tz = "Australia/Sydney" if exchange == "asx" else "Asia/Kolkata"
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return date.today()

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Import data layer (must come before any data calls) ──────────────────────
from dashboard.data import (
    get_signals,
    get_portfolio,
    get_trades,
    get_regime,
    get_cumulative_pnl,
    get_score_history,
    get_backtest_results,
    get_todays_scores,
    is_market_open,
    market_status,
)

# ── Auto-refresh: 30 s when market open, 5 min when closed ───────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    _either_open = is_market_open("asx") or is_market_open("nse")
    _interval_ms = 30_000 if _either_open else 300_000
    st_autorefresh(interval=_interval_ms, key="auto_refresh")
except ImportError:
    pass

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Trading mode badge ─────────────────────────────────────────────────
    import os
    _phase = int(os.getenv("TRADING_PHASE", 1))
    if _phase >= 3:
        st.title("💰 AI Trading")
        st.error("🔴 LIVE TRADING", icon="⚠️")
    elif _phase == 2:
        st.title("📈 AI Trading")
        st.info("🔗 IBKR Paper Trading")
    else:
        st.title("📈 AI Trading")
        st.caption("📋 Internal Paper · ASX & NSE")

    _capital = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
    _risk_per_trade = _capital * 0.015
    st.caption(f"Capital: **${_capital:,.0f}** · Risk/trade: **${_risk_per_trade:,.0f}**")

    exchange = st.radio(
        "Exchange",
        options=["asx", "nse"],
        format_func=lambda x: "🇦🇺  ASX 200" if x == "asx" else "🇮🇳  NSE NIFTY 100",
    )
    currency = "$" if exchange == "asx" else "₹"
    exchange_label = "ASX 200 🇦🇺" if exchange == "asx" else "NSE NIFTY 100 🇮🇳"

    st.divider()

    page = st.selectbox(
        "Page",
        options=["📊 Overview", "🏆 Signals", "📋 Portfolio", "💼 Positions", "📈 Trade History", "🔬 Backtest"],
    )

    st.divider()

    # ── Market status badge ────────────────────────────────────────────────
    mkt = market_status(exchange)
    _market_open = mkt["open"]
    if _market_open:
        st.success(f"{mkt['label']}")
    else:
        st.error(f"{mkt['label']}")
    st.caption(f"🕐 {mkt['local_time']}")

    if _market_open:
        st.caption("⚡ Live prices · refreshing every 30 s")
    else:
        st.caption("📦 Cached prices · refreshing every 5 min")

    st.divider()

    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

    from dashboard.data import _use_supabase
    source = "☁️ Supabase" if _use_supabase() else "🖥️ Local DB"
    st.caption(f"Data: {source}")


# ── Cached data loads ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_regime(exch):
    return get_regime(exch)

@st.cache_data(ttl=30)   # short TTL — live prices update every 30 s during market hours
def load_portfolio(exch, live=False):
    return get_portfolio(exch, live=live)

@st.cache_data(ttl=300)
def load_signals(exch, sig_date, n):
    return get_signals(exch, signal_date=sig_date, n=n)

@st.cache_data(ttl=300)
def load_trades(exch, days):
    return get_trades(exch, days=days)

@st.cache_data(ttl=300)
def load_cumulative_pnl(exch, days):
    return get_cumulative_pnl(exch, days=days)

@st.cache_data(ttl=3600)
def load_backtest(exch):
    return get_backtest_results(exch)

@st.cache_data(ttl=300)
def load_score_history(ticker, days):
    return get_score_history(ticker, days=days)


# ── Page helpers ──────────────────────────────────────────────────────────────

def _regime_banner(regime):
    """Show a success/warning banner for the current market regime."""
    ok = regime.get("regime_ok")
    idx = regime.get("index")
    idx_name = regime.get("index_name", "Index")
    ema = regime.get("ema200")
    pct = regime.get("pct_above")

    if ok is None:
        st.info("Regime data not yet available — scheduler will populate this after next run.")
        return

    if ok:
        msg = (
            f"**RISK-ON** ✅  |  {idx_name}: `{idx:,.0f}`"
            + (f"  —  {pct:+.1f}% above 200-day EMA (`{ema:,.0f}`)" if ema else "")
        )
        st.success(msg)
    else:
        msg = (
            f"**RISK-OFF** ⚠️  |  {idx_name}: `{idx:,.0f}`"
            + (f"  —  {pct:.1f}% below 200-day EMA (`{ema:,.0f}`) — positions halved"
               if ema else "")
        )
        st.warning(msg)


def _pnl_chart(pnl_series, currency_sym, title="Cumulative P&L"):
    import plotly.graph_objects as go
    if not pnl_series:
        st.info("No closed trades yet — P&L chart will appear once positions are closed.")
        return
    dates = [r["date"] for r in pnl_series]
    cumulative = [r["cumulative_pnl"] for r in pnl_series]
    final = cumulative[-1] if cumulative else 0
    colour = "#22c55e" if final >= 0 else "#ef4444"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=cumulative,
        mode="lines+markers",
        fill="tozeroy",
        fillcolor=f"rgba({'34,197,94' if final >= 0 else '239,68,68'},0.12)",
        line=dict(color=colour, width=2),
        marker=dict(size=4),
        name="Cumulative P&L",
        hovertemplate=f"%{{x}}<br>{currency_sym}%{{y:+,.0f}}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Date", yaxis_title=f"P&L ({currency_sym})",
        height=320, margin=dict(t=40, b=30, l=10, r=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix=currency_sym),
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Overview
# ══════════════════════════════════════════════════════════════════════════════

if page == "📊 Overview":
    st.header(f"📊 Overview — {exchange_label}")

    regime    = load_regime(exchange)
    portfolio = load_portfolio(exchange, live=_market_open)
    pnl_data  = load_cumulative_pnl(exchange, 90)

    if portfolio.get("prices_live"):
        st.caption("⚡ Prices updating live from market data")

    # ── Capital deployment bar ─────────────────────────────────────────────
    import os
    _cap = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
    _deployed = total_invested
    _deploy_pct = min(_deployed / _cap * 100, 100) if _cap else 0
    _avail = max(_cap - _deployed, 0)
    _risk_per_trade = _cap * 0.015

    cap_c1, cap_c2, cap_c3 = st.columns(3)
    cap_c1.metric("Capital Deployed", f"{currency}{_deployed:,.0f}",
                  delta=f"{_deploy_pct:.0f}% of {currency}{_cap:,.0f}")
    cap_c2.metric("Available Cash",   f"{currency}{_avail:,.0f}")
    cap_c3.metric("Risk per Trade",   f"{currency}{_risk_per_trade:,.0f}",
                  delta="1.5% ATR dollar-risk", delta_color="off")
    st.progress(min(_deploy_pct / 100, 1.0), text=f"Portfolio {_deploy_pct:.0f}% deployed")
    st.divider()

    # ── Metric cards ──────────────────────────────────────────────────────────
    total_pnl           = portfolio.get("total_unrealised_pnl", 0)
    total_invested      = portfolio.get("total_invested", 0)
    total_current_value = portfolio.get("total_current_value", 0)
    total_pnl_pct       = (total_pnl / total_invested * 100) if total_invested else 0

    diff = total_current_value - total_invested

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invested",  f"{currency}{total_invested:,.0f}")
    c2.metric(
        "Current Value",
        f"{currency}{total_current_value:,.0f}",
        delta=_delta(diff, currency),          # -₹682 or +$1,540
        delta_color="normal",                  # negative string → red, positive → green
    )
    c3.metric(
        "Unrealised P&L",
        f"{currency}{abs(total_pnl):,.0f}" if total_pnl < 0 else f"{currency}{total_pnl:,.0f}",
        delta=f"{_delta_pct(total_pnl_pct)}  ({portfolio['winners']}W / {portfolio['losers']}L)",
        delta_color="normal",                  # sign from pct string drives colour
    )
    ok = regime.get("regime_ok")
    regime_label = "BULLISH ✅" if ok else ("CAUTIOUS ⚠️" if ok is False else "—")
    pct_above = regime.get("pct_above")
    c4.metric(
        "Market Regime",
        regime_label,
        delta=f"{pct_above:+.1f}% vs EMA200" if pct_above is not None else None,
        delta_color="normal",   # pct_above sign drives colour: negative = red, positive = green
    )

    st.divider()
    _regime_banner(regime)
    st.divider()

    # ── Cumulative P&L chart ──────────────────────────────────────────────────
    _pnl_chart(pnl_data, currency, title="90-Day Cumulative Net P&L")

    # ── IBKR paper account widget (phase 2+) ─────────────────────────────────
    if _phase >= 2:
        with st.expander("🔗 IBKR Paper Account", expanded=False):
            try:
                from execution.ibkr_paper_trader import get_ibkr_account_summary
                ibkr = get_ibkr_account_summary()
                if ibkr:
                    acc = ibkr.get("account", {})
                    ic1, ic2, ic3 = st.columns(3)
                    ic1.metric("Net Liquidation",  acc.get("NetLiquidation",  "—"))
                    ic2.metric("Available Funds",  acc.get("AvailableFunds",  "—"))
                    ic3.metric("Unrealised P&L",   acc.get("UnrealizedPnL",  "—"))
                    if ibkr.get("positions"):
                        import pandas as pd
                        st.dataframe(
                            pd.DataFrame(ibkr["positions"]),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("No open positions in IBKR paper account yet.")
                else:
                    st.warning("TWS not responding — check that TWS is running with API enabled.")
            except Exception as e:
                st.warning(f"IBKR connect error: {e}")

    # ── Top 5 open positions summary ──────────────────────────────────────────
    positions = portfolio.get("positions", [])
    if positions:
        st.subheader(f"Open Positions ({portfolio['total_positions']} total)")
        import pandas as pd
        df = pd.DataFrame(positions[:5])
        for col in ["unrealised_pnl", "unrealised_pnl_pct", "entry_price",
                    "current_price", "invested", "current_value"]:
            if col not in df.columns:
                df[col] = None
        st.dataframe(
            df[["ticker", "invested", "current_value",
                "entry_price", "current_price",
                "unrealised_pnl", "unrealised_pnl_pct", "days_held"]],
            column_config={
                "ticker": "Ticker",
                "invested": st.column_config.NumberColumn(f"Invested ({currency})", format="%.0f"),
                "current_value": st.column_config.NumberColumn(f"Current Value ({currency})", format="%.0f"),
                "entry_price": st.column_config.NumberColumn(f"Avg Entry ({currency})", format="%.3f"),
                "current_price": st.column_config.NumberColumn(f"Last Price ({currency})", format="%.3f"),
                "unrealised_pnl": st.column_config.NumberColumn(f"P&L ({currency})", format="%+.2f"),
                "unrealised_pnl_pct": st.column_config.NumberColumn("P&L %", format="%+.1f%%"),
                "days_held": st.column_config.NumberColumn("Days Held"),
            },
            use_container_width=True,
            hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Signals
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🏆 Signals":
    st.header(f"🏆 Top Signals — {exchange_label}")

    col_date, col_n = st.columns([2, 1])
    with col_date:
        signal_date = st.date_input("Signal Date", value=_today(exchange))
    with col_n:
        n_signals = st.slider("Show top N", min_value=5, max_value=20, value=10)

    signals = load_signals(exchange, signal_date, n_signals)

    if not signals:
        st.info(
            f"No signals found for {signal_date.strftime('%d %b %Y')}. "
            "The scanner runs weekdays during pre-market hours."
        )
    else:
        st.caption(f"Showing {len(signals)} signal(s) for {signal_date.strftime('%d %b %Y')}")

        import pandas as pd
        df = pd.DataFrame(signals)

        # Add Yahoo Finance link column
        df["chart"] = df["ticker"].apply(
            lambda t: f"https://finance.yahoo.com/quote/{t}"
        )

        # Upside % column
        def _upside(row):
            e, t = row.get("entry_price"), row.get("target_price")
            if e and t and e > 0:
                return round((t - e) / e * 100, 1)
            return None
        df["upside_pct"] = df.apply(_upside, axis=1)

        display_cols = [
            "ticker", "composite_score", "sentiment_score", "fundamental_score",
            "technical_score", "insider_score",
            "entry_price", "target_price", "upside_pct", "stop_loss_price",
            "position_size_aud", "regime_ok", "chart",
        ]
        # Only include cols that exist
        display_cols = [c for c in display_cols if c in df.columns]

        st.dataframe(
            df[display_cols],
            column_config={
                "ticker": "Ticker",
                "composite_score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%.1f"
                ),
                "sentiment_score": st.column_config.ProgressColumn(
                    "Sentiment", min_value=0, max_value=100, format="%.0f"
                ),
                "fundamental_score": st.column_config.ProgressColumn(
                    "Business", min_value=0, max_value=100, format="%.0f"
                ),
                "technical_score": st.column_config.ProgressColumn(
                    "Chart", min_value=0, max_value=100, format="%.0f"
                ),
                "insider_score": st.column_config.ProgressColumn(
                    "Insider", min_value=0, max_value=100, format="%.0f"
                ),
                "entry_price": st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                "target_price": st.column_config.NumberColumn(f"Target ({currency})", format="%.3f"),
                "upside_pct": st.column_config.NumberColumn("Upside %", format="%+.1f%%"),
                "stop_loss_price": st.column_config.NumberColumn(f"Stop ({currency})", format="%.3f"),
                "position_size_aud": st.column_config.NumberColumn(
                    f"Position ({currency})", format="%.0f"
                ),
                "regime_ok": st.column_config.CheckboxColumn("Regime OK"),
                "chart": st.column_config.LinkColumn("Chart", display_text="📊 View"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # Score history expander for a selected ticker
        tickers_list = [s["ticker"] for s in signals]
        with st.expander("📈 Score History for a Ticker"):
            selected = st.selectbox("Select ticker", tickers_list)
            hist = load_score_history(selected, 30)
            if hist:
                import plotly.graph_objects as go
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[h["date"] for h in hist],
                    y=[h["composite_score"] for h in hist],
                    mode="lines+markers", name="Composite",
                    line=dict(color="#6366f1", width=2),
                ))
                fig.update_layout(
                    title=f"{selected} — 30-day Composite Score",
                    yaxis=dict(range=[0, 100]),
                    height=280, margin=dict(t=40, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No score history available yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Portfolio
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📋 Portfolio":
    col_h, col_badge = st.columns([4, 1])
    col_h.header(f"📋 Open Positions — {exchange_label}")
    if _market_open:
        col_badge.success("⚡ Live")
    else:
        col_badge.info("📦 Cached")

    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    total_invested      = portfolio.get("total_invested", 0)
    total_current_value = portfolio.get("total_current_value", 0)
    total_pnl           = portfolio.get("total_unrealised_pnl", 0)
    total_pnl_pct       = (total_pnl / total_invested * 100) if total_invested else 0

    # ── Top summary row: capital view ─────────────────────────────────────────
    diff = total_current_value - total_invested

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invested",  f"{currency}{total_invested:,.0f}")
    c2.metric(
        "Current Value",
        f"{currency}{total_current_value:,.0f}",
        delta=_delta(diff, currency),          # -₹682 or +$1,540
        delta_color="normal",
    )
    c3.metric(
        "Unrealised P&L",
        f"{currency}{abs(total_pnl):,.0f}" if total_pnl < 0 else f"{currency}{total_pnl:,.0f}",
        delta=_delta_pct(total_pnl_pct),
        delta_color="normal",
    )
    c4.metric(
        "Open Positions", portfolio["total_positions"],
        delta=f"{portfolio['winners']}W / {portfolio['losers']}L",
        delta_color="off",
    )

    # ── Prominent P&L call-out ─────────────────────────────────────────────────
    if positions:
        pnl_colour = "off" if total_pnl == 0 else ("normal" if total_pnl > 0 else "inverse")
        if total_pnl > 0:
            st.success(
                f"**Overall Profit: {currency}{total_pnl:+,.2f}** ({total_pnl_pct:+.2f}%)  "
                f"— Portfolio value {currency}{total_current_value:,.0f} vs "
                f"{currency}{total_invested:,.0f} invested"
            )
        elif total_pnl < 0:
            st.error(
                f"**Overall Loss: {currency}{total_pnl:+,.2f}** ({total_pnl_pct:+.2f}%)  "
                f"— Portfolio value {currency}{total_current_value:,.0f} vs "
                f"{currency}{total_invested:,.0f} invested"
            )
        else:
            st.info(f"Portfolio break-even — {currency}{total_invested:,.0f} invested")

    if not positions:
        st.info(
            "No open positions. Positions are opened when a stock scores above the "
            "signal threshold and an order is placed at market open."
        )
    else:
        import pandas as pd
        df = pd.DataFrame(positions)

        # Derived columns
        df["stop_gap_pct"] = (
            (df["current_price"] - df["stop_loss_price"]) / df["current_price"] * 100
        ).round(1)
        df["target_gap_pct"] = (
            (df["target_price"] - df["current_price"]) / df["current_price"] * 100
        ).round(1)
        df["chart"] = df["ticker"].apply(
            lambda t: f"https://finance.yahoo.com/quote/{t}"
        )

        cols = [
            "ticker", "entry_date", "days_held",
            "invested", "current_value",
            "entry_price", "current_price",
            "unrealised_pnl", "unrealised_pnl_pct",
            "stop_gap_pct", "target_gap_pct",
            "signal_score", "chart",
        ]
        cols = [c for c in cols if c in df.columns]

        st.dataframe(
            df[cols],
            column_config={
                "ticker": "Ticker",
                "entry_date": st.column_config.DateColumn("Entry Date", format="DD MMM YYYY"),
                "days_held": st.column_config.NumberColumn("Days Held"),
                "invested": st.column_config.NumberColumn(f"Invested ({currency})", format="%.0f"),
                "current_value": st.column_config.NumberColumn(f"Current Value ({currency})", format="%.0f"),
                "entry_price": st.column_config.NumberColumn(f"Avg Entry ({currency})", format="%.3f"),
                "current_price": st.column_config.NumberColumn(f"Last Price ({currency})", format="%.3f"),
                "unrealised_pnl": st.column_config.NumberColumn(
                    f"P&L ({currency})", format="%+.2f"
                ),
                "unrealised_pnl_pct": st.column_config.NumberColumn("P&L %", format="%+.1f%%"),
                "stop_gap_pct": st.column_config.NumberColumn("Above Stop %", format="%.1f%%"),
                "target_gap_pct": st.column_config.NumberColumn("To Target %", format="%.1f%%"),
                "signal_score": st.column_config.ProgressColumn(
                    "Signal Score", min_value=0, max_value=100, format="%.0f"
                ),
                "chart": st.column_config.LinkColumn("Chart", display_text="📊 View"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # Per-position P&L bar chart
        import plotly.express as px
        fig = px.bar(
            df.sort_values("unrealised_pnl"),
            x="ticker", y="unrealised_pnl",
            color="unrealised_pnl",
            color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
            color_continuous_midpoint=0,
            labels={"unrealised_pnl": f"Unrealised P&L ({currency})", "ticker": ""},
            title="Unrealised P&L by Position",
        )
        fig.update_layout(height=300, margin=dict(t=40, b=20), showlegend=False)
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Positions
# ══════════════════════════════════════════════════════════════════════════════

elif page == "💼 Positions":
    import pandas as pd
    import plotly.express as px

    col_h, col_badge = st.columns([4, 1])
    col_h.header(f"💼 Positions — {exchange_label}")
    if _market_open:
        col_badge.success("⚡ Live · 30s")
    else:
        col_badge.info("📦 Cached · 5 min")

    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    if not positions:
        st.info("No open positions yet.")
    else:
        df = pd.DataFrame(positions)

        # ── Derived columns ────────────────────────────────────────────────
        df["stop_gap_pct"]   = ((df["current_price"] - df["stop_loss_price"]) / df["current_price"] * 100).round(2)
        df["target_gap_pct"] = ((df["target_price"]  - df["current_price"])   / df["current_price"] * 100).round(2)
        df["pnl_pct"]        = df["unrealised_pnl_pct"].round(2)
        df["days_held"]      = df["days_held"].fillna(0).astype(int)

        # Capital concentration + dollar risk at stop
        import os
        _cap = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
        df["capital_pct"] = (df["invested"] / _cap * 100).round(1)
        df["risk_at_stop"] = (
            (df["current_price"] - df["stop_loss_price"]) * df.get("shares", 0)
        ).round(0).abs()

        def _status(row):
            pnl   = row.get("unrealised_pnl_pct") or 0
            sg    = row.get("stop_gap_pct") or 100
            tg    = row.get("target_gap_pct") or 100
            if sg <= 2:   return "🚨 Near Stop"
            if tg <= 3:   return "🎯 Near Target"
            if pnl >= 10: return "🚀 Strong Gain"
            if pnl > 0:   return "🟢 Profitable"
            if pnl > -5:  return "🟡 Small Loss"
            return "🔴 At Loss"

        df["status"] = df.apply(_status, axis=1)
        df["chart"]  = df["ticker"].apply(lambda t: f"https://finance.yahoo.com/quote/{t}")

        # ── Today's signal score vs entry score ────────────────────────────
        tickers_list = df["ticker"].tolist()
        todays_scores = get_todays_scores(tickers_list, exchange)

        def _score_trend(row):
            ticker      = row["ticker"]
            entry_score = row.get("signal_score") or 0
            today_score = todays_scores.get(ticker)
            if today_score is None:
                return "—"
            diff = today_score - entry_score
            arrow = "↑" if diff > 2 else ("↓" if diff < -2 else "→")
            return f"{today_score:.0f} {arrow}"

        df["score_today"] = df.apply(_score_trend, axis=1)

        # ── Summary metrics ────────────────────────────────────────────────
        total_invested      = portfolio.get("total_invested", 0)
        total_current_value = portfolio.get("total_current_value", 0)
        total_pnl           = portfolio.get("total_unrealised_pnl", 0)
        total_pnl_pct       = (total_pnl / total_invested * 100) if total_invested else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Positions",      len(df))
        c2.metric("Total Invested", f"{currency}{total_invested:,.0f}")
        c3.metric("Current Value",  f"{currency}{total_current_value:,.0f}",
                  delta=_delta(total_current_value - total_invested, currency), delta_color="normal")
        c4.metric("Unrealised P&L", f"{currency}{abs(total_pnl):,.0f}",
                  delta=_delta_pct(total_pnl_pct), delta_color="normal")

        st.divider()

        # ══════════════════════════════════════════════════════════════════
        # FILTERS
        # ══════════════════════════════════════════════════════════════════
        st.subheader("🔍 Filters")
        fc1, fc2, fc3, fc4 = st.columns(4)

        # Status filter
        all_statuses = sorted(df["status"].unique().tolist())
        selected_statuses = fc1.multiselect(
            "Status",
            options=all_statuses,
            default=all_statuses,
        )

        # P&L direction
        pnl_filter = fc2.radio(
            "P&L Direction",
            options=["All", "Profitable only", "Losing only"],
            horizontal=False,
        )

        # Days held range
        max_days = int(df["days_held"].max()) if len(df) else 90
        days_range = fc3.slider(
            "Days Held",
            min_value=0,
            max_value=max(max_days, 1),
            value=(0, max(max_days, 1)),
        )

        # Min signal score
        min_score = fc4.slider(
            "Min Signal Score",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
        )

        # Sort order
        sort_options = {
            "P&L % (best first)":   ("pnl_pct", False),
            "P&L % (worst first)":  ("pnl_pct", True),
            "Days Held (longest)":  ("days_held", False),
            "Signal Score (best)":  ("signal_score", False),
            "Ticker (A–Z)":         ("ticker", True),
        }
        sort_col1, sort_col2 = st.columns([2, 4])
        sort_choice = sort_col1.selectbox("Sort by", options=list(sort_options.keys()))
        sort_field, sort_asc = sort_options[sort_choice]

        st.divider()

        # ── Apply filters ──────────────────────────────────────────────────
        filtered = df.copy()

        if selected_statuses:
            filtered = filtered[filtered["status"].isin(selected_statuses)]

        if pnl_filter == "Profitable only":
            filtered = filtered[filtered["pnl_pct"] > 0]
        elif pnl_filter == "Losing only":
            filtered = filtered[filtered["pnl_pct"] <= 0]

        filtered = filtered[
            (filtered["days_held"] >= days_range[0]) &
            (filtered["days_held"] <= days_range[1])
        ]

        if min_score > 0:
            filtered = filtered[filtered["signal_score"] >= min_score]

        filtered = filtered.sort_values(sort_field, ascending=sort_asc)

        # ── Results count ──────────────────────────────────────────────────
        st.caption(f"Showing **{len(filtered)}** of **{len(df)}** positions")

        if filtered.empty:
            st.warning("No positions match the current filters.")
        else:
            # ── Main positions table ───────────────────────────────────────
            display_cols = [
                "status", "ticker",
                "entry_date", "days_held",
                "capital_pct", "invested", "current_value",
                "entry_price", "current_price",
                "unrealised_pnl", "pnl_pct",
                "risk_at_stop",
                "stop_gap_pct", "target_gap_pct",
                "signal_score", "score_today", "chart",
            ]
            display_cols = [c for c in display_cols if c in filtered.columns]

            st.dataframe(
                filtered[display_cols],
                column_config={
                    "status":          "Status",
                    "ticker":          "Ticker",
                    "entry_date":      st.column_config.DateColumn("Entry Date", format="DD MMM YYYY"),
                    "days_held":       st.column_config.NumberColumn("Days", format="%d"),
                    "invested":        st.column_config.NumberColumn(f"Invested ({currency})", format="%.0f"),
                    "current_value":   st.column_config.NumberColumn(f"Value ({currency})", format="%.0f"),
                    "entry_price":     st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                    "current_price":   st.column_config.NumberColumn(f"Price ({currency})", format="%.3f"),
                    "unrealised_pnl":  st.column_config.NumberColumn(f"P&L ({currency})", format="%+.2f"),
                    "pnl_pct":         st.column_config.NumberColumn("P&L %", format="%+.2f%%"),
                    "stop_gap_pct":    st.column_config.NumberColumn("Above Stop %", format="%.1f%%"),
                    "target_gap_pct":  st.column_config.NumberColumn("To Target %", format="%.1f%%"),
                    "capital_pct":     st.column_config.NumberColumn("Capital %", format="%.1f%%"),
                    "risk_at_stop":    st.column_config.NumberColumn(f"Risk $ at Stop ({currency})", format="%.0f"),
                    "signal_score":    st.column_config.ProgressColumn(
                                           "Entry Score", min_value=0, max_value=100, format="%.0f"),
                    "score_today":     "Score Today (↑↓→)",
                    "chart":           st.column_config.LinkColumn("Chart", display_text="📊"),
                },
                use_container_width=True,
                hide_index=True,
                height=min(80 + len(filtered) * 35, 600),
            )

            # ── Status breakdown ───────────────────────────────────────────
            col_chart1, col_chart2 = st.columns(2)

            with col_chart1:
                status_counts = filtered["status"].value_counts().reset_index()
                status_counts.columns = ["status", "count"]
                fig_status = px.pie(
                    status_counts, values="count", names="status",
                    title="Position Status Breakdown",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig_status.update_layout(height=300, margin=dict(t=40, b=10))
                fig_status.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_status, use_container_width=True)

            with col_chart2:
                fig_pnl = px.bar(
                    filtered.sort_values("pnl_pct"),
                    x="ticker", y="pnl_pct",
                    color="pnl_pct",
                    color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
                    color_continuous_midpoint=0,
                    title="P&L % by Position",
                    labels={"pnl_pct": "P&L %", "ticker": ""},
                )
                fig_pnl.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
                fig_pnl.update_layout(height=300, margin=dict(t=40, b=20), showlegend=False)
                fig_pnl.update_coloraxes(showscale=False)
                st.plotly_chart(fig_pnl, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trade History
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📈 Trade History":
    st.header(f"📈 Trade History — {exchange_label}")

    days_back = st.slider("Look-back period (days)", 30, 365, 90, step=30)
    trades    = load_trades(exchange, days_back)
    pnl_data  = load_cumulative_pnl(exchange, days_back)

    if not trades:
        st.info(f"No closed trades in the last {days_back} days.")
    else:
        # ── Summary metrics ────────────────────────────────────────────────
        total_net = sum(t.get("net_pnl") or 0 for t in trades)
        winners   = sum(1 for t in trades if (t.get("net_pnl") or 0) > 0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Net Realised P&L", f"{currency}{total_net:+,.0f}")
        c2.metric("Closed Trades", len(trades))
        c3.metric("Win Rate", f"{winners / len(trades) * 100:.0f}%")

        # ── Cumulative P&L line chart ──────────────────────────────────────
        _pnl_chart(pnl_data, currency, title=f"Cumulative P&L ({days_back}-day window)")

        col_table, col_pie = st.columns([3, 1])

        with col_table:
            st.subheader("Closed Trades")
            import pandas as pd
            df = pd.DataFrame(trades)
            cols = [
                "ticker", "entry_date", "exit_date",
                "entry_price", "exit_price",
                "shares", "net_pnl", "exit_reason", "signal_score",
            ]
            cols = [c for c in cols if c in df.columns]
            st.dataframe(
                df[cols],
                column_config={
                    "ticker": "Ticker",
                    "entry_date": st.column_config.DateColumn("Entry", format="DD MMM YYYY"),
                    "exit_date": st.column_config.DateColumn("Exit", format="DD MMM YYYY"),
                    "entry_price": st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                    "exit_price": st.column_config.NumberColumn(f"Exit ({currency})", format="%.3f"),
                    "shares": st.column_config.NumberColumn("Shares", format="%.0f"),
                    "net_pnl": st.column_config.NumberColumn(f"Net P&L ({currency})", format="%+.2f"),
                    "exit_reason": "Exit Reason",
                    "signal_score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%.0f"
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )

        with col_pie:
            st.subheader("Exit Reasons")
            import pandas as pd, plotly.express as px
            reasons = pd.DataFrame(trades)["exit_reason"].value_counts().reset_index()
            reasons.columns = ["exit_reason", "count"]
            colour_map = {
                "stop_loss": "#ef4444",
                "target":    "#22c55e",
                "stale":     "#f59e0b",
                "manual":    "#6366f1",
                "regime":    "#a855f7",
            }
            fig = px.pie(
                reasons, values="count", names="exit_reason",
                color="exit_reason", color_discrete_map=colour_map,
                hole=0.4,
            )
            fig.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10))
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Backtest
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🔬 Backtest":
    st.header(f"🔬 Walk-Forward Backtest — {exchange_label}")
    st.caption(
        "Results computed every Sunday at 08:00 and cached. "
        "The backtest covers the last 6 months of signals."
    )

    results = load_backtest(exchange)

    if not results:
        if not _use_supabase() if False else True:
            st.info(
                "No backtest results cached yet. Results are written to Supabase after the "
                "Sunday morning backtest run. Check back on Monday."
            )
    else:
        import pandas as pd, plotly.express as px

        rows = []
        for ticker, metrics in results.items():
            if isinstance(metrics, dict):
                rows.append({
                    "ticker": ticker,
                    "num_trades": metrics.get("num_trades", 0),
                    "win_rate_pct": round((metrics.get("win_rate") or 0) * 100, 1),
                    "avg_return_pct": metrics.get("avg_return_pct", 0),
                    "sharpe": metrics.get("sharpe", 0),
                    "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
                    "total_return_pct": metrics.get("total_return_pct", 0),
                })

        df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)

        # ── Summary metrics ────────────────────────────────────────────────
        profitable = (df["total_return_pct"] > 0).sum()
        avg_win_rate = df["win_rate_pct"].mean()
        c1, c2, c3 = st.columns(3)
        c1.metric("Tickers Tested", len(df))
        c2.metric("Profitable Strategies", f"{profitable}/{len(df)}")
        c3.metric("Avg Win Rate", f"{avg_win_rate:.1f}%")

        # ── Results table ──────────────────────────────────────────────────
        st.dataframe(
            df,
            column_config={
                "ticker": "Ticker",
                "num_trades": st.column_config.NumberColumn("# Trades"),
                "win_rate_pct": st.column_config.ProgressColumn(
                    "Win Rate %", min_value=0, max_value=100, format="%.0f%%"
                ),
                "avg_return_pct": st.column_config.NumberColumn("Avg Return %", format="%+.1f%%"),
                "sharpe": st.column_config.NumberColumn("Sharpe Ratio", format="%.2f"),
                "max_drawdown_pct": st.column_config.NumberColumn("Max DD %", format="%.1f%%"),
                "total_return_pct": st.column_config.NumberColumn("Total Return %", format="%+.1f%%"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # ── Win rate bar chart (top 20) ────────────────────────────────────
        top20 = df.head(20)
        fig = px.bar(
            top20, x="ticker", y="win_rate_pct",
            color="sharpe",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            title="Top 20 Tickers by Sharpe Ratio — Win Rate %",
            labels={"win_rate_pct": "Win Rate %", "ticker": "", "sharpe": "Sharpe"},
        )
        fig.add_hline(y=55, line_dash="dash", line_color="gray",
                      annotation_text="55% threshold", annotation_position="top right")
        fig.update_layout(height=360, margin=dict(t=50, b=30))
        st.plotly_chart(fig, use_container_width=True)
