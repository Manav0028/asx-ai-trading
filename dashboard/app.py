"""
AI Trading Dashboard  ·  Phase 2  ·  Redesign
Streamlit — 6 pages, Apple + TradingView inspired dark UI.
Glassmorphism cards, candlestick charts, TradingView embeds, sparklines.

Theme: Dark professional. Red/green reserved exclusively for P&L values.
       All status indicators use neutral slate tones + icons.

Run locally:   streamlit run dashboard/app.py
Deployed to:   Streamlit Cloud (ms-aitrading.streamlit.app)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="AI Trading · Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Base & typography */
* { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"] {
    background: #0a0b0f !important;
}
h1,h2,h3 { letter-spacing: -0.5px; font-weight: 700; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #080910 !important;
    border-right: 1px solid rgba(255,255,255,0.05);
}
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label {
    font-size: 0.78rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 16px 20px;
    transition: border-color 0.2s;
}
[data-testid="stMetric"]:hover { border-color: rgba(99,102,241,0.4); }
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 0.72rem !important; text-transform: uppercase; letter-spacing: 0.08em; }
[data-testid="stMetricValue"] { color: #f1f5f9 !important; font-size: 1.5rem !important; font-weight: 700; }

/* Glassmorphism card class */
.glass {
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 12px;
}

/* Ticker chip — linked badge */
.ticker-chip {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 5px 12px; border-radius: 8px;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.25);
    color: #818cf8; font-weight: 700; font-size: 0.9rem;
    text-decoration: none; cursor: pointer;
    transition: all 0.15s;
}
.ticker-chip:hover { background: rgba(99,102,241,0.22); color: #a5b4fc; }

/* Score pill */
.score-pill {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.8rem; font-weight: 700;
    background: rgba(99,102,241,0.2); color: #a5b4fc;
    border: 1px solid rgba(99,102,241,0.3);
}

/* Status dot */
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }
.dot-live { background:#4ade80; box-shadow: 0 0 6px #4ade80; }
.dot-closed { background:#475569; }

/* Section label */
.sec-label {
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.12em;
    text-transform: uppercase; color: #475569; margin: 20px 0 8px;
}

/* Signal card */
.sig-card {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px; padding: 16px 18px; margin-bottom: 4px;
}
.sig-card:hover { border-color: rgba(99,102,241,0.3); }

/* Position spark card */
.spark-card {
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px; padding: 14px 16px; margin-bottom: 8px;
}

/* Info card (replaces st.info/success/warning for non-P&L content) */
.info-card {
    padding: 12px 16px;
    border-radius: 10px;
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.07);
    color: #cbd5e1;
    font-size: 0.9rem;
    margin: 8px 0;
}
.info-card strong { color: #e2e8f0; }

/* Scrollable table wrapper */
.scroll-table { overflow-x: auto; border-radius: 12px; }

/* Divider */
hr.slim { border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 16px 0; }

/* Progress bar override */
[data-testid="stProgress"] > div > div { background: #6366f1 !important; border-radius: 4px; }

/* DataFrame header */
[data-testid="stDataFrame"] thead tr th {
    background: #0d0e14 !important;
    color: #475569 !important;
    font-size: 0.7rem !important;
    text-transform: uppercase; letter-spacing: 0.08em;
    border-bottom: 1px solid rgba(255,255,255,0.06) !important;
}

/* Plotly chart border-radius */
.element-container iframe { border-radius: 12px; }
.js-plotly-plot { border-radius: 12px; }

/* Mode badge in sidebar */
.mode-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.25);
    color: #818cf8; font-size: 0.78rem; font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _delta(val: float, currency: str = "") -> str:
    """P&L delta string: sign before currency so Streamlit reads it correctly."""
    sign = "+" if val >= 0 else "-"
    return f"{sign}{currency}{abs(val):,.0f}"


def _delta_pct(val: float) -> str:
    return f"{val:+.2f}%"


def _today(exchange: str) -> date:
    try:
        tz = "Australia/Sydney" if exchange == "asx" else "Asia/Kolkata"
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return date.today()


def _tv_url(ticker: str) -> str:
    if ticker.endswith(".AX"):
        sym = f"ASX:{ticker[:-3]}"
    elif ticker.endswith(".NS"):
        sym = f"NSE:{ticker[:-3]}"
    else:
        sym = ticker
    return f"https://www.tradingview.com/chart/?symbol={sym}"


def _yahoo_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}"


def _ticker_links(ticker: str) -> str:
    tv  = _tv_url(ticker)
    yh  = _yahoo_url(ticker)
    return (
        f'<a href="{tv}" target="_blank" class="ticker-chip">📈 {ticker}</a>'
        f'<a href="{yh}" target="_blank" style="margin-left:6px;font-size:0.72rem;'
        f'color:#475569;text-decoration:none">Yahoo ↗</a>'
    )


def _pnl_color(val: float) -> str:
    return "#4ade80" if (val or 0) >= 0 else "#f87171"


def _sec(label: str) -> None:
    st.markdown(f'<div class="sec-label">{label}</div>', unsafe_allow_html=True)


def _info_card(text: str) -> None:
    st.markdown(f'<div class="info-card">{text}</div>', unsafe_allow_html=True)


# ── Import data layer ─────────────────────────────────────────────────────────
from dashboard.data import (
    get_signals, get_portfolio, get_trades, get_regime,
    get_cumulative_pnl, get_score_history, get_backtest_results,
    get_todays_scores, is_market_open, market_status, _use_supabase,
    get_price_history, get_multi_close, ticker_tv_url, ticker_yahoo_url,
)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    _either_open = is_market_open("asx") or is_market_open("nse")
    _interval_ms = 30_000 if _either_open else 300_000
    st_autorefresh(interval=_interval_ms, key="auto_refresh")
except ImportError:
    pass


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div style="padding:8px 0 16px">'
        '<span style="font-size:1.3rem;font-weight:800;color:#f1f5f9">AI Trading</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    _phase   = int(os.getenv("TRADING_PHASE", 1))
    _capital = float(os.getenv("PORTFOLIO_CAPITAL", 100000))
    _risk    = _capital * 0.015

    mode_text = {1: "Internal Paper", 2: "IBKR Paper", 3: "LIVE"}
    mode_icon = {1: "📋", 2: "🔗", 3: "💰"}
    st.markdown(
        f'<div style="margin-bottom:12px">'
        f'<span class="mode-badge">{mode_icon.get(_phase,"📋")} {mode_text.get(_phase,"Paper")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="font-size:0.78rem;color:#64748b;margin-bottom:12px">'
        f'Capital <b style="color:#94a3b8">${_capital:,.0f}</b>'
        f' &nbsp;·&nbsp; Risk/trade <b style="color:#94a3b8">${_risk:,.0f}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    exchange = st.radio(
        "Exchange",
        options=["asx", "nse"],
        format_func=lambda x: "🇦🇺 ASX 200" if x == "asx" else "🇮🇳 NSE NIFTY 100",
    )
    currency       = "$" if exchange == "asx" else "₹"
    exchange_label = "ASX 200 🇦🇺" if exchange == "asx" else "NSE NIFTY 100 🇮🇳"

    page = st.selectbox(
        "Navigate",
        ["📊 Overview", "🏆 Signals", "📋 Portfolio",
         "💼 Positions", "📈 Trade History", "🔬 Backtest"],
    )

    st.divider()

    mkt          = market_status(exchange)
    _market_open = mkt["open"]
    dot_cls      = "dot-live" if _market_open else "dot-closed"
    mkt_state    = "Open" if _market_open else "Closed"
    st.markdown(
        f'<div style="font-size:0.85rem;color:#cbd5e1">'
        f'<span class="dot {dot_cls}"></span>'
        f'{mkt["local_time"]} &nbsp;·&nbsp; {mkt_state}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if _market_open:
        st.caption("Prices updating every 30 s")
    else:
        st.caption("Cached · refreshing every 5 min")

    st.divider()
    if st.button("↺ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"{'☁️ Supabase' if _use_supabase() else '🖥 Local DB'}")


# ── Cached loaders ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_regime(exch):
    return get_regime(exch)

@st.cache_data(ttl=30)
def load_portfolio(exch, live=False):
    return get_portfolio(exch, live=live)

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
def fetch_ohlcv(ticker: str, days: int = 60):
    return get_price_history(ticker, days)

@st.cache_data(ttl=300)
def fetch_sparklines(tickers: list, days: int = 20):
    return get_multi_close(list(tickers), days)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _chart_base(h=320, title="", margin=(40, 20, 30, 10)):
    return dict(
        title=dict(text=title, font=dict(size=13, color="#64748b")) if title else None,
        height=h,
        margin=dict(t=margin[0], b=margin[1], l=margin[2], r=margin[3]),
        plot_bgcolor="#0a0b0f",
        paper_bgcolor="#0a0b0f",
        font=dict(color="#64748b", size=11),
        xaxis=dict(gridcolor="#1a1b26", color="#475569", showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#1a1b26", color="#475569", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.25, font=dict(size=10)),
        hovermode="x unified",
    )


def _candlestick_fig(ohlcv: list, entry: float, target: float, stop: float, ticker: str):
    import plotly.graph_objects as go
    if not ohlcv:
        return None
    dates  = [r["date"]  for r in ohlcv]
    opens  = [r["open"]  for r in ohlcv]
    highs  = [r["high"]  for r in ohlcv]
    lows   = [r["low"]   for r in ohlcv]
    closes = [r["close"] for r in ohlcv]

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=dates, open=opens, high=highs, low=lows, close=closes,
        name=ticker,
        increasing=dict(line=dict(color="#4ade80", width=1), fillcolor="rgba(74,222,128,0.7)"),
        decreasing=dict(line=dict(color="#f87171", width=1), fillcolor="rgba(248,113,113,0.7)"),
    ))

    shapes      = []
    annotations = []
    if entry:
        shapes.append(dict(
            type="line", x0=dates[0], x1=dates[-1], y0=entry, y1=entry,
            line=dict(color="rgba(255,255,255,0.6)", width=1.5, dash="dot"),
        ))
        annotations.append(dict(
            x=dates[-1], y=entry, text=f"Entry {entry:.2f}",
            showarrow=False, xanchor="right", font=dict(color="#94a3b8", size=10),
        ))
    if target:
        shapes.append(dict(
            type="line", x0=dates[0], x1=dates[-1], y0=target, y1=target,
            line=dict(color="rgba(74,222,128,0.7)", width=1.5, dash="dash"),
        ))
        annotations.append(dict(
            x=dates[-1], y=target, text=f"Target {target:.2f}",
            showarrow=False, xanchor="right", font=dict(color="#4ade80", size=10),
        ))
    if stop:
        shapes.append(dict(
            type="line", x0=dates[0], x1=dates[-1], y0=stop, y1=stop,
            line=dict(color="rgba(248,113,113,0.7)", width=1.5, dash="dash"),
        ))
        annotations.append(dict(
            x=dates[-1], y=stop, text=f"Stop {stop:.2f}",
            showarrow=False, xanchor="right", font=dict(color="#f87171", size=10),
        ))

    layout = _chart_base(h=280, margin=(10, 20, 30, 60))
    layout.update(
        shapes=shapes,
        annotations=annotations,
        xaxis_rangeslider_visible=False,
        showlegend=False,
    )
    fig.update_layout(**layout)
    return fig


def _sparkline_fig(closes: list, entry_price: float, ticker: str):
    import plotly.graph_objects as go
    if not closes:
        return None
    dates  = [r["date"]  for r in closes]
    vals   = [r["close"] for r in closes]
    last   = vals[-1] if vals else 0
    colour      = "#4ade80" if last >= (entry_price or last) else "#f87171"
    fill_colour = "rgba(74,222,128,0.08)" if last >= (entry_price or last) else "rgba(248,113,113,0.08)"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=vals, mode="lines",
        line=dict(color=colour, width=2),
        fill="tozeroy", fillcolor=fill_colour,
        name=ticker,
        hovertemplate=f"%{{x}}<br>${{y:.3f}}<extra></extra>",
    ))
    if entry_price:
        fig.add_hline(y=entry_price, line_dash="dot",
                      line_color="rgba(255,255,255,0.35)", line_width=1)
    layout = _chart_base(h=90, margin=(2, 2, 2, 2))
    layout.update(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
        hovermode=False,
    )
    fig.update_layout(**layout)
    return fig


def _pnl_area_chart(pnl_series, currency_sym, title="Cumulative P&L"):
    import plotly.graph_objects as go
    if not pnl_series:
        return None
    dates  = [r["date"]           for r in pnl_series]
    vals   = [r["cumulative_pnl"] for r in pnl_series]
    daily  = [r["daily_pnl"]      for r in pnl_series]
    final  = vals[-1] if vals else 0
    colour = "#4ade80" if final >= 0 else "#f87171"
    fill   = "rgba(74,222,128,0.1)" if final >= 0 else "rgba(248,113,113,0.1)"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=vals, mode="lines",
        line=dict(color=colour, width=2.5),
        fill="tozeroy", fillcolor=fill,
        name="Cumulative",
        hovertemplate=f"%{{x}}<br>Cumulative: {currency_sym}%{{y:+,.0f}}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=dates, y=daily, name="Daily",
        marker_color=[("#4ade80" if v >= 0 else "#f87171") for v in daily],
        opacity=0.35, yaxis="y2",
        hovertemplate=f"%{{x}}<br>Daily: {currency_sym}%{{y:+,.0f}}<extra></extra>",
    ))
    layout = _chart_base(h=320, title=title, margin=(40, 30, 30, 10))
    layout.update(
        yaxis2=dict(overlaying="y", side="right", showgrid=False, color="#475569"),
        yaxis=dict(tickprefix=currency_sym, gridcolor="#1a1b26", zeroline=True,
                   zerolinecolor="#334155", zerolinewidth=1),
    )
    fig.update_layout(**layout)
    return fig


def _tv_widget(ticker: str, exchange: str, height: int = 500):
    import streamlit.components.v1 as components
    if exchange == "asx":
        sym = f"ASX:{ticker.replace('.AX', '')}"
        tz  = "Australia/Sydney"
    else:
        sym = f"NSE:{ticker.replace('.NS', '')}"
        tz  = "Asia/Kolkata"
    html = f"""
    <div style="border-radius:14px;overflow:hidden;height:{height}px;">
    <div class="tradingview-widget-container" style="height:100%;">
      <div class="tradingview-widget-container__widget" style="height:100%;"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {{
        "autosize": true,
        "symbol": "{sym}",
        "interval": "D",
        "timezone": "{tz}",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "backgroundColor": "#0a0b0f",
        "gridColor": "rgba(26,27,38,1)",
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "calendar": false,
        "studies": ["RSI@tv-basicstudies","Volume@tv-basicstudies"],
        "support_host": "https://www.tradingview.com"
      }}
      </script>
    </div>
    </div>
    """
    components.html(html, height=height + 10, scrolling=False)


def _regime_card(regime):
    ok       = regime.get("regime_ok")
    idx      = regime.get("index")
    idx_name = regime.get("index_name", "Index")
    ema      = regime.get("ema200")
    pct      = regime.get("pct_above")

    if ok is None:
        _info_card("Regime data not yet available — scheduler will populate this after the next run.")
        return

    icon  = "✅" if ok else "⚠️"
    state = "RISK-ON" if ok else "RISK-OFF"
    idx_str = f"{idx_name}: <strong>{idx:,.0f}</strong>" if idx else ""
    pct_colour = _pnl_color(pct or 0)
    pct_str = (
        f" &nbsp;·&nbsp; <span style='color:{pct_colour}'>{pct:+.1f}%</span> vs EMA200"
        f" (<strong>{ema:,.0f}</strong>)"
        if ema and pct is not None else ""
    )
    st.markdown(
        f'<div class="info-card">{icon} <strong>{state}</strong>'
        f'&nbsp;&nbsp;{idx_str}{pct_str}</div>',
        unsafe_allow_html=True,
    )


def _allocation_donut(positions, currency_sym, h=300):
    import plotly.graph_objects as go
    tickers = [p["ticker"] for p in positions[:12]]
    values  = [p.get("invested", 0) or 0 for p in positions[:12]]
    if not tickers or sum(values) == 0:
        return None
    colours = [f"hsl({220 + i * 12},70%,{50 + i * 3}%)" for i in range(len(tickers))]
    fig = go.Figure(go.Pie(
        labels=tickers, values=values, hole=0.65,
        marker=dict(colors=colours, line=dict(color="#0a0b0f", width=2)),
        textfont=dict(size=10, color="#cbd5e1"),
        hovertemplate="%{label}<br>$%{value:,.0f} (%{percent})<extra></extra>",
    ))
    total = sum(values)
    fig.add_annotation(
        text=f"{currency_sym}{total:,.0f}", x=0.5, y=0.55,
        font=dict(size=18, color="#f1f5f9", family="Arial"), showarrow=False,
    )
    fig.add_annotation(
        text="invested", x=0.5, y=0.42,
        font=dict(size=11, color="#64748b"), showarrow=False,
    )
    layout = _chart_base(h=h, margin=(10, 10, 10, 10))
    layout.update(showlegend=False)
    fig.update_layout(**layout)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Overview
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Overview":
    st.markdown("## Portfolio Overview")

    regime    = load_regime(exchange)
    portfolio = load_portfolio(exchange, live=_market_open)
    pnl_data  = load_pnl(exchange, 90)
    positions = portfolio.get("positions", [])

    total_invested      = portfolio.get("total_invested", 0) or 0
    total_current_value = portfolio.get("total_current_value", 0) or 0
    total_pnl           = portfolio.get("total_unrealised_pnl", 0) or 0
    total_pnl_pct       = (total_pnl / total_invested * 100) if total_invested else 0
    diff                = total_current_value - total_invested
    _deploy_pct         = min(total_invested / _capital * 100, 100) if _capital else 0

    if portfolio.get("prices_live"):
        st.caption("⚡ Prices live from market data")

    # Row 1: 4 metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invested",      f"{currency}{total_invested:,.0f}")
    c2.metric("Current Value", f"{currency}{total_current_value:,.0f}",
              delta=_delta(diff, currency), delta_color="normal")
    c3.metric("Unrealised P&L",
              f"{currency}{abs(total_pnl):,.0f}" if total_pnl < 0 else f"{currency}{total_pnl:,.0f}",
              delta=f"{_delta_pct(total_pnl_pct)}  ({portfolio.get('winners',0)}W / {portfolio.get('losers',0)}L)",
              delta_color="normal")
    ok        = regime.get("regime_ok")
    pct_above = regime.get("pct_above")
    c4.metric(
        "Market Regime",
        "RISK-ON ✅" if ok else ("RISK-OFF ⚠️" if ok is False else "—"),
        delta=f"{pct_above:+.1f}% vs EMA200" if pct_above is not None else None,
        delta_color="normal",
    )

    # Deployment progress bar
    st.progress(min(_deploy_pct / 100, 1.0))
    st.caption(
        f"Deployed {_deploy_pct:.0f}% of {currency}{_capital:,.0f}"
        f" &nbsp;·&nbsp; Available {currency}{max(_capital - total_invested, 0):,.0f}"
    )

    st.divider()
    _regime_card(regime)
    st.divider()

    # Row 2: P&L area chart + Allocation donut
    ch1, ch2 = st.columns([2, 1])
    with ch1:
        fig = _pnl_area_chart(pnl_data, currency, "90-Day Cumulative Net P&L")
        if fig:
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False, "responsive": True})
        else:
            _info_card("No closed trades yet — chart appears once positions are closed.")
    with ch2:
        if positions:
            fig_donut = _allocation_donut(positions, currency, h=300)
            if fig_donut:
                st.plotly_chart(fig_donut, use_container_width=True,
                                config={"displayModeBar": False, "responsive": True})

    # Row 3: Open Positions table
    if positions:
        _sec("Open Positions")
        import pandas as pd
        df = pd.DataFrame(positions[:8])
        for col in ["unrealised_pnl", "unrealised_pnl_pct", "entry_price",
                    "current_price", "invested", "current_value", "days_held",
                    "trading_mode"]:
            if col not in df.columns:
                df[col] = None
        df["tv_link"] = df["ticker"].apply(ticker_tv_url)

        show_cols = ["ticker", "tv_link", "trading_mode", "days_held",
                     "invested", "current_value", "entry_price",
                     "current_price", "unrealised_pnl", "unrealised_pnl_pct"]
        show_cols = [c for c in show_cols if c in df.columns]

        st.dataframe(
            df[show_cols],
            column_config={
                "ticker":             "Ticker",
                "tv_link":            st.column_config.LinkColumn("Chart", display_text="TV ↗"),
                "trading_mode":       "Mode",
                "days_held":          st.column_config.NumberColumn("Days"),
                "invested":           st.column_config.NumberColumn(f"Invested ({currency})", format="%.0f"),
                "current_value":      st.column_config.NumberColumn(f"Value ({currency})", format="%.0f"),
                "entry_price":        st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                "current_price":      st.column_config.NumberColumn(f"Price ({currency})", format="%.3f"),
                "unrealised_pnl":     st.column_config.NumberColumn(f"P&L ({currency})", format="%+.2f"),
                "unrealised_pnl_pct": st.column_config.NumberColumn("P&L %", format="%+.1f%%"),
            },
            use_container_width=True, hide_index=True,
        )

    # Row 4: IBKR account expander (phase >= 2)
    if _phase >= 2:
        with st.expander("IBKR Paper Account", expanded=False):
            try:
                from execution.ibkr_paper_trader import get_ibkr_account_summary
                ibkr = get_ibkr_account_summary()
                if ibkr:
                    acc = ibkr.get("account", {})
                    ic1, ic2, ic3 = st.columns(3)
                    ic1.metric("Net Liquidation", acc.get("NetLiquidation", "—"))
                    ic2.metric("Available Funds",  acc.get("AvailableFunds", "—"))
                    ic3.metric("Unrealised P&L",   acc.get("UnrealizedPnL",  "—"))
                    if ibkr.get("positions"):
                        import pandas as pd
                        st.dataframe(pd.DataFrame(ibkr["positions"]),
                                     use_container_width=True, hide_index=True)
                    else:
                        _info_card("No open positions in IBKR paper account yet.")
                else:
                    _info_card("TWS not responding — verify TWS is running with API enabled.")
            except Exception as e:
                _info_card(f"IBKR connect error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Signals
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏆 Signals":
    import pandas as pd

    st.markdown("## Signal Scanner")

    col_date, col_n, col_note = st.columns([2, 1, 3])
    with col_date:
        signal_date = st.date_input("Date", value=_today(exchange))
    with col_n:
        n_signals = st.slider("Top N", 5, 25, 10)
    with col_note:
        st.markdown(
            '<div style="padding-top:28px;font-size:0.78rem;color:#475569">'
            'Scanner runs weekdays pre-market. Scores 0-100.'
            '</div>',
            unsafe_allow_html=True,
        )

    signals = load_signals(exchange, signal_date, n_signals)

    if not signals:
        _info_card(
            f"No signals for <strong>{signal_date.strftime('%d %b %Y')}</strong>. "
            "The scanner runs weekdays pre-market."
        )
    else:
        st.caption(f"{len(signals)} signal(s)  ·  {signal_date.strftime('%d %b %Y')}")

        # Signal cards — 2-column grid
        for i in range(0, len(signals), 2):
            c1, c2 = st.columns(2)
            for sig, col in zip(signals[i:i + 2], [c1, c2]):
                with col:
                    ticker  = sig.get("ticker", "")
                    score   = sig.get("composite_score") or 0
                    ep      = sig.get("entry_price") or 0
                    tp      = sig.get("target_price") or 0
                    sl      = sig.get("stop_loss_price") or 0
                    upside  = round((tp - ep) / ep * 100, 1) if ep and tp else 0
                    pnl_col = _pnl_color(upside)
                    tv_url  = ticker_tv_url(ticker)
                    yahoo_url = ticker_yahoo_url(ticker)

                    st.markdown(f'''
                    <div class="sig-card">
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                        <div>
                          <a href="{tv_url}" target="_blank" class="ticker-chip">📈 {ticker}</a>
                          <a href="{yahoo_url}" target="_blank"
                             style="margin-left:6px;font-size:0.72rem;color:#475569;text-decoration:none">
                             Yahoo ↗
                          </a>
                        </div>
                        <span class="score-pill">{score:.0f} / 100</span>
                      </div>
                      <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:0.8rem;color:#94a3b8;margin-bottom:8px">
                        <span>Entry <b style="color:#e2e8f0">{currency}{ep:.3f}</b></span>
                        <span>Target <b style="color:#4ade80">{currency}{tp:.3f}</b></span>
                        <span>Stop <b style="color:#f87171">{currency}{sl:.3f}</b></span>
                        <span>Upside <b style="color:{pnl_col}">{upside:+.1f}%</b></span>
                      </div>
                    </div>
                    ''', unsafe_allow_html=True)

                    # Mini candlestick chart
                    ohlcv = fetch_ohlcv(ticker, 45)
                    if ohlcv:
                        fig = _candlestick_fig(
                            ohlcv,
                            sig.get("entry_price"),
                            sig.get("target_price"),
                            sig.get("stop_loss_price"),
                            ticker,
                        )
                        if fig:
                            st.plotly_chart(fig, use_container_width=True,
                                            config={"displayModeBar": False, "responsive": True})

                    # Score breakdown horizontal bars
                    score_items = [
                        ("Sentiment",   sig.get("sentiment_score")   or 0, "#a78bfa"),
                        ("Technical",   sig.get("technical_score")   or 0, "#38bdf8"),
                        ("Fundamental", sig.get("fundamental_score") or 0, "#fb923c"),
                        ("Insider",     sig.get("insider_score")     or 0, "#4ade80"),
                    ]
                    bars_html = '<div style="margin-top:8px">'
                    for label, val, col_hex in score_items:
                        val = val or 0
                        bars_html += f'''
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                          <div style="width:70px;font-size:0.68rem;color:#64748b;text-align:right">{label}</div>
                          <div style="flex:1;background:rgba(255,255,255,0.06);border-radius:4px;height:6px;overflow:hidden">
                            <div style="width:{min(val,100)}%;background:{col_hex};height:100%;border-radius:4px"></div>
                          </div>
                          <div style="width:28px;font-size:0.68rem;color:#94a3b8;text-align:left">{val:.0f}</div>
                        </div>'''
                    pos_size = sig.get("position_size_aud") or 0
                    regime_ok = sig.get("regime_ok")
                    bars_html += (
                        f'<div style="font-size:0.72rem;color:#64748b;margin-top:4px">'
                        f'Position size: <b style="color:#e2e8f0">{currency}{pos_size:,.0f}</b>'
                        f' &nbsp;·&nbsp; Regime: {"✅" if regime_ok else "⚠️"}'
                        f'</div>'
                    )
                    bars_html += '</div>'
                    st.markdown(bars_html, unsafe_allow_html=True)

        st.divider()

        # Full signals table
        _sec("All Signals")
        df = pd.DataFrame(signals)
        df["tv_link"] = df["ticker"].apply(ticker_tv_url)
        df["upside_pct"] = df.apply(
            lambda row: round(
                (row.get("target_price", 0) - row.get("entry_price", 0))
                / row.get("entry_price", 1) * 100, 1
            ) if (row.get("entry_price") or 0) > 0 else 0,
            axis=1,
        )
        sig_cols = ["ticker", "tv_link", "composite_score", "sentiment_score",
                    "fundamental_score", "technical_score", "insider_score",
                    "entry_price", "target_price", "upside_pct",
                    "stop_loss_price", "position_size_aud", "regime_ok"]
        sig_cols = [c for c in sig_cols if c in df.columns]
        st.dataframe(
            df[sig_cols],
            column_config={
                "ticker":             "Ticker",
                "tv_link":            st.column_config.LinkColumn("Chart", display_text="TV ↗"),
                "composite_score":    st.column_config.ProgressColumn(
                                          "Score", min_value=0, max_value=100, format="%.1f"),
                "sentiment_score":    st.column_config.ProgressColumn(
                                          "Sentiment", min_value=0, max_value=100, format="%.0f"),
                "fundamental_score":  st.column_config.ProgressColumn(
                                          "Fundamental", min_value=0, max_value=100, format="%.0f"),
                "technical_score":    st.column_config.ProgressColumn(
                                          "Technical", min_value=0, max_value=100, format="%.0f"),
                "insider_score":      st.column_config.ProgressColumn(
                                          "Insider", min_value=0, max_value=100, format="%.0f"),
                "entry_price":        st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                "target_price":       st.column_config.NumberColumn(f"Target ({currency})", format="%.3f"),
                "upside_pct":         st.column_config.NumberColumn("Upside %", format="%+.1f%%"),
                "stop_loss_price":    st.column_config.NumberColumn(f"Stop ({currency})", format="%.3f"),
                "position_size_aud":  st.column_config.NumberColumn(f"Position ({currency})", format="%.0f"),
                "regime_ok":          st.column_config.CheckboxColumn("Regime"),
            },
            use_container_width=True, hide_index=True,
        )

        st.divider()

        # TradingView widget for selected ticker
        _sec("Interactive Chart")
        tv_tickers = [s["ticker"] for s in signals]
        if tv_tickers:
            selected_tv = st.selectbox("Select ticker", tv_tickers, key="tv_sel_signals")
            _tv_widget(selected_tv, exchange, height=480)

        # Score history expander
        with st.expander("Score History", expanded=False):
            hist_ticker = st.selectbox("Ticker", [s["ticker"] for s in signals], key="hist_sel")
            hist = load_score_history(hist_ticker, 30)
            if hist:
                import plotly.graph_objects as go
                fig_h = go.Figure()
                colour_map = {
                    "composite_score":   "#6366f1",
                    "technical_score":   "#38bdf8",
                    "fundamental_score": "#f59e0b",
                    "sentiment_score":   "#a78bfa",
                    "insider_score":     "#94a3b8",
                }
                for key, col_h in colour_map.items():
                    if any(h.get(key) for h in hist):
                        fig_h.add_trace(go.Scatter(
                            x=[h["date"] for h in hist],
                            y=[h.get(key) or 0 for h in hist],
                            mode="lines", name=key.replace("_score", "").title(),
                            line=dict(color=col_h,
                                      width=2.5 if key == "composite_score" else 1.5),
                        ))
                layout_h = _chart_base(h=280, title=f"{hist_ticker} — 30-day Scores",
                                       margin=(40, 20, 20, 10))
                layout_h.update(yaxis=dict(range=[0, 100], gridcolor="#1a1b26"))
                fig_h.update_layout(**layout_h)
                st.plotly_chart(fig_h, use_container_width=True,
                                config={"displayModeBar": False, "responsive": True})
            else:
                _info_card("No score history yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Portfolio
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Portfolio":
    import pandas as pd

    st.markdown("## Portfolio")
    if _market_open:
        st.caption("⚡ Live prices  ·  30 s refresh")
    else:
        st.caption("Cached  ·  5 min refresh")

    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    total_invested      = portfolio.get("total_invested", 0) or 0
    total_current_value = portfolio.get("total_current_value", 0) or 0
    total_pnl           = portfolio.get("total_unrealised_pnl", 0) or 0
    total_pnl_pct       = (total_pnl / total_invested * 100) if total_invested else 0
    diff                = total_current_value - total_invested

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invested",      f"{currency}{total_invested:,.0f}")
    c2.metric("Current Value", f"{currency}{total_current_value:,.0f}",
              delta=_delta(diff, currency), delta_color="normal")
    c3.metric("Unrealised P&L",
              f"{currency}{abs(total_pnl):,.0f}" if total_pnl < 0 else f"{currency}{total_pnl:,.0f}",
              delta=_delta_pct(total_pnl_pct), delta_color="normal")
    c4.metric("Positions",  portfolio.get("total_positions", 0),
              delta=f"{portfolio.get('winners',0)}W / {portfolio.get('losers',0)}L",
              delta_color="off")

    # P&L summary card
    if positions:
        pnl_colour = _pnl_color(total_pnl)
        pnl_sign   = "+" if total_pnl >= 0 else ""
        st.markdown(
            f'<div class="info-card">'
            f'Portfolio value <strong>{currency}{total_current_value:,.0f}</strong>'
            f' vs {currency}{total_invested:,.0f} invested &nbsp;·&nbsp; '
            f'P&L: <span style="color:{pnl_colour};font-weight:700">'
            f'{pnl_sign}{currency}{total_pnl:,.2f} ({total_pnl_pct:+.2f}%)</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if not positions:
        _info_card("No open positions. Positions open when a stock scores above the signal threshold at market open.")
    else:
        df = pd.DataFrame(positions)

        # Derived columns
        for col in ["current_price", "stop_loss_price", "target_price",
                    "entry_price", "shares", "invested", "current_value",
                    "unrealised_pnl", "unrealised_pnl_pct", "days_held",
                    "signal_score", "trading_mode", "entry_date"]:
            if col not in df.columns:
                df[col] = None

        df["stop_gap_pct"]   = (
            (df["current_price"].fillna(0) - df["stop_loss_price"].fillna(0))
            / df["current_price"].replace(0, float("nan")) * 100
        ).round(1)
        df["target_gap_pct"] = (
            (df["target_price"].fillna(0) - df["current_price"].fillna(0))
            / df["current_price"].replace(0, float("nan")) * 100
        ).round(1)
        df["tv_link"] = df["ticker"].apply(ticker_tv_url)

        _sec("Holdings")
        hold_cols = ["ticker", "tv_link", "trading_mode", "entry_date", "days_held",
                     "invested", "current_value", "entry_price", "current_price",
                     "unrealised_pnl", "unrealised_pnl_pct",
                     "stop_gap_pct", "target_gap_pct", "signal_score"]
        hold_cols = [c for c in hold_cols if c in df.columns]
        st.dataframe(
            df[hold_cols],
            column_config={
                "ticker":             "Ticker",
                "tv_link":            st.column_config.LinkColumn("Chart", display_text="TV ↗"),
                "trading_mode":       "Mode",
                "entry_date":         st.column_config.DateColumn("Entry", format="DD MMM YYYY"),
                "days_held":          st.column_config.NumberColumn("Days"),
                "invested":           st.column_config.NumberColumn(f"Invested ({currency})", format="%.0f"),
                "current_value":      st.column_config.NumberColumn(f"Value ({currency})", format="%.0f"),
                "entry_price":        st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                "current_price":      st.column_config.NumberColumn(f"Price ({currency})", format="%.3f"),
                "unrealised_pnl":     st.column_config.NumberColumn(f"P&L ({currency})", format="%+.2f"),
                "unrealised_pnl_pct": st.column_config.NumberColumn("P&L %", format="%+.1f%%"),
                "stop_gap_pct":       st.column_config.NumberColumn("Above Stop %", format="%.1f%%"),
                "target_gap_pct":     st.column_config.NumberColumn("To Target %", format="%.1f%%"),
                "signal_score":       st.column_config.ProgressColumn(
                                          "Score", min_value=0, max_value=100, format="%.0f"),
            },
            use_container_width=True, hide_index=True,
        )

        # P&L distribution horizontal bar
        _sec("P&L Distribution")
        import plotly.graph_objects as go
        df_sorted = df.sort_values("unrealised_pnl", ascending=True)
        pnl_vals  = (df_sorted["unrealised_pnl"].fillna(0)).tolist()
        bar_colors = [_pnl_color(v) for v in pnl_vals]
        fig_bar = go.Figure(go.Bar(
            x=pnl_vals,
            y=df_sorted["ticker"].tolist(),
            orientation="h",
            marker_color=bar_colors,
        ))
        layout_bar = _chart_base(h=max(200, len(df) * 28), margin=(10, 10, 30, 10))
        layout_bar.update(
            xaxis=dict(tickprefix=currency,
                       gridcolor="#1a1b26", zeroline=True,
                       zerolinecolor="#334155", zerolinewidth=1),
            yaxis=dict(color="#94a3b8"),
            showlegend=False,
        )
        fig_bar.update_layout(**layout_bar)
        st.plotly_chart(fig_bar, use_container_width=True,
                        config={"displayModeBar": False, "responsive": True})

        # Allocation donut
        _sec("Position Allocation")
        fig_donut = _allocation_donut(positions, currency, h=320)
        if fig_donut:
            st.plotly_chart(fig_donut, use_container_width=True,
                            config={"displayModeBar": False, "responsive": True})


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Positions (detailed analysis)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💼 Positions":
    import pandas as pd
    import plotly.graph_objects as go
    import plotly.express as px

    st.markdown("## Position Monitor")
    if _market_open:
        st.caption("⚡ Live · 30 s")
    else:
        st.caption("Cached · 5 min refresh")

    portfolio = load_portfolio(exchange, live=_market_open)
    positions = portfolio.get("positions", [])

    if not positions:
        _info_card("No open positions yet.")
    else:
        total_invested      = portfolio.get("total_invested", 0) or 0
        total_current_value = portfolio.get("total_current_value", 0) or 0
        total_pnl           = portfolio.get("total_unrealised_pnl", 0) or 0
        total_pnl_pct       = (total_pnl / total_invested * 100) if total_invested else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Positions",      len(positions))
        c2.metric("Invested",       f"{currency}{total_invested:,.0f}")
        c3.metric("Current Value",  f"{currency}{total_current_value:,.0f}",
                  delta=_delta(total_current_value - total_invested, currency),
                  delta_color="normal")
        c4.metric("Unrealised P&L", f"{currency}{abs(total_pnl):,.0f}",
                  delta=_delta_pct(total_pnl_pct), delta_color="normal")

        st.divider()

        # Sparkline card grid
        _sec("Live Positions")
        positions_sorted = sorted(positions,
                                   key=lambda x: -(x.get("unrealised_pnl_pct") or 0))
        sparklines = fetch_sparklines([p["ticker"] for p in positions_sorted], 14)

        cols_per_row = 4
        for i in range(0, len(positions_sorted), cols_per_row):
            batch   = positions_sorted[i:i + cols_per_row]
            columns = st.columns(cols_per_row)
            for pos, col in zip(batch, columns):
                with col:
                    ticker  = pos.get("ticker", "")
                    pnl_pct = pos.get("unrealised_pnl_pct") or 0
                    pnl_col = _pnl_color(pnl_pct)
                    tv_url  = ticker_tv_url(ticker)
                    entry_p = pos.get("entry_price") or 0
                    sp_data = sparklines.get(ticker, [])

                    st.markdown(f'''
                    <div class="spark-card">
                      <div style="display:flex;justify-content:space-between;align-items:flex-start">
                        <a href="{tv_url}" target="_blank"
                           style="font-weight:700;color:#818cf8;font-size:0.9rem;text-decoration:none">
                           {ticker}
                        </a>
                        <span style="font-size:0.72rem;color:#475569">{pos.get("days_held",0)}d</span>
                      </div>
                      <div style="font-size:1.15rem;font-weight:700;color:{pnl_col};margin:4px 0">
                        {pnl_pct:+.2f}%
                      </div>
                      <div style="font-size:0.72rem;color:#475569">
                        Entry {currency}{entry_p:.3f}
                      </div>
                    </div>
                    ''', unsafe_allow_html=True)

                    if sp_data:
                        fig_sp = _sparkline_fig(sp_data, entry_p, ticker)
                        if fig_sp:
                            st.plotly_chart(fig_sp, use_container_width=True,
                                            config={"displayModeBar": False, "responsive": True})

        st.divider()

        # Full DataFrame with filters
        df = pd.DataFrame(positions)
        for col in ["current_price", "stop_loss_price", "target_price",
                    "entry_price", "shares", "invested", "current_value",
                    "unrealised_pnl", "unrealised_pnl_pct", "days_held",
                    "signal_score", "trading_mode", "entry_date"]:
            if col not in df.columns:
                df[col] = None

        df["stop_gap_pct"]   = (
            (df["current_price"].fillna(0) - df["stop_loss_price"].fillna(0))
            / df["current_price"].replace(0, float("nan")) * 100
        ).round(2)
        df["target_gap_pct"] = (
            (df["target_price"].fillna(0) - df["current_price"].fillna(0))
            / df["current_price"].replace(0, float("nan")) * 100
        ).round(2)
        df["pnl_pct"]     = (df["unrealised_pnl_pct"].fillna(0)).round(2)
        df["days_held"]   = df["days_held"].fillna(0).astype(int)
        df["capital_pct"] = (df["invested"].fillna(0) / _capital * 100).round(1)
        df["risk_at_stop"] = (
            (df["current_price"].fillna(0) - df["stop_loss_price"].fillna(0))
            * df["shares"].fillna(0)
        ).abs().round(0)

        def _mode_label(m):
            return {"ibkr_paper": "IBKR Paper", "live": "Live", "paper": "Internal"}.get(m, m or "Internal")
        df["mode_label"] = df["trading_mode"].apply(_mode_label) if "trading_mode" in df.columns else "Internal"

        def _status(row):
            pnl = row.get("pnl_pct") or 0
            sg  = row.get("stop_gap_pct") or 100
            tg  = row.get("target_gap_pct") or 100
            if sg <= 2:   return "Near Stop"
            if tg <= 3:   return "Near Target"
            if pnl >= 10: return "Strong Gain"
            if pnl > 0:   return "Profit"
            if pnl > -5:  return "Small Loss"
            return "At Loss"
        df["status"]  = df.apply(_status, axis=1)
        df["tv_link"] = df["ticker"].apply(ticker_tv_url)

        todays = get_todays_scores(df["ticker"].tolist(), exchange)
        def _score_today(row):
            today = todays.get(row["ticker"])
            if today is None:
                return "—"
            diff = today - (row.get("signal_score") or 0)
            arr  = "↑" if diff > 2 else ("↓" if diff < -2 else "→")
            return f"{today:.0f} {arr}"
        df["score_today"] = df.apply(_score_today, axis=1)

        _sec("Filters")
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)

        all_modes    = sorted(df["mode_label"].unique().tolist())
        sel_modes    = fc1.multiselect("Mode", all_modes, default=all_modes)
        all_statuses = sorted(df["status"].unique().tolist())
        sel_statuses = fc2.multiselect("Status", all_statuses, default=all_statuses)
        pnl_filter   = fc3.radio("Direction", ["All", "Profitable", "Losing"], horizontal=False)
        max_days     = int(df["days_held"].max()) if len(df) else 90
        days_range   = fc4.slider("Days Held", 0, max(max_days, 1), (0, max(max_days, 1)))
        min_score    = fc5.slider("Min Score", 0, 100, 0, step=5)

        sort_opts = {
            "P&L % best first":  ("pnl_pct",     False),
            "P&L % worst first": ("pnl_pct",     True),
            "Days held longest": ("days_held",   False),
            "Signal score best": ("signal_score", False),
            "Ticker A-Z":        ("ticker",       True),
        }
        sc1, _ = st.columns([2, 4])
        sort_choice = sc1.selectbox("Sort by", list(sort_opts.keys()))
        sort_field, sort_asc = sort_opts[sort_choice]

        filt = df.copy()
        if sel_modes:     filt = filt[filt["mode_label"].isin(sel_modes)]
        if sel_statuses:  filt = filt[filt["status"].isin(sel_statuses)]
        if pnl_filter == "Profitable": filt = filt[filt["pnl_pct"] > 0]
        elif pnl_filter == "Losing":   filt = filt[filt["pnl_pct"] <= 0]
        filt = filt[(filt["days_held"] >= days_range[0]) & (filt["days_held"] <= days_range[1])]
        if min_score > 0:
            filt = filt[filt["signal_score"].fillna(0) >= min_score]
        filt = filt.sort_values(sort_field, ascending=sort_asc)

        st.caption(f"Showing **{len(filt)}** of **{len(df)}** positions")

        _sec("Detailed View")
        if filt.empty:
            _info_card("No positions match the current filters.")
        else:
            dcols = ["mode_label", "status", "ticker", "tv_link",
                     "entry_date", "days_held",
                     "capital_pct", "invested", "current_value",
                     "entry_price", "current_price",
                     "unrealised_pnl", "pnl_pct",
                     "risk_at_stop", "stop_gap_pct", "target_gap_pct",
                     "signal_score", "score_today"]
            dcols = [c for c in dcols if c in filt.columns]
            st.dataframe(
                filt[dcols],
                column_config={
                    "mode_label":      "Mode",
                    "status":          "Status",
                    "ticker":          "Ticker",
                    "tv_link":         st.column_config.LinkColumn("Chart", display_text="TV ↗"),
                    "entry_date":      st.column_config.DateColumn("Entry", format="DD MMM YYYY"),
                    "days_held":       st.column_config.NumberColumn("Days", format="%d"),
                    "capital_pct":     st.column_config.NumberColumn("Capital %", format="%.1f%%"),
                    "invested":        st.column_config.NumberColumn(f"Invested ({currency})", format="%.0f"),
                    "current_value":   st.column_config.NumberColumn(f"Value ({currency})", format="%.0f"),
                    "entry_price":     st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                    "current_price":   st.column_config.NumberColumn(f"Price ({currency})", format="%.3f"),
                    "unrealised_pnl":  st.column_config.NumberColumn(f"P&L ({currency})", format="%+.2f"),
                    "pnl_pct":         st.column_config.NumberColumn("P&L %", format="%+.2f%%"),
                    "risk_at_stop":    st.column_config.NumberColumn(f"Risk at Stop ({currency})", format="%.0f"),
                    "stop_gap_pct":    st.column_config.NumberColumn("Above Stop %", format="%.1f%%"),
                    "target_gap_pct":  st.column_config.NumberColumn("To Target %", format="%.1f%%"),
                    "signal_score":    st.column_config.ProgressColumn(
                                           "Entry Score", min_value=0, max_value=100, format="%.0f"),
                    "score_today":     "Score Today",
                },
                use_container_width=True, hide_index=True,
                height=min(80 + len(filt) * 35, 600),
            )

            # Charts row
            col1, col2 = st.columns(2)
            with col1:
                sc = filt["status"].value_counts().reset_index()
                sc.columns = ["status", "count"]
                fig_pie = px.pie(
                    sc, values="count", names="status",
                    color_discrete_sequence=["#6366f1","#38bdf8","#a78bfa",
                                             "#94a3b8","#475569","#334155"],
                    hole=0.45,
                )
                layout_pie = _chart_base(h=300, margin=(10, 10, 10, 10))
                layout_pie.update(showlegend=True)
                fig_pie.update_layout(**layout_pie)
                fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_pie, use_container_width=True,
                                config={"displayModeBar": False, "responsive": True})
            with col2:
                fig_pnl = go.Figure(go.Bar(
                    x=filt.sort_values("pnl_pct")["ticker"].tolist(),
                    y=filt.sort_values("pnl_pct")["pnl_pct"].tolist(),
                    marker_color=[_pnl_color(v) for v in
                                  filt.sort_values("pnl_pct")["pnl_pct"].tolist()],
                ))
                fig_pnl.add_hline(y=0, line_dash="dot", line_color="#334155", line_width=1)
                layout_pnl = _chart_base(h=300, margin=(10, 20, 30, 10))
                layout_pnl.update(showlegend=False,
                                   yaxis=dict(ticksuffix="%", gridcolor="#1a1b26"))
                fig_pnl.update_layout(**layout_pnl)
                st.plotly_chart(fig_pnl, use_container_width=True,
                                config={"displayModeBar": False, "responsive": True})

        st.divider()
        _sec("Interactive Chart")
        pos_tickers = [p["ticker"] for p in positions]
        if pos_tickers:
            tv_sel = st.selectbox("Select ticker", pos_tickers, key="tv_sel_positions")
            _tv_widget(tv_sel, exchange, height=500)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trade History
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Trade History":
    import pandas as pd

    st.markdown("## Trade History")

    days_back = st.slider("Look-back period (days)", 30, 365, 90, step=30)
    trades    = load_trades(exchange, days_back)
    pnl_data  = load_pnl(exchange, days_back)

    if not trades:
        _info_card(f"No closed trades in the last {days_back} days.")
    else:
        total_net = sum(t.get("net_pnl") or 0 for t in trades)
        winners   = sum(1 for t in trades if (t.get("net_pnl") or 0) > 0)
        win_rate  = winners / len(trades) * 100 if trades else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Net Realised P&L", f"{currency}{total_net:+,.0f}",
                  delta="profit" if total_net >= 0 else "loss",
                  delta_color="normal")
        c2.metric("Closed Trades", len(trades))
        c3.metric("Win Rate", f"{win_rate:.0f}%")

        # P&L area chart
        fig_pnl = _pnl_area_chart(pnl_data, currency,
                                   f"Cumulative P&L ({days_back}-day window)")
        if fig_pnl:
            st.plotly_chart(fig_pnl, use_container_width=True,
                            config={"displayModeBar": False, "responsive": True})
        else:
            _info_card("No closed trades yet.")

        # Table + exit reasons donut
        col_table, col_pie = st.columns([3, 1])
        with col_table:
            _sec("Closed Trades")
            df = pd.DataFrame(trades)
            df["tv_link"] = df["ticker"].apply(ticker_tv_url)
            cols = ["ticker", "tv_link", "entry_date", "exit_date",
                    "entry_price", "exit_price",
                    "shares", "net_pnl", "exit_reason", "signal_score"]
            cols = [c for c in cols if c in df.columns]
            st.dataframe(
                df[cols],
                column_config={
                    "ticker":       "Ticker",
                    "tv_link":      st.column_config.LinkColumn("Chart", display_text="TV ↗"),
                    "entry_date":   st.column_config.DateColumn("Entry", format="DD MMM YYYY"),
                    "exit_date":    st.column_config.DateColumn("Exit", format="DD MMM YYYY"),
                    "entry_price":  st.column_config.NumberColumn(f"Entry ({currency})", format="%.3f"),
                    "exit_price":   st.column_config.NumberColumn(f"Exit ({currency})", format="%.3f"),
                    "shares":       st.column_config.NumberColumn("Shares", format="%.0f"),
                    "net_pnl":      st.column_config.NumberColumn(f"Net P&L ({currency})", format="%+.2f"),
                    "exit_reason":  "Reason",
                    "signal_score": st.column_config.ProgressColumn(
                                        "Score", min_value=0, max_value=100, format="%.0f"),
                },
                use_container_width=True, hide_index=True,
            )

        with col_pie:
            _sec("Exit Reasons")
            import plotly.express as px
            reasons_df = pd.DataFrame(trades)
            if "exit_reason" in reasons_df.columns:
                reasons = reasons_df["exit_reason"].value_counts().reset_index()
                reasons.columns = ["exit_reason", "count"]
                colour_map = {
                    "stop_loss":       "#f87171",
                    "intraday_stop":   "#fb923c",
                    "target":          "#4ade80",
                    "intraday_target": "#34d399",
                    "stale":           "#94a3b8",
                    "manual":          "#6366f1",
                    "regime":          "#a78bfa",
                }
                fig_r = px.pie(reasons, values="count", names="exit_reason",
                               color="exit_reason", color_discrete_map=colour_map, hole=0.45)
                layout_r = _chart_base(h=280, margin=(10, 10, 10, 10))
                layout_r.update(showlegend=True)
                fig_r.update_layout(**layout_r)
                fig_r.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_r, use_container_width=True,
                                config={"displayModeBar": False, "responsive": True})

        # Interactive chart
        _sec("Interactive Chart")
        traded_tickers = list({t["ticker"] for t in trades})
        if traded_tickers:
            tv_sel_hist = st.selectbox("Select ticker", sorted(traded_tickers), key="tv_sel_hist")
            _tv_widget(tv_sel_hist, exchange, height=480)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Backtest
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔬 Backtest":
    import pandas as pd

    st.markdown("## Walk-Forward Backtest")
    st.caption("Computed every Sunday 08:00 and cached. Covers the last 6 months of signals.")

    results = load_backtest(exchange)

    if not results:
        _info_card("No backtest results cached yet. Results are written to Supabase after the "
                   "Sunday morning run — check back Monday.")
    else:
        import plotly.graph_objects as go
        import plotly.express as px

        rows = []
        for ticker, metrics in results.items():
            if isinstance(metrics, dict):
                rows.append({
                    "ticker":           ticker,
                    "num_trades":       metrics.get("num_trades", 0) or 0,
                    "win_rate_pct":     round((metrics.get("win_rate") or 0) * 100, 1),
                    "avg_return_pct":   metrics.get("avg_return_pct", 0) or 0,
                    "sharpe":           metrics.get("sharpe", 0) or 0,
                    "max_drawdown_pct": metrics.get("max_drawdown_pct", 0) or 0,
                    "total_return_pct": metrics.get("total_return_pct", 0) or 0,
                })
        df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)

        profitable = (df["total_return_pct"] > 0).sum() if len(df) else 0
        avg_win    = df["win_rate_pct"].mean() if len(df) else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Tickers Tested",        len(df))
        c2.metric("Profitable Strategies", f"{profitable}/{len(df)}")
        c3.metric("Avg Win Rate",          f"{avg_win:.1f}%")

        st.dataframe(
            df,
            column_config={
                "ticker":           "Ticker",
                "num_trades":       st.column_config.NumberColumn("# Trades"),
                "win_rate_pct":     st.column_config.ProgressColumn(
                                        "Win Rate %", min_value=0, max_value=100, format="%.0f%%"),
                "avg_return_pct":   st.column_config.NumberColumn("Avg Return %", format="%+.1f%%"),
                "sharpe":           st.column_config.NumberColumn("Sharpe", format="%.2f"),
                "max_drawdown_pct": st.column_config.NumberColumn("Max DD %", format="%.1f%%"),
                "total_return_pct": st.column_config.NumberColumn("Total Return %", format="%+.1f%%"),
            },
            use_container_width=True, hide_index=True,
        )

        # Scatter: avg_return vs win_rate, sized by num_trades, coloured by sharpe
        _sec("Return vs Win Rate")
        if len(df) > 1:
            fig_scatter = px.scatter(
                df, x="avg_return_pct", y="win_rate_pct",
                size="num_trades", color="sharpe",
                color_continuous_scale=["#f87171", "#94a3b8", "#4ade80"],
                color_continuous_midpoint=0,
                hover_name="ticker",
                labels={
                    "avg_return_pct": "Avg Return %",
                    "win_rate_pct":   "Win Rate %",
                    "sharpe":         "Sharpe",
                },
                size_max=30,
            )
            fig_scatter.add_hline(y=55, line_dash="dash", line_color="#334155",
                                   annotation_text="55% threshold",
                                   annotation_position="top right",
                                   annotation_font_color="#475569")
            fig_scatter.add_vline(x=0, line_dash="dot", line_color="#334155")
            layout_sc = _chart_base(h=400, margin=(40, 30, 50, 10))
            layout_sc.update(coloraxis_colorbar=dict(
                tickfont=dict(color="#475569"), title=dict(font=dict(color="#475569"))))
            fig_scatter.update_layout(**layout_sc)
            st.plotly_chart(fig_scatter, use_container_width=True,
                            config={"displayModeBar": False, "responsive": True})

        # Bar: top 15 by Sharpe
        _sec("Top 15 by Sharpe")
        top15 = df.head(15)
        fig_bar = go.Figure(go.Bar(
            x=top15["ticker"].tolist(),
            y=top15["win_rate_pct"].tolist(),
            marker_color=[
                f"hsl({int(220 + s * 20)},70%,55%)"
                for s in top15["sharpe"].tolist()
            ],
            text=[f"{v:.0f}%" for v in top15["win_rate_pct"].tolist()],
            textposition="outside",
            textfont=dict(color="#94a3b8", size=10),
        ))
        fig_bar.add_hline(y=55, line_dash="dash", line_color="#334155",
                           annotation_text="55% threshold",
                           annotation_position="top right",
                           annotation_font_color="#475569")
        layout_bar2 = _chart_base(h=340, margin=(40, 30, 30, 10))
        layout_bar2.update(
            showlegend=False,
            yaxis=dict(ticksuffix="%", gridcolor="#1a1b26", range=[0, 100]),
        )
        fig_bar.update_layout(**layout_bar2)
        st.plotly_chart(fig_bar, use_container_width=True,
                        config={"displayModeBar": False, "responsive": True})
