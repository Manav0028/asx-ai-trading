"""
Layer 05 · Output — Daily Report Generator
Plain-English formatting with full context for each signal.
Exchange-agnostic: uses active exchange name, currency symbol, and index name.
"""
import logging
from datetime import date
from typing import Dict, List

from ai_engine.regime_filter import get_regime_summary
from ai_engine.sentiment import get_sentiment_meta
from ai_engine.technical_engine import get_technical_meta
from ai_engine.fundamental_scorer import get_fundamental_meta
from alerts.email_alerts import send_daily_email
from alerts.telegram_bot import send_daily_report
from config import get_active_exchange
from config.settings import TOP_N_DAILY_REPORT, SIGNAL_THRESHOLD
from signals.aggregator import get_top_signals
from signals.watchlist import get_watchlist_summary, update_watchlist_prices

logger = logging.getLogger(__name__)


def _score_emoji(score: float) -> str:
    if score >= 85: return "🔥"
    if score >= 75: return "🟢"
    if score >= 60: return "🟡"
    return "🔴"


def _pnl_emoji(pnl: float) -> str:
    return "📈" if pnl >= 0 else "📉"


def _upside(entry, target) -> str:
    if not entry or not target or entry == 0:
        return ""
    return f"+{(target - entry) / entry * 100:.1f}%"


def _format_signal_block(s: Dict, rank: int, currency: str) -> str:
    ticker = s["ticker"]
    score = s["composite_score"]
    entry = s.get("entry_price") or 0
    target = s.get("target_price") or 0
    stop = s.get("stop_loss_price") or 0
    pos = s.get("position_size_aud") or 0

    emoji = _score_emoji(score)
    upside = _upside(entry, target)

    sent_meta = get_sentiment_meta(ticker)
    tech_meta  = get_technical_meta(ticker)
    fund_meta  = get_fundamental_meta(ticker)

    news_theme = sent_meta.get("key_theme", "") or "mixed news"
    tech_signal = (tech_meta.get("signals") or [""])[0]

    summary_parts = []
    if news_theme:
        summary_parts.append(f"news: {news_theme}")
    if tech_signal:
        summary_parts.append(tech_signal.split("—")[0].strip().lower())
    summary = " | ".join(summary_parts[:2])

    return (
        f"{emoji} *{rank}. {ticker}* — `{score:.1f}/100`\n"
        f"   Buy `{currency}{entry:.2f}` → Target `{currency}{target:.2f}` ({upside}) | Stop `{currency}{stop:.2f}`\n"
        f"   Position: `{currency}{pos:,.0f}` | {summary}"
    )


def _format_watchlist_line(p: Dict, currency: str) -> str:
    pnl = p.get("unrealised_pnl") or 0
    pct = p.get("unrealised_pnl_pct") or 0
    days = p.get("days_held") or 0
    current = p.get("current_price") or 0
    stop = p.get("stop_loss_price") or 0
    target = p.get("target_price") or 0

    emoji = _pnl_emoji(pnl)
    stop_gap = f"{(current - stop) / current * 100:.1f}% to stop" if stop else ""
    target_gap = f"{(target - current) / current * 100:.1f}% to target" if target else ""

    return (
        f"{emoji} *{p['ticker']}* `{pct:+.1f}%` (`{currency}{pnl:+,.0f}`) | "
        f"{days}d held | {stop_gap} | {target_gap}"
    )


def generate_and_send() -> str:
    exchange = get_active_exchange()
    currency = exchange.currency_symbol
    today = date.today().strftime("%A %d %b %Y")

    update_watchlist_prices()

    regime = get_regime_summary()
    signals = get_top_signals(n=TOP_N_DAILY_REPORT)
    watchlist = get_watchlist_summary()

    regime_str = "BULLISH ✅" if regime["regime_ok"] else "CAUTIOUS ⚠️"
    index_val = regime.get("index", "N/A")
    ema200 = regime.get("ema200", "N/A")
    pct_above = regime.get("pct_above", 0) or 0
    index_name = regime.get("index_name", exchange.index_name)
    regime_note = (
        "All signals active." if regime["regime_ok"]
        else f"Position sizes halved — market {abs(pct_above):.1f}% below its 200-day average."
    )

    port_pnl  = watchlist["total_unrealised_pnl"]
    positions = watchlist["total_positions"]
    winners   = watchlist["winners"]
    losers    = watchlist["losers"]

    lines = [
        f"*{today}*",
        f"",
        f"🌏 *Market ({exchange.name}):* {regime_str}",
        f"{index_name} at `{index_val:,}` vs 200-day avg `{ema200:,}` ({pct_above:+.1f}%)",
        f"_{regime_note}_",
        f"",
        f"💼 *Portfolio:* {positions} positions | P&L `{currency}{port_pnl:+,.2f}`",
        f"   ✅ {winners} winning | ❌ {losers} losing",
        f"",
    ]

    if signals:
        lines.append(f"🏆 *Top {len(signals)} Signals Today (score ≥ {SIGNAL_THRESHOLD:.0f}):*")
        for i, sig in enumerate(signals, 1):
            lines.append(_format_signal_block(sig, i, currency))
            lines.append("")
    else:
        lines.append(f"_No stocks above the {SIGNAL_THRESHOLD:.0f} threshold today._")
        if not regime["regime_ok"]:
            lines.append("_Position sizes are halved while market is below its 200-day average._")
        lines.append("")

    if watchlist["positions"]:
        lines.append("📋 *Open Positions:*")
        for pos in watchlist["positions"]:
            lines.append(_format_watchlist_line(pos, currency))

    report_text = "\n".join(lines)

    send_daily_report(report_text)
    send_daily_email(signals, watchlist, regime)

    plain = report_text.replace("*", "").replace("`", "").replace("_", "")
    logger.info("Daily report sent:\n%s", plain)
    return report_text
