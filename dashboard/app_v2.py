"""
AI Trading Dashboard V2 — Zerodha Kite Inspired
Clean, minimal, data-dense. Watchlist sidebar, holdings-first layout.

Run:   streamlit run dashboard/app_v2.py --server.port 8502
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Trading V2",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Data imports ──────────────────────────────────────────────────────────────
from dashboard.data import (
    get_signals, get_portfolio, get_trades, get_regime,
    get_cumulative_pnl, get_score_history, get_backtest_results,
    get_todays_scores, is_market_open, market_status, _use_supabase,
    get_price_history, get_multi_close, ticker_tv_url, ticker_yahoo_url,
)

# ── CSS: Zerodha Kite dark theme ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { box-sizing: border-box; font-family: 'Inter', -apple-system, sans-serif !important; }

/* Root background */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], .main { background: #1b1b1d !important; }
[data-testid="stHeader"] { background: #1b1b1d !important; }

/* ── Sidebar: Watchlist style ───────────────────────── */
section[data-testid="stSidebar"] {
    background: #1b1b1d !important;
    border-right: 1px solid #2a2a2d;
    width: 320px !important;
}
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label {
    font-size: 0.75rem; color: #8b8b8e;
    text-transform: uppercase; letter-spacing: 0.06em;
}

/* ── Top index bar ──────────────────────────────────── */
.idx-bar {
    display: flex; align-items: center; gap: 24px;
    padding: 10px 20px;
    background: #232325;
    border-bottom: 1px solid #2a2a2d;
    font-size: 0.82rem; color: #9b9ba0;
    margin: -1rem -1rem 16px -1rem;
}
.idx-bar .idx-name { color: #e0e0e3; font-weight: 600; }
.idx-bar .idx-up { color: #4caf50; }
.idx-bar .idx-down { color: #e54040; }

/* ── Summary strip ──────────────────────────────────── */
.summary-strip {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 16px 0; border-bottom: 1px solid #2a2a2d; margin-bottom: 20px;
}
.summary-item { text-align: center; }
.summary-item .label { font-size: 0.72rem; color: #6b6b6e; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
.summary-item .value { font-size: 1.2rem; font-weight: 700; color: #e0e0e3; }
.summary-item .value.up { color: #4caf50; }
.summary-item .value.down { color: #e54040; }
.summary-item .sub { font-size: 0.72rem; margin-top: 2px; }
.summary-item .sub.up { color: #4caf50; }
.summary-item .sub.down { color: #e54040; }

/* ── Holdings table ─────────────────────────────────── */
.kite-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.kite-table thead th {
    color: #6b6b6e; font-size: 0.72rem; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.06em;
    padding: 10px 12px; border-bottom: 1px solid #2a2a2d; text-align: right;
}
.kite-table thead th:first-child { text-align: left; }
.kite-table tbody td {
    padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
    color: #c8c8cb; text-align: right;
}
.kite-table tbody td:first-child { text-align: left; font-weight: 600; color: #e0e0e3; }
.kite-table tbody tr:hover { background: rgba(255,255,255,0.02); }
.kite-table .up { color: #4caf50; }
.kite-table .down { color: #e54040; }
.kite-table .ticker-link {
    color: #e0e0e3; text-decoration: none; font-weight: 600;
    transition: color 0.15s;
}
.kite-table .ticker-link:hover { color: #5b8def; }

/* Total row */
.kite-table .total-row td {
    border-top: 1px solid #2a2a2d; font-weight: 700; color: #e0e0e3;
    padding-top: 14px;
}

/* ── Allocation bar ─────────────────────────────────── */
.alloc-bar { display: flex; height: 28px; border-radius: 4px; overflow: hidden; margin: 16px 0; }
.alloc-seg { transition: width 0.3s; }

/* ── Watchlist item (sidebar) ───────────────────────── */
.wl-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
    cursor: default; transition: background 0.1s;
}
.wl-item:hover { background: rgba(255,255,255,0.02); }
.wl-ticker { font-size: 0.82rem; font-weight: 600; color: #e0e0e3; }
.wl-right { text-align: right; }
.wl-change { font-size: 0.78rem; margin-right: 8px; }
.wl-pct { font-size: 0.78rem; margin-right: 8px; }
.wl-price { font-size: 0.82rem; color: #e0e0e3; font-weight: 500; }

/* ── P&L card (big number) ──────────────────────────── */
.pnl-hero { padding: 20px 0; }
.pnl-hero .big-num { font-size: 2rem; font-weight: 700; }
.pnl-hero .big-sub { font-size: 0.82rem; color: #6b6b6e; margin-top: 2px; }
.pnl-hero .side-stat { font-size: 0.85rem; color: #9b9ba0; }
.pnl-hero .side-stat b { color: #e0e0e3; }

/* ── Section headers ────────────────────────────────── */
.kite-section {
    font-size: 0.78rem; font-weight: 600; color: #6b6b6e;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin: 24px 0 12px; padding-bottom: 8px;
    border-bottom: 1px solid #2a2a2d;
}

/* ── Tab bar ────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #2a2a2d;
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: #6b6b6e !important; font-size: 0.82rem !important;
    font-weight: 500 !important; padding: 10px 20px !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #5b8def !important;
    border-bottom: 2px solid #5b8def !important;
}

/* ── Nav bar (top) ──────────────────────────────────── */
.top-nav {
    display: flex; align-items: center; gap: 32px;
    padding: 10px 0; margin-bottom: 8px;
}
.top-nav a {
    color: #6b6b6e; text-decoration: none; font-size: 0.85rem;
    font-weight: 500; padding: 6px 0;
    border-bottom: 2px solid transparent; transition: all 0.15s;
}
.top-nav a:hover { color: #e0e0e3; }
.top-nav a.active { color: #5b8def; border-bottom-color: #5b8def; }

/* ── Metric cards (Streamlit override) ──────────────── */
[data-testid="stMetric"] {
    background: transparent !important;
    border: none !important; padding: 8px 0 !important;
}
[data-testid="stMetricLabel"] {
    color: #6b6b6e !important; font-size: 0.68rem !important;
    text-transform: uppercase; letter-spacing: 0.06em;
}
[data-testid="stMetricValue"] { color: #e0e0e3 !important; font-size: 1.3rem !important; font-weight: 700; }

/* ── DataFrame override ─────────────────────────────── */
[data-testid="stDataFrame"] thead tr th {
    background: #232325 !important; color: #6b6b6e !important;
    font-size: 0.7rem !important; text-transform: uppercase;
    letter-spacing: 0.06em;
    border-bottom: 1px solid #2a2a2d !important;
}
[data-testid="stDataFrame"] { border-radius: 0 !important; }

/* ── Plotly ──────────────────────────────────────────── */
.js-plotly-plot { border-radius: 4px; }

/* ── Signal card ────────────────────────────────────── */
.sig-card-v2 {
    background: #232325; border: 1px solid #2a2a2d;
    border-radius: 6px; padding: 14px 16px; margin-bottom: 8px;
}
.sig-card-v2:hover { border-color: #3a3a3d; }
.sig-card-v2 .sig-ticker { font-weight: 700; color: #e0e0e3; font-size: 0.95rem; }
.sig-card-v2 .sig-score { font-weight: 700; font-size: 0.9rem; }

/* ── Hide streamlit branding ────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pnl_class(val: float) -> str:
    return "up" if (val or 0) >= 0 else "down"

def _pnl_sign(val: float, cur: str = "") -> str:
    if val >= 0:
        return f"+{cur}{val:,.2f}"
    return f"-{cur}{abs(val):,.2f}"

def _pnl_pct(val: float) -> str:
    return f"{val:+.2f}%"

def _tv_url(ticker: str) -> str:
    if ticker.endswith(".AX"): return f"https://www.tradingview.com/chart/?symbol=ASX:{ticker[:-3]}"
    if ticker.endswith(".NS"): return f"https://www.tradingview.com/chart/?symbol=NSE:{ticker[:-3]}"
    return f"https://www.tradingview.com/chart/?symbol={ticker}"

def _today(exchange: str) -> date:
    try:
        tz = "Australia/Sydney" if exchange == "asx" else "Asia/Kolkata"
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return date.today()

# Allocation bar colors
_ALLOC_COLORS = [
    "#5b8def", "#4caf50", "#ff9800", "#e54040", "#9c27b0",
    "#00bcd4", "#ff5722", "#8bc34a", "#ffc107", "#607d8b",
    "#e91e63", "#3f51b5", "#009688", "#cddc39", "#795548",
    "#2196f3", "#ff6f00",
]


# ── Auto-refresh ──────────────────────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    _either_open = is_market_open("asx") or is_market_open("nse")
    st_autorefresh(interval=30_000 if _either_open else 300_000, key="auto_v2")
except ImportError:
    pass


# ── Cached loaders ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_portfolio(exch, live=False):
    return get_portfolio(exch, live=live)

@st.cache_data(ttl=300)
def load_regime(exch):
    return get_regime(exch)

@st.cache_data(ttl=300)
def load_signals(exch, sig_date, n):
    return get_signals(exch, signal_date=sig_date, n=n)

@st.cache_data(ttl=300)
def load_trades(exch, days):
    return get_trades(exch, days=days)

@st.cache_data(ttl=300)
def load_pnl(exch, days):
    return get_cumulative_pnl(exch, days=days)

@st.cache_data(ttl=3600)
def load_backtest(exch):
    return get_backtest_results(exch)

@st.cache_data(ttl=300)
def load_score_history(ticker, days):
    return get_score_history(ticker, days=days)

@st.cache_data(ttl=300)
def fetch_ohlcv(ticker, days=60):
    return get_price_history(ticker, days)

@st.cache_data(ttl=300)
def fetch_sparklines(tickers, days=20):
    return get_multi_close(list(tickers), days)


# ── Chart base ────────────────────────────────────────────────────────────────
def _chart_base(h=300, title="", margin=(30, 20, 40, 10)):
    return dict(
        title=dict(text=title, font=dict(size=12, color="#6b6b6e")) if title else None,
        height=h,
        margin=dict(t=margin[0], b=margin[1], l=margin[2], r=margin[3]),
        plot_bgcolor="#1b1b1d",
        paper_bgcolor="#1b1b1d",
        font=dict(color="#6b6b6e", size=11, family="Inter"),
        xaxis=dict(gridcolor="#2a2a2d", color="#6b6b6e", showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#2a2a2d", color="#6b6b6e", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2, font=dict(size=10)),
        hovermode="x unified",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Watchlist + Controls
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Exchange selector
    exchange = st.radio(
        "Exchange",
        ["asx", "nse"],
        format_func=lambda x: "ASX 200" if x == "asx" else "NSE NIFTY 100",
        horizontal=True,
    )
    currency = "$" if exchange == "asx" else "₹"

    # Market status
    mkt = market_status(exchange)
    _market_open = mkt["open"]

    st.markdown(
        f'<div style="font-size:0.78rem;color:#6b6b6e;padding:4px 0 8px">'
        f'{mkt["local_time"]} &middot; '
        f'<span style="color:{"#4caf50" if _market_open else "#e54040"}">'
        f'{"Market Open" if _market_open else "Market Closed"}</span></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div style="border-bottom:1px solid #2a2a2d;margin:4px 0 8px"></div>',
                unsafe_allow_html=True)

    # Watchlist in sidebar
    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    if positions:
        wl_count = len(positions)
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0 8px">'
            f'<span style="font-size:0.78rem;color:#6b6b6e;font-weight:600">'
            f'Holdings ({wl_count})</span></div>',
            unsafe_allow_html=True,
        )

        for p in positions:
            t = p["ticker"]
            cp = p.get("current_price") or 0
            ep = p.get("entry_price") or 0
            pnl = p.get("unrealised_pnl") or 0
            pnl_pct = p.get("unrealised_pnl_pct") or 0
            cls = _pnl_class(pnl)
            chg = cp - ep

            short = t.replace(".AX", "").replace(".NS", "")
            st.markdown(
                f'<div class="wl-item">'
                f'  <span class="wl-ticker">{short}</span>'
                f'  <div class="wl-right">'
                f'    <span class="wl-change {cls}">{chg:+.2f}</span>'
                f'    <span class="wl-pct {cls}">{pnl_pct:+.1f}%</span>'
                f'    <span class="wl-price">{cp:,.2f}</span>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="padding:40px 12px;text-align:center;color:#6b6b6e">'
            'No active positions</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="border-bottom:1px solid #2a2a2d;margin:8px 0"></div>',
                unsafe_allow_html=True)

    # Info strip
    _phase = int(os.getenv("TRADING_PHASE", 1))
    _capital = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
    mode_text = {1: "Paper", 2: "IBKR Paper", 3: "LIVE"}
    st.markdown(
        f'<div style="font-size:0.72rem;color:#6b6b6e;padding:4px 0">'
        f'Mode: <b style="color:#9b9ba0">{mode_text.get(_phase, "Paper")}</b>'
        f' &middot; Capital: <b style="color:#9b9ba0">{currency}{_capital:,.0f}</b>'
        f' &middot; {"Supabase" if _use_supabase() else "Local DB"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button("Refresh", use_container_width=True, type="secondary"):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT — Tabs
# ══════════════════════════════════════════════════════════════════════════════

tab_dash, tab_holdings, tab_signals, tab_history, tab_backtest = st.tabs([
    "Dashboard", "Holdings", "Signals", "Trade History", "Backtest",
])


# ── TAB 1: Dashboard ─────────────────────────────────────────────────────────
with tab_dash:
    import pandas as pd

    total_invested = portfolio.get("total_invested", 0) or 0
    total_value = portfolio.get("total_current_value", 0) or 0
    total_pnl = portfolio.get("total_unrealised_pnl", 0) or 0
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    regime = load_regime(exchange)

    # ── Summary strip (like Kite top bar) ─────────────────────────────────
    pnl_cls = _pnl_class(total_pnl)

    # P&L hero card + stats
    col_pnl, col_stats = st.columns([1, 1])
    with col_pnl:
        st.markdown(
            f'<div class="pnl-hero">'
            f'  <div class="kite-section">Holdings ({len(positions)})</div>'
            f'  <div class="big-num {pnl_cls}">{currency}{abs(total_pnl):,.2f}</div>'
            f'  <div class="big-sub"><span class="{pnl_cls}">{_pnl_pct(total_pnl_pct)}</span> &nbsp; P&L</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with col_stats:
        st.markdown(
            f'<div style="padding:20px 0">'
            f'  <div class="kite-section">Summary</div>'
            f'  <div class="pnl-hero">'
            f'    <div class="side-stat">Current value &nbsp; <b>{currency}{total_value:,.2f}</b></div>'
            f'    <div class="side-stat">Investment &nbsp; <b>{currency}{total_invested:,.2f}</b></div>'
            f'    <div class="side-stat">Winners / Losers &nbsp; <b>{portfolio.get("winners",0)}W / {portfolio.get("losers",0)}L</b></div>'
            f'    <div class="side-stat">Regime &nbsp; <b>{"RISK-ON" if regime.get("regime_ok") else "RISK-OFF"}'
            f' ({regime.get("pct_above", 0):+.1f}% vs EMA200)</b></div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Allocation bar ────────────────────────────────────────────────────
    if positions and total_value > 0:
        bar_html = '<div class="alloc-bar">'
        for i, p in enumerate(positions):
            pct = (p.get("current_value", 0) / total_value * 100) if total_value else 0
            color = _ALLOC_COLORS[i % len(_ALLOC_COLORS)]
            bar_html += f'<div class="alloc-seg" style="width:{pct:.1f}%;background:{color}" title="{p["ticker"]}: {pct:.1f}%"></div>'
        bar_html += '</div>'
        st.markdown(bar_html, unsafe_allow_html=True)

        st.markdown(
            f'<div style="font-size:0.82rem;color:#9b9ba0;padding:4px 0">'
            f'{currency}{total_value:,.2f}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    # ── Market overview chart ─────────────────────────────────────────────
    st.markdown('<div class="kite-section">Market Overview</div>', unsafe_allow_html=True)

    pnl_data = load_pnl(exchange, 90)
    if pnl_data:
        import plotly.graph_objects as go
        dates = [r.get("exit_date") or r.get("date") for r in pnl_data]
        cum = [r.get("cumulative_net_pnl", 0) for r in pnl_data]
        daily = [r.get("net_pnl", 0) for r in pnl_data]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=cum, mode="lines",
            line=dict(color="#5b8def", width=2),
            fill="tozeroy", fillcolor="rgba(91,141,239,0.08)",
            name="Cumulative P&L",
        ))
        fig.add_trace(go.Bar(
            x=dates, y=daily,
            marker_color=["#4caf50" if v >= 0 else "#e54040" for v in daily],
            opacity=0.5, name="Daily P&L",
        ))
        layout = _chart_base(h=280)
        layout["barmode"] = "overlay"
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div style="padding:60px;text-align:center;color:#6b6b6e">'
            'No closed trades yet</div>',
            unsafe_allow_html=True,
        )


# ── TAB 2: Holdings ──────────────────────────────────────────────────────────
with tab_holdings:
    if not positions:
        st.markdown(
            '<div style="padding:80px;text-align:center;color:#6b6b6e;font-size:1.1rem">'
            'You don\'t have any positions yet</div>',
            unsafe_allow_html=True,
        )
    else:
        # Summary strip
        day_pnl = total_pnl  # approximation — could compute day change separately
        st.markdown(
            f'<div class="summary-strip">'
            f'  <div class="summary-item"><div class="label">Total Investment</div>'
            f'    <div class="value">{currency}{total_invested:,.2f}</div></div>'
            f'  <div class="summary-item"><div class="label">Current Value</div>'
            f'    <div class="value">{currency}{total_value:,.2f}</div></div>'
            f'  <div class="summary-item"><div class="label">Day\'s P&L</div>'
            f'    <div class="value {_pnl_class(day_pnl)}">{_pnl_sign(day_pnl, currency)}</div>'
            f'    <div class="sub {_pnl_class(day_pnl)}">{_pnl_pct(total_pnl_pct)}</div></div>'
            f'  <div class="summary-item"><div class="label">Total P&L</div>'
            f'    <div class="value {_pnl_class(total_pnl)}">{_pnl_sign(total_pnl, currency)}</div>'
            f'    <div class="sub {_pnl_class(total_pnl)}">{_pnl_pct(total_pnl_pct)}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Holdings table (Kite-style HTML)
        table_html = '''<table class="kite-table"><thead><tr>
            <th>Instrument</th><th>Qty.</th><th>Avg. cost</th><th>LTP</th>
            <th>Invested</th><th>Cur. val</th><th>P&L</th><th>Net chg.</th><th>Days</th>
        </tr></thead><tbody>'''

        for p in positions:
            t = p["ticker"]
            short = t.replace(".AX", "").replace(".NS", "")
            shares = p.get("shares") or 0
            entry = p.get("entry_price") or 0
            cp = p.get("current_price") or 0
            invested = p.get("invested") or 0
            cur_val = p.get("current_value") or 0
            pnl = p.get("unrealised_pnl") or 0
            pnl_pct = p.get("unrealised_pnl_pct") or 0
            days = p.get("days_held") or 0
            cls = _pnl_class(pnl)
            tv = _tv_url(t)

            table_html += f'''<tr>
                <td><a href="{tv}" target="_blank" class="ticker-link">{short}</a></td>
                <td>{shares:,.0f}</td>
                <td>{entry:,.2f}</td>
                <td>{cp:,.2f}</td>
                <td>{currency}{invested:,.2f}</td>
                <td>{currency}{cur_val:,.2f}</td>
                <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                <td class="{cls}">{_pnl_pct(pnl_pct)}</td>
                <td>{days}</td>
            </tr>'''

        # Total row
        table_html += f'''<tr class="total-row">
            <td>Total</td><td></td><td></td><td></td>
            <td>{currency}{total_invested:,.2f}</td>
            <td>{currency}{total_value:,.2f}</td>
            <td class="{_pnl_class(total_pnl)}">{_pnl_sign(total_pnl, currency)}</td>
            <td class="{_pnl_class(total_pnl)}">{_pnl_pct(total_pnl_pct)}</td>
            <td></td>
        </tr>'''

        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)

        # Allocation bar
        if total_value > 0:
            bar_html = '<div class="alloc-bar" style="margin-top:20px">'
            for i, p in enumerate(positions):
                pct = (p.get("current_value", 0) / total_value * 100)
                color = _ALLOC_COLORS[i % len(_ALLOC_COLORS)]
                short = p["ticker"].replace(".AX", "").replace(".NS", "")
                bar_html += f'<div class="alloc-seg" style="width:{pct:.1f}%;background:{color}" title="{short}: {currency}{p.get("current_value",0):,.0f} ({pct:.1f}%)"></div>'
            bar_html += '</div>'
            st.markdown(bar_html, unsafe_allow_html=True)

        # P&L horizontal bar chart
        st.markdown('<div class="kite-section" style="margin-top:24px">P&L by Position</div>',
                    unsafe_allow_html=True)

        import plotly.graph_objects as go
        sorted_pos = sorted(positions, key=lambda x: x.get("unrealised_pnl", 0))
        tickers_short = [p["ticker"].replace(".AX", "").replace(".NS", "") for p in sorted_pos]
        pnls = [p.get("unrealised_pnl", 0) for p in sorted_pos]
        colors = ["#4caf50" if v >= 0 else "#e54040" for v in pnls]

        fig = go.Figure(go.Bar(
            y=tickers_short, x=pnls, orientation="h",
            marker_color=colors, text=[f"{currency}{v:+,.0f}" for v in pnls],
            textposition="outside", textfont=dict(size=11),
        ))
        fig.update_layout(**_chart_base(h=max(len(positions) * 30, 300)))
        fig.update_layout(yaxis=dict(autorange=True))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── TAB 3: Signals ────────────────────────────────────────────────────────────
with tab_signals:
    sig_date = _today(exchange)
    signals = load_signals(exchange, sig_date, 20)

    if not signals:
        st.markdown(
            f'<div style="padding:60px;text-align:center;color:#6b6b6e">'
            f'No signals for {sig_date}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="kite-section">Signals for {sig_date} ({len(signals)} found)</div>',
                    unsafe_allow_html=True)

        # Signal cards — 2 columns
        cols = st.columns(2)
        for i, sig in enumerate(signals):
            with cols[i % 2]:
                t = sig.get("ticker", "")
                short = t.replace(".AX", "").replace(".NS", "")
                score = sig.get("composite_score", 0)
                entry = sig.get("entry_price", 0)
                target = sig.get("target_price", 0)
                stop = sig.get("stop_loss_price", 0)
                tv = _tv_url(t)

                score_color = "#4caf50" if score >= 70 else ("#ff9800" if score >= 60 else "#e54040")
                upside = ((target - entry) / entry * 100) if entry and target else 0
                risk = ((entry - stop) / entry * 100) if entry and stop else 0

                st.markdown(
                    f'<div class="sig-card-v2">'
                    f'  <div style="display:flex;justify-content:space-between;align-items:center">'
                    f'    <a href="{tv}" target="_blank" class="ticker-link sig-ticker">{short}</a>'
                    f'    <span class="sig-score" style="color:{score_color}">{score:.0f}</span>'
                    f'  </div>'
                    f'  <div style="font-size:0.78rem;color:#6b6b6e;margin-top:6px">'
                    f'    Entry {currency}{entry:,.2f} &nbsp;&middot;&nbsp; '
                    f'    Target {currency}{target:,.2f} <span class="up">(+{upside:.1f}%)</span> &nbsp;&middot;&nbsp; '
                    f'    Stop {currency}{stop:,.2f} <span class="down">(-{risk:.1f}%)</span>'
                    f'  </div>'
                    f'  <div style="font-size:0.72rem;color:#4a4a4d;margin-top:4px">'
                    f'    Sent: {sig.get("sentiment_score", 0):.0f} &middot; '
                    f'    Fund: {sig.get("fundamental_score", 0):.0f} &middot; '
                    f'    Tech: {sig.get("technical_score", 0):.0f} &middot; '
                    f'    Ins: {sig.get("insider_score", 0):.0f}'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Signals table
        st.markdown('<div class="kite-section" style="margin-top:16px">Full Signal Table</div>',
                    unsafe_allow_html=True)
        import pandas as pd
        df_sig = pd.DataFrame(signals)
        display_cols = ["ticker", "composite_score", "entry_price", "target_price",
                        "stop_loss_price", "sentiment_score", "fundamental_score",
                        "technical_score", "insider_score"]
        display_cols = [c for c in display_cols if c in df_sig.columns]
        if display_cols:
            st.dataframe(df_sig[display_cols], use_container_width=True, hide_index=True)


# ── TAB 4: Trade History ──────────────────────────────────────────────────────
with tab_history:
    trades = load_trades(exchange, 90)

    if not trades:
        st.markdown(
            '<div style="padding:60px;text-align:center;color:#6b6b6e">'
            'No closed trades in the last 90 days</div>',
            unsafe_allow_html=True,
        )
    else:
        # Summary
        total_realized = sum(t.get("net_pnl", 0) for t in trades)
        wins = sum(1 for t in trades if (t.get("net_pnl", 0) > 0))
        win_rate = (wins / len(trades) * 100) if trades else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Closed Trades", len(trades))
        c2.metric("Net P&L", f"{currency}{total_realized:+,.2f}")
        c3.metric("Win Rate", f"{win_rate:.0f}%")
        c4.metric("Wins / Losses", f"{wins}W / {len(trades) - wins}L")

        # P&L chart
        pnl_data = load_pnl(exchange, 90)
        if pnl_data:
            import plotly.graph_objects as go
            dates = [r.get("exit_date") or r.get("date") for r in pnl_data]
            cum = [r.get("cumulative_net_pnl", 0) for r in pnl_data]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates, y=cum, mode="lines",
                line=dict(color="#5b8def", width=2),
                fill="tozeroy", fillcolor="rgba(91,141,239,0.08)",
            ))
            fig.update_layout(**_chart_base(h=250, title="Cumulative P&L"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Trades table
        st.markdown('<div class="kite-section">Trade Log</div>', unsafe_allow_html=True)

        table_html = '''<table class="kite-table"><thead><tr>
            <th>Ticker</th><th>Entry</th><th>Exit</th><th>Shares</th>
            <th>Entry Price</th><th>Exit Price</th><th>P&L</th><th>Reason</th>
        </tr></thead><tbody>'''

        for t in trades:
            ticker = t.get("ticker", "")
            short = ticker.replace(".AX", "").replace(".NS", "")
            pnl = t.get("net_pnl", 0)
            cls = _pnl_class(pnl)
            tv = _tv_url(ticker)

            table_html += f'''<tr>
                <td><a href="{tv}" target="_blank" class="ticker-link">{short}</a></td>
                <td>{t.get("entry_date", "")}</td>
                <td>{t.get("exit_date", "")}</td>
                <td>{t.get("shares", 0):,.0f}</td>
                <td>{currency}{t.get("entry_price", 0):,.2f}</td>
                <td>{currency}{t.get("exit_price", 0):,.2f}</td>
                <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                <td style="font-size:0.78rem;color:#6b6b6e">{t.get("exit_reason", "")}</td>
            </tr>'''

        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)

        # Exit reasons breakdown
        st.markdown('<div class="kite-section" style="margin-top:16px">Exit Reasons</div>',
                    unsafe_allow_html=True)
        import plotly.graph_objects as go
        from collections import Counter
        reasons = Counter(t.get("exit_reason", "unknown") for t in trades)
        fig = go.Figure(go.Pie(
            labels=list(reasons.keys()),
            values=list(reasons.values()),
            hole=0.6,
            marker=dict(colors=_ALLOC_COLORS[:len(reasons)]),
            textinfo="label+percent",
            textfont=dict(size=11, color="#9b9ba0"),
        ))
        layout = _chart_base(h=280)
        layout["showlegend"] = False
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── TAB 5: Backtest ───────────────────────────────────────────────────────────
with tab_backtest:
    bt = load_backtest(exchange)
    results = bt.get("results", []) if bt else []

    if not results:
        st.markdown(
            '<div style="padding:60px;text-align:center;color:#6b6b6e">'
            'No backtest results available</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="kite-section">Backtest Results ({len(results)} strategies)</div>',
                    unsafe_allow_html=True)

        # Scatter: return vs win rate
        import plotly.graph_objects as go
        returns = [r.get("total_return_pct", 0) for r in results]
        win_rates = [r.get("win_rate", 0) for r in results]
        sharpes = [r.get("sharpe", 0) for r in results]
        n_trades = [r.get("total_trades", 10) for r in results]
        names = [r.get("strategy", f"S{i}") for i, r in enumerate(results)]

        fig = go.Figure(go.Scatter(
            x=win_rates, y=returns, mode="markers+text",
            marker=dict(
                size=[max(n / 3, 8) for n in n_trades],
                color=sharpes, colorscale="Viridis", showscale=True,
                colorbar=dict(title="Sharpe", tickfont=dict(color="#6b6b6e")),
                line=dict(width=1, color="#2a2a2d"),
            ),
            text=names, textposition="top center",
            textfont=dict(size=10, color="#9b9ba0"),
        ))
        layout = _chart_base(h=350, title="Return vs Win Rate (size=trades, color=Sharpe)")
        layout["xaxis"]["title"] = "Win Rate %"
        layout["yaxis"]["title"] = "Total Return %"
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Results table
        import pandas as pd
        df_bt = pd.DataFrame(results)
        st.dataframe(df_bt, use_container_width=True, hide_index=True)
