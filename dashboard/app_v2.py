"""
AI Trading Dashboard V2 — Professional Fintech UI
Dark theme, data-dense, WCAG AA compliant.

Run:   streamlit run dashboard/app_v2.py --server.port 8502
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Trading",
    page_icon="📊",
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

# ── CSS: Professional dark fintech theme ─────────────────────────────────────
# Design tokens:
#   bg-primary:    #121214   (deeper black, less gray)
#   bg-secondary:  #1a1a1e   (cards/surfaces)
#   bg-tertiary:   #222226   (elevated surfaces)
#   border:        #2c2c30
#   text-primary:  #eaeaed   (14:1 contrast)
#   text-secondary:#a0a0a6   (5.8:1 contrast — WCAG AA)
#   text-tertiary: #78787e   (4.0:1 — labels only, ≥16px)
#   accent-blue:   #6993ff   (links, active)
#   profit-green:  #00c48c   (softer green, less saturated)
#   loss-red:      #ff5a5a   (softer red)
#   warning-amber: #ffb347
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --bg-primary:    #121214;
    --bg-secondary:  #1a1a1e;
    --bg-tertiary:   #222226;
    --bg-hover:      #282830;
    --border:        #2c2c30;
    --border-subtle: rgba(255,255,255,0.04);
    --text-primary:  #eaeaed;
    --text-secondary:#a0a0a6;
    --text-tertiary: #78787e;
    --accent:        #6993ff;
    --accent-dim:    rgba(105,147,255,0.12);
    --profit:        #00c48c;
    --profit-dim:    rgba(0,196,140,0.10);
    --loss:          #ff5a5a;
    --loss-dim:      rgba(255,90,90,0.10);
    --warning:       #ffb347;
    --radius-sm:     6px;
    --radius-md:     10px;
    --radius-lg:     14px;
}

* {
    box-sizing: border-box;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], .main {
    background: var(--bg-primary) !important;
}
[data-testid="stHeader"] { background: var(--bg-primary) !important; }

/* ── Sidebar ──────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border);
    width: 320px !important;
}
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label {
    font-size: 0.75rem; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.08em;
    font-weight: 600;
}

/* ── Summary strip ────────────────────────────────────── */
.summary-strip {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 20px 0; border-bottom: 1px solid var(--border); margin-bottom: 24px;
}
.summary-item { text-align: center; flex: 1; }
.summary-item .label {
    font-size: 0.75rem; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-bottom: 6px; font-weight: 500;
}
.summary-item .value {
    font-size: 1.25rem; font-weight: 700; color: var(--text-primary);
    font-variant-numeric: tabular-nums;
}
.summary-item .value.up { color: var(--profit); }
.summary-item .value.down { color: var(--loss); }
.summary-item .sub {
    font-size: 0.75rem; margin-top: 4px;
    font-variant-numeric: tabular-nums;
}
.summary-item .sub.up { color: var(--profit); }
.summary-item .sub.down { color: var(--loss); }

/* ── Holdings table ───────────────────────────────────── */
.kite-table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    font-size: 0.85rem;
}
.kite-table thead th {
    color: var(--text-secondary); font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em;
    padding: 12px 14px; border-bottom: 1px solid var(--border);
    text-align: right; position: sticky; top: 0;
    background: var(--bg-primary);
}
.kite-table thead th:first-child { text-align: left; }
.kite-table tbody td {
    padding: 14px; border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary); text-align: right;
    font-variant-numeric: tabular-nums;
    transition: background 0.15s;
}
.kite-table tbody td:first-child {
    text-align: left; font-weight: 600; color: var(--text-primary);
}
.kite-table tbody tr:hover td { background: var(--bg-hover); }
.kite-table .up { color: var(--profit); }
.kite-table .down { color: var(--loss); }
.kite-table .ticker-link {
    color: var(--text-primary); text-decoration: none; font-weight: 600;
    transition: color 0.15s;
}
.kite-table .ticker-link:hover { color: var(--accent); }
.kite-table .total-row td {
    border-top: 2px solid var(--border); font-weight: 700;
    color: var(--text-primary); padding-top: 16px;
}

/* ── Allocation bar ───────────────────────────────────── */
.alloc-bar {
    display: flex; height: 8px; border-radius: 4px;
    overflow: hidden; margin: 20px 0 8px;
    background: var(--bg-tertiary);
}
.alloc-seg { transition: width 0.4s ease-out; min-width: 2px; }

.alloc-legend {
    display: flex; flex-wrap: wrap; gap: 12px;
    padding: 4px 0 0; font-size: 0.75rem; color: var(--text-secondary);
}
.alloc-legend-item {
    display: flex; align-items: center; gap: 6px;
    font-variant-numeric: tabular-nums;
}
.alloc-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}

/* ── Watchlist item ───────────────────────────────────── */
.wl-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 14px; border-bottom: 1px solid var(--border-subtle);
    cursor: default; transition: background 0.15s;
    border-radius: var(--radius-sm); margin: 0 -4px;
}
.wl-item:hover { background: var(--bg-hover); }
.wl-ticker { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
.wl-right {
    text-align: right; display: flex; align-items: center; gap: 10px;
    font-variant-numeric: tabular-nums;
}
.wl-change { font-size: 0.78rem; }
.wl-pct {
    font-size: 0.72rem; font-weight: 500;
    padding: 2px 6px; border-radius: 4px;
}
.wl-pct.up { background: var(--profit-dim); color: var(--profit); }
.wl-pct.down { background: var(--loss-dim); color: var(--loss); }
.wl-price { font-size: 0.85rem; color: var(--text-primary); font-weight: 500; min-width: 64px; text-align: right; }

/* ── P&L hero ─────────────────────────────────────────── */
.pnl-hero { padding: 24px 0; }
.pnl-hero .big-num {
    font-size: 2.2rem; font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
}
.pnl-hero .big-sub {
    font-size: 0.85rem; color: var(--text-tertiary); margin-top: 4px;
    font-variant-numeric: tabular-nums;
}
.pnl-hero .side-stat {
    font-size: 0.85rem; color: var(--text-secondary);
    padding: 6px 0;
    font-variant-numeric: tabular-nums;
}
.pnl-hero .side-stat b { color: var(--text-primary); font-weight: 600; }

/* ── Section headers ──────────────────────────────────── */
.kite-section {
    font-size: 0.78rem; font-weight: 600; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.08em;
    margin: 28px 0 14px; padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
}
.kite-section .badge-count {
    background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px;
    font-size: 0.72rem; font-weight: 500; letter-spacing: 0;
    text-transform: none; color: var(--text-tertiary);
}

/* ── Filter bar ──────────────────────────────────────── */
.filter-bar {
    display: flex; align-items: center; gap: 8px;
    margin: 0 0 16px; padding: 10px 14px;
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-md);
}

/* ── Tab bar ──────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border);
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: var(--text-tertiary) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 12px 24px !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s, border-color 0.15s;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: var(--text-secondary) !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
}

/* ── Metric cards ─────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    padding: 16px 20px !important;
}
[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    font-variant-numeric: tabular-nums !important;
}

/* ── DataFrame ────────────────────────────────────────── */
[data-testid="stDataFrame"] thead tr th {
    background: var(--bg-tertiary) !important;
    color: var(--text-secondary) !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600 !important;
    border-bottom: 1px solid var(--border) !important;
}
[data-testid="stDataFrame"] {
    border-radius: var(--radius-md) !important;
    overflow: hidden;
}

/* ── Signal card ──────────────────────────────────────── */
.sig-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 10px;
    transition: border-color 0.2s, background 0.2s;
}
.sig-card:hover {
    border-color: #3c3c42;
    background: var(--bg-tertiary);
}
.sig-card .sig-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px;
}
.sig-card .sig-ticker {
    font-weight: 700; color: var(--text-primary); font-size: 1rem;
    text-decoration: none;
}
.sig-card .sig-ticker:hover { color: var(--accent); }
.sig-badge {
    font-weight: 700; font-size: 0.82rem;
    padding: 4px 10px; border-radius: 6px;
    font-variant-numeric: tabular-nums;
}
.sig-badge.high { background: var(--profit-dim); color: var(--profit); }
.sig-badge.mid { background: rgba(255,179,71,0.12); color: var(--warning); }
.sig-badge.low { background: var(--loss-dim); color: var(--loss); }
.sig-levels {
    display: flex; gap: 16px; font-size: 0.78rem;
    color: var(--text-secondary); margin-top: 8px;
    font-variant-numeric: tabular-nums;
}
.sig-levels span { display: flex; align-items: center; gap: 4px; }
.sig-subscores {
    display: flex; gap: 14px; font-size: 0.72rem;
    color: var(--text-tertiary); margin-top: 8px;
    font-variant-numeric: tabular-nums;
}
.sig-subscores .score-pill {
    padding: 2px 8px; border-radius: 4px;
    background: rgba(255,255,255,0.04);
}

/* ── Empty states ─────────────────────────────────────── */
.empty-state {
    padding: 80px 40px; text-align: center;
}
.empty-state .empty-icon {
    font-size: 2rem; margin-bottom: 16px; opacity: 0.3;
    filter: grayscale(100%);
}
.empty-state .empty-title {
    font-size: 1rem; font-weight: 600;
    color: var(--text-secondary); margin-bottom: 8px;
}
.empty-state .empty-sub {
    font-size: 0.85rem; color: var(--text-tertiary);
    max-width: 360px; margin: 0 auto;
    line-height: 1.5;
}

/* ── Status badge ─────────────────────────────────────── */
.status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.78rem; font-weight: 500;
}
.status-dot {
    width: 7px; height: 7px; border-radius: 50%;
}
.status-dot.open { background: var(--profit); box-shadow: 0 0 6px var(--profit); }
.status-dot.closed { background: var(--loss); }

/* ── Strategy Radar ───────────────────────────────────── */
.radar-card {
    background: var(--card, #1c1c22); border: 1px solid var(--border, #2a2a31);
    border-radius: 8px; padding: 14px 16px; margin-bottom: 10px;
}
.radar-card.firing { border-color: var(--profit); box-shadow: 0 0 0 1px var(--profit-dim); }
.radar-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.radar-ticker { font-size: 1rem; font-weight: 600; color: var(--text, #f4f4f6); text-decoration: none; }
.radar-ticker:hover { color: var(--accent); }
.dir-chip {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em;
    padding: 2px 8px; border-radius: 4px; text-transform: uppercase;
}
.dir-chip.long  { background: var(--profit-dim); color: var(--profit); }
.dir-chip.short { background: var(--loss-dim);   color: var(--loss); }
.strat-chip {
    font-size: 0.72rem; font-weight: 500; padding: 2px 8px; border-radius: 4px;
    background: var(--accent-dim); color: var(--accent);
}
.fire-chip {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 4px;
    background: var(--profit-dim); color: var(--profit);
}
.fire-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--profit);
            animation: radar-pulse 1.6s ease-out infinite; }
@keyframes radar-pulse {
    0%   { box-shadow: 0 0 0 0 var(--profit-dim); }
    70%  { box-shadow: 0 0 0 6px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
}
@media (prefers-reduced-motion: reduce) { .fire-dot { animation: none; } }
.radar-stats { display: flex; gap: 18px; font-size: 0.78rem; color: var(--text-dim, #78787e);
               font-variant-numeric: tabular-nums; flex-wrap: wrap; }
.radar-stats b { color: var(--text, #f4f4f6); font-weight: 600; }
.radar-empty { padding: 28px; text-align: center; color: var(--text-dim, #78787e);
               border: 1px dashed var(--border, #2a2a31); border-radius: 8px; font-size: 0.85rem; }

/* ── Regime badge ─────────────────────────────────────── */
.regime-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: 6px; font-size: 0.78rem;
    font-weight: 600;
}
.regime-badge.risk-on {
    background: var(--profit-dim); color: var(--profit);
}
.regime-badge.risk-off {
    background: var(--loss-dim); color: var(--loss);
}

/* ── Plotly ────────────────────────────────────────────── */
.js-plotly-plot { border-radius: var(--radius-md); }

/* ── Hide streamlit branding ──────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* ── Scrollbar ────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #3c3c42; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4c4c52; }

/* ── Button override ──────────────────────────────────── */
.stButton > button {
    background: var(--bg-tertiary) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    background: var(--bg-hover) !important;
    color: var(--text-primary) !important;
    border-color: #3c3c42 !important;
}

/* ── Radio pill style ─────────────────────────────────── */
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] {
    gap: 0 !important;
}

/* ── Selectbox / date input ──────────────────────────── */
[data-testid="stSelectbox"] label,
[data-testid="stDateInput"] label,
[data-testid="stNumberInput"] label {
    font-size: 0.72rem !important; color: var(--text-secondary) !important;
    text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600 !important;
}

/* ── Select container fix (prevent overlaps in grid) ─── */
[data-testid="stSelectbox"],
[data-testid="stDateInput"],
[data-testid="stNumberInput"] {
    z-index: 1;
}

/* ── Deploy button dim ───────────────────────────────── */
[data-testid="stToolbar"] { opacity: 0.4; transition: opacity 0.2s; }
[data-testid="stToolbar"]:hover { opacity: 1; }
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

def _short(ticker: str) -> str:
    return ticker.replace(".AX", "").replace(".NS", "")

def _tv_symbol(ticker: str) -> str:
    if ticker.endswith(".AX"): return f"ASX:{ticker[:-3]}"
    if ticker.endswith(".NS"): return f"NSE:{ticker[:-3]}"
    return ticker

_ALLOC_COLORS = [
    "#6993ff", "#00c48c", "#ffb347", "#ff5a5a", "#a78bfa",
    "#22d3ee", "#f472b6", "#84cc16", "#fbbf24", "#64748b",
    "#e879f9", "#818cf8", "#2dd4bf", "#fb923c", "#94a3b8",
    "#38bdf8", "#c084fc",
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
        title=dict(text=title, font=dict(size=12, color="#a0a0a6")) if title else dict(text=""),
        height=h,
        margin=dict(t=margin[0], b=margin[1], l=margin[2], r=margin[3]),
        plot_bgcolor="#121214",
        paper_bgcolor="#121214",
        font=dict(color="#a0a0a6", size=11, family="Inter"),
        xaxis=dict(gridcolor="#222226", color="#78787e", showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#222226", color="#78787e", zeroline=False, gridwidth=1),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2, font=dict(size=10, color="#a0a0a6")),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#222226", bordercolor="#2c2c30", font=dict(color="#eaeaed", size=12)),
    )


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    exchange = st.radio(
        "Exchange",
        ["asx", "nse"],
        format_func=lambda x: "ASX 200" if x == "asx" else "NSE NIFTY 100",
        horizontal=True,
    )
    currency = "$" if exchange == "asx" else "₹"

    mkt = market_status(exchange)
    _market_open = mkt["open"]
    dot_cls = "open" if _market_open else "closed"
    status_text = "Market Open" if _market_open else "Market Closed"

    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0 12px">'
        f'  <span style="font-size:0.78rem;color:var(--text-tertiary)">{mkt["local_time"]}</span>'
        f'  <span class="status-badge">'
        f'    <span class="status-dot {dot_cls}"></span>'
        f'    <span style="color:{"var(--profit)" if _market_open else "var(--loss)"}">{status_text}</span>'
        f'  </span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div style="border-bottom:1px solid var(--border);margin:0 0 12px"></div>',
                unsafe_allow_html=True)

    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    if positions:
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0 10px">'
            f'  <span style="font-size:0.78rem;color:var(--text-secondary);font-weight:600;'
            f'    text-transform:uppercase;letter-spacing:0.08em">Holdings</span>'
            f'  <span style="font-size:0.72rem;color:var(--text-tertiary);'
            f'    background:var(--bg-tertiary);padding:2px 8px;border-radius:4px">{len(positions)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for p in positions:
            t = p["ticker"]
            cp = p.get("current_price") or 0
            pnl = p.get("unrealised_pnl") or 0
            pnl_pct = p.get("unrealised_pnl_pct") or 0
            cls = _pnl_class(pnl)

            st.markdown(
                f'<div class="wl-item">'
                f'  <span class="wl-ticker">{_short(t)}</span>'
                f'  <div class="wl-right">'
                f'    <span class="wl-pct {cls}">{pnl_pct:+.1f}%</span>'
                f'    <span class="wl-price">{cp:,.2f}</span>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="empty-state" style="padding:40px 12px">'
            '  <div class="empty-title">No active positions</div>'
            '  <div class="empty-sub">Signals will appear when the market opens and the AI engine runs.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="border-bottom:1px solid var(--border);margin:12px 0"></div>',
                unsafe_allow_html=True)

    _phase = int(os.getenv("TRADING_PHASE", 1))
    _capital = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
    mode_map = {1: ("Paper", "var(--warning)"), 2: ("IBKR Paper", "var(--accent)"), 3: ("LIVE", "var(--profit)")}
    mode_text, mode_color = mode_map.get(_phase, ("Paper", "var(--warning)"))

    st.markdown(
        f'<div style="font-size:0.75rem;color:var(--text-tertiary);padding:4px 0;line-height:1.8">'
        f'  Mode: <span style="color:{mode_color};font-weight:600">{mode_text}</span><br>'
        f'  Capital: <span style="color:var(--text-secondary);font-weight:500">{currency}{_capital:,.0f}</span><br>'
        f'  Source: <span style="color:var(--text-secondary);font-weight:500">{"Supabase" if _use_supabase() else "Local DB"}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    if st.button("Refresh", use_container_width=True, type="secondary"):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ══════════════════════════════════════════════════════════════════════════════

tab_dash, tab_holdings, tab_signals, tab_radar, tab_charts, tab_scanner, tab_history, tab_backtest = st.tabs([
    "Dashboard", "Holdings", "Signals", "Radar", "Charts", "Scanner", "Trade History", "Backtest",
])


# ── TAB 1: Dashboard ─────────────────────────────────────────────────────────
with tab_dash:
    import pandas as pd

    total_invested = portfolio.get("total_invested", 0) or 0
    total_value = portfolio.get("total_current_value", 0) or 0
    total_pnl = portfolio.get("total_unrealised_pnl", 0) or 0
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    regime = load_regime(exchange)
    pnl_cls = _pnl_class(total_pnl)
    regime_ok = regime.get("regime_ok")

    col_pnl, col_stats = st.columns([1, 1])
    with col_pnl:
        st.markdown(
            f'<div class="pnl-hero">'
            f'  <div class="kite-section">Total P&L</div>'
            f'  <div class="big-num {pnl_cls}">{_pnl_sign(total_pnl, currency)}</div>'
            f'  <div class="big-sub"><span class="{pnl_cls}">{_pnl_pct(total_pnl_pct)}</span>'
            f'  &nbsp;on {len(positions)} positions</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with col_stats:
        regime_cls = "risk-on" if regime_ok else "risk-off"
        regime_text = "RISK-ON" if regime_ok else "RISK-OFF"

        st.markdown(
            f'<div style="padding:24px 0">'
            f'  <div class="kite-section">Summary</div>'
            f'  <div class="pnl-hero">'
            f'    <div class="side-stat">Current value &nbsp; <b>{currency}{total_value:,.2f}</b></div>'
            f'    <div class="side-stat">Investment &nbsp; <b>{currency}{total_invested:,.2f}</b></div>'
            f'    <div class="side-stat">Win / Loss &nbsp; <b>{portfolio.get("winners",0)}W / {portfolio.get("losers",0)}L</b></div>'
            f'    <div class="side-stat">Regime &nbsp; '
            f'      <span class="regime-badge {regime_cls}">{regime_text}'
            f'      ({regime.get("pct_above", 0):+.1f}%)</span>'
            f'    </div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Allocation bar + legend
    if positions and total_value > 0:
        bar_html = '<div class="alloc-bar">'
        legend_html = '<div class="alloc-legend">'
        for i, p in enumerate(positions):
            pct = (p.get("current_value", 0) / total_value * 100) if total_value else 0
            color = _ALLOC_COLORS[i % len(_ALLOC_COLORS)]
            short = _short(p["ticker"])
            bar_html += f'<div class="alloc-seg" style="width:{pct:.1f}%;background:{color}" title="{short}: {pct:.1f}%"></div>'
            if pct >= 3:
                legend_html += (
                    f'<span class="alloc-legend-item">'
                    f'<span class="alloc-dot" style="background:{color}"></span>'
                    f'{short} {pct:.0f}%</span>'
                )
        bar_html += '</div>'
        legend_html += '</div>'
        st.markdown(bar_html + legend_html, unsafe_allow_html=True)

    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

    # Market overview chart with period filter
    dash_period = st.selectbox("P&L Period", ["30 days", "60 days", "90 days", "180 days", "1 year"],
                               index=2, key="dash_pnl_period")
    dash_days = {"30 days": 30, "60 days": 60, "90 days": 90, "180 days": 180, "1 year": 365}[dash_period]
    st.markdown(f'<div class="kite-section">Market Overview — {dash_period} P&L</div>', unsafe_allow_html=True)

    pnl_data = load_pnl(exchange, dash_days)
    if pnl_data:
        import plotly.graph_objects as go
        dates = [r.get("date") or r.get("exit_date") for r in pnl_data]
        cum = [r.get("cumulative_pnl", 0) for r in pnl_data]
        daily = [r.get("daily_pnl", 0) for r in pnl_data]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=cum, mode="lines",
            line=dict(color="#6993ff", width=2),
            fill="tozeroy", fillcolor="rgba(105,147,255,0.06)",
            name="Cumulative P&L",
        ))
        fig.add_trace(go.Bar(
            x=dates, y=daily,
            marker_color=["#00c48c" if v >= 0 else "#ff5a5a" for v in daily],
            opacity=0.4, name="Daily P&L",
        ))
        layout = _chart_base(h=300)
        layout["barmode"] = "overlay"
        layout["yaxis"]["tickprefix"] = currency
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="empty-state">'
            '  <div class="empty-title">No closed trades yet</div>'
            '  <div class="empty-sub">P&L data will appear after the first position is closed.</div>'
            '</div>',
            unsafe_allow_html=True,
        )


# ── TAB 2: Holdings ──────────────────────────────────────────────────────────
with tab_holdings:
    if not positions:
        st.markdown(
            '<div class="empty-state">'
            '  <div class="empty-title">No positions yet</div>'
            '  <div class="empty-sub">When the AI engine generates buy signals above the threshold, '
            '  positions will be opened and displayed here.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        hold_sort = st.selectbox("Sort by", ["Default", "P&L (high to low)", "P&L (low to high)",
                                              "P&L % (high to low)", "Value (high to low)", "Days held"],
                                 index=0, key="hold_sort")
        if hold_sort == "P&L (high to low)":
            positions = sorted(positions, key=lambda x: x.get("unrealised_pnl", 0), reverse=True)
        elif hold_sort == "P&L (low to high)":
            positions = sorted(positions, key=lambda x: x.get("unrealised_pnl", 0))
        elif hold_sort == "P&L % (high to low)":
            positions = sorted(positions, key=lambda x: x.get("unrealised_pnl_pct", 0), reverse=True)
        elif hold_sort == "Value (high to low)":
            positions = sorted(positions, key=lambda x: x.get("current_value", 0), reverse=True)
        elif hold_sort == "Days held":
            positions = sorted(positions, key=lambda x: x.get("days_held", 0), reverse=True)

        day_pnl = portfolio.get("total_day_pnl", 0) or 0
        day_pnl_pct = (day_pnl / total_value * 100) if total_value else 0
        st.markdown(
            f'<div class="summary-strip">'
            f'  <div class="summary-item"><div class="label">Investment</div>'
            f'    <div class="value">{currency}{total_invested:,.2f}</div></div>'
            f'  <div class="summary-item"><div class="label">Current Value</div>'
            f'    <div class="value">{currency}{total_value:,.2f}</div></div>'
            f'  <div class="summary-item"><div class="label">Day\'s P&L</div>'
            f'    <div class="value {_pnl_class(day_pnl)}">{_pnl_sign(day_pnl, currency)}</div>'
            f'    <div class="sub {_pnl_class(day_pnl)}">{_pnl_pct(day_pnl_pct)}</div></div>'
            f'  <div class="summary-item"><div class="label">Total P&L</div>'
            f'    <div class="value {_pnl_class(total_pnl)}">{_pnl_sign(total_pnl, currency)}</div>'
            f'    <div class="sub {_pnl_class(total_pnl)}">{_pnl_pct(total_pnl_pct)}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        table_html = '''<table class="kite-table"><thead><tr>
            <th>Instrument</th><th>Qty.</th><th>Avg. cost</th><th>LTP</th>
            <th>Invested</th><th>Cur. val</th><th>P&L</th><th>Net chg.</th><th>Days</th>
        </tr></thead><tbody>'''

        for p in positions:
            t = p["ticker"]
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
                <td><a href="{tv}" target="_blank" class="ticker-link">{_short(t)}</a></td>
                <td>{shares:,.0f}</td>
                <td>{entry:,.2f}</td>
                <td>{cp:,.2f}</td>
                <td>{currency}{invested:,.2f}</td>
                <td>{currency}{cur_val:,.2f}</td>
                <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                <td class="{cls}">{_pnl_pct(pnl_pct)}</td>
                <td>{days}</td>
            </tr>'''

        table_html += f'''<tr class="total-row">
            <td>Total ({len(positions)})</td><td></td><td></td><td></td>
            <td>{currency}{total_invested:,.2f}</td>
            <td>{currency}{total_value:,.2f}</td>
            <td class="{_pnl_class(total_pnl)}">{_pnl_sign(total_pnl, currency)}</td>
            <td class="{_pnl_class(total_pnl)}">{_pnl_pct(total_pnl_pct)}</td>
            <td></td>
        </tr>'''

        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)

        # Allocation bar + legend
        if total_value > 0:
            bar_html = '<div class="alloc-bar" style="margin-top:24px">'
            legend_html = '<div class="alloc-legend">'
            for i, p in enumerate(positions):
                pct = (p.get("current_value", 0) / total_value * 100)
                color = _ALLOC_COLORS[i % len(_ALLOC_COLORS)]
                short = _short(p["ticker"])
                bar_html += f'<div class="alloc-seg" style="width:{pct:.1f}%;background:{color}" title="{short}: {pct:.1f}%"></div>'
                legend_html += (
                    f'<span class="alloc-legend-item">'
                    f'<span class="alloc-dot" style="background:{color}"></span>'
                    f'{short} {currency}{p.get("current_value",0):,.0f}</span>'
                )
            bar_html += '</div>'
            legend_html += '</div>'
            st.markdown(bar_html + legend_html, unsafe_allow_html=True)

        # P&L horizontal bar chart
        st.markdown('<div class="kite-section" style="margin-top:28px">P&L by Position</div>',
                    unsafe_allow_html=True)

        import plotly.graph_objects as go
        sorted_pos = sorted(positions, key=lambda x: x.get("unrealised_pnl", 0))
        tickers_short = [_short(p["ticker"]) for p in sorted_pos]
        pnls = [p.get("unrealised_pnl", 0) for p in sorted_pos]
        colors = ["#00c48c" if v >= 0 else "#ff5a5a" for v in pnls]

        fig = go.Figure(go.Bar(
            y=tickers_short, x=pnls, orientation="h",
            marker_color=colors,
            marker_line=dict(width=0),
            text=[f"{currency}{v:+,.0f}" for v in pnls],
            textposition="outside", textfont=dict(size=11, color="#a0a0a6"),
        ))
        layout = _chart_base(h=max(len(positions) * 32, 300))
        layout["yaxis"]["autorange"] = True
        layout["xaxis"]["tickprefix"] = currency
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── TAB 3: Signals ────────────────────────────────────────────────────────────
with tab_signals:
    sig_col1, sig_col2, sig_col3 = st.columns([1, 1, 1])
    with sig_col1:
        sig_date = st.date_input("Signal Date", value=_today(exchange), key="sig_date_pick")
    with sig_col2:
        sig_min_score = st.number_input("Min Score", min_value=0, max_value=100, value=0, step=5, key="sig_min")
    with sig_col3:
        sig_count = st.selectbox("Show Top", [10, 20, 50], index=1, key="sig_count")

    signals = load_signals(exchange, sig_date, sig_count)
    if sig_min_score > 0:
        signals = [s for s in signals if (s.get("composite_score", 0) or 0) >= sig_min_score]

    if not signals:
        st.markdown(
            f'<div class="empty-state">'
            f'  <div class="empty-title">No signals for {sig_date}</div>'
            f'  <div class="empty-sub">Signals are generated daily during market hours. '
            f'  Try an earlier date or lower the minimum score filter.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        buy_count = sum(1 for s in signals if (s.get("composite_score", 0) or 0) >= 65)
        st.markdown(
            f'<div class="kite-section">Signals for {sig_date}'
            f' <span class="badge-count">{len(signals)} total</span>'
            f' <span class="badge-count" style="background:var(--profit-dim);color:var(--profit)">{buy_count} buy</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        cols = st.columns(2)
        for i, sig in enumerate(signals):
            with cols[i % 2]:
                t = sig.get("ticker", "")
                score = sig.get("composite_score", 0)
                entry = sig.get("entry_price", 0)
                target = sig.get("target_price", 0)
                stop = sig.get("stop_loss_price", 0)
                tv = _tv_url(t)

                badge_cls = "high" if score >= 70 else ("mid" if score >= 60 else "low")
                upside = ((target - entry) / entry * 100) if entry and target else 0
                risk = ((entry - stop) / entry * 100) if entry and stop else 0

                rr_ratio = (upside / risk) if risk > 0 else 0
                rr_color = "var(--profit)" if rr_ratio >= 1.5 else ("var(--warning)" if rr_ratio >= 1.0 else "var(--loss)")

                strat = sig.get("strategy_name")
                strat_chip = (
                    f'<span class="score-pill" style="background:var(--accent-dim, rgba(98,84,243,.15));'
                    f'color:var(--accent, #8b7cf6)">{strat.replace("_", " ")}</span>'
                ) if strat else ""

                st.markdown(
                    f'<div class="sig-card">'
                    f'  <div class="sig-header">'
                    f'    <a href="{tv}" target="_blank" class="sig-ticker">{_short(t)}</a>'
                    f'    {strat_chip}'
                    f'    <span class="sig-badge {badge_cls}">{score:.0f}</span>'
                    f'  </div>'
                    f'  <div class="sig-levels">'
                    f'    <span>Entry <b>{currency}{entry:,.2f}</b></span>'
                    f'    <span style="color:var(--profit)">Target <b>{currency}{target:,.2f}</b> (+{upside:.1f}%)</span>'
                    f'    <span style="color:var(--loss)">Stop <b>{currency}{stop:,.2f}</b> (-{risk:.1f}%)</span>'
                    f'    <span style="color:{rr_color}">R:R <b>{rr_ratio:.1f}</b></span>'
                    f'  </div>'
                    f'  <div class="sig-subscores">'
                    f'    <span class="score-pill">Sent {sig.get("sentiment_score", 0):.0f}</span>'
                    f'    <span class="score-pill">Fund {sig.get("fundamental_score", 0):.0f}</span>'
                    f'    <span class="score-pill">Tech {sig.get("technical_score", 0):.0f}</span>'
                    f'    <span class="score-pill">Ins {sig.get("insider_score", 0):.0f}</span>'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="kite-section" style="margin-top:20px">Full Signal Table</div>',
                    unsafe_allow_html=True)
        import pandas as pd
        df_sig = pd.DataFrame(signals)
        display_cols = ["ticker", "strategy_name", "composite_score", "entry_price", "target_price",
                        "stop_loss_price", "sentiment_score", "fundamental_score",
                        "technical_score", "insider_score"]
        display_cols = [c for c in display_cols if c in df_sig.columns]
        if display_cols:
            st.dataframe(df_sig[display_cols], use_container_width=True, hide_index=True)


# ── TAB 4: Strategy Radar (live per-stock strategy engine) ───────────────────
with tab_radar:
    from dashboard.data import get_strategy_radar, ticker_tv_url as _tv

    radar = get_strategy_radar(exchange)
    firing = [r for r in radar if r["firing"]]
    validated_r = [r for r in radar if r["validated"]]
    longs = sum(1 for r in validated_r if r["direction"] == "long")
    shorts = len(validated_r) - longs

    st.markdown(
        f'<div class="kite-section">Strategy Radar'
        f' <span class="badge-count">{len(radar)} stocks scanned</span>'
        f' <span class="badge-count" style="background:var(--profit-dim);color:var(--profit)">'
        f'{len(firing)} firing now</span>'
        f' <span class="badge-count">{longs} long / {shorts} short validated</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:var(--text-dim,#78787e);font-size:13px;margin-bottom:14px">'
        'Each stock trades only the strategy its own 2-year history validated — in-sample backtest '
        'AND out-of-sample forward test. A card lights up when that validated strategy\'s entry '
        'condition fires on today\'s bar, long or short.</div>',
        unsafe_allow_html=True,
    )

    if not radar:
        st.markdown(
            '<div class="radar-empty">No strategy assignments yet — run '
            '<code>python main.py --select-strategies</code> or wait for the Sunday 07:00 job.</div>',
            unsafe_allow_html=True,
        )
    else:
        # ── Dynamic ticker inspector ──────────────────────────────────────
        import streamlit.components.v1 as _components
        from dashboard.data import get_live_prices as _get_live_prices

        def _radar_label(r):
            tname = r["ticker"].rsplit(".", 1)[0]
            strat_label = (r["strategy_name"] or "—").replace("_", " ")
            tag = "FIRING" if r["firing"] else ("validated" if r["validated"] else "unvalidated")
            return f'{tname} · {strat_label} ({r["direction"]}) · {tag}'

        radar_by_label = {_radar_label(r): r for r in radar}
        default_idx = 0
        labels = list(radar_by_label.keys())
        if firing:
            default_idx = labels.index(_radar_label(firing[0]))

        st.markdown('<div class="kite-section" style="margin-top:6px">Inspect a Stock</div>',
                    unsafe_allow_html=True)
        selected_label = st.selectbox(
            "Select a ticker to view its chart and trade plan",
            options=labels,
            index=default_idx,
            key="radar_inspect_ticker",
        )
        sel = radar_by_label[selected_label]
        sel_ticker = sel["ticker"]
        sel_symbol = _tv_symbol(sel_ticker)

        live_prices = _get_live_prices([sel_ticker])
        current_price = live_prices.get(sel_ticker)

        entry = sel.get("entry_price")
        target = sel.get("target_price")
        stop = sel.get("stop_loss_price")
        direction = sel["direction"]

        # Progress bar from stop -> entry -> target, marker at current price
        progress_html = ""
        if entry and target and stop and current_price:
            lo = min(stop, target)
            hi = max(stop, target)
            span = hi - lo if hi != lo else 1
            pct = max(0.0, min(100.0, (current_price - lo) / span * 100))
            entry_pct = max(0.0, min(100.0, (entry - lo) / span * 100))
            stop_label = f"Stop {currency}{stop:.2f}"
            target_label = f"Target {currency}{target:.2f}"
            left_label, right_label = (stop_label, target_label) if stop < target else (target_label, stop_label)
            if current_price >= target if direction == "long" else current_price <= target:
                bar_color = "var(--profit)"
            elif current_price <= stop if direction == "long" else current_price >= stop:
                bar_color = "var(--loss, #ff5a5a)"
            else:
                bar_color = "var(--accent)"
            progress_html = (
                '<div style="margin-top:10px">'
                f'  <div style="display:flex;justify-content:space-between;font-size:0.75rem;'
                f'color:var(--text-dim,#78787e);margin-bottom:4px">'
                f'    <span>{left_label}</span><span>Entry {currency}{entry:.2f}</span><span>{right_label}</span>'
                f'  </div>'
                f'  <div style="position:relative;height:8px;border-radius:4px;background:#2c2c30">'
                f'    <div style="position:absolute;left:{entry_pct:.1f}%;top:-3px;width:2px;height:14px;'
                f'background:var(--text-dim,#78787e)"></div>'
                f'    <div style="position:absolute;left:{pct:.1f}%;top:-4px;width:10px;height:16px;'
                f'border-radius:3px;background:{bar_color};transform:translateX(-50%)"></div>'
                f'  </div>'
                f'  <div style="text-align:center;font-size:0.85rem;margin-top:6px;color:var(--text,#f4f4f6)">'
                f'    Current <b>{currency}{current_price:.2f}</b>'
                f'  </div>'
                '</div>'
            )

        strat_label = (sel.get("strategy_name") or "—").replace("_", " ")
        fw_pf = sel.get("fw_profit_factor") or 0
        fw_wr = (sel.get("fw_win_rate") or 0) * 100
        rank = sel.get("rank_score") or 0

        st.markdown(
            f'<div class="radar-card{" firing" if sel["firing"] else ""}" style="margin-top:8px">'
            f'  <div class="radar-head">'
            f'    <a class="radar-ticker" href="{_tv(sel_ticker)}" target="_blank">{sel_ticker.rsplit(".", 1)[0]}</a>'
            f'    <span class="dir-chip {direction}">{direction}</span>'
            f'    <span class="strat-chip">{strat_label}</span>'
            + (f'    <span class="fire-chip"><span class="fire-dot"></span>FIRING</span>' if sel["firing"] else "")
            + f'  </div>'
            f'  <div class="radar-stats">'
            f'    <span>Fwd PF <b>{fw_pf:.2f}</b></span>'
            f'    <span>Fwd WR <b>{fw_wr:.0f}%</b></span>'
            f'    <span>Rank <b>{rank:.2f}</b></span>'
            f'  </div>'
            f'  {progress_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        chart_html = f"""
        <div id="radar-chart-container" style="height:420px; border-radius:10px; overflow:hidden; border:1px solid #2c2c30; margin-top:10px;">
        <div class="tradingview-widget-container" style="height:100%;width:100%">
          <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
          {{
            "autosize": true,
            "symbol": "{sel_symbol}",
            "interval": "D",
            "timezone": "{'Australia/Sydney' if exchange == 'asx' else 'Asia/Kolkata'}",
            "theme": "dark",
            "style": "1",
            "locale": "en",
            "backgroundColor": "#121214",
            "gridColor": "rgba(44, 44, 48, 0.6)",
            "hide_top_toolbar": false,
            "hide_legend": false,
            "allow_symbol_change": false,
            "save_image": false,
            "calendar": false,
            "hide_volume": false,
            "support_host": "https://www.tradingview.com",
            "studies": ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"]
          }}
          </script>
        </div>
        </div>
        """
        _components.html(chart_html, height=430, scrolling=False)

        if firing:
            st.markdown('<div class="kite-section" style="margin-top:6px">Firing Today</div>',
                        unsafe_allow_html=True)
            for r in firing:
                tname = r["ticker"].rsplit(".", 1)[0]
                strat_label = (r["strategy_name"] or "").replace("_", " ")
                entry = f'{currency}{r["entry_price"]:.2f}' if r.get("entry_price") else "—"
                target = f'{currency}{r["target_price"]:.2f}' if r.get("target_price") else "—"
                stop = f'{currency}{r["stop_loss_price"]:.2f}' if r.get("stop_loss_price") else "—"
                st.markdown(
                    f'<div class="radar-card firing">'
                    f'  <div class="radar-head">'
                    f'    <a class="radar-ticker" href="{_tv(r["ticker"])}" target="_blank">{tname}</a>'
                    f'    <span class="dir-chip {r["direction"]}">{r["direction"]}</span>'
                    f'    <span class="strat-chip">{strat_label}</span>'
                    f'    <span class="fire-chip"><span class="fire-dot"></span>FIRING</span>'
                    f'  </div>'
                    f'  <div class="radar-stats">'
                    f'    <span>Entry <b>{entry}</b></span>'
                    f'    <span>Target <b>{target}</b></span>'
                    f'    <span>Stop <b>{stop}</b></span>'
                    f'    <span>Fwd PF <b>{r["fw_profit_factor"] or 0:.2f}</b></span>'
                    f'    <span>Fwd WR <b>{(r["fw_win_rate"] or 0) * 100:.0f}%</b></span>'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="radar-empty">No validated strategy fires on today\'s bar — '
                'the engine only trades when a proven edge sets up. Patience is a position.</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="kite-section" style="margin-top:20px">Validated — Watching</div>',
                    unsafe_allow_html=True)
        watching = [r for r in validated_r if not r["firing"]]
        if watching:
            cols = st.columns(2)
            for idx, r in enumerate(watching):
                tname = r["ticker"].rsplit(".", 1)[0]
                strat_label = (r["strategy_name"] or "").replace("_", " ")
                score = f'{r["composite_score"]:.0f}' if r.get("composite_score") is not None else "—"
                with cols[idx % 2]:
                    st.markdown(
                        f'<div class="radar-card">'
                        f'  <div class="radar-head">'
                        f'    <a class="radar-ticker" href="{_tv(r["ticker"])}" target="_blank">{tname}</a>'
                        f'    <span class="dir-chip {r["direction"]}">{r["direction"]}</span>'
                        f'    <span class="strat-chip">{strat_label}</span>'
                        f'  </div>'
                        f'  <div class="radar-stats">'
                        f'    <span>Score <b>{score}</b></span>'
                        f'    <span>Fwd PF <b>{r["fw_profit_factor"] or 0:.2f}</b></span>'
                        f'    <span>Rank <b>{r["rank_score"] or 0:.2f}</b></span>'
                        f'  </div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown('<div class="radar-empty">No validated assignments yet for this exchange.</div>',
                        unsafe_allow_html=True)


# ── TAB 5: Charts (TradingView) ───────────────────────────────────────────────
with tab_charts:
    import streamlit.components.v1 as components

    # Ticker selector: holdings + manual entry
    chart_options = [_tv_symbol(p["ticker"]) for p in positions] if positions else []
    default_symbol = "ASX:XJO" if exchange == "asx" else "NSE:NIFTY"

    col_sym, col_interval, col_style = st.columns([2, 1, 1])
    with col_sym:
        if chart_options:
            selected_symbol = st.selectbox(
                "Symbol",
                options=[default_symbol] + chart_options,
                index=0,
                key="tv_chart_symbol",
            )
        else:
            selected_symbol = st.text_input("Symbol", value=default_symbol, key="tv_chart_symbol_input")

    with col_interval:
        interval_map = {"1 min": "1", "5 min": "5", "15 min": "15", "1 hour": "60", "4 hour": "240", "Daily": "D", "Weekly": "W"}
        selected_interval = st.selectbox("Interval", list(interval_map.keys()), index=5, key="tv_interval")

    with col_style:
        style_map = {"Candles": "1", "Bars": "0", "Line": "2", "Area": "3", "Heikin Ashi": "8", "Hollow Candles": "9"}
        selected_style = st.selectbox("Chart Type", list(style_map.keys()), index=0, key="tv_style")

    tv_interval = interval_map[selected_interval]
    tv_style = style_map[selected_style]

    chart_html = f"""
    <div id="tv-chart-container" style="height:560px; border-radius:10px; overflow:hidden; border:1px solid #2c2c30;">
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {{
        "autosize": true,
        "symbol": "{selected_symbol}",
        "interval": "{tv_interval}",
        "timezone": "{'Australia/Sydney' if exchange == 'asx' else 'Asia/Kolkata'}",
        "theme": "dark",
        "style": "{tv_style}",
        "locale": "en",
        "backgroundColor": "#121214",
        "gridColor": "rgba(44, 44, 48, 0.6)",
        "hide_top_toolbar": false,
        "hide_legend": false,
        "allow_symbol_change": true,
        "save_image": true,
        "calendar": false,
        "hide_volume": false,
        "support_host": "https://www.tradingview.com",
        "studies": [
          "MASimple@tv-basicstudies",
          "RSI@tv-basicstudies",
          "Volume@tv-basicstudies"
        ]
      }}
      </script>
    </div>
    <!-- TradingView Widget END -->
    </div>
    """
    components.html(chart_html, height=570, scrolling=False)

    # Technical Analysis + Symbol Profile side by side
    st.markdown('<div class="kite-section" style="margin-top:24px">Technical Analysis</div>',
                unsafe_allow_html=True)

    col_ta, col_profile = st.columns([1, 1])

    with col_ta:
        # Build our own TA summary from the engine data when available
        _ta_ticker = None
        if selected_symbol.startswith("ASX:"):
            _ta_ticker = selected_symbol.replace("ASX:", "") + ".AX"
        elif selected_symbol.startswith("NSE:"):
            _ta_ticker = selected_symbol.replace("NSE:", "") + ".NS"

        _ta_meta = None
        if _ta_ticker:
            try:
                from ai_engine.technical_engine import get_technical_meta
                _ta_meta = get_technical_meta(_ta_ticker)
            except Exception:
                pass

        if _ta_meta and _ta_meta.get("entry"):
            _rsi = _ta_meta.get("rsi", 50)
            _stoch = _ta_meta.get("stoch_rsi", 50)
            _adx = _ta_meta.get("adx", 25)
            _bb_pct = _ta_meta.get("bb_position_pct", 50)
            _atr = _ta_meta.get("atr", 0)
            _score = _ta_meta.get("composite_score", 50)
            _macd_bull = _ta_meta.get("macd_bullish", False)
            _signals = _ta_meta.get("signals", [])
            _trend = _ta_meta.get("adx_desc", "unknown")

            _verdict = "Strong Buy" if _score >= 75 else ("Buy" if _score >= 65 else ("Neutral" if _score >= 45 else ("Sell" if _score >= 30 else "Strong Sell")))
            _v_color = "var(--profit)" if _score >= 65 else ("var(--warning)" if _score >= 45 else "var(--loss)")

            def _gauge_bar(label, value, max_val=100, invert=False):
                pct = min(value / max_val * 100, 100)
                if invert:
                    color = "var(--profit)" if value < 35 else ("var(--warning)" if value < 65 else "var(--loss)")
                else:
                    color = "var(--profit)" if value > 65 else ("var(--warning)" if value > 35 else "var(--loss)")
                return (
                    f'<div style="margin:10px 0">'
                    f'  <div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px">'
                    f'    <span style="color:var(--text-secondary)">{label}</span>'
                    f'    <span style="color:{color};font-weight:600">{value:.1f}</span>'
                    f'  </div>'
                    f'  <div style="height:6px;background:var(--bg-tertiary);border-radius:3px;overflow:hidden">'
                    f'    <div style="width:{pct:.0f}%;height:100%;background:{color};border-radius:3px"></div>'
                    f'  </div>'
                    f'</div>'
                )

            ta_card = (
                f'<div style="background:var(--bg-secondary);border:1px solid var(--border);'
                f'  border-radius:var(--radius-md);padding:20px;height:420px;overflow-y:auto">'
                f'  <div style="text-align:center;margin-bottom:16px">'
                f'    <div style="font-size:2rem;font-weight:700;color:{_v_color}">{_score:.0f}</div>'
                f'    <div style="font-size:0.85rem;color:{_v_color};font-weight:600">{_verdict}</div>'
                f'  </div>'
                + _gauge_bar("RSI (14)", _rsi)
                + _gauge_bar("Stochastic RSI", _stoch)
                + _gauge_bar("Bollinger %B", _bb_pct)
                + _gauge_bar("ADX (Trend)", _adx)
                + f'<div style="margin:10px 0">'
                + f'  <div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px">'
                + f'    <span style="color:var(--text-secondary)">MACD</span>'
                + f'    <span style="color:{"var(--profit)" if _macd_bull else "var(--loss)"};font-weight:600">'
                + f'      {"Bullish" if _macd_bull else "Bearish"}</span>'
                + f'  </div>'
                + f'</div>'
                + f'<div style="margin:10px 0">'
                + f'  <div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px">'
                + f'    <span style="color:var(--text-secondary)">ATR</span>'
                + f'    <span style="color:var(--text-primary);font-weight:600">{currency}{_atr:.3f}</span>'
                + f'  </div>'
                + f'</div>'
                + f'<div style="margin:10px 0">'
                + f'  <div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px">'
                + f'    <span style="color:var(--text-secondary)">Trend</span>'
                + f'    <span style="color:var(--text-primary);font-weight:600">{_trend}</span>'
                + f'  </div>'
                + f'</div>'
                + f'<div style="border-top:1px solid var(--border);margin-top:12px;padding-top:10px">'
                + f'  <div style="font-size:0.72rem;color:var(--text-tertiary);text-transform:uppercase;'
                + f'    letter-spacing:0.06em;margin-bottom:6px">Signals</div>'
                + ''.join(
                    f'<div style="font-size:0.78rem;color:var(--text-secondary);padding:3px 0">• {s}</div>'
                    for s in _signals[:5]
                )
                + f'</div>'
                + f'</div>'
            )
            st.markdown(ta_card, unsafe_allow_html=True)
        else:
            ta_html = f"""
            <div style="border-radius:10px; overflow:hidden; border:1px solid #2c2c30; height:420px;">
            <div class="tradingview-widget-container">
              <div class="tradingview-widget-container__widget"></div>
              <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>
              {{
                "interval": "{tv_interval}",
                "width": "100%",
                "isTransparent": false,
                "height": "100%",
                "symbol": "{selected_symbol}",
                "showIntervalTabs": true,
                "displayMode": "single",
                "locale": "en",
                "colorTheme": "dark"
              }}
              </script>
            </div>
            </div>
            """
            components.html(ta_html, height=430, scrolling=False)

    with col_profile:
        profile_html = f"""
        <div style="border-radius:10px; overflow:hidden; border:1px solid #2c2c30; height:420px;">
        <div class="tradingview-widget-container">
          <div class="tradingview-widget-container__widget"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-symbol-profile.js" async>
          {{
            "width": "100%",
            "height": "100%",
            "isTransparent": false,
            "colorTheme": "dark",
            "symbol": "{selected_symbol}",
            "locale": "en"
          }}
          </script>
        </div>
        </div>
        """
        components.html(profile_html, height=430, scrolling=False)


# ── TAB 5: Scanner (TradingView) ─────────────────────────────────────────────
with tab_scanner:
    import streamlit.components.v1 as components

    st.markdown('<div class="kite-section">Stock Screener</div>', unsafe_allow_html=True)

    tv_exchange = "ASX" if exchange == "asx" else "NSE"

    screener_html = f"""
    <div style="border-radius:10px; overflow:hidden; border:1px solid #2c2c30;">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-screener.js" async>
      {{
        "width": "100%",
        "height": 650,
        "defaultColumn": "overview",
        "defaultScreen": "most_capitalized",
        "showToolbar": true,
        "locale": "en",
        "market": "{'australia' if exchange == 'asx' else 'india'}",
        "colorTheme": "dark"
      }}
      </script>
    </div>
    </div>
    """
    components.html(screener_html, height=670, scrolling=False)

    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

    # Heatmap
    st.markdown('<div class="kite-section">Market Heatmap</div>', unsafe_allow_html=True)

    heatmap_source = "AllAU" if exchange == "asx" else "AllIN"

    heatmap_html = f"""
    <div style="border-radius:10px; overflow:hidden; border:1px solid #2c2c30;">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
      {{
        "exchanges": [],
        "dataSource": "{heatmap_source}",
        "grouping": "sector",
        "blockSize": "market_cap_basic",
        "blockColor": "change",
        "locale": "en",
        "symbolUrl": "",
        "colorTheme": "dark",
        "hasTopBar": true,
        "isDataSet498": false,
        "isZoomEnabled": true,
        "hasSymbolTooltip": true,
        "isMonoSize": false,
        "width": "100%",
        "height": 500
      }}
      </script>
    </div>
    </div>
    """
    components.html(heatmap_html, height=520, scrolling=False)

    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

    # Market Overview ticker tape
    st.markdown('<div class="kite-section">Market Overview</div>', unsafe_allow_html=True)

    import json

    if exchange == "asx":
        ticker_symbols = [
            {"proName": "ASX:XJO", "title": "ASX 200"},
            {"proName": "ASX:BHP", "title": "BHP"},
            {"proName": "ASX:CBA", "title": "CBA"},
            {"proName": "ASX:CSL", "title": "CSL"},
            {"proName": "ASX:NAB", "title": "NAB"},
            {"proName": "ASX:WBC", "title": "WBC"},
            {"proName": "ASX:ANZ", "title": "ANZ"},
            {"proName": "ASX:MQG", "title": "MQG"},
            {"proName": "ASX:WES", "title": "WES"},
            {"proName": "ASX:FMG", "title": "FMG"},
            {"proName": "FX:AUDUSD", "title": "AUD/USD"},
        ]
    else:
        ticker_symbols = [
            {"proName": "NSE:NIFTY", "title": "NIFTY 50"},
            {"proName": "NSE:RELIANCE", "title": "Reliance"},
            {"proName": "NSE:TCS", "title": "TCS"},
            {"proName": "NSE:HDFCBANK", "title": "HDFC Bank"},
            {"proName": "NSE:INFY", "title": "Infosys"},
            {"proName": "NSE:ICICIBANK", "title": "ICICI Bank"},
            {"proName": "NSE:HINDUNILVR", "title": "HUL"},
            {"proName": "NSE:ITC", "title": "ITC"},
            {"proName": "NSE:SBIN", "title": "SBI"},
            {"proName": "NSE:BHARTIARTL", "title": "Airtel"},
            {"proName": "FX:USDINR", "title": "USD/INR"},
        ]

    symbols_json = json.dumps(ticker_symbols)
    tab_json = json.dumps([{"title": f"{exchange.upper()} Stocks", "symbols": ticker_symbols}])

    overview_html = """
    <div style="border-radius:10px; overflow:hidden; border:1px solid #2c2c30;">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js" async>
      {
        "colorTheme": "dark",
        "dateRange": "1D",
        "showChart": true,
        "locale": "en",
        "largeChartUrl": "",
        "isTransparent": false,
        "showSymbolLogo": true,
        "showFloatingTooltip": true,
        "width": "100%",
        "height": 450,
        "tabs": """ + tab_json + """
      }
      </script>
    </div>
    </div>
    """
    components.html(overview_html, height=460, scrolling=False)


# ── TAB 6: Trade History ──────────────────────────────────────────────────────
with tab_history:
    hist_period = st.selectbox("Period", ["30 days", "60 days", "90 days", "180 days", "1 year", "All time"],
                               index=2, key="hist_period")
    hist_days = {"30 days": 30, "60 days": 60, "90 days": 90, "180 days": 180, "1 year": 365, "All time": 3650}[hist_period]
    trades = load_trades(exchange, hist_days)

    if not trades:
        st.markdown(
            '<div class="empty-state">'
            '  <div class="empty-title">No closed trades</div>'
            '  <div class="empty-sub">Trade history will appear after positions are closed '
            '  via stop-loss, target hit, or manual exit.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        total_realized = sum(t.get("net_pnl", 0) for t in trades)
        wins = sum(1 for t in trades if (t.get("net_pnl", 0) > 0))
        losses = len(trades) - wins
        win_rate = (wins / len(trades) * 100) if trades else 0
        avg_win = (sum(t.get("net_pnl", 0) for t in trades if t.get("net_pnl", 0) > 0) / max(wins, 1))
        avg_loss = (sum(t.get("net_pnl", 0) for t in trades if t.get("net_pnl", 0) <= 0) / max(losses, 1))
        profit_factor = abs(avg_win * wins / (avg_loss * losses)) if losses and avg_loss else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Closed Trades", len(trades))
        c2.metric("Net P&L", f"{currency}{total_realized:+,.2f}")
        c3.metric("Win Rate", f"{win_rate:.0f}%")
        c4.metric("Avg Win / Loss", f"{currency}{avg_win:+,.0f} / {currency}{avg_loss:+,.0f}")
        c5.metric("Profit Factor", f"{profit_factor:.2f}")

        pnl_data = load_pnl(exchange, hist_days)
        if pnl_data:
            import plotly.graph_objects as go
            dates = [r.get("date") or r.get("exit_date") for r in pnl_data]
            cum = [r.get("cumulative_pnl", 0) for r in pnl_data]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates, y=cum, mode="lines",
                line=dict(color="#6993ff", width=2),
                fill="tozeroy", fillcolor="rgba(105,147,255,0.06)",
                name="Cumulative P&L",
            ))
            layout = _chart_base(h=260, title="Cumulative Realized P&L")
            layout["yaxis"]["tickprefix"] = currency
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<div class="kite-section">Trade Log</div>', unsafe_allow_html=True)

        table_html = '''<table class="kite-table"><thead><tr>
            <th>Ticker</th><th>Entry</th><th>Exit</th><th>Shares</th>
            <th>Entry Price</th><th>Exit Price</th><th>P&L</th><th>Reason</th>
        </tr></thead><tbody>'''

        for t in trades:
            ticker = t.get("ticker", "")
            pnl = t.get("net_pnl", 0)
            cls = _pnl_class(pnl)
            tv = _tv_url(ticker)

            table_html += f'''<tr>
                <td><a href="{tv}" target="_blank" class="ticker-link">{_short(ticker)}</a></td>
                <td>{t.get("entry_date", "")}</td>
                <td>{t.get("exit_date", "")}</td>
                <td>{t.get("shares", 0):,.0f}</td>
                <td>{currency}{t.get("entry_price", 0):,.2f}</td>
                <td>{currency}{t.get("exit_price", 0):,.2f}</td>
                <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                <td style="font-size:0.78rem;color:var(--text-tertiary)">{t.get("exit_reason", "")}</td>
            </tr>'''

        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)

        st.markdown('<div class="kite-section" style="margin-top:20px">Exit Reasons</div>',
                    unsafe_allow_html=True)
        import plotly.graph_objects as go
        from collections import Counter
        reasons = Counter(t.get("exit_reason", "unknown") for t in trades)
        fig = go.Figure(go.Pie(
            labels=list(reasons.keys()),
            values=list(reasons.values()),
            hole=0.65,
            marker=dict(colors=_ALLOC_COLORS[:len(reasons)], line=dict(color="#121214", width=2)),
            textinfo="label+percent",
            textfont=dict(size=11, color="#a0a0a6"),
        ))
        layout = _chart_base(h=280)
        layout["showlegend"] = False
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── TAB 7: Backtest ───────────────────────────────────────────────────────────
with tab_backtest:
    bt = load_backtest(exchange)
    results = bt.get("results", []) if bt else []

    if not results:
        st.markdown(
            '<div class="empty-state">'
            '  <div class="empty-title">No backtest results</div>'
            '  <div class="empty-sub">Backtest results are generated periodically to evaluate '
            '  strategy performance across historical data.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="kite-section">Backtest Results'
            f' <span class="badge-count">{len(results)} strategies</span></div>',
            unsafe_allow_html=True,
        )

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
                colorbar=dict(title=dict(text="Sharpe", font=dict(color="#a0a0a6")),
                              tickfont=dict(color="#78787e")),
                line=dict(width=1, color="#2c2c30"),
            ),
            text=names, textposition="top center",
            textfont=dict(size=10, color="#a0a0a6"),
        ))
        layout = _chart_base(h=360, title="Return vs Win Rate (size = trades, color = Sharpe)")
        layout["xaxis"]["title"] = dict(text="Win Rate %", font=dict(color="#78787e", size=12))
        layout["yaxis"]["title"] = dict(text="Total Return %", font=dict(color="#78787e", size=12))
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        import pandas as pd
        df_bt = pd.DataFrame(results)
        st.dataframe(df_bt, use_container_width=True, hide_index=True)

    # ── Per-stock strategy assignments ────────────────────────────────────────
    from dashboard.data import get_strategy_assignments
    assignments = get_strategy_assignments(exchange)
    if assignments:
        import pandas as pd
        validated_n = sum(1 for a in assignments if a.get("validated"))
        st.markdown(
            f'<div class="kite-section" style="margin-top:20px">Per-Stock Strategy Assignments'
            f' <span class="badge-count">{len(assignments)} stocks</span>'
            f' <span class="badge-count" style="background:var(--profit-dim);color:var(--profit)">'
            f'{validated_n} validated</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="color:var(--text-dim,#78787e);font-size:13px;margin-bottom:8px">'
            'Each stock trades only its best-performing strategy, validated on in-sample backtest '
            '(70% of history) and out-of-sample forward test (last 30%). Unvalidated stocks are '
            'never traded automatically.</div>',
            unsafe_allow_html=True,
        )
        df_sa = pd.DataFrame(assignments)
        sa_cols = ["ticker", "strategy_name", "validated",
                   "bt_trades", "bt_win_rate", "bt_profit_factor",
                   "fw_trades", "fw_win_rate", "fw_profit_factor",
                   "fw_total_return_pct", "rank_score"]
        sa_cols = [c for c in sa_cols if c in df_sa.columns]
        st.dataframe(
            df_sa[sa_cols].sort_values(["validated", "rank_score"], ascending=False),
            use_container_width=True, hide_index=True,
        )
