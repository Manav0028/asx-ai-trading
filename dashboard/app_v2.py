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
    get_price_history, get_multi_close, get_multi_today_ohlc,
    ticker_tv_url, ticker_yahoo_url,
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
# Async font loading — preconnect + non-blocking <link> avoids render-blocking @import
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"></noscript>
""", unsafe_allow_html=True)

st.markdown("""
<style>

:root {
    /* ── Surfaces ── */
    --bg-primary:    #121214;
    --bg-secondary:  #1a1a1e;
    --bg-tertiary:   #222226;
    --bg-hover:      #282830;
    /* ── Borders ── */
    --border:        #2c2c30;
    --border-strong: #3c3c42;
    --border-subtle: rgba(255,255,255,0.04);
    /* ── Text ── */
    --text-primary:  #eaeaed;
    --text-secondary:#a0a0a6;
    --text-tertiary: #78787e;
    /* ── Accent ── */
    --accent:        #6993ff;
    --accent-dim:    rgba(105,147,255,0.12);
    /* ── Semantic ── */
    --profit:        #00c48c;
    --profit-dim:    rgba(0,196,140,0.10);
    --loss:          #ff5a5a;
    --loss-dim:      rgba(255,90,90,0.10);
    --warning:       #ffb347;
    --warning-dim:   rgba(255,179,71,0.12);
    --gold:          #d4a017;
    --gold-dim:      rgba(212,160,23,0.15);
    /* ── Categorical palette (allocation bars, charts) ── */
    --cat-1:#6993ff; --cat-2:#00c48c; --cat-3:#ffb347; --cat-4:#ff5a5a;
    --cat-5:#a78bfa; --cat-6:#22d3ee; --cat-7:#f472b6; --cat-8:#84cc16;
    --cat-9:#fbbf24; --cat-10:#64748b; --cat-11:#e879f9; --cat-12:#818cf8;
    --cat-13:#2dd4bf; --cat-14:#fb923c; --cat-15:#94a3b8; --cat-16:#38bdf8;
    /* ── Radius ── */
    --radius-sm:     6px;
    --radius-md:     10px;
    --radius-lg:     14px;
    --radius-pill:   999px;
    /* ── Typography ── */
    --font-sans:     'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono:     'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
    --text-2xs:      0.72rem;
    --text-xs:       0.78rem;
    --text-sm:       0.85rem;
    --text-base:     1rem;
    --text-lg:       1.25rem;
    --text-xl:       1.4rem;
    --text-2xl:      2.2rem;
    --weight-regular: 400;
    --weight-medium:  500;
    --weight-semibold:600;
    --weight-bold:    700;
    --tracking-label: 0.08em;
    --tracking-chip:  0.06em;
    --tracking-tight: -0.02em;
    /* ── Motion ── */
    --ease-out:      cubic-bezier(0.16, 1, 0.3, 1);
    --dur-fast:      0.15s;
    --dur-med:       0.2s;
    --dur-slow:      0.4s;
    /* ── Glows (live status only, no generic shadows) ── */
    --glow-profit:   0 0 6px var(--profit);
    --glow-firing:   0 0 0 1px var(--profit-dim);
    --glow-nearmiss: 0 0 0 1px rgba(212,160,23,0.25);
    --focus-ring:    0 0 0 2px var(--accent-dim);
}

* {
    box-sizing: border-box;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

/* ── DS utility classes (design system) ── */
.ds-label {
    font-size: var(--text-2xs); font-weight: var(--weight-semibold);
    text-transform: uppercase; letter-spacing: var(--tracking-label);
    color: var(--text-secondary);
}
.ds-num { font-variant-numeric: tabular-nums; }
.ds-mono {
    font-family: var(--font-mono) !important;
    font-variant-numeric: tabular-nums; letter-spacing: -0.01em;
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
    font-size: var(--text-2xs); color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: var(--tracking-label);
    margin-bottom: 6px; font-weight: var(--weight-semibold);
}
.summary-item .value {
    font-size: var(--text-lg); font-weight: var(--weight-bold); color: var(--text-primary);
    font-variant-numeric: tabular-nums;
}
.summary-item .value.up { color: var(--profit); }
.summary-item .value.down { color: var(--loss); }
.summary-item .sub {
    font-size: var(--text-xs); margin-top: 4px;
    font-variant-numeric: tabular-nums;
}
.summary-item .sub.up { color: var(--profit); }
.summary-item .sub.down { color: var(--loss); }

/* ── Holdings table ───────────────────────────────────── */
.kite-table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    font-size: var(--text-sm); font-family: var(--font-sans);
}
.kite-table thead th {
    color: var(--text-secondary); font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    text-transform: uppercase; letter-spacing: var(--tracking-label);
    padding: 12px 14px; border-bottom: 1px solid var(--border);
    text-align: right; position: sticky; top: 0;
    background: var(--bg-primary); white-space: nowrap;
}
.kite-table thead th:first-child { text-align: left; }
.kite-table tbody td {
    padding: 14px; border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary); text-align: right;
    font-variant-numeric: tabular-nums;
    transition: background var(--dur-fast);
}
.kite-table tbody td:first-child {
    text-align: left; font-weight: var(--weight-semibold); color: var(--text-primary);
}
.kite-table tbody tr:hover td { background: var(--bg-hover); }
.kite-table .up { color: var(--profit); }
.kite-table .down { color: var(--loss); }
.kite-table .ticker-link {
    color: var(--text-primary); text-decoration: none; font-weight: 600;
    font-family: var(--font-mono) !important; letter-spacing: -0.01em;
    transition: color var(--dur-fast);
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
.alloc-seg { transition: width var(--dur-slow) var(--ease-out); min-width: 2px; }

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
.wl-ohlc { font-size: 0.66rem; color: var(--text-tertiary); letter-spacing: 0.02em; margin-top: 2px; }
.wl-ohlc b { color: var(--text-secondary); }
.wl-score-chip {
    font-size: var(--text-2xs); font-weight: var(--weight-bold); padding: 2px 6px;
    border-radius: var(--radius-sm); background: var(--accent-dim); color: var(--accent);
    min-width: 28px; text-align: center; font-variant-numeric: tabular-nums;
}
.wl-score-chip.high { background: var(--profit-dim); color: var(--profit); }
.wl-score-chip.low  { background: rgba(120,120,126,0.15); color: var(--text-tertiary); }

/* ── Sidebar section header ───────────────────────────── */
.sb-section {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0 8px; cursor: pointer;
}
.sb-section-title {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.09em;
    text-transform: uppercase; color: var(--text-secondary);
}
.sb-count {
    font-size: 0.70rem; background: var(--bg-tertiary); color: var(--text-tertiary);
    padding: 1px 7px; border-radius: 4px;
}

/* ── Ticker inspector overlay ─────────────────────────── */
.insp-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 24px;
}
.insp-title {
    display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
}
.insp-ticker {
    font-size: 2rem; font-weight: var(--weight-bold); color: var(--text-primary);
    font-family: var(--font-mono) !important; letter-spacing: var(--tracking-tight);
}
.insp-price {
    font-size: var(--text-xl); font-weight: var(--weight-bold);
    font-family: var(--font-mono) !important; font-variant-numeric: tabular-nums;
    color: var(--text-primary);
}
.insp-code {
    font-size: var(--text-sm); color: var(--text-tertiary);
    font-family: var(--font-mono) !important;
}

/* ── OHLC strip ───────────────────────────────────────── */
.insp-ohlc {
    display: flex; gap: 0; margin-bottom: 24px;
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-md); overflow: hidden;
}
.insp-ohlc-cell {
    flex: 1; padding: 14px 16px; text-align: center;
    border-right: 1px solid var(--border);
}
.insp-ohlc-cell:last-child { border-right: none; }
.insp-ohlc-label {
    font-size: var(--text-2xs); color: var(--text-tertiary);
    text-transform: uppercase; letter-spacing: var(--tracking-label);
    margin-bottom: 5px; font-weight: var(--weight-semibold);
}
.insp-ohlc-val {
    font-size: var(--text-base); font-weight: var(--weight-bold);
    font-family: var(--font-mono) !important;
    font-variant-numeric: tabular-nums; color: var(--text-primary);
}

/* ── Section blocks inside inspector ─────────────────── */
.insp-section {
    font-size: var(--text-xs); font-weight: var(--weight-semibold);
    color: var(--text-secondary); text-transform: uppercase;
    letter-spacing: var(--tracking-label);
    margin: 0 0 12px; padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}
.insp-card {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 16px 20px; height: 100%;
}

/* ── Stat rows inside inspector ───────────────────────── */
.insp-stat-row {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 6px 0; border-bottom: 1px solid var(--border-subtle);
    font-size: var(--text-sm);
}
.insp-stat-row:last-child { border-bottom: none; }
.insp-stat-label { color: var(--text-tertiary); }
.insp-stat-val {
    color: var(--text-primary); font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
}

/* ── Score pills row ──────────────────────────────────── */
.insp-scores {
    display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px;
}
.insp-score-pill {
    flex: 1; min-width: 64px; text-align: center;
    background: var(--bg-tertiary); border-radius: var(--radius-sm);
    padding: 10px 8px;
}
.insp-score-pill .pill-label {
    font-size: var(--text-2xs); color: var(--text-tertiary);
    text-transform: uppercase; letter-spacing: var(--tracking-label);
    margin-bottom: 4px; font-weight: var(--weight-semibold);
}
.insp-score-pill .pill-val {
    font-size: var(--text-lg); font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
}

/* ── History mini-table inside inspector ──────────────── */
.insp-hist-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--text-sm); }
.insp-hist-table th {
    font-size: var(--text-2xs); color: var(--text-tertiary); text-transform: uppercase;
    letter-spacing: var(--tracking-label); font-weight: var(--weight-semibold);
    padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: right;
}
.insp-hist-table th:first-child { text-align: left; }
.insp-hist-table td {
    padding: 8px 10px; border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary); text-align: right;
    font-variant-numeric: tabular-nums;
}
.insp-hist-table td:first-child { text-align: left; color: var(--text-primary); }

/* ── Levels strip (Entry / Target / Stop) ─────────────── */
.insp-levels {
    display: flex; gap: 0; margin-top: 12px;
    border-radius: var(--radius-sm); overflow: hidden;
    border: 1px solid var(--border);
}
.insp-level-cell { flex: 1; padding: 10px 12px; text-align: center; background: var(--bg-tertiary); border-right: 1px solid var(--border); }
.insp-level-cell:last-child { border-right: none; }
.insp-level-label { font-size: var(--text-2xs); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: var(--tracking-label); margin-bottom: 3px; }
.insp-level-val { font-size: var(--text-base); font-weight: var(--weight-bold); font-family: var(--font-mono) !important; font-variant-numeric: tabular-nums; }

/* ── P&L hero ─────────────────────────────────────────── */
.pnl-hero { padding: 24px 0; }
.pnl-hero .big-num {
    font-size: var(--text-2xl); font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    letter-spacing: var(--tracking-tight);
}
.pnl-hero .big-sub {
    font-size: var(--text-sm); color: var(--text-tertiary); margin-top: 4px;
    font-variant-numeric: tabular-nums;
}
.pnl-hero .side-stat {
    font-size: var(--text-sm); color: var(--text-secondary);
    padding: 6px 0; font-variant-numeric: tabular-nums;
}
.pnl-hero .side-stat b { color: var(--text-primary); font-weight: var(--weight-semibold); }

/* ── Section headers ──────────────────────────────────── */
.kite-section {
    font-size: var(--text-xs); font-weight: var(--weight-semibold); color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: var(--tracking-label);
    margin: 28px 0 14px; padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
}
.kite-section .badge-count {
    background: var(--bg-tertiary); padding: 2px 8px; border-radius: var(--radius-sm);
    font-size: var(--text-2xs); font-weight: var(--weight-medium); letter-spacing: 0;
    text-transform: none; color: var(--text-tertiary); font-variant-numeric: tabular-nums;
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
    transition: border-color var(--dur-med), background var(--dur-med);
}
.sig-card:hover {
    border-color: var(--border-strong);
    background: var(--bg-tertiary);
}
.sig-card .sig-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px;
}
.sig-card .sig-ticker {
    font-weight: 700; color: var(--text-primary); font-size: var(--text-base);
    text-decoration: none; font-family: var(--font-mono) !important;
    letter-spacing: -0.01em; transition: color var(--dur-fast);
}
.sig-card .sig-ticker:hover { color: var(--accent); }
.sig-badge {
    font-weight: 700; font-size: var(--text-xs);
    padding: 4px 10px; border-radius: var(--radius-sm);
    font-variant-numeric: tabular-nums;
}
.sig-badge.high { background: var(--profit-dim); color: var(--profit); }
.sig-badge.mid  { background: var(--warning-dim); color: var(--warning); }
.sig-badge.low  { background: var(--loss-dim);    color: var(--loss); }
.sig-levels {
    display: flex; gap: 16px; font-size: 0.78rem;
    color: var(--text-secondary); margin-top: 8px;
    font-variant-numeric: tabular-nums;
}
.sig-levels span { display: flex; align-items: center; gap: 4px; }
.sig-subscores {
    display: flex; gap: 10px; flex-wrap: wrap; font-size: var(--text-2xs);
    color: var(--text-tertiary); margin-top: 8px;
    font-variant-numeric: tabular-nums;
}
.sig-subscores .score-pill {
    display: inline-flex; gap: 5px; align-items: baseline;
    padding: 2px 8px; border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.04);
}
.sig-subscores .score-pill b {
    color: var(--text-secondary); font-weight: var(--weight-semibold);
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
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 14px 16px; margin-bottom: 10px;
    transition: border-color var(--dur-med);
}
.radar-card.firing    { border-color: var(--profit); box-shadow: var(--glow-firing); }
.radar-card.near-miss { border-color: var(--gold);   box-shadow: var(--glow-nearmiss); }
.near-miss-chip {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: var(--text-2xs); font-weight: var(--weight-semibold); padding: 2px 8px; border-radius: var(--radius-sm);
    background: var(--gold-dim); color: var(--gold);
}
.radar-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.radar-ticker {
    font-size: var(--text-base); font-weight: var(--weight-semibold);
    color: var(--text-primary); text-decoration: none;
    font-family: var(--font-mono) !important; letter-spacing: -0.01em;
    transition: color var(--dur-fast);
}
.radar-ticker:hover { color: var(--accent); }
.dir-chip {
    font-size: var(--text-2xs); font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-chip); padding: 2px 8px;
    border-radius: var(--radius-sm); text-transform: uppercase;
}
.dir-chip.long  { background: var(--profit-dim); color: var(--profit); }
.dir-chip.short { background: var(--loss-dim);   color: var(--loss); }
.strat-chip {
    font-size: var(--text-xs); font-weight: var(--weight-medium);
    padding: 2px 8px; border-radius: var(--radius-sm);
    background: var(--accent-dim); color: var(--accent);
}
.fire-chip {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: var(--text-2xs); font-weight: var(--weight-semibold);
    padding: 2px 8px; border-radius: var(--radius-sm);
    background: var(--profit-dim); color: var(--profit);
}
.fire-dot {
    width: 6px; height: 6px; border-radius: 50%; background: var(--profit);
    animation: radar-pulse 1.6s ease-out infinite;
}
@keyframes radar-pulse {
    0%   { box-shadow: 0 0 0 0 var(--profit-dim); }
    70%  { box-shadow: 0 0 0 6px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
}
@media (prefers-reduced-motion: reduce) { .fire-dot { animation: none; } }
.radar-stats {
    display: flex; gap: 18px; font-size: var(--text-xs);
    color: var(--text-tertiary); font-variant-numeric: tabular-nums; flex-wrap: wrap;
}
.radar-stats b { color: var(--text-primary); font-weight: var(--weight-semibold); }
.radar-empty {
    padding: 28px; text-align: center; color: var(--text-tertiary);
    border: 1px dashed var(--border); border-radius: var(--radius-sm); font-size: var(--text-sm);
}
.radar-explain {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 14px 16px; margin-top: 10px;
    font-size: var(--text-sm); color: var(--text-tertiary); line-height: 1.55;
}
.radar-explain h4 {
    margin: 0 0 6px 0; font-size: var(--text-2xs); font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-chip); text-transform: uppercase; color: var(--text-primary);
}
.radar-explain + .radar-explain { margin-top: 8px; }
.radar-explain b { color: var(--text-primary); }
.gate-pass { color: var(--profit); font-weight: var(--weight-semibold); }
.gate-fail { color: var(--loss);   font-weight: var(--weight-semibold); }

/* ── Regime badge ─────────────────────────────────────── */
.regime-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: var(--radius-sm);
    font-size: var(--text-xs); font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
}
.regime-badge.risk-on  { background: var(--profit-dim); color: var(--profit); }
.regime-badge.risk-off { background: var(--loss-dim);   color: var(--loss); }

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
    font-weight: var(--weight-medium) !important;
    transition: background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast) !important;
}
.stButton > button:hover {
    background: var(--bg-hover) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-strong) !important;
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

/* ── Loss row highlight ────────────────────────────────*/
.kite-table tbody tr.loss-row td { background: rgba(255,90,90,0.04); }
.kite-table tbody tr.loss-row:hover td { background: rgba(255,90,90,0.09); }

/* ── Bought / in-portfolio badge on signal card ───────*/
.sig-card.is-bought {
    border-color: var(--profit);
    box-shadow: 0 0 0 1px var(--profit-dim);
}
.sig-card.is-holding {
    border-color: #6993ff;
    box-shadow: 0 0 0 1px rgba(105,147,255,0.18);
}
.bought-badge {
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em;
    padding: 2px 7px; border-radius: 4px; text-transform: uppercase;
    background: var(--profit-dim); color: var(--profit); margin-left: 4px;
}
.holding-badge {
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em;
    padding: 2px 7px; border-radius: 4px; text-transform: uppercase;
    background: rgba(105,147,255,0.15); color: #6993ff; margin-left: 4px;
}

/* ── Signal card layout ───────────────────────────────*/
.sig-meta {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 2px;
}
.sig-strategy {
    font-size: 0.72rem; font-weight: 500; padding: 2px 8px; border-radius: 4px;
    background: var(--accent-dim); color: var(--accent);
}
.sig-dir { font-size: 0.68rem; font-weight: 700; padding: 2px 7px; border-radius: 4px; text-transform: uppercase; }
.sig-dir.long  { background: var(--profit-dim); color: var(--profit); }
.sig-dir.short { background: var(--loss-dim); color: var(--loss); }

/* ── Signal hover tooltip ─────────────────────────────*/
.sig-card { position: relative; }
.sig-tooltip {
    display: none; position: absolute; z-index: 999;
    top: 0; left: 50%; transform: translateX(-50%) translateY(-105%);
    min-width: 260px; max-width: 320px;
    background: #1e1e24; border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 12px 14px;
    font-size: 0.78rem; color: var(--text-secondary);
    box-shadow: 0 8px 32px rgba(0,0,0,0.5); line-height: 1.55;
    pointer-events: none;
}
.sig-card:hover .sig-tooltip { display: block; }
.sig-tooltip h5 {
    margin: 0 0 6px; font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-primary);
}
.sig-tooltip .tt-row {
    display: flex; justify-content: space-between;
    border-bottom: 1px solid rgba(255,255,255,0.04); padding: 3px 0;
}
.sig-tooltip .tt-row:last-child { border: none; }
.sig-tooltip .tt-label { color: var(--text-tertiary); }
.sig-tooltip .tt-val { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; }

/* ── P&L hero two-up ──────────────────────────────────*/
.pnl-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 8px; }
.pnl-card {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 18px 20px;
}
.pnl-card .pnl-label {
    font-size: var(--text-2xs); font-weight: var(--weight-semibold); color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: var(--tracking-label); margin-bottom: 6px;
}
.pnl-card .pnl-value {
    font-size: var(--text-2xl); font-weight: var(--weight-bold); font-variant-numeric: tabular-nums;
    letter-spacing: var(--tracking-tight); line-height: 1.1;
}
.pnl-card .pnl-sub {
    font-size: var(--text-xs); margin-top: 5px;
    color: var(--text-tertiary); font-variant-numeric: tabular-nums;
}
.pnl-card .pnl-value.up  { color: var(--profit); }
.pnl-card .pnl-value.down { color: var(--loss); }
.pnl-card .pnl-sub.up   { color: var(--profit); }
.pnl-card .pnl-sub.down  { color: var(--loss); }

/* ── Holdings split summary ───────────────────────────*/
.hold-summary {
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;
}
.hold-block {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 14px 16px;
}
.hold-block .hb-title {
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-tertiary); margin-bottom: 10px;
}
.hold-block .hb-row {
    display: flex; justify-content: space-between;
    font-size: 0.8rem; padding: 3px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}
.hold-block .hb-row:last-child { border: none; padding-bottom: 0; }
.hold-block .hb-key { color: var(--text-secondary); }
.hold-block .hb-val { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.hold-block .hb-val.up { color: var(--profit); }
.hold-block .hb-val.down { color: var(--loss); }

/* ── Strategy prediction overlay chart ───────────────*/
.pred-container {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 14px 16px; margin-top: 10px;
}
.pred-container h4 {
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--text-primary); margin: 0 0 8px;
}

/* ── Table scroll wrapper (mobile) ───────────────────*/
.kite-table-wrap {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}
.kite-table-wrap .kite-table { min-width: 560px; }

/* ══════════════════════════════════════════════════════
   MOBILE RESPONSIVE — breakpoints: 768px and 420px
   ══════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    /* ── Container: reduce horizontal padding ── */
    .main .block-container {
        padding-left: 12px !important;
        padding-right: 12px !important;
        max-width: 100% !important;
    }

    /* ── Sidebar: full-width when open on mobile ── */
    section[data-testid="stSidebar"] {
        width: 100% !important;
        min-width: 100% !important;
    }

    /* ── Tab bar: horizontal scroll, no wrap ── */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        flex-wrap: nowrap !important;
        scrollbar-width: none !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        font-size: 0.75rem !important;
        padding: 10px 14px !important;
        white-space: nowrap !important;
        min-height: 44px !important;
    }

    /* ── P&L grid: single column ── */
    .pnl-grid {
        grid-template-columns: 1fr !important;
        gap: 10px !important;
    }
    .pnl-card .pnl-value { font-size: 1.7rem !important; }

    /* ── Summary strip: 2-up on mobile ── */
    .summary-strip {
        flex-wrap: wrap !important;
        gap: 16px 0 !important;
        padding: 14px 0 !important;
    }
    .summary-item { flex: 1 1 50% !important; min-width: 130px !important; }
    .summary-item .value { font-size: 1.1rem !important; }

    /* ── Holdings split: single column ── */
    .hold-summary { grid-template-columns: 1fr !important; }

    /* ── Filter bar: wrap ── */
    .filter-bar { flex-wrap: wrap !important; gap: 8px 8px !important; }

    /* ── Inspector header: stack vertically ── */
    .insp-header {
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 12px !important;
    }
    .insp-ticker { font-size: 1.5rem !important; }
    .insp-price  { font-size: 1.1rem !important; }

    /* ── OHLC strip: 2×2 grid on mobile ── */
    .insp-ohlc { flex-wrap: wrap !important; }
    .insp-ohlc-cell {
        flex: 1 1 50% !important;
        border-right: none !important;
        border-bottom: 1px solid var(--border) !important;
    }
    .insp-ohlc-cell:nth-child(odd)  { border-right: 1px solid var(--border) !important; }
    .insp-ohlc-cell:last-child,
    .insp-ohlc-cell:nth-last-child(2):nth-child(odd) { border-bottom: none !important; }

    /* ── Score pills: 2 per row ── */
    .insp-score-pill {
        flex: 1 1 calc(50% - 5px) !important;
        min-width: 80px !important;
    }

    /* ── Levels strip: wrap on very small screens ── */
    .insp-levels { flex-wrap: wrap !important; }
    .insp-level-cell { flex: 1 1 33% !important; }

    /* ── Signal card: reduce padding ── */
    .sig-card { padding: 12px 14px !important; }
    .sig-levels { flex-wrap: wrap !important; gap: 6px 12px !important; }
    .sig-subscores { gap: 6px !important; }

    /* ── Radar stats: wrap ── */
    .radar-stats { flex-wrap: wrap !important; gap: 8px !important; }
    .radar-head  { flex-wrap: wrap !important; }

    /* ── Alloc legend: wrap ── */
    .alloc-legend { flex-wrap: wrap !important; gap: 8px !important; }

    /* ── Empty state: compact ── */
    .empty-state { padding: 40px 16px !important; }

    /* ── Button: min touch target ── */
    .stButton > button {
        min-height: 44px !important;
        font-size: 0.85rem !important;
        padding: 8px 16px !important;
    }

    /* ── Select / dropdown: min touch height ── */
    [data-baseweb="select"] { min-height: 44px !important; }
    [data-baseweb="input"]  { min-height: 44px !important; }

    /* ── Tooltip: show below card on mobile to avoid clipping ── */
    .sig-tooltip {
        top: 100% !important;
        transform: translateX(-50%) translateY(8px) !important;
    }

    /* ── Metric value: slightly smaller ── */
    [data-testid="stMetricValue"] { font-size: 1.15rem !important; }

    /* ── kite-section: tighter margin ── */
    .kite-section { margin: 16px 0 10px !important; }

    /* ── Table scroll wrapper: enforce on mobile ── */
    .kite-table-wrap { overflow-x: auto !important; }
    .kite-table-wrap .kite-table { min-width: 560px !important; }
}

@media (max-width: 420px) {
    .pnl-card .pnl-value { font-size: 1.4rem !important; }
    .insp-ticker { font-size: 1.25rem !important; }
    .summary-item { flex: 1 1 100% !important; }
    .summary-item .value { font-size: 1.2rem !important; }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        font-size: 0.68rem !important;
        padding: 8px 10px !important;
    }
    .radar-head { flex-direction: column !important; align-items: flex-start !important; }
    .insp-ohlc-cell { flex: 1 1 50% !important; }
    .insp-level-cell { flex: 1 1 50% !important; }
    .alloc-legend-item { font-size: 0.68rem !important; }
}
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

def _pnl_class_var(v):
    return "var(--profit)" if v > 0 else ("var(--loss)" if v < 0 else "var(--text-secondary)")

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
def load_portfolio(exch, live=False):
    # Refresh every 30s while market is open; every 5 min when closed
    ttl = 30 if live else 300
    return _load_portfolio_cached(exch, live, ttl)

@st.cache_data(ttl=30)
def _load_portfolio_cached_fast(exch, live):
    return get_portfolio(exch, live=live)

@st.cache_data(ttl=300)
def _load_portfolio_cached_slow(exch, live):
    return get_portfolio(exch, live=live)

def _load_portfolio_cached(exch, live, ttl):
    if ttl <= 30:
        return _load_portfolio_cached_fast(exch, live)
    return _load_portfolio_cached_slow(exch, live)

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

@st.cache_data(ttl=120)
def fetch_batch_ohlc(tickers: tuple) -> dict:
    """Batch fetch today's OHLC for multiple tickers in one yfinance call."""
    return get_multi_today_ohlc(list(tickers))

@st.cache_data(ttl=120)
def fetch_today_ohlc(ticker: str) -> dict:
    """Return today's O/H/L/C for the given ticker (last 2 days, take latest)."""
    try:
        rows = get_price_history(ticker, days=3)
        if rows:
            r = rows[-1]
            return {
                "open":  r.get("open")  or r.get("Open"),
                "high":  r.get("high")  or r.get("High"),
                "low":   r.get("low")   or r.get("Low"),
                "close": r.get("close") or r.get("Close"),
                "date":  str(r.get("date") or r.get("Date") or ""),
            }
    except Exception:
        pass
    return {}


# ── Session state ─────────────────────────────────────────────────────────────
if "sidebar_sel" not in st.session_state:
    st.session_state.sidebar_sel = None   # ticker string or None
if "sidebar_sel_src" not in st.session_state:
    st.session_state.sidebar_sel_src = None  # "holding" | "signal"
if "sb_hold_open" not in st.session_state:
    st.session_state.sb_hold_open = True
if "sb_sig_open" not in st.session_state:
    st.session_state.sb_sig_open = True


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


def _build_candle_chart(
    dates, opens, highs, lows, closes, volumes=None,
    levels=None,   # list of (price, label, bg_color, text_color)
    zone=None,     # (y0, y1, fill_color) for shaded prediction zone
    currency="$", title="", h=400, y_range=None,
):
    """
    Modern candlestick chart with volume subplot, EMA, and pill-badge level labels.
    """
    import plotly.graph_objects as _go_c
    from plotly.subplots import make_subplots as _make_sub

    has_vol = bool(volumes and any(v for v in volumes))
    row_heights = [0.75, 0.25] if has_vol else [1.0]
    rows = 2 if has_vol else 1

    fig = _make_sub(rows=rows, cols=1, shared_xaxes=True,
                    vertical_spacing=0.02, row_heights=row_heights)

    # ── Candlesticks ──────────────────────────────────────────────────────────
    fig.add_trace(_go_c.Candlestick(
        x=dates, open=opens, high=highs, low=lows, close=closes,
        name="Price",
        increasing_line_color="#00c48c", decreasing_line_color="#ff5a5a",
        increasing_fillcolor="rgba(0,196,140,0.3)",
        decreasing_fillcolor="rgba(255,90,90,0.3)",
        line=dict(width=1),
        whiskerwidth=0.6,
    ), row=1, col=1)

    # ── 20-day EMA ───────────────────────────────────────────────────────────
    if len(closes) >= 5:
        k = min(20, len(closes))
        mul = 2 / (k + 1)
        prev = sum(closes[:k]) / k
        ema = [None] * (k - 1) + [prev]
        for c in closes[k:]:
            prev = c * mul + prev * (1 - mul)
            ema.append(prev)
        fig.add_trace(_go_c.Scatter(
            x=dates, y=ema, mode="lines", name=f"EMA{k}",
            line=dict(color="#6993ff", width=1.5),
            opacity=0.8,
        ), row=1, col=1)

    # ── Volume bars ──────────────────────────────────────────────────────────
    if has_vol:
        vol_colors = [
            "rgba(0,196,140,0.45)" if (closes[i] or 0) >= (opens[i] or 0) else "rgba(255,90,90,0.45)"
            for i in range(len(dates))
        ]
        fig.add_trace(_go_c.Bar(
            x=dates, y=volumes, name="Volume",
            marker_color=vol_colors, showlegend=False,
        ), row=2, col=1)

    # ── Level lines + pill badges ─────────────────────────────────────────────
    # yref must use the subplot axis name ("y" for row=1 in a subplot figure)
    _price_yref = "y" if rows == 1 else "y"   # row-1 axis is always "y" in make_subplots
    if levels:
        sorted_lvls = sorted(levels, key=lambda x: x[0])
        placed = []
        for price, label, bg, fg in sorted_lvls:
            y_label = price
            for py in placed:
                if abs(y_label - py) / max(abs(py), 1) < 0.022:
                    y_label = py * 1.024
            placed.append(y_label)

            # Level line — use yref not row/col (can't mix them)
            fig.add_shape(
                type="line", x0=0, x1=1, xref="paper",
                y0=price, y1=price, yref=_price_yref,
                line=dict(color=bg, width=1.5, dash="dot"),
            )
            # Pill badge outside right edge
            fig.add_annotation(
                x=1.01, xref="paper", y=y_label, yref=_price_yref,
                text=f"<b>{label}</b><br><span style='font-size:10px'>{currency}{price:,.2f}</span>",
                showarrow=False, align="left",
                font=dict(color=fg, size=11, family="Inter"),
                bgcolor=bg, borderpad=5,
                xanchor="left", yanchor="middle",
            )

    # ── Prediction zone ──────────────────────────────────────────────────────
    if zone:
        y0, y1, fill = zone
        fig.add_hrect(y0=y0, y1=y1, yref=_price_yref, fillcolor=fill, line_width=0)

    # ── Y-axis zoom ───────────────────────────────────────────────────────────
    if y_range is None and closes:
        level_vals = [p for p, *_ in (levels or [])]
        recent = closes[-30:]
        all_vals = recent + level_vals
        span = max(all_vals) - min(all_vals)
        pad = span * 0.15 if span > 0 else max(all_vals) * 0.05
        y_range = [min(all_vals) - pad, max(all_vals) + pad]

    # ── Layout — avoid passing xaxis/yaxis dicts which break subplot linking ──
    _BG = "#121214"
    fig.update_layout(
        height=h,
        title=dict(text=title, font=dict(size=12, color="#a0a0a6")) if title else {},
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#a0a0a6", size=11, family="Inter"),
        showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#222226", bordercolor="#2c2c30",
                        font=dict(color="#eaeaed", size=12)),
        margin=dict(t=32, b=20, l=62, r=130),
        xaxis_rangeslider_visible=False,
    )
    # Axis styling via update_xaxes / update_yaxes (subplot-safe)
    fig.update_xaxes(showgrid=False, zeroline=False, color="#78787e", linecolor="#2c2c30")
    fig.update_yaxes(gridcolor="#1e1e22", zeroline=False, color="#78787e")
    fig.update_yaxes(tickprefix=currency, row=1, col=1)
    if y_range:
        fig.update_yaxes(range=y_range, row=1, col=1)
    if has_vol:
        fig.update_yaxes(showticklabels=False, gridcolor="#1e1e22", row=2, col=1)
        fig.update_xaxes(showticklabels=True, row=2, col=1)

    return fig


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
        f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0 10px">'
        f'  <span style="font-size:0.77rem;color:var(--text-tertiary)">{mkt["local_time"]}</span>'
        f'  <span class="status-badge">'
        f'    <span class="status-dot {dot_cls}"></span>'
        f'    <span style="color:{"var(--profit)" if _market_open else "var(--loss)"}">{status_text}</span>'
        f'  </span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div style="border-bottom:1px solid var(--border);margin:0 0 10px"></div>',
                unsafe_allow_html=True)

    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    # Sort holdings by unrealised P&L% descending (best first)
    _pos_sorted = sorted(positions, key=lambda p: p.get("unrealised_pnl_pct") or 0, reverse=True)

    # Load today's top signals for sidebar
    from datetime import date as _date
    _today_sig_date = _today(exchange)
    _sb_signals = load_signals(exchange, _today_sig_date, 20)
    _sb_signals_sorted = sorted(_sb_signals, key=lambda s: s.get("composite_score") or 0, reverse=True)

    # Batch-fetch OHLC for all sidebar tickers in ONE call (avoids N individual yfinance requests)
    _sb_tickers = tuple(dict.fromkeys(
        [p["ticker"] for p in _pos_sorted] + [s.get("ticker","") for s in _sb_signals_sorted if s.get("ticker")]
    ))
    _sb_ohlc = fetch_batch_ohlc(_sb_tickers) if _sb_tickers else {}

    # ── HOLDINGS section ──────────────────────────────────────────────────────
    _hold_toggle = st.toggle(
        f"Holdings  ({len(_pos_sorted)})",
        value=st.session_state.sb_hold_open,
        key="sb_hold_toggle",
    )
    st.session_state.sb_hold_open = _hold_toggle

    if _hold_toggle:
        if _pos_sorted:
            for p in _pos_sorted:
                t = p["ticker"]
                cp = p.get("current_price") or 0
                pnl_pct = p.get("unrealised_pnl_pct") or 0
                pnl = p.get("unrealised_pnl") or 0
                cls = _pnl_class(pnl)
                ohlc = _sb_ohlc.get(t, {})
                o = ohlc.get("open") or 0
                h = ohlc.get("high") or 0
                l = ohlc.get("low") or 0
                c = ohlc.get("close") or cp

                is_selected = st.session_state.sidebar_sel == t
                btn_label = f"{'▶ ' if is_selected else ''}{_short(t)}   {pnl_pct:+.1f}%   {currency}{cp:,.2f}"
                if st.button(btn_label, key=f"sb_h_{t}", use_container_width=True,
                             type="primary" if is_selected else "secondary"):
                    if st.session_state.sidebar_sel == t:
                        st.session_state.sidebar_sel = None
                        st.session_state.sidebar_sel_src = None
                    else:
                        st.session_state.sidebar_sel = t
                        st.session_state.sidebar_sel_src = "holding"
                    st.rerun()

                if o or h or l or c:
                    st.markdown(
                        f'<div class="wl-ohlc" style="margin:-6px 0 6px 4px">'
                        f'O:<b>{currency}{o:,.2f}</b> '
                        f'H:<b style="color:var(--profit)">{currency}{h:,.2f}</b> '
                        f'L:<b style="color:var(--loss)">{currency}{l:,.2f}</b> '
                        f'C:<b>{currency}{c:,.2f}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown('<div style="font-size:0.76rem;color:var(--text-tertiary);padding:6px 2px">No active positions</div>',
                        unsafe_allow_html=True)

    st.markdown('<div style="border-bottom:1px solid var(--border);margin:8px 0"></div>',
                unsafe_allow_html=True)

    # ── SIGNALS section ───────────────────────────────────────────────────────
    _sig_toggle = st.toggle(
        f"Signals  ({len(_sb_signals_sorted)})",
        value=st.session_state.sb_sig_open,
        key="sb_sig_toggle",
    )
    st.session_state.sb_sig_open = _sig_toggle

    if _sig_toggle:
        if _sb_signals_sorted:
            for sig in _sb_signals_sorted:
                t = sig.get("ticker", "")
                score = sig.get("composite_score") or 0
                direction = sig.get("direction") or "long"
                sz = sig.get("position_size_aud") or 0
                ohlc = _sb_ohlc.get(t, {})
                o = ohlc.get("open") or 0
                h = ohlc.get("high") or 0
                l = ohlc.get("low") or 0
                c = ohlc.get("close") or sig.get("entry_price") or 0
                dir_icon = "▲" if direction == "long" else "▼"
                score_chip = "high" if score >= 70 else ("low" if score < 60 else "")
                actionable = sz > 0

                is_selected = st.session_state.sidebar_sel == t
                btn_label = f"{'▶ ' if is_selected else ''}{dir_icon} {_short(t)}   {score:.0f}"
                btn_style = "primary" if is_selected else ("secondary" if actionable else "secondary")
                if st.button(btn_label, key=f"sb_s_{t}", use_container_width=True, type=btn_style):
                    if st.session_state.sidebar_sel == t:
                        st.session_state.sidebar_sel = None
                        st.session_state.sidebar_sel_src = None
                    else:
                        st.session_state.sidebar_sel = t
                        st.session_state.sidebar_sel_src = "signal"
                    st.rerun()

                if o or h or l or c:
                    st.markdown(
                        f'<div class="wl-ohlc" style="margin:-6px 0 6px 4px">'
                        f'O:<b>{currency}{o:,.2f}</b> '
                        f'H:<b style="color:var(--profit)">{currency}{h:,.2f}</b> '
                        f'L:<b style="color:var(--loss)">{currency}{l:,.2f}</b> '
                        f'C:<b>{currency}{c:,.2f}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown('<div style="font-size:0.76rem;color:var(--text-tertiary);padding:6px 2px">No signals for today</div>',
                        unsafe_allow_html=True)

    st.markdown('<div style="border-bottom:1px solid var(--border);margin:8px 0"></div>',
                unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    _phase = int(os.getenv("TRADING_PHASE", 1))
    _capital = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
    mode_map = {1: ("Paper", "var(--warning)"), 2: ("IBKR Paper", "var(--accent)"), 3: ("LIVE", "var(--profit)")}
    mode_text, mode_color = mode_map.get(_phase, ("Paper", "var(--warning)"))

    st.markdown(
        f'<div style="font-size:0.73rem;color:var(--text-tertiary);padding:4px 0 6px;line-height:1.9">'
        f'  Mode: <span style="color:{mode_color};font-weight:600">{mode_text}</span> &nbsp;·&nbsp;'
        f'  {currency}{_capital:,.0f}'
        f'  <br>Source: <span style="color:var(--text-secondary);font-weight:500">{"Supabase" if _use_supabase() else "Local DB"}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("Refresh", use_container_width=True, type="secondary"):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TICKER INSPECTOR — full-screen overlay replacing all tabs when a ticker is selected
# ══════════════════════════════════════════════════════════════════════════════

def _render_ticker_inspector(ticker: str, positions: list, currency: str, exchange: str):
    """
    Full-screen stock inspector shown instead of the normal tabs.
    Gathers data from all tabs (signal, position, radar, trade history) for one ticker.
    """
    from dashboard.data import get_strategy_radar as _get_radar, get_trades as _get_trades

    # ── Data gathering ───────────────────────────────────────────────────────
    pos     = next((p for p in positions if p["ticker"] == ticker), None)
    all_sig = load_signals(exchange, _today(exchange), 200)
    sig     = next((s for s in all_sig if s.get("ticker") == ticker), None)

    all_radar = _get_radar(exchange)
    radar     = next((r for r in all_radar if r["ticker"] == ticker), None)

    all_trades = _get_trades(exchange, days=730)
    hist_trades = [t for t in all_trades if t.get("ticker") == ticker]

    ohlc  = fetch_today_ohlc(ticker)
    ohlcv = fetch_ohlcv(ticker, days=120)

    short     = _short(ticker)
    cp        = (pos or {}).get("current_price") or (sig or {}).get("entry_price") or 0
    direction = (sig or {}).get("direction") or (pos or {}).get("direction") or (radar or {}).get("direction") or "long"
    dir_icon  = "▲ LONG" if direction == "long" else "▼ SHORT"
    dir_color = "var(--profit)" if direction == "long" else "var(--loss)"

    # ── Close button + header ────────────────────────────────────────────────
    close_col, title_col = st.columns([1, 11])
    with close_col:
        if st.button("✕  Back", key="insp_close"):
            st.session_state.sidebar_sel = None
            st.session_state.sidebar_sel_src = None
            st.rerun()

    # Status badges
    badge_parts = []
    if sig:
        score = sig.get("composite_score", 0) or 0
        score_color = "var(--profit)" if score >= 70 else ("var(--warning)" if score >= 60 else "var(--loss)")
        score_bg    = "var(--profit-dim)" if score >= 70 else ("var(--warning-dim)" if score >= 60 else "var(--loss-dim)")
        badge_parts.append(
            f'<span style="background:{score_bg};color:{score_color};padding:4px 12px;'
            f'border-radius:var(--radius-sm);font-size:var(--text-sm);font-weight:700;'
            f'font-variant-numeric:tabular-nums">{score:.0f}/100</span>'
        )
    if radar:
        if radar.get("firing"):
            badge_parts.append(
                '<span style="background:var(--profit-dim);color:var(--profit);padding:4px 12px;'
                'border-radius:var(--radius-sm);font-size:var(--text-xs);font-weight:700;'
                'display:inline-flex;align-items:center;gap:6px">'
                '<span style="width:7px;height:7px;border-radius:50%;background:var(--profit);'
                'animation:radar-pulse 1.6s ease-out infinite;display:inline-block"></span>FIRING</span>'
            )
        elif radar.get("near_miss"):
            badge_parts.append(
                '<span style="background:var(--gold-dim);color:var(--gold);padding:4px 12px;'
                'border-radius:var(--radius-sm);font-size:var(--text-xs);font-weight:700">NEAR MISS</span>'
            )
        elif radar.get("validated"):
            badge_parts.append(
                '<span style="background:var(--accent-dim);color:var(--accent);padding:4px 12px;'
                'border-radius:var(--radius-sm);font-size:var(--text-xs);font-weight:700">VALIDATED</span>'
            )
    if pos:
        pnl_pct = pos.get("unrealised_pnl_pct") or 0
        pos_color = "var(--profit)" if pnl_pct >= 0 else "var(--loss)"
        pos_bg    = "var(--profit-dim)" if pnl_pct >= 0 else "var(--loss-dim)"
        badge_parts.append(
            f'<span style="background:{pos_bg};color:{pos_color};padding:4px 12px;'
            f'border-radius:var(--radius-sm);font-size:var(--text-xs);font-weight:700">'
            f'IN PORTFOLIO &nbsp;{pnl_pct:+.1f}%</span>'
        )

    badges_html = " ".join(badge_parts)
    st.markdown(
        f'<div class="insp-header">'
        f'  <div class="insp-title">'
        f'    <span class="insp-ticker">{short}</span>'
        f'    <span style="color:{dir_color};font-weight:700;font-size:var(--text-sm)">{dir_icon}</span>'
        f'    <span class="insp-code">{ticker}</span>'
        f'    <span class="insp-price">{currency}{cp:,.2f}</span>'
        f'  </div>'
        f'  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">{badges_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── OHLC strip ───────────────────────────────────────────────────────────
    o = ohlc.get("open") or 0
    h_price = ohlc.get("high") or 0
    l_price = ohlc.get("low") or 0
    c_price = ohlc.get("close") or cp
    chg_pct = ((c_price - o) / o * 100) if o else 0
    chg_col = "var(--profit)" if chg_pct >= 0 else "var(--loss)"
    if o or h_price or l_price or c_price:
        st.markdown(
            f'<div class="insp-ohlc">'
            f'  <div class="insp-ohlc-cell"><div class="insp-ohlc-label">Open</div>'
            f'    <div class="insp-ohlc-val">{currency}{o:,.2f}</div></div>'
            f'  <div class="insp-ohlc-cell"><div class="insp-ohlc-label">High</div>'
            f'    <div class="insp-ohlc-val" style="color:var(--profit)">{currency}{h_price:,.2f}</div></div>'
            f'  <div class="insp-ohlc-cell"><div class="insp-ohlc-label">Low</div>'
            f'    <div class="insp-ohlc-val" style="color:var(--loss)">{currency}{l_price:,.2f}</div></div>'
            f'  <div class="insp-ohlc-cell"><div class="insp-ohlc-label">Close</div>'
            f'    <div class="insp-ohlc-val">{currency}{c_price:,.2f}</div></div>'
            f'  <div class="insp-ohlc-cell"><div class="insp-ohlc-label">Day chg</div>'
            f'    <div class="insp-ohlc-val" style="color:{chg_col}">{chg_pct:+.2f}%</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Chart (full width) — combined price + prediction levels ─────────────
    # Pre-parse OHLCV once; used by both this chart and the verdict text below.
    _pred_src = sig or radar
    _pred_ep  = (_pred_src or {}).get("entry_price")
    _pred_tp  = (_pred_src or {}).get("target_price")
    _pred_sp  = (_pred_src or {}).get("stop_loss_price")

    _dates2 = _closes2 = []
    if ohlcv:
        _dates2  = [r.get("date") or r.get("Date") for r in ohlcv]
        _closes2 = [r.get("close") or r.get("Close") or 0 for r in ohlcv]
        _opens2  = [r.get("open")  or r.get("Open")  or c for r, c in zip(ohlcv, _closes2)]
        _highs2  = [r.get("high")  or r.get("High")  or c for r, c in zip(ohlcv, _closes2)]
        _lows2   = [r.get("low")   or r.get("Low")   or c for r, c in zip(ohlcv, _closes2)]
        _vols2   = [r.get("volume") or r.get("Volume") or 0 for r in ohlcv]

        _pred_levels = []
        if _pred_ep: _pred_levels.append((_pred_ep, "Entry",  "#3c3c44", "#eaeaed"))
        if _pred_tp: _pred_levels.append((_pred_tp, "Target", "#00c48c", "#ffffff"))
        if _pred_sp: _pred_levels.append((_pred_sp, "Stop",   "#ff5a5a", "#ffffff"))

        _pred_zone = None
        if _pred_ep and _pred_tp:
            _zc = "rgba(0,196,140,0.08)" if direction == "long" else "rgba(255,90,90,0.08)"
            _pred_zone = (min(_pred_ep, _pred_tp), max(_pred_ep, _pred_tp), _zc)

        fig = _build_candle_chart(
            _dates2, _opens2, _highs2, _lows2, _closes2, volumes=_vols2,
            levels=_pred_levels, zone=_pred_zone,
            currency=currency, title="Strategy Prediction vs Real-time Price", h=400,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Direction verdict below chart
        if _closes2 and _pred_ep:
            _latest = _closes2[-1]
            if direction == "long":
                _ok  = _latest > _pred_ep
                _txt = (f"Price {currency}{_latest:.2f} is {'above' if _ok else 'below'} entry"
                        f" — moving {'with' if _ok else 'against'} the long prediction.")
            else:
                _ok  = _latest < _pred_ep
                _txt = (f"Price {currency}{_latest:.2f} is {'below' if _ok else 'above'} entry"
                        f" — moving {'with' if _ok else 'against'} the short prediction.")
            st.markdown(
                f'<div style="font-size:0.85rem;color:{"var(--profit)" if _ok else "var(--loss)"};'
                f'font-weight:500;padding:4px 0 16px">{_txt}</div>',
                unsafe_allow_html=True,
            )

    # ── Three info columns ───────────────────────────────────────────────────
    col_sig, col_pos, col_radar = st.columns(3)

    # Signal column
    with col_sig:
        st.markdown('<div class="insp-section">Signal</div>', unsafe_allow_html=True)
        if sig:
            score = sig.get("composite_score", 0) or 0
            entry = sig.get("entry_price", 0) or 0
            target = sig.get("target_price", 0) or 0
            stop = sig.get("stop_loss_price", 0) or 0
            upside = ((target - entry) / entry * 100) if entry and target else 0
            risk   = ((entry - stop)  / entry * 100) if entry and stop  else 0
            rr     = (upside / risk) if risk > 0 else 0
            rr_col = "var(--profit)" if rr >= 1.5 else ("var(--warning)" if rr >= 1.0 else "var(--loss)")
            strat  = (sig.get("strategy_name") or "—").replace("_", " ")

            # Levels strip
            st.markdown(
                f'<div class="insp-levels">'
                f'  <div class="insp-level-cell">'
                f'    <div class="insp-level-label">Entry</div>'
                f'    <div class="insp-level-val" style="color:var(--text-primary)">{currency}{entry:,.2f}</div></div>'
                f'  <div class="insp-level-cell">'
                f'    <div class="insp-level-label">Target <span style="color:var(--profit)">+{upside:.1f}%</span></div>'
                f'    <div class="insp-level-val" style="color:var(--profit)">{currency}{target:,.2f}</div></div>'
                f'  <div class="insp-level-cell">'
                f'    <div class="insp-level-label">Stop <span style="color:var(--loss)">-{risk:.1f}%</span></div>'
                f'    <div class="insp-level-val" style="color:var(--loss)">{currency}{stop:,.2f}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            rows = [
                ("R:R", f'<span style="color:{rr_col};font-weight:700">{rr:.1f}</span>'),
                ("Strategy", strat),
                ("Date", str(sig.get("date") or "—")),
                ("Regime", "Risk-ON" if sig.get("regime_ok") else ("Risk-OFF" if sig.get("regime_ok") is False else "—")),
                ("Strategy fired", "Yes" if sig.get("strategy_fires") else "No"),
            ]
            rows_html = "".join(
                f'<div class="insp-stat-row">'
                f'  <span class="insp-stat-label">{k}</span>'
                f'  <span class="insp-stat-val">{v}</span>'
                f'</div>' for k, v in rows
            )
            st.markdown(f'<div style="margin-top:12px">{rows_html}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--text-tertiary);font-size:var(--text-sm);padding:8px 0">No signal today</div>', unsafe_allow_html=True)

    # Position column
    with col_pos:
        st.markdown('<div class="insp-section">Position</div>', unsafe_allow_html=True)
        if pos:
            pnl      = pos.get("unrealised_pnl") or 0
            pnl_pct  = pos.get("unrealised_pnl_pct") or 0
            day_pnl  = pos.get("day_pnl") or 0
            day_pct  = pos.get("day_pnl_pct") or 0
            invested = pos.get("position_size_aud") or pos.get("invested") or 0
            cur_val  = pos.get("current_value") or 0
            pnl_col  = "var(--profit)" if pnl >= 0 else "var(--loss)"
            day_col  = "var(--profit)" if day_pnl >= 0 else "var(--loss)"

            rows = [
                ("Entry date",     str(pos.get("entry_date") or "—")),
                ("Days held",      str(pos.get("days_held") or 0)),
                ("Shares",         f"{pos.get('shares', 0):,.0f}"),
                ("Entry price",    f"{currency}{pos.get('entry_price', 0):,.2f}"),
                ("Invested",       f"{currency}{invested:,.2f}"),
                ("Current value",  f"{currency}{cur_val:,.2f}"),
                ("Unrealised P&L", f'<span style="color:{pnl_col}">{_pnl_sign(pnl, currency)} ({pnl_pct:+.2f}%)</span>'),
                ("Day P&L",        f'<span style="color:{day_col}">{_pnl_sign(day_pnl, currency)} ({day_pct:+.2f}%)</span>' if day_pnl else "—"),
            ]
            rows_html = "".join(
                f'<div class="insp-stat-row">'
                f'  <span class="insp-stat-label">{k}</span>'
                f'  <span class="insp-stat-val">{v}</span>'
                f'</div>' for k, v in rows
            )
            st.markdown(rows_html, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--text-tertiary);font-size:var(--text-sm);padding:8px 0">Not in portfolio</div>', unsafe_allow_html=True)

    # Radar column
    with col_radar:
        st.markdown('<div class="insp-section">Strategy Radar</div>', unsafe_allow_html=True)
        if radar:
            strat_name = (radar.get("strategy_name") or "—").replace("_", " ")
            status_str = ("Firing" if radar.get("firing") else
                          ("Near Miss" if radar.get("near_miss") else
                           ("Validated" if radar.get("validated") else "Watching")))
            rows = [
                ("Strategy",    strat_name),
                ("Status",      status_str),
                ("Direction",   (radar.get("direction") or "long").upper()),
                ("Fwd PF",      f"{radar.get('fw_profit_factor', 0) or 0:.2f}"),
                ("Fwd win rate",f"{radar.get('fw_win_rate', 0) or 0:.1f}%"),
                ("Fwd trades",  str(radar.get("fw_trades") or "—")),
                ("BT win rate", f"{radar.get('bt_win_rate', 0) or 0:.1f}%"),
                ("BT profit factor", f"{radar.get('bt_profit_factor', 0) or 0:.2f}"),
                ("Rank score",  f"{radar.get('rank_score', 0) or 0:.2f}"),
            ]
            rows_html = "".join(
                f'<div class="insp-stat-row">'
                f'  <span class="insp-stat-label">{k}</span>'
                f'  <span class="insp-stat-val">{v}</span>'
                f'</div>' for k, v in rows
            )
            st.markdown(rows_html, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--text-tertiary);font-size:var(--text-sm);padding:8px 0">No radar assignment</div>', unsafe_allow_html=True)

    # ── Sub-scores row ───────────────────────────────────────────────────────
    if sig:
        score_items = [
            ("Sentiment",    sig.get("sentiment_score")   or 0),
            ("Fundamental",  sig.get("fundamental_score") or 0),
            ("Technical",    sig.get("technical_score")   or 0),
            ("Insider",      sig.get("insider_score")     or 0),
            ("Composite",    sig.get("composite_score")   or 0),
        ]
        pills_html = "".join(
            f'<div class="insp-score-pill">'
            f'  <div class="pill-label">{lbl}</div>'
            f'  <div class="pill-val" style="color:{"var(--profit)" if v >= 65 else ("var(--warning)" if v >= 50 else "var(--loss)")}">{v:.0f}</div>'
            f'</div>'
            for lbl, v in score_items
        )
        st.markdown(
            f'<div class="insp-scores">{pills_html}</div>',
            unsafe_allow_html=True,
        )

    # ── Trade history ────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="kite-section" style="margin-top:28px">Trade History'
        f' <span class="badge-count">{len(hist_trades)} closed trades</span></div>',
        unsafe_allow_html=True,
    )
    if hist_trades:
        def _clean_reason(r):
            return str(r or "—").replace("_", " ").title()
        rows_html = "".join(
            f'<tr>'
            f'  <td style="text-align:left;color:var(--text-secondary)">{str(t.get("exit_date",""))[:10]}</td>'
            f'  <td style="color:var(--profit)" title="Profit">{_pnl_sign(t.get("realised_pnl") or 0, currency)}</td>'
            f'  <td style="color:{"var(--profit)" if (t.get("realised_pnl_pct") or 0) >= 0 else "var(--loss)"}">'
            f'    {(t.get("realised_pnl_pct") or 0):+.1f}%</td>'
            f'  <td>{t.get("shares","—")}</td>'
            f'  <td>{currency}{t.get("entry_price", 0):,.2f}</td>'
            f'  <td>{currency}{t.get("exit_price", 0):,.2f}</td>'
            f'  <td style="text-align:left;color:var(--text-tertiary)">{_clean_reason(t.get("exit_reason"))}</td>'
            f'</tr>'
            for t in hist_trades
        )
        st.markdown(
            f'<table class="insp-hist-table">'
            f'<thead><tr>'
            f'  <th style="text-align:left">Exit date</th>'
            f'  <th>P&L</th><th>Return</th><th>Shares</th>'
            f'  <th>Entry</th><th>Exit</th>'
            f'  <th style="text-align:left">Reason</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )


if st.session_state.sidebar_sel:
    _render_ticker_inspector(
        st.session_state.sidebar_sel,
        positions if "positions" in dir() else [],
        currency if "currency" in dir() else "$",
        exchange if "exchange" in dir() else "asx",
    )
    st.stop()  # Nothing else renders — inspector replaces all tabs


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ══════════════════════════════════════════════════════════════════════════════

tab_dash, tab_holdings, tab_signals, tab_radar, tab_charts, tab_scanner, tab_history, tab_backtest, tab_research = st.tabs([
    "Dashboard", "Holdings", "Signals", "Radar", "Charts", "Scanner", "Trade History", "Backtest", "Research",
])


# ── TAB 1: Dashboard ─────────────────────────────────────────────────────────
with tab_dash:
    import pandas as pd

    total_invested = portfolio.get("total_invested", 0) or 0
    total_value = portfolio.get("total_current_value", 0) or 0
    unreal_pnl   = portfolio.get("total_unrealised_pnl", 0) or 0
    realised_pnl = portfolio.get("total_realised_pnl", 0) or 0
    total_pnl    = portfolio.get("total_pnl", 0) or 0
    unreal_pct    = (unreal_pnl / total_invested * 100) if total_invested else 0
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    regime = load_regime(exchange)
    pnl_cls = _pnl_class(total_pnl)
    regime_ok = regime.get("regime_ok")

    _pill = (
        'style="margin-left:8px;font-size:var(--text-2xs);font-weight:500;'
        'text-transform:none;letter-spacing:0;color:var(--text-tertiary);'
        'background:var(--bg-tertiary);padding:2px 7px;border-radius:var(--radius-sm)"'
    )
    st.markdown(
        f'<div class="pnl-grid">'
        f'  <div class="pnl-card">'
        f'    <div class="pnl-label">Unrealised P&L'
        f'      <span {_pill}>Open positions</span></div>'
        f'    <div class="pnl-value {_pnl_class(unreal_pnl)}">{_pnl_sign(unreal_pnl, currency)}</div>'
        f'    <div class="pnl-sub {_pnl_class(unreal_pnl)}">{_pnl_pct(unreal_pct)}'
        f'      &nbsp;<span style="color:var(--text-tertiary);font-weight:400">from entry · {len(positions)} holdings</span></div>'
        f'  </div>'
        f'  <div class="pnl-card">'
        f'    <div class="pnl-label">Realised P&L'
        f'      <span {_pill}>Closed trades</span></div>'
        f'    <div class="pnl-value {_pnl_class(realised_pnl)}">{_pnl_sign(realised_pnl, currency)}</div>'
        f'    <div class="pnl-sub {_pnl_class(realised_pnl)}">'
        f'      <span style="color:var(--text-tertiary);font-weight:400">all-time · exited positions</span></div>'
        f'  </div>'
        f'  <div class="pnl-card">'
        f'    <div class="pnl-label">Total P&L'
        f'      <span {_pill}>Unrealised + Realised</span></div>'
        f'    <div class="pnl-value {pnl_cls}">{_pnl_sign(total_pnl, currency)}</div>'
        f'    <div class="pnl-sub {pnl_cls}">{_pnl_pct(total_pnl_pct)}'
        f'      &nbsp;<span style="color:var(--text-tertiary);font-weight:400">'
        f'      {len(positions)} open + all closed trades</span></div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if True:  # regime stats block
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

    # Market overview chart with free-form period filter
    pcol1, pcol2 = st.columns([2, 1])
    with pcol1:
        dash_period = st.selectbox("P&L Period", ["7 days", "30 days", "60 days", "90 days", "180 days", "1 year", "Custom"],
                                   index=3, key="dash_pnl_period")
    with pcol2:
        dash_custom = st.number_input("Custom days", min_value=1, max_value=3650, value=90, step=1,
                                      key="dash_custom_days", label_visibility="visible")
    _period_map = {"7 days": 7, "30 days": 30, "60 days": 60, "90 days": 90,
                   "180 days": 180, "1 year": 365, "Custom": int(dash_custom)}
    dash_days = _period_map[dash_period]
    st.markdown(f'<div class="kite-section">Realized P&L — last {dash_days} days</div>', unsafe_allow_html=True)

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
        # ── Filters ──────────────────────────────────────────────────────────
        hf1, hf2, hf3 = st.columns([1, 1, 1])
        with hf1:
            hold_sort = st.selectbox("Sort by", ["Default", "P&L ↑", "P&L ↓", "P&L % ↑", "Value ↓", "Days held ↓"],
                                     index=0, key="hold_sort")
        with hf2:
            all_entry_dates = sorted({str(p.get("entry_date", "")) for p in positions if p.get("entry_date")})
            hold_date_from = st.date_input("Entered from", value=None, key="hold_date_from")
        with hf3:
            hold_date_to = st.date_input("Entered to", value=None, key="hold_date_to")

        # apply date filter
        _pos = positions
        if hold_date_from:
            _pos = [p for p in _pos if p.get("entry_date") and str(p["entry_date"]) >= str(hold_date_from)]
        if hold_date_to:
            _pos = [p for p in _pos if p.get("entry_date") and str(p["entry_date"]) <= str(hold_date_to)]

        if hold_sort == "P&L ↑":
            _pos = sorted(_pos, key=lambda x: x.get("unrealised_pnl", 0), reverse=True)
        elif hold_sort == "P&L ↓":
            _pos = sorted(_pos, key=lambda x: x.get("unrealised_pnl", 0))
        elif hold_sort == "P&L % ↑":
            _pos = sorted(_pos, key=lambda x: x.get("unrealised_pnl_pct", 0), reverse=True)
        elif hold_sort == "Value ↓":
            _pos = sorted(_pos, key=lambda x: x.get("current_value", 0), reverse=True)
        elif hold_sort == "Days held ↓":
            _pos = sorted(_pos, key=lambda x: x.get("days_held", 0), reverse=True)

        # Derived totals for filtered set
        _total_invested  = sum(p.get("invested", 0) or 0 for p in _pos)
        _total_value     = sum(p.get("current_value", 0) or 0 for p in _pos)
        _unrealised_pnl  = sum(p.get("unrealised_pnl", 0) or 0 for p in _pos)
        _day_pnl         = sum(p.get("day_pnl", 0) or 0 for p in _pos)
        _day_pnl_pct     = (_day_pnl / _total_value * 100) if _total_value else 0
        _unreal_pct      = (_unrealised_pnl / _total_invested * 100) if _total_invested else 0

        from dashboard.data import _realised_pnl_totals as _rpt
        _real_all, _real_today = _rpt(exchange)

        st.markdown(
            f'<div class="hold-summary">'
            f'  <div class="hold-block">'
            f'    <div class="hb-title">Unrealised P&L'
            f'      <span style="margin-left:6px;font-size:0.65rem;font-weight:500;font-style:italic;'
            f'      color:var(--text-tertiary);text-transform:none;letter-spacing:0">'
            f'      Open positions · from entry</span></div>'
            f'    <div class="hb-row"><span class="hb-key">Unrealised gain/loss</span>'
            f'      <span class="hb-val {_pnl_class(_unrealised_pnl)}">{_pnl_sign(_unrealised_pnl, currency)} ({_pnl_pct(_unreal_pct)})</span></div>'
            f'    <div class="hb-row"><span class="hb-key">Positions shown</span>'
            f'      <span class="hb-val">{len(_pos)} of {len(positions)}</span></div>'
            f'    <div class="hb-row"><span class="hb-key">Current value</span>'
            f'      <span class="hb-val">{currency}{_total_value:,.2f}</span></div>'
            f'    <div class="hb-row"><span class="hb-key">Intraday move</span>'
            f'      <span class="hb-val {_pnl_class(_day_pnl)}">{_pnl_sign(_day_pnl, currency)} ({_pnl_pct(_day_pnl_pct)})</span></div>'
            f'  </div>'
            f'  <div class="hold-block">'
            f'    <div class="hb-title">Total P&L'
            f'      <span style="margin-left:6px;font-size:0.65rem;font-weight:500;font-style:italic;'
            f'      color:var(--text-tertiary);text-transform:none;letter-spacing:0">'
            f'      Unrealised + Realised (all-time)</span></div>'
            f'    <div class="hb-row"><span class="hb-key">Unrealised (open)</span>'
            f'      <span class="hb-val {_pnl_class(_unrealised_pnl)}">{_pnl_sign(_unrealised_pnl, currency)}</span></div>'
            f'    <div class="hb-row"><span class="hb-key">Realised (closed trades)</span>'
            f'      <span class="hb-val {_pnl_class(_real_all)}">{_pnl_sign(_real_all, currency)}</span></div>'
            f'    <div class="hb-row" style="border-top:1px solid var(--border);padding-top:6px;margin-top:2px">'
            f'      <span class="hb-key" style="font-weight:600;color:var(--text-secondary)">Combined Total</span>'
            f'      <span class="hb-val {_pnl_class(total_pnl)}" style="font-size:1rem">{_pnl_sign(total_pnl, currency)}</span></div>'
            f'    <div class="hb-row"><span class="hb-key">W / L</span>'
            f'      <span class="hb-val">{portfolio.get("winners",0)}W / {portfolio.get("losers",0)}L</span></div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        table_html = '''<table class="kite-table"><thead><tr>
            <th>Instrument</th><th>Qty.</th><th>Avg. cost</th><th>LTP</th>
            <th>Invested</th><th>Cur. val</th><th>Day P&L</th><th>P&L</th><th>Net chg.</th><th>Days</th>
        </tr></thead><tbody>'''

        for p in _pos:
            t = p["ticker"]
            shares = p.get("shares") or 0
            entry = p.get("entry_price") or 0
            cp = p.get("current_price") or 0
            invested = p.get("invested") or 0
            cur_val = p.get("current_value") or 0
            pnl = p.get("unrealised_pnl") or 0
            pnl_pct = p.get("unrealised_pnl_pct") or 0
            dpnl = p.get("day_pnl") or 0
            days = p.get("days_held") or 0
            cls = _pnl_class(pnl)
            dcls = _pnl_class(dpnl)
            row_cls = "loss-row" if pnl < 0 else ""
            tv = _tv_url(t)

            table_html += f'''<tr class="{row_cls}">
                <td><a href="{tv}" target="_blank" class="ticker-link">{_short(t)}</a></td>
                <td>{shares:,.0f}</td>
                <td>{entry:,.2f}</td>
                <td>{cp:,.2f}</td>
                <td>{currency}{invested:,.2f}</td>
                <td>{currency}{cur_val:,.2f}</td>
                <td class="{dcls}">{_pnl_sign(dpnl, currency)}</td>
                <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                <td class="{cls}">{_pnl_pct(pnl_pct)}</td>
                <td>{days}</td>
            </tr>'''

        table_html += f'''<tr class="total-row">
            <td>Total ({len(_pos)})</td><td></td><td></td><td></td>
            <td>{currency}{_total_invested:,.2f}</td>
            <td>{currency}{_total_value:,.2f}</td>
            <td class="{_pnl_class(_day_pnl)}">{_pnl_sign(_day_pnl, currency)}</td>
            <td class="{_pnl_class(_unrealised_pnl)}">{_pnl_sign(_unrealised_pnl, currency)}</td>
            <td class="{_pnl_class(_unrealised_pnl)}">{_pnl_pct(_unreal_pct)}</td>
            <td></td>
        </tr>'''

        table_html += '</tbody></table>'
        st.markdown('<div class="kite-table-wrap">' + table_html + '</div>', unsafe_allow_html=True)

        # Allocation bar + legend
        if _total_value > 0:
            bar_html = '<div class="alloc-bar" style="margin-top:24px">'
            legend_html = '<div class="alloc-legend">'
            for i, p in enumerate(_pos):
                pct = (p.get("current_value", 0) / _total_value * 100)
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
        sorted_pos = sorted(_pos, key=lambda x: x.get("unrealised_pnl", 0))
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
    sc1, sc2, sc3, sc4, sc5 = st.columns([1.2, 0.8, 0.8, 0.8, 1.2])
    with sc1:
        sig_date = st.date_input("Signal Date", value=_today(exchange), key="sig_date_pick")
    with sc2:
        sig_min_score = st.number_input("Min Score", min_value=0, max_value=100, value=0, step=5, key="sig_min")
    with sc3:
        sig_count = st.selectbox("Show Top", [10, 20, 50, 100], index=1, key="sig_count")
    with sc4:
        sig_dir_filter = st.selectbox("Direction", ["All", "Long", "Short"], key="sig_dir")
    with sc5:
        sig_sort = st.selectbox("Sort by", ["Score ↓", "Score ↑", "R:R ↓", "Upside ↓", "Entry price ↓", "Entry price ↑"],
                                key="sig_sort")

    signals = load_signals(exchange, sig_date, sig_count)

    # Direction filter
    if sig_dir_filter == "Long":
        signals = [s for s in signals if (s.get("direction") or "long") == "long"]
    elif sig_dir_filter == "Short":
        signals = [s for s in signals if (s.get("direction") or "long") == "short"]

    if sig_min_score > 0:
        signals = [s for s in signals if (s.get("composite_score", 0) or 0) >= sig_min_score]

    # Sort
    def _rr(s):
        e = s.get("entry_price") or 0; tgt = s.get("target_price") or 0; stp = s.get("stop_loss_price") or 0
        up = abs(tgt - e) / e * 100 if e and tgt else 0
        dn = abs(e - stp) / e * 100 if e and stp else 0
        return up / dn if dn else 0

    if sig_sort == "Score ↑":
        signals = sorted(signals, key=lambda s: s.get("composite_score", 0) or 0)
    elif sig_sort == "R:R ↓":
        signals = sorted(signals, key=_rr, reverse=True)
    elif sig_sort == "Upside ↓":
        signals = sorted(signals, key=lambda s: abs((s.get("target_price", 0) or 0) - (s.get("entry_price", 0) or 0)), reverse=True)
    elif sig_sort == "Entry price ↓":
        signals = sorted(signals, key=lambda s: s.get("entry_price", 0) or 0, reverse=True)
    elif sig_sort == "Entry price ↑":
        signals = sorted(signals, key=lambda s: s.get("entry_price", 0) or 0)
    else:
        signals = sorted(signals, key=lambda s: s.get("composite_score", 0) or 0, reverse=True)

    # Split portfolio into: bought on signal date vs already held before it
    _sig_date_str = str(sig_date)
    bought_today   = {p["ticker"] for p in positions if str(p.get("entry_date", "")) == _sig_date_str}
    holding_before = {p["ticker"] for p in positions if str(p.get("entry_date", "")) != _sig_date_str and p["ticker"] not in bought_today}
    bought_tickers = bought_today | holding_before  # all in portfolio (for count badge)

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
        buy_count = sum(1 for s in signals if (s.get("position_size_aud", 0) or 0) > 0)
        short_count = sum(1 for s in signals if (s.get("direction") or "long") == "short")
        st.markdown(
            f'<div class="kite-section">Signals for {sig_date}'
            f' <span class="badge-count">{len(signals)} total</span>'
            f' <span class="badge-count" style="background:var(--profit-dim);color:var(--profit)">{buy_count} buy</span>'
            f' <span class="badge-count" style="background:var(--loss-dim);color:var(--loss)">{short_count} short</span>'
            f' <span class="badge-count" style="background:var(--profit-dim);color:var(--profit)">{len(bought_today & {s.get("ticker","") for s in signals})} bought today</span>'
            f' <span class="badge-count" style="background:rgba(105,147,255,0.15);color:#6993ff">{len(holding_before & {s.get("ticker","") for s in signals})} holding</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        cols = st.columns(2)
        for i, sig in enumerate(signals):
            with cols[i % 2]:
                t = sig.get("ticker", "")
                score = sig.get("composite_score", 0) or 0
                entry = sig.get("entry_price", 0) or 0
                target = sig.get("target_price", 0) or 0
                stop = sig.get("stop_loss_price", 0) or 0
                direction = sig.get("direction") or "long"
                tv = _tv_url(t)
                is_bought_today   = t in bought_today
                is_holding_before = t in holding_before

                badge_cls = "high" if score >= 70 else ("mid" if score >= 60 else "low")

                if direction == "long":
                    upside = ((target - entry) / entry * 100) if entry and target else 0
                    risk   = ((entry - stop)  / entry * 100) if entry and stop  else 0
                else:
                    upside = ((entry - target) / entry * 100) if entry and target else 0
                    risk   = ((stop - entry)   / entry * 100) if entry and stop  else 0

                rr_ratio = (upside / risk) if risk > 0 else 0
                rr_color = ("var(--profit)" if rr_ratio >= 1.5
                            else ("var(--warning)" if rr_ratio >= 1.0 else "var(--loss)"))

                strat = (sig.get("strategy_name") or "").replace("_", " ")
                sent = sig.get("sentiment_score") or 0
                fund = sig.get("fundamental_score") or 0
                tech = sig.get("technical_score") or 0
                ins  = sig.get("insider_score") or 0
                regime_ok = sig.get("regime_ok")

                # Hover tooltip details
                regime_str = "Risk-ON" if regime_ok else ("Risk-OFF" if regime_ok is False else "—")
                strat_fires = sig.get("strategy_fires", False)
                tooltip = (
                    f'<div class="sig-tooltip">'
                    f'  <h5>{_short(t)} — Signal Details</h5>'
                    f'  <div class="tt-row"><span class="tt-label">Strategy</span><span class="tt-val">{strat or "—"}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Direction</span><span class="tt-val">{direction.upper()}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Composite score</span><span class="tt-val">{score:.0f}/100</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Sentiment</span><span class="tt-val">{sent:.0f}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Fundamental</span><span class="tt-val">{fund:.0f}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Technical</span><span class="tt-val">{tech:.0f}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Insider</span><span class="tt-val">{ins:.0f}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Market regime</span><span class="tt-val">{regime_str}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Strategy fired</span><span class="tt-val">{"Yes" if strat_fires else "No"}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">R:R</span><span class="tt-val">{rr_ratio:.2f}</span></div>'
                    f'  <div class="tt-row"><span class="tt-label">Portfolio status</span><span class="tt-val">{"Bought today" if is_bought_today else ("Already holding" if is_holding_before else "Not held")}</span></div>'
                    f'</div>'
                )

                if is_bought_today:
                    card_cls = "sig-card is-bought"
                    bought_badge = '<span class="bought-badge">Bought</span>'
                elif is_holding_before:
                    card_cls = "sig-card is-holding"
                    bought_badge = '<span class="holding-badge">Holding</span>'
                else:
                    card_cls = "sig-card"
                    bought_badge = ""
                strat_html = f'<span class="sig-strategy">{strat}</span>' if strat else ""

                st.markdown(
                    f'<div class="{card_cls}">'
                    f'  {tooltip}'
                    f'  <div class="sig-header">'
                    f'    <div style="display:flex;align-items:center;gap:8px">'
                    f'      <a href="{tv}" target="_blank" class="sig-ticker">{_short(t)}</a>'
                    f'      {bought_badge}'
                    f'    </div>'
                    f'    <div style="display:flex;align-items:center;gap:6px">'
                    f'      {strat_html}'
                    f'      <span class="sig-dir {direction}">{direction}</span>'
                    f'      <span class="sig-badge {badge_cls}">{score:.0f}</span>'
                    f'    </div>'
                    f'  </div>'
                    f'  <div class="sig-levels">'
                    f'    <span>Entry <b>{currency}{entry:,.2f}</b></span>'
                    f'    <span style="color:var(--profit)">Target <b>{currency}{target:,.2f}</b> (+{upside:.1f}%)</span>'
                    f'    <span style="color:var(--loss)">Stop <b>{currency}{stop:,.2f}</b> (-{risk:.1f}%)</span>'
                    f'    <span style="color:{rr_color}">R:R <b>{rr_ratio:.1f}</b></span>'
                    f'  </div>'
                    f'  <div class="sig-subscores">'
                    f'    <span class="score-pill">Sent <b>{sent:.0f}</b></span>'
                    f'    <span class="score-pill">Fund <b>{fund:.0f}</b></span>'
                    f'    <span class="score-pill">Tech <b>{tech:.0f}</b></span>'
                    f'    <span class="score-pill">Ins <b>{ins:.0f}</b></span>'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="kite-section" style="margin-top:20px">Full Signal Table</div>',
                    unsafe_allow_html=True)
        import pandas as pd
        df_sig = pd.DataFrame(signals)
        _clean = lambda v: str(v).replace("_", " ").title() if isinstance(v, str) else v
        if "strategy_name" in df_sig.columns:
            df_sig["strategy_name"] = df_sig["strategy_name"].apply(_clean)
        display_cols = ["ticker", "direction", "strategy_name", "composite_score", "entry_price",
                        "target_price", "stop_loss_price", "sentiment_score", "fundamental_score",
                        "technical_score", "insider_score"]
        display_cols = [c for c in display_cols if c in df_sig.columns]
        if display_cols:
            st.dataframe(df_sig[display_cols], use_container_width=True, hide_index=True)


# ── TAB 4: Strategy Radar (live per-stock strategy engine) ───────────────────
with tab_radar:
    from dashboard.data import get_strategy_radar, ticker_tv_url as _tv

    radar = get_strategy_radar(exchange)
    firing = [r for r in radar if r["firing"]]
    near_misses = [r for r in radar if r["near_miss"]]
    validated_r = [r for r in radar if r["validated"]]
    longs = sum(1 for r in validated_r if r["direction"] == "long")
    shorts = len(validated_r) - longs

    st.markdown(
        f'<div class="kite-section">Strategy Radar'
        f' <span class="badge-count">{len(radar)} stocks scanned</span>'
        f' <span class="badge-count" style="background:var(--profit-dim);color:var(--profit)">'
        f'{len(firing)} firing now</span>'
        f' <span class="badge-count" style="background:rgba(212,160,23,0.15);color:#d4a017">'
        f'{len(near_misses)} near miss</span>'
        f' <span class="badge-count">{longs} long / {shorts} short validated</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:var(--text-dim,#78787e);font-size:13px;margin-bottom:14px">'
        'Each stock trades only the strategy its own 2-year history validated — in-sample backtest '
        'AND out-of-sample forward test. A trade is placed only when <b>both</b> gates pass on '
        'today\'s bar: the validated strategy\'s entry condition fires, AND the composite score '
        'clears the 65-point threshold (long) or drops below 35 (short). "Near miss" means the '
        'strategy fired but the score gate blocked it.</div>',
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

        # ── Plain-language "why this stock, why this signal" explainer ────
        from config.settings import SIGNAL_THRESHOLD as _THRESH
        try:
            from strategies.selector import get_strategy_signal as _get_strat_sig
            live_strat = _get_strat_sig(sel_ticker)
        except Exception:
            live_strat = None

        bt_trades = sel.get("bt_trades")
        bt_wr = sel.get("bt_win_rate")
        bt_pf = sel.get("bt_profit_factor")
        bt_ret = sel.get("bt_avg_return_pct")
        fw_trades = sel.get("fw_trades")
        fw_ret = sel.get("fw_total_return_pct")

        pick_bits = []
        if bt_trades:
            pick_bits.append(f'<b>{bt_trades}</b> backtested trades over 2 years, '
                              f'<b>{(bt_wr or 0) * 100:.0f}%</b> win rate, '
                              f'profit factor <b>{bt_pf or 0:.2f}</b>'
                              + (f', avg return <b>{bt_ret:.1f}%</b>/trade' if bt_ret is not None else ''))
        if fw_trades:
            pick_bits.append(f'confirmed out-of-sample on <b>{fw_trades}</b> more trades '
                              f'(<b>{fw_wr:.0f}%</b> win rate, PF <b>{fw_pf:.2f}</b>'
                              + (f', total return <b>{fw_ret:.1f}%</b>' if fw_ret is not None else '') + ')')
        pick_summary = "; ".join(pick_bits) if pick_bits else "not enough trade history yet to validate this assignment."

        st.markdown(
            f'<div class="radar-explain">'
            f'<h4>How {sel_ticker.rsplit(".", 1)[0]} was picked</h4>'
            f'The selection job backtests every strategy in the library against this stock\'s own '
            f'2-year price history and assigns the <b>{strat_label}</b> strategy ({direction}) because it '
            f'was the best/only one to pass both gates: {pick_summary} '
            f'Its overall rank score is <b>{rank:.2f}</b> (higher = stronger edge vs other validated stocks on {exchange.upper()}).'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Composite score breakdown
        comp = sel.get("composite_score")
        sent = sel.get("sentiment_score")
        fund = sel.get("fundamental_score")
        tech = sel.get("technical_score")
        ins = sel.get("insider_score")
        regime_ok = sel.get("regime_ok")

        if comp is not None:
            score_line = (
                f'Today\'s composite score is <b>{comp:.0f}/100</b> — built from '
                f'sentiment <b>{(sent or 0):.0f}</b>, fundamentals <b>{(fund or 0):.0f}</b>, '
                f'technicals <b>{(tech or 0):.0f}</b>, and insider activity <b>{(ins or 0):.0f}</b> '
                f'(weighted average). Market regime is '
                + (f'<span class="gate-pass">risk-ON</span>' if regime_ok else f'<span class="gate-fail">risk-OFF</span>')
                + '.'
            )
        else:
            score_line = "No signal has been computed for this stock yet today."

        # Strategy fire status
        if live_strat:
            if live_strat.get("fires"):
                fire_line = (f'The <b>{strat_label}</b> entry condition <span class="gate-pass">fired</span> '
                              f'on today\'s bar: <i>{live_strat.get("reason")}</i>.')
            else:
                fire_line = (f'The <b>{strat_label}</b> entry condition did '
                              f'<span class="gate-fail">not fire</span> today: <i>{live_strat.get("reason")}</i>. '
                              f'No trade is considered until this condition triggers again.')
        else:
            fire_line = "Strategy fire status could not be computed right now."

        # Score-gate status
        if comp is not None:
            if direction == "long":
                gate_ok = comp >= _THRESH
                gate_line = (f'Score gate needs <b>≥ {_THRESH:.0f}</b> for a long — '
                              f'{comp:.0f} {"clears" if gate_ok else "is below"} it'
                              f' (<span class="{"gate-pass" if gate_ok else "gate-fail"}">'
                              f'{"PASS" if gate_ok else "FAIL"}</span>).')
            else:
                gate_ok = comp <= (100 - _THRESH)
                gate_line = (f'Score gate needs <b>≤ {100 - _THRESH:.0f}</b> for a short — '
                              f'{comp:.0f} {"clears" if gate_ok else "is above"} it'
                              f' (<span class="{"gate-pass" if gate_ok else "gate-fail"}">'
                              f'{"PASS" if gate_ok else "FAIL"}</span>).')
        else:
            gate_line = ""

        # Overall verdict
        if sel["firing"]:
            verdict = ('<span class="gate-pass">Both gates passed</span> — this is a live, '
                        'actionable signal and a position was opened/sized today.')
        elif sel["near_miss"]:
            verdict = ('The strategy fired but the <span class="gate-fail">score gate blocked it</span> — '
                        'a "near miss". No position was taken.')
        elif sel["validated"]:
            verdict = ('This stock is validated and being watched, but its strategy did not fire today — '
                        'no position was taken.')
        else:
            verdict = 'This stock has not been validated for any strategy — it is scored but not traded.'

        st.markdown(
            f'<div class="radar-explain">'
            f'<h4>What happened today</h4>'
            f'{score_line} {fire_line} {gate_line}<br><br>{verdict}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Strategy Prediction Chart ─────────────────────────────────────────
        # Shows the last 60 days of OHLCV with entry/target/stop levels overlaid
        # so you can see if price is moving in the predicted direction.
        st.markdown('<div class="kite-section" style="margin-top:14px">Strategy Prediction vs Real-time Price</div>',
                    unsafe_allow_html=True)
        import plotly.graph_objects as _go

        try:
            _ohlcv = fetch_ohlcv(sel_ticker, days=60)
        except Exception:
            _ohlcv = []

        if _ohlcv:
            _dates  = [r.get("date") or r.get("Date") for r in _ohlcv]
            _closes = [r.get("close") or r.get("Close") or 0 for r in _ohlcv]
            _opens  = [r.get("open")  or r.get("Open")  or c for r, c in zip(_ohlcv, _closes)]
            _highs  = [r.get("high")  or r.get("High")  or c for r, c in zip(_ohlcv, _closes)]
            _lows   = [r.get("low")   or r.get("Low")   or c for r, c in zip(_ohlcv, _closes)]
            _vols   = [r.get("volume") or r.get("Volume") or 0 for r in _ohlcv]

            _entry_v  = sel.get("entry_price")
            _target_v = sel.get("target_price")
            _stop_v   = sel.get("stop_loss_price")

            _pred_levels = []
            if _entry_v:  _pred_levels.append((_entry_v,  "Entry",  "#3c3c44", "#eaeaed"))
            if _target_v: _pred_levels.append((_target_v, "Target", "#00c48c", "#ffffff"))
            if _stop_v:   _pred_levels.append((_stop_v,   "Stop",   "#ff5a5a", "#ffffff"))

            _pred_zone = None
            if _entry_v and _target_v:
                _zc = "rgba(0,196,140,0.08)" if direction == "long" else "rgba(255,90,90,0.08)"
                _pred_zone = (min(_entry_v, _target_v), max(_entry_v, _target_v), _zc)

            _fig_pred = _build_candle_chart(
                _dates, _opens, _highs, _lows, _closes, volumes=_vols,
                levels=_pred_levels, zone=_pred_zone,
                currency=currency, title="", h=400,
            )
            st.plotly_chart(_fig_pred, use_container_width=True, config={"displayModeBar": False})

            # Direction verdict vs latest price
            if _closes and _entry_v:
                _latest = _closes[-1]
                if direction == "long":
                    _pred_ok = _latest > _entry_v
                    _pred_txt = f"Price {currency}{_latest:.2f} is {'above' if _pred_ok else 'below'} entry — moving {'with' if _pred_ok else 'against'} the long prediction."
                else:
                    _pred_ok = _latest < _entry_v
                    _pred_txt = f"Price {currency}{_latest:.2f} is {'below' if _pred_ok else 'above'} entry — moving {'with' if _pred_ok else 'against'} the short prediction."
                _pred_color = "var(--profit)" if _pred_ok else "var(--loss)"
                st.markdown(
                    f'<div style="font-size:0.82rem;color:{_pred_color};padding:6px 0 14px;font-weight:500">'
                    f'{_pred_txt}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="radar-empty">Price history not available for prediction chart.</div>',
                        unsafe_allow_html=True)

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

        if near_misses:
            st.markdown('<div class="kite-section" style="margin-top:20px">Near Miss — Strategy Fired, Score Gate Blocked</div>',
                        unsafe_allow_html=True)
            for r in near_misses:
                tname = r["ticker"].rsplit(".", 1)[0]
                strat_label = (r["strategy_name"] or "").replace("_", " ")
                score = f'{r["composite_score"]:.0f}' if r.get("composite_score") is not None else "—"
                entry = f'{currency}{r["entry_price"]:.2f}' if r.get("entry_price") else "—"
                target = f'{currency}{r["target_price"]:.2f}' if r.get("target_price") else "—"
                stop = f'{currency}{r["stop_loss_price"]:.2f}' if r.get("stop_loss_price") else "—"
                st.markdown(
                    f'<div class="radar-card near-miss">'
                    f'  <div class="radar-head">'
                    f'    <a class="radar-ticker" href="{_tv(r["ticker"])}" target="_blank">{tname}</a>'
                    f'    <span class="dir-chip {r["direction"]}">{r["direction"]}</span>'
                    f'    <span class="strat-chip">{strat_label}</span>'
                    f'    <span class="near-miss-chip">NEAR MISS</span>'
                    f'  </div>'
                    f'  <div class="radar-stats">'
                    f'    <span>Score <b>{score}</b> (needs {"≥65" if r["direction"] == "long" else "≤35"})</span>'
                    f'    <span>Entry <b>{entry}</b></span>'
                    f'    <span>Target <b>{target}</b></span>'
                    f'    <span>Stop <b>{stop}</b></span>'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="kite-section" style="margin-top:20px">Validated — Watching</div>',
                    unsafe_allow_html=True)
        watching = [r for r in validated_r if not r["firing"] and not r["near_miss"]]
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
    # ── Filters ───────────────────────────────────────────────────────────────
    hf1, hf2, hf3, hf4, hf5 = st.columns([1.2, 0.8, 0.8, 0.8, 0.8])
    with hf1:
        hist_period = st.selectbox("Period", ["7 days", "30 days", "60 days", "90 days", "180 days", "1 year", "All time"],
                                   index=3, key="hist_period")
    with hf2:
        hist_date_from = st.date_input("Exit date from", value=None, key="hist_date_from")
    with hf3:
        hist_date_to = st.date_input("Exit date to", value=None, key="hist_date_to")
    with hf4:
        hist_outcome = st.selectbox("Outcome", ["All", "Wins", "Losses"], key="hist_outcome")
    with hf5:
        hist_type = st.selectbox("Type", ["Realised", "Unrealised"], key="hist_type")

    hist_days = {"7 days": 7, "30 days": 30, "60 days": 60, "90 days": 90,
                 "180 days": 180, "1 year": 365, "All time": 3650}[hist_period]

    if hist_type == "Unrealised":
        # Show open positions as "unrealised trades"
        st.markdown('<div class="kite-section">Unrealised (Open Positions)</div>', unsafe_allow_html=True)
        if not positions:
            st.markdown('<div class="radar-empty">No open positions.</div>', unsafe_allow_html=True)
        else:
            _u_total = sum(p.get("unrealised_pnl", 0) or 0 for p in positions)
            _u_table = '''<table class="kite-table"><thead><tr>
                <th>Ticker</th><th>Entry Date</th><th>Entry Price</th><th>Current Price</th>
                <th>Shares</th><th>Unrealised P&L</th><th>Net chg.</th><th>Days held</th>
            </tr></thead><tbody>'''
            for p in positions:
                pnl = p.get("unrealised_pnl", 0) or 0
                cls = _pnl_class(pnl)
                row_cls = "loss-row" if pnl < 0 else ""
                tv = _tv_url(p["ticker"])
                _u_table += f'''<tr class="{row_cls}">
                    <td><a href="{tv}" target="_blank" class="ticker-link">{_short(p["ticker"])}</a></td>
                    <td>{p.get("entry_date","")}</td>
                    <td>{currency}{p.get("entry_price",0):,.2f}</td>
                    <td>{currency}{p.get("current_price",0):,.2f}</td>
                    <td>{p.get("shares",0):,.0f}</td>
                    <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                    <td class="{cls}">{_pnl_pct(p.get("unrealised_pnl_pct",0) or 0)}</td>
                    <td>{p.get("days_held",0)}</td>
                </tr>'''
            _u_table += f'''<tr class="total-row">
                <td>Total ({len(positions)})</td><td></td><td></td><td></td><td></td>
                <td class="{_pnl_class(_u_total)}">{_pnl_sign(_u_total, currency)}</td><td></td><td></td>
            </tr></tbody></table>'''
            st.markdown('<div class="kite-table-wrap">' + _u_table + '</div>', unsafe_allow_html=True)
    else:
        trades = load_trades(exchange, hist_days)

        # Apply date and outcome filters
        if hist_date_from:
            trades = [t for t in trades if str(t.get("exit_date","")) >= str(hist_date_from)]
        if hist_date_to:
            trades = [t for t in trades if str(t.get("exit_date","")) <= str(hist_date_to)]
        if hist_outcome == "Wins":
            trades = [t for t in trades if (t.get("net_pnl", 0) or 0) > 0]
        elif hist_outcome == "Losses":
            trades = [t for t in trades if (t.get("net_pnl", 0) or 0) <= 0]

        def _clean_reason(r):
            return str(r or "").replace("_", " ").strip().title()

        if not trades:
            st.markdown(
                '<div class="empty-state">'
                '  <div class="empty-title">No closed trades match filters</div>'
                '  <div class="empty-sub">Try a wider date range or change the outcome filter.</div>'
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
                daily_vals = [r.get("daily_pnl", 0) for r in pnl_data]

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=dates, y=cum, mode="lines",
                    line=dict(color="#6993ff", width=2),
                    fill="tozeroy", fillcolor="rgba(105,147,255,0.06)",
                    name="Cumulative P&L",
                ))
                fig.add_trace(go.Bar(
                    x=dates, y=daily_vals,
                    marker_color=["#00c48c" if v >= 0 else "#ff5a5a" for v in daily_vals],
                    opacity=0.4, name="Daily P&L",
                ))
                layout = _chart_base(h=260, title="Cumulative Realized P&L")
                layout["yaxis"]["tickprefix"] = currency
                layout["barmode"] = "overlay"
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
                row_cls = "loss-row" if pnl < 0 else ""
                tv = _tv_url(ticker)
                reason = _clean_reason(t.get("exit_reason", ""))

                table_html += f'''<tr class="{row_cls}">
                    <td><a href="{tv}" target="_blank" class="ticker-link">{_short(ticker)}</a></td>
                    <td>{t.get("entry_date", "")}</td>
                    <td>{t.get("exit_date", "")}</td>
                    <td>{t.get("shares", 0):,.0f}</td>
                    <td>{currency}{t.get("entry_price", 0):,.2f}</td>
                    <td>{currency}{t.get("exit_price", 0):,.2f}</td>
                    <td class="{cls}">{_pnl_sign(pnl, currency)}</td>
                    <td style="font-size:0.78rem;color:var(--text-secondary)">{reason}</td>
                </tr>'''

            table_html += '</tbody></table>'
            st.markdown('<div class="kite-table-wrap">' + table_html + '</div>', unsafe_allow_html=True)

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


# ── TAB 9: Research ───────────────────────────────────────────────────────────
with tab_research:
    import math
    from datetime import timedelta as _td

    st.markdown(
        '<div class="kite-section">Research Dashboard</div>'
        '<div style="color:var(--text-secondary);font-size:13px;margin-bottom:20px">'
        'Auto-computed from live signals, holdings, and trade history. '
        'Tracks the five profit-leakage hypotheses in real time.</div>',
        unsafe_allow_html=True,
    )

    # ── Load data ─────────────────────────────────────────────────────────────
    _r_signals   = load_signals(exchange, _today(exchange), 200)
    _r_positions = portfolio.get("positions", []) if "portfolio" in dir() else []
    _r_trades    = load_trades(exchange, 365)
    _r_radar     = get_strategy_radar(exchange)
    _r_regime    = load_regime(exchange)

    # ── SECTION 1 · Hypothesis Tracker ───────────────────────────────────────
    st.markdown('<div class="kite-section" style="margin-top:4px">Hypothesis Tracker</div>', unsafe_allow_html=True)

    # H1 — signal lag: do we have signals with high scores but no matching open position?
    _actionable = [s for s in _r_signals if (s.get("composite_score") or 0) >= 70]
    _pos_tickers = {p["ticker"] for p in _r_positions}
    _h1_missed   = [s for s in _actionable if s["ticker"] not in _pos_tickers]
    _h1_acted    = [s for s in _actionable if s["ticker"] in _pos_tickers]
    _h1_conv     = round(len(_h1_acted) / max(len(_actionable), 1) * 100)
    _h1_status   = "confirmed" if _h1_conv < 50 else ("watch" if _h1_conv < 80 else "clear")

    # H2 — exit nudge: positions at/near target or stop
    _h2_at_risk = []
    for _p in _r_positions:
        _cp  = _p.get("current_price") or 0
        _tp  = _p.get("target_price") or 0
        _sp  = _p.get("stop_loss_price") or 0
        if _tp and _cp >= _tp * 0.97:
            _h2_at_risk.append((_p["ticker"], "near target", _cp, _tp))
        elif _sp and _cp <= _sp * 1.03:
            _h2_at_risk.append((_p["ticker"], "near stop", _cp, _sp))
    _h2_status = "confirmed" if _h2_at_risk else "watch"

    # H3 — decision friction: how many radar signals are firing but not held?
    _h3_firing_unheld = [r for r in _r_radar if r.get("firing") and r["ticker"] not in _pos_tickers]
    _h3_status = "confirmed" if len(_h3_firing_unheld) >= 2 else "watch"

    # H4 — score drift: positions whose current composite score < 60 (entered at ≥70)
    _sig_by_ticker = {s["ticker"]: s for s in _r_signals}
    _h4_drifted = []
    for _p in _r_positions:
        _cur_sig = _sig_by_ticker.get(_p["ticker"])
        _cur_score = (_cur_sig or {}).get("composite_score") or 0
        if _cur_score and _cur_score < 60:
            _h4_drifted.append((_p["ticker"], _cur_score))
    _h4_status = "confirmed" if _h4_drifted else "clear"

    # H5 — regime blindness: signals firing in risk-off regime
    _regime_ok = _r_regime.get("regime_ok", True)
    _h5_fire_in_riskoff = _actionable if not _regime_ok else []
    _h5_status = "confirmed" if _h5_fire_in_riskoff else "clear"

    def _hyp_color(status):
        return {"confirmed": "#ff5a5a", "watch": "#d4a017", "clear": "#00c48c"}.get(status, "#9090a0")

    def _hyp_bg(status):
        return {"confirmed": "rgba(255,90,90,0.1)", "watch": "rgba(212,160,23,0.1)", "clear": "rgba(0,196,140,0.08)"}.get(status, "")

    _hyps = [
        ("H1", "Signal Lag", _h1_status,
         f"{len(_h1_missed)} high-score signals not acted on today ({_h1_conv}% conversion rate).",
         "Entry price may have moved by the time you see the signal. Add push alerts at score ≥ 70."),
        ("H2", "No Exit Nudge", _h2_status,
         f"{len(_h2_at_risk)} holding(s) within 3% of target or stop right now." if _h2_at_risk else "No holdings near target or stop today.",
         "Dashboard gives no in-row alert when a position hits its predicted level."),
        ("H3", "Decision Friction", _h3_status,
         f"{len(_h3_firing_unheld)} strategy radar signal(s) firing but not in portfolio.",
         "Multiple steps (signal → inspector → decide) add latency before acting on live signals."),
        ("H4", "Score Drift", _h4_status,
         f"{len(_h4_drifted)} holding(s) now scoring < 60 — thesis may have weakened." if _h4_drifted else "All holdings maintain score ≥ 60.",
         "Holdings tab has no live score column — deteriorating theses aren't visible at a glance."),
        ("H5", "Regime Blindness", _h5_status,
         f"{'Risk-OFF — ' + str(len(_h5_fire_in_riskoff)) + ' buy signals firing against regime.' if not _regime_ok else 'Regime is RISK-ON — signals are aligned.'}",
         "Regime context is shown once at Dashboard top but absent from the Signal card view."),
    ]

    _hyp_cols = st.columns(5)
    for _i, (_hid, _htitle, _hstatus, _hfact, _hrec) in enumerate(_hyps):
        with _hyp_cols[_i]:
            st.markdown(
                f'<div style="background:var(--bg-secondary);border:1px solid var(--border);'
                f'border-top:3px solid {_hyp_color(_hstatus)};border-radius:8px;padding:14px 12px">'
                f'  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
                f'    <span style="font-size:11px;font-weight:700;color:var(--text-tertiary);letter-spacing:0.05em">{_hid}</span>'
                f'    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;'
                f'    padding:2px 7px;border-radius:4px;background:{_hyp_bg(_hstatus)};color:{_hyp_color(_hstatus)}">'
                f'    {_hstatus}</span></div>'
                f'  <div style="font-size:13px;font-weight:600;color:var(--text-primary);margin-bottom:6px">{_htitle}</div>'
                f'  <div style="font-size:12px;color:var(--text-secondary);line-height:1.5">{_hfact}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── SECTION 2 · Signal → Action Diary ────────────────────────────────────
    st.markdown('<div class="kite-section" style="margin-top:28px">Signal → Action Diary — Last 30 days</div>', unsafe_allow_html=True)

    _diary_days = 30
    _all_trades_365 = _r_trades
    _recent_trades  = [t for t in _all_trades_365
                       if t.get("entry_date") and
                       (date.today() - (date.fromisoformat(str(t["entry_date"])[:10]))).days <= _diary_days]

    _entered_tickers = {str(t["ticker"]) for t in _recent_trades}
    _today_signals_all = load_signals(exchange, _today(exchange), 200)
    _high_signals_today = [s for s in _today_signals_all if (s.get("composite_score") or 0) >= 60]

    _diary_rows = []
    for _s in sorted(_today_signals_all, key=lambda x: x.get("composite_score") or 0, reverse=True)[:30]:
        _tk   = _s.get("ticker", "")
        _sc   = _s.get("composite_score") or 0
        _held = _tk in _pos_tickers
        _ever_traded = _tk in _entered_tickers
        if _sc < 55:
            continue
        _action = "Holding" if _held else ("Traded (closed)" if _ever_traded else "No action")
        _act_col = {"Holding": "#00c48c", "Traded (closed)": "#6993ff", "No action": "#ff5a5a"}.get(_action, "#9090a0")
        _diary_rows.append({
            "Ticker": _tk,
            "Score": f"{_sc:.0f}",
            "Sentiment": f"{_s.get('sentiment_score') or 0:.0f}",
            "Technical": f"{_s.get('technical_score') or 0:.0f}",
            "Fundamental": f"{_s.get('fundamental_score') or 0:.0f}",
            "Entry px": f"{currency}{_s.get('entry_price') or 0:.2f}" if _s.get("entry_price") else "—",
            "Target px": f"{currency}{_s.get('target_price') or 0:.2f}" if _s.get("target_price") else "—",
            "Action": _action,
            "_act_col": _act_col,
        })

    if _diary_rows:
        _acted   = sum(1 for r in _diary_rows if r["Action"] != "No action")
        _missed  = sum(1 for r in _diary_rows if r["Action"] == "No action")
        _conv_rt = round(_acted / max(len(_diary_rows), 1) * 100)

        _m1, _m2, _m3 = st.columns(3)
        with _m1:
            st.markdown(
                f'<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:14px 16px">'
                f'  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-tertiary);margin-bottom:6px">Signals ≥55 today</div>'
                f'  <div style="font-size:2rem;font-weight:700;color:var(--text-primary);font-variant-numeric:tabular-nums">{len(_diary_rows)}</div>'
                f'</div>', unsafe_allow_html=True)
        with _m2:
            st.markdown(
                f'<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:14px 16px">'
                f'  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-tertiary);margin-bottom:6px">Acted on</div>'
                f'  <div style="font-size:2rem;font-weight:700;color:var(--profit);font-variant-numeric:tabular-nums">{_acted}</div>'
                f'</div>', unsafe_allow_html=True)
        with _m3:
            st.markdown(
                f'<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:14px 16px">'
                f'  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-tertiary);margin-bottom:6px">Conversion rate</div>'
                f'  <div style="font-size:2rem;font-weight:700;font-variant-numeric:tabular-nums;'
                f'  color:{"var(--profit)" if _conv_rt >= 60 else "var(--loss)"}">{_conv_rt}%</div>'
                f'</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        _diary_table = '<table class="kite-table"><thead><tr>'
        for _col in ["Ticker", "Score", "Sent", "Tech", "Fund", "Entry", "Target", "Action taken"]:
            _diary_table += f'<th>{_col}</th>'
        _diary_table += '</tr></thead><tbody>'
        for _row in _diary_rows:
            _diary_table += '<tr>'
            _diary_table += f'<td><span class="ticker-link" style="font-family:var(--font-mono)">{_row["Ticker"]}</span></td>'
            _sc_v = int(_row["Score"])
            _sc_cl = "profit" if _sc_v >= 70 else ("warning" if _sc_v >= 60 else "loss")
            _diary_table += f'<td><span class="score-badge {_sc_cl}">{_row["Score"]}</span></td>'
            _diary_table += f'<td style="color:var(--text-secondary)">{_row["Sentiment"]}</td>'
            _diary_table += f'<td style="color:var(--text-secondary)">{_row["Technical"]}</td>'
            _diary_table += f'<td style="color:var(--text-secondary)">{_row["Fundamental"]}</td>'
            _diary_table += f'<td style="font-family:var(--font-mono)">{_row["Entry px"]}</td>'
            _diary_table += f'<td style="font-family:var(--font-mono)">{_row["Target px"]}</td>'
            _diary_table += (
                f'<td><span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;'
                f'background:{_row["_act_col"]}22;color:{_row["_act_col"]}">{_row["Action"]}</span></td>'
            )
            _diary_table += '</tr>'
        _diary_table += '</tbody></table>'
        st.markdown('<div class="kite-table-wrap">' + _diary_table + '</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state"><div class="empty-title">No signals today</div></div>', unsafe_allow_html=True)

    # ── SECTION 3 · Exit Retrospective ───────────────────────────────────────
    st.markdown('<div class="kite-section" style="margin-top:28px">Exit Retrospective — Last 365 days</div>', unsafe_allow_html=True)

    _closed = [t for t in _r_trades if t.get("exit_date") and t.get("exit_price")]
    if _closed:
        _wins  = [t for t in _closed if (t.get("realised_pnl") or 0) > 0]
        _loss  = [t for t in _closed if (t.get("realised_pnl") or 0) <= 0]
        _total_real = sum(t.get("realised_pnl") or 0 for t in _closed)
        _avg_win    = sum(t.get("realised_pnl") or 0 for t in _wins) / max(len(_wins), 1)
        _avg_loss   = sum(t.get("realised_pnl") or 0 for t in _loss) / max(len(_loss), 1)
        _pf         = abs(_avg_win / _avg_loss) if _avg_loss else 0
        _wr         = round(len(_wins) / max(len(_closed), 1) * 100)

        _e1, _e2, _e3, _e4 = st.columns(4)
        for _col, _label, _val, _fmt, _color in [
            (_e1, "Closed trades",  len(_closed),     str,    "var(--text-primary)"),
            (_e2, "Win rate",       f"{_wr}%",         str,    "var(--profit)" if _wr >= 50 else "var(--loss)"),
            (_e3, "Profit factor",  f"{_pf:.2f}x",     str,    "var(--profit)" if _pf >= 1 else "var(--loss)"),
            (_e4, "Total realised", _pnl_sign(_total_real, currency), str, _pnl_class_var(_total_real)),
        ]:
            with _col:
                st.markdown(
                    f'<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:14px 16px">'
                    f'  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-tertiary);margin-bottom:6px">{_label}</div>'
                    f'  <div style="font-size:1.8rem;font-weight:700;font-variant-numeric:tabular-nums;color:{_color}">{_val}</div>'
                    f'</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        _retro_table = '<table class="kite-table"><thead><tr>'
        for _c in ["Ticker", "Entry date", "Exit date", "Days held", "Entry px", "Exit px", "Realised P&L", "Outcome"]:
            _retro_table += f'<th>{_c}</th>'
        _retro_table += '</tr></thead><tbody>'

        for _t in _closed[:50]:
            _rpnl  = _t.get("realised_pnl") or 0
            _days  = 0
            try:
                _ed = date.fromisoformat(str(_t.get("entry_date", ""))[:10])
                _xd = date.fromisoformat(str(_t.get("exit_date",  ""))[:10])
                _days = (_xd - _ed).days
            except Exception:
                pass
            _outcome = "Win" if _rpnl > 0 else "Loss"
            _oc      = "var(--profit)" if _rpnl > 0 else "var(--loss)"
            _retro_table += (
                f'<tr>'
                f'<td><span style="font-family:var(--font-mono);font-weight:600">{_t.get("ticker","")}</span></td>'
                f'<td style="color:var(--text-secondary)">{str(_t.get("entry_date",""))[:10]}</td>'
                f'<td style="color:var(--text-secondary)">{str(_t.get("exit_date",""))[:10]}</td>'
                f'<td style="font-variant-numeric:tabular-nums">{_days}d</td>'
                f'<td style="font-family:var(--font-mono)">{currency}{float(_t.get("entry_price") or 0):.2f}</td>'
                f'<td style="font-family:var(--font-mono)">{currency}{float(_t.get("exit_price") or 0):.2f}</td>'
                f'<td style="font-family:var(--font-mono);color:{_oc};font-weight:600">{_pnl_sign(_rpnl, currency)}</td>'
                f'<td><span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;'
                f'background:{_oc}22;color:{_oc}">{_outcome}</span></td>'
                f'</tr>'
            )
        _retro_table += '</tbody></table>'
        st.markdown('<div class="kite-table-wrap">' + _retro_table + '</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="empty-state"><div class="empty-title">No closed trades yet</div>'
            '<div class="empty-sub">Exit retrospective will populate as you close positions.</div></div>',
            unsafe_allow_html=True,
        )

    # ── SECTION 4 · Score Drift Alert ────────────────────────────────────────
    if _h4_drifted or _h2_at_risk:
        st.markdown('<div class="kite-section" style="margin-top:28px">Live Alerts — Act Now</div>', unsafe_allow_html=True)

        for _ticker, _score in _h4_drifted:
            st.markdown(
                f'<div style="background:rgba(255,90,90,0.08);border:1px solid rgba(255,90,90,0.3);'
                f'border-radius:8px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:12px">'
                f'  <span style="font-size:18px">⚠️</span>'
                f'  <div><b style="font-family:var(--font-mono);color:var(--text-primary)">{_ticker}</b>'
                f'  <span style="color:var(--text-secondary);font-size:12px;margin-left:8px">'
                f'  Score has dropped to <b style="color:var(--loss)">{_score:.0f}</b> — '
                f'  thesis may have weakened. Consider reviewing the position.</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        for _ticker, _kind, _cp, _level in _h2_at_risk:
            _is_target = "target" in _kind
            _col = "var(--profit)" if _is_target else "var(--loss)"
            _icon = "🎯" if _is_target else "🛑"
            st.markdown(
                f'<div style="background:{"rgba(0,196,140,0.08)" if _is_target else "rgba(255,90,90,0.08)"};'
                f'border:1px solid {"rgba(0,196,140,0.3)" if _is_target else "rgba(255,90,90,0.3)"};'
                f'border-radius:8px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:12px">'
                f'  <span style="font-size:18px">{_icon}</span>'
                f'  <div><b style="font-family:var(--font-mono);color:var(--text-primary)">{_ticker}</b>'
                f'  <span style="color:var(--text-secondary);font-size:12px;margin-left:8px">'
                f'  {_kind.title()}: price {currency}{_cp:.2f} vs level {currency}{_level:.2f}. '
                f'  Review your exit plan.</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
