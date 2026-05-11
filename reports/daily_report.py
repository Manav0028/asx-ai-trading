"""
Layer 05 · Output — Daily Report Generator
Runs at 7:30 AM. Generates top 10 signal list + watchlist P&L + regime.
"""
import logging
from datetime import date
from typing import Dict

from ai_engine.regime_filter import get_regime_summary
from alerts.email_alerts import send_daily_email
from alerts.telegram_bot import send_daily_report
from config.settings import TOP_N_DAILY_REPORT
from signals.aggregator import get_top_signals
from signals.watchlist import get_watchlist_summary

logger = logging.getLogger(__name__)


def _format_signal_line(s: Dict, rank: int) -> str:
    ticker = s["ticker"]
    score = s["composite_score"]
    entry = s.get("entry_price") or 0
    target = s.get("target_price") or 0
    stop = s.get("stop_loss_price") or 0
    return (
        f"{rank}. *{ticker}* — Score: `{score:.1f}`\n"
        f"   Entry: `${entry:.3f}` | Target: `${target:.3f}` | Stop: `${stop:.3f}`"
    )


def _format_watchlist_line(p: Dict) -> str:
    pnl = p.get("unrealised_pnl") or 0
    pct = p.get("unrealised_pnl_pct") or 0
    days = p.get("days_held") or 0
    emoji = "📈" if pnl >= 0 else "📉"
    return f"{emoji} *{p['ticker']}* `{pct:+.1f}%` (`${pnl:+,.0f}`) | {days}d held"


def generate_and_send() -> str:
    today = date.today().strftime("%d %b %Y")
    regime = get_regime_summary()
    signals = get_top_signals(n=TOP_N_DAILY_REPORT)
    watchlist = get_watchlist_summary()

    # ── Build Telegram text ───────────────────────────────────────────────────
    regime_str = "RISK-ON ✅" if regime["regime_ok"] else "RISK-OFF ⚠️"
    lines = [
        f"*Date:* {today}",
        f"*Regime:* {regime_str} | XJO: `{regime['xjo']}` | EMA200: `{regime['ema200']}`",
        "",
        f"*Portfolio:* {watchlist['total_positions']} positions | "
        f"P&L: `${watchlist['total_unrealised_pnl']:+,.2f}`",
        "",
        f"*Top {len(signals)} Signals (≥75):*",
    ]

    for i, sig in enumerate(signals, 1):
        lines.append(_format_signal_line(sig, i))

    if watchlist["positions"]:
        lines.append("\n*Active Watchlist:*")
        for pos in watchlist["positions"][:5]:
            lines.append(_format_watchlist_line(pos))

    report_text = "\n".join(lines)

    # ── Send via Telegram ─────────────────────────────────────────────────────
    send_daily_report(report_text)

    # ── Send via email ────────────────────────────────────────────────────────
    send_daily_email(signals, watchlist, regime)

    # ── Log to stdout ─────────────────────────────────────────────────────────
    plain = report_text.replace("*", "").replace("`", "")
    logger.info("Daily report:\n%s", plain)

    return report_text
