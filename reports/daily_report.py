"""
Layer 05 · Output — Daily Report Generator (Enhanced)
Plain-English formatting with full context for each signal.
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
from config.settings import TOP_N_DAILY_REPORT
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


def _format_signal_block(s: Dict, rank: int) -> str:
    ticker = s["ticker"]
    score = s["composite_score"]
    entry = s.get("entry_price") or 0
    target = s.get("target_price") or 0
    stop = s.get("stop_loss_price") or 0
    pos = s.get("position_size_aud") or 0

    emoji = _score_emoji(score)
    upside = _upside(entry, target)

    # Pull cached AI metadata
    sent_meta = get_sentiment_meta(ticker)
    tech_meta  = get_technical_meta(ticker)
    fund_meta  = get_fundamental_meta(ticker)

    news_theme = sent_meta.get("key_theme", "") or "mixed news"
    tech_signal = (tech_meta.get("signals") or [""])[0]
    fund_high   = fund_meta.get("highlights", "")

    # One-line plain-English summary
    summary_parts = []
    if news_theme:
        summary_parts.append(f"news: {news_theme}")
    if tech_signal:
        summary_parts.append(tech_signal.split("—")[0].strip().lower())
    summary = " | ".join(summary_parts[:2])

    line = (
        f"{emoji} *{rank}. {ticker}* — `{score:.1f}/100`\n"
        f"   Buy `${entry:.2f}` → Target `${target:.2f}` ({upside}) | Stop `${stop:.2f}`\n"
        f"   Position: `${pos:,.0f}` | {summary}"
    )
    return line


def _format_watchlist_line(p: Dict) -> str:
    pnl = p.get("unrealised_pnl") or 0
    pct = p.get("unrealised_pnl_pct") or 0
    days = p.get("days_held") or 0
    entry = p.get("entry_price") or 0
    current = p.get("current_price") or 0
    stop = p.get("stop_loss_price") or 0
    target = p.get("target_price") or 0

    emoji = _pnl_emoji(pnl)
    stop_gap = f"{(current - stop) / current * 100:.1f}% to stop" if stop else ""
    target_gap = f"{(target - current) / current * 100:.1f}% to target" if target else ""

    return (
        f"{emoji} *{p['ticker']}* `{pct:+.1f}%` (`${pnl:+,.0f}`) | "
        f"{days}d held | {stop_gap} | {target_gap}"
    )


def generate_and_send() -> str:
    today = date.today().strftime("%A %d %b %Y")

    # Refresh watchlist prices first
    update_watchlist_prices()

    regime = get_regime_summary()
    signals = get_top_signals(n=TOP_N_DAILY_REPORT)
    watchlist = get_watchlist_summary()

    regime_str = "BULLISH ✅" if regime["regime_ok"] else "CAUTIOUS ⚠️"
    xjo = regime.get("xjo", "N/A")
    ema200 = regime.get("ema200", "N/A")
    pct_above = regime.get("pct_above", 0)
    regime_note = (
        "All signals active." if regime["regime_ok"]
        else f"Scores reduced 20% — market {abs(pct_above):.1f}% below its 200-day average."
    )

    port_pnl  = watchlist["total_unrealised_pnl"]
    positions = watchlist["total_positions"]
    winners   = watchlist["winners"]
    losers    = watchlist["losers"]

    lines = [
        f"*{today}*",
        f"",
        f"🌏 *Market:* {regime_str}",
        f"ASX 200 at `{xjo:,}` vs 200-day avg `{ema200:,}` ({pct_above:+.1f}%)",
        f"_{regime_note}_",
        f"",
        f"💼 *Portfolio:* {positions} positions | P&L `${port_pnl:+,.2f}`",
        f"   ✅ {winners} winning | ❌ {losers} losing",
        f"",
    ]

    if signals:
        lines.append(f"🏆 *Top {len(signals)} Signals Today (score ≥ 75):*")
        for i, sig in enumerate(signals, 1):
            lines.append(_format_signal_block(sig, i))
            lines.append("")
    else:
        lines.append("_No stocks above the 75 threshold today._")
        if not regime["regime_ok"]:
            lines.append("_Scores are reduced while market is below its 200-day average._")
        lines.append("")

    if watchlist["positions"]:
        lines.append("📋 *Open Positions:*")
        for pos in watchlist["positions"]:
            lines.append(_format_watchlist_line(pos))

    report_text = "\n".join(lines)

    send_daily_report(report_text)
    send_daily_email(signals, watchlist, regime)

    plain = report_text.replace("*", "").replace("`", "").replace("_", "")
    logger.info("Daily report sent:\n%s", plain)
    return report_text
