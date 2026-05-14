"""
Layer 05 · Output — Daily Report Generator
Each report has a prominent exchange banner so ASX and NSE reports
are immediately distinguishable in Telegram.
"""
import logging
from datetime import date
from typing import Dict, List

from ai_engine.regime_filter import get_regime_summary
from ai_engine.sentiment import get_sentiment_meta
from ai_engine.technical_engine import get_technical_meta
from ai_engine.fundamental_scorer import get_fundamental_meta
from alerts.email_alerts import send_daily_email
from alerts.telegram_bot import _send
from config import get_active_exchange
from config.settings import TOP_N_DAILY_REPORT, SIGNAL_THRESHOLD
from signals.aggregator import get_top_signals
from signals.watchlist import get_watchlist_summary, update_watchlist_prices

logger = logging.getLogger(__name__)

_MD_SPECIAL = str.maketrans({"*": "", "_": "", "`": "", "[": "", "]": ""})

def _safe(text: str, max_len: int = 90) -> str:
    """Strip Markdown special chars from dynamic content and truncate."""
    cleaned = str(text or "").translate(_MD_SPECIAL).strip()
    return cleaned[:max_len] + "…" if len(cleaned) > max_len else cleaned


def _score_emoji(score: float) -> str:
    if score >= 85: return "🔥"
    if score >= 75: return "🟢"
    if score >= 65: return "🟡"
    return "🔴"


def _pnl_emoji(pnl: float) -> str:
    return "📈" if pnl >= 0 else "📉"


def _upside(entry, target) -> str:
    if not entry or not target or entry == 0:
        return ""
    return f"+{(target - entry) / entry * 100:.1f}%"


def _score_bar(score: float, length: int = 8) -> str:
    filled = round(score / 100 * length)
    return "█" * filled + "░" * (length - filled)


def _format_signal_block(s: Dict, rank: int, currency: str) -> str:
    ticker  = s["ticker"]
    score   = s["composite_score"]
    entry   = s.get("entry_price") or 0
    target  = s.get("target_price") or 0
    stop    = s.get("stop_loss_price") or 0
    pos     = s.get("position_size_aud") or 0
    shares  = int(pos / entry) if entry > 0 else 0
    regime_ok = s.get("regime_ok", True)

    emoji   = _score_emoji(score)
    upside  = _upside(entry, target)
    bar     = _score_bar(score)
    size_note = "½ size — cautious market" if not regime_ok else "full size"

    sent_meta  = get_sentiment_meta(ticker)
    tech_meta  = get_technical_meta(ticker)
    fund_meta  = get_fundamental_meta(ticker)

    news_theme  = _safe(sent_meta.get("key_theme") or "mixed news", 50)
    news_reason = _safe(sent_meta.get("reasoning") or news_theme, 85)
    tech_sigs   = tech_meta.get("signals") or []
    tech_line   = _safe(tech_sigs[0] if tech_sigs else "Technicals constructive", 70)
    fund_raw    = fund_meta.get("highlights", "") or ""
    fund_line   = _safe(fund_raw.split(".")[0] if fund_raw else "Data loading", 70)

    return (
        f"\n{emoji} *#{rank} {ticker}* `{score:.1f}/100` {bar}\n"
        f"  💰 Buy `{currency}{entry:.2f}` → Target `{currency}{target:.2f}` ({upside}) | Stop `{currency}{stop:.2f}`\n"
        f"  📦 {shares} shares ≈ `{currency}{pos:,.0f}` ({size_note})\n"
        f"  📰 News `{s.get('sentiment_score',50):.0f}` — {news_reason}\n"
        f"  📊 Chart `{s.get('technical_score',50):.0f}` — {tech_line}\n"
        f"  🏦 Biz `{s.get('fundamental_score',50):.0f}` — {fund_line}"
    )


def _format_watchlist_line(p: Dict, currency: str) -> str:
    pnl     = p.get("unrealised_pnl") or 0
    pct     = p.get("unrealised_pnl_pct") or 0
    days    = p.get("days_held") or 0
    current = p.get("current_price") or 0
    stop    = p.get("stop_loss_price") or 0
    target  = p.get("target_price") or 0
    ticker  = p["ticker"]

    emoji      = _pnl_emoji(pnl)
    stop_gap   = f"{(current - stop) / current * 100:.1f}% above stop" if stop and current else "—"
    target_gap = f"{(target - current) / current * 100:.1f}% to target" if target and current else "—"

    return (
        f"  {emoji} *{ticker}* `{pct:+.1f}%` (`{currency}{pnl:+,.0f}`) | "
        f"{days}d | {stop_gap} | {target_gap}"
    )


def generate_and_send() -> str:
    exchange   = get_active_exchange()
    currency   = exchange.currency_symbol
    flag       = exchange.flag
    exch_name  = exchange.name
    today      = date.today().strftime("%A %d %b %Y")

    update_watchlist_prices()

    regime   = get_regime_summary()
    signals  = get_top_signals(n=TOP_N_DAILY_REPORT)
    watchlist = get_watchlist_summary()

    regime_ok   = regime["regime_ok"]
    regime_str  = "BULLISH ✅" if regime_ok else "CAUTIOUS ⚠️"
    index_val   = regime.get("index", "N/A")
    ema200      = regime.get("ema200", "N/A")
    pct_above   = regime.get("pct_above", 0) or 0
    index_name  = regime.get("index_name", exchange.index_name)

    if regime_ok:
        regime_note = "All signals fully active — normal position sizes."
    else:
        regime_note = (
            f"Market is {abs(pct_above):.1f}% below its 200-day average. "
            f"Position sizes halved as a precaution — signals still fire."
        )

    port_pnl  = watchlist["total_unrealised_pnl"]
    positions = watchlist["total_positions"]
    winners   = watchlist["winners"]
    losers    = watchlist["losers"]

    # ── Header ────────────────────────────────────────────────────────────────
    lines = [
        f"📊 *DAILY REPORT*",
        f"{'─' * 30}",
        f"{flag} *{exch_name}*",
        f"{'─' * 30}",
        f"",
        f"📅 *{today}*",
        f"",
        f"🌏 *Market:* {regime_str}",
        f"`{index_name}` at `{index_val:,}` | 200d avg `{ema200:,}` ({pct_above:+.1f}%)",
        f"_{regime_note}_",
        f"",
        f"💼 *Portfolio* — {positions} open positions",
        f"  P&L: `{currency}{port_pnl:+,.2f}` | "
        f"✅ {winners} winning  ❌ {losers} losing",
        f"",
    ]

    # ── Signals ───────────────────────────────────────────────────────────────
    if signals:
        lines.append(f"🏆 *Top Signals — Score ≥ {SIGNAL_THRESHOLD:.0f}:*")
        for i, sig in enumerate(signals, 1):
            lines.append(_format_signal_block(sig, i, currency))
    else:
        lines.append(f"_No stocks above the {SIGNAL_THRESHOLD:.0f} threshold today._")
        if not regime_ok:
            lines.append(
                f"_Tip: Market needs to recover {abs(pct_above):.1f}% "
                f"to reach its 200-day average ({ema200:,}). "
                f"Scores are unaffected — trades fire as soon as stocks qualify._"
            )

    lines.append("")

    # ── Watchlist ─────────────────────────────────────────────────────────────
    if watchlist["positions"]:
        lines.append("📋 *Open Positions:*")
        for pos in watchlist["positions"]:
            lines.append(_format_watchlist_line(pos, currency))
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += [
        f"{'─' * 30}",
        f"_Next report tomorrow 7:30 AM | Orders placed at market open_",
    ]

    report_text = "\n".join(lines)

    # Send to Telegram (no extra prefix — the report header IS the badge)
    _send(report_text)
    send_daily_email(signals, watchlist, regime)

    plain = report_text.replace("*", "").replace("`", "").replace("_", "")
    logger.info("Daily report sent:\n%s", plain)
    return report_text
