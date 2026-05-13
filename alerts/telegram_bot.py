"""
Layer 05 · Alerts — Telegram Bot
All messages written in plain English with full context — no jargon.
Exchange-aware: uses active exchange name, currency symbol, and index name.
"""
import logging
from typing import Dict, List, Optional

import requests

from config.settings import SIGNAL_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _exchange():
    from config import get_active_exchange
    return get_active_exchange()


def _send(text: str, parse_mode: str = "Markdown") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured")
        return False
    try:
        url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


def _score_bar(score: float, length: int = 10) -> str:
    filled = round(score / 100 * length)
    return "█" * filled + "░" * (length - filled)


def _conviction_label(score: float) -> str:
    """Conviction tiers relative to the signal threshold (65 baseline)."""
    high = SIGNAL_THRESHOLD + 23   # ≥88 → Very High
    mid  = SIGNAL_THRESHOLD + 15   # ≥80 → High
    low  = SIGNAL_THRESHOLD + 10   # ≥75 → Moderate-High
    if score >= high: return "⭐⭐⭐ Very High"
    if score >= mid:  return "⭐⭐ High"
    if score >= low:  return "⭐ Moderate-High"
    return "— Moderate"


def _fmt(value: float, currency: str) -> str:
    """Format a price with exchange currency symbol."""
    return f"{currency}{value:,.2f}"


def _upside_pct(entry: float, target: float) -> str:
    if not entry or not target: return "N/A"
    return f"+{(target - entry) / entry * 100:.1f}%"


def _downside_pct(entry: float, stop: float) -> str:
    if not entry or not stop: return "N/A"
    return f"-{(entry - stop) / entry * 100:.1f}%"


# ── New Trade Signal ──────────────────────────────────────────────────────────

def send_signal_alert(
    signal: Dict,
    tech_meta: dict = None,
    fund_meta: dict = None,
    sent_meta: dict = None,
) -> bool:
    ex = _exchange()
    currency = ex.currency_symbol
    ticker = signal["ticker"]
    score  = signal["composite_score"]
    entry  = signal.get("entry_price") or 0
    target = signal.get("target_price") or 0
    stop   = signal.get("stop_loss_price") or 0
    pos    = signal.get("position_size_aud") or 0
    shares = int(pos / entry) if entry > 0 else 0

    conviction = _conviction_label(score)
    upside     = _upside_pct(entry, target)
    downside   = _downside_pct(entry, stop)

    s_sent = signal.get("sentiment_score", 50)
    s_fund = signal.get("fundamental_score", 50)
    s_tech = signal.get("technical_score", 50)
    s_ins  = signal.get("insider_score", 50)

    news_line    = (sent_meta or {}).get("reasoning", "Recent news is broadly positive.")
    fund_line    = (fund_meta or {}).get("highlights", "")
    tech_signals = (tech_meta or {}).get("signals", [])
    tech_line    = tech_signals[0] if tech_signals else "Technicals looking constructive."

    msg = (
        f"🟢 *NEW BUY SIGNAL — {ticker}* ({ex.name})\n"
        f"Conviction: {conviction}\n"
        f"Overall Score: `{score:.1f}/100` {_score_bar(score)}\n"
        f"\n"
        f"💰 *Trade Setup*\n"
        f"  Buy at:    `{_fmt(entry, currency)}`\n"
        f"  Target:    `{_fmt(target, currency)}` ({upside} potential gain)\n"
        f"  Stop-loss: `{_fmt(stop, currency)}` ({downside} max loss)\n"
        f"  Size:      `{shares} shares ≈ {_fmt(pos, currency)}`\n"
        f"\n"
        f"📊 *Why this stock?*\n"
        f"  News:     `{s_sent:.0f}/100` — {news_line}\n"
        f"  Business: `{s_fund:.0f}/100` — {fund_line}\n"
        f"  Chart:    `{s_tech:.0f}/100` — {tech_line}\n"
        f"  Insiders: `{s_ins:.0f}/100`\n"
        f"\n"
        f"⚠️ _Paper trade only — not real money_"
    )
    return _send(msg)


# ── Stop-Loss Triggered ───────────────────────────────────────────────────────

def send_stop_loss_alert(
    ticker: str, fill_price: float, pnl: float,
    entry_price: float = None, days_held: int = None,
) -> bool:
    currency = _exchange().currency_symbol
    loss_pct = abs(pnl / entry_price * 100) if entry_price else 0
    held_str = f" after {days_held} days" if days_held else ""
    msg = (
        f"🔴 *STOP-LOSS HIT — {ticker}*\n"
        f"\n"
        f"The stock dropped from entry, triggering the automatic safety exit{held_str}.\n"
        f"\n"
        f"  Sold at:   `{_fmt(fill_price, currency)}`\n"
        f"  Loss:      `{currency}{abs(pnl):,.2f}` ({loss_pct:.1f}% of position)\n"
        f"\n"
        f"✅ _Stop-losses protect capital — small losses keep you in the game._"
    )
    return _send(msg)


# ── Target Hit ────────────────────────────────────────────────────────────────

def send_target_alert(
    ticker: str, fill_price: float, pnl: float,
    entry_price: float = None, days_held: int = None,
) -> bool:
    currency = _exchange().currency_symbol
    gain_pct = (pnl / entry_price * 100) if entry_price else 0
    held_str = f" in {days_held} days" if days_held else ""
    msg = (
        f"🎯 *TARGET REACHED — {ticker}*\n"
        f"\n"
        f"The stock hit the profit target{held_str} and was sold automatically.\n"
        f"\n"
        f"  Sold at: `{_fmt(fill_price, currency)}`\n"
        f"  Profit:  `{currency}{pnl:,.2f}` (+{gain_pct:.1f}% gain) ✅\n"
        f"\n"
        f"💼 _Profits locked in. Looking for the next opportunity._"
    )
    return _send(msg)


# ── Daily Report ──────────────────────────────────────────────────────────────

def send_daily_report(report_text: str) -> bool:
    ex = _exchange()
    return _send(f"📊 *{ex.name.upper()} DAILY REPORT*\n\n{report_text}")


# ── Regime Change ─────────────────────────────────────────────────────────────

def send_regime_change(regime_ok: bool, index_val: float, ema200: float) -> bool:
    ex = _exchange()
    pct = (index_val - ema200) / ema200 * 100
    if regime_ok:
        msg = (
            f"✅ *MARKET TURNED BULLISH — {ex.name}*\n"
            f"\n"
            f"The {ex.index_name} has climbed back above its 200-day average — "
            f"a positive sign for the broader market.\n"
            f"\n"
            f"  {ex.index_name}: `{index_val:,.0f}` ({pct:+.1f}% above average)\n"
            f"\n"
            f"🟢 _Signals are now fully active. New trade alerts may follow._"
        )
    else:
        msg = (
            f"⚠️ *MARKET TURNED CAUTIOUS — {ex.name}*\n"
            f"\n"
            f"The {ex.index_name} has dropped below its 200-day average — "
            f"historically a sign of broader market weakness. Position sizes are "
            f"halved as a precaution.\n"
            f"\n"
            f"  {ex.index_name}: `{index_val:,.0f}` ({pct:.1f}% below average)\n"
            f"\n"
            f"🔴 _New positions at half normal size until market recovers._"
        )
    return _send(msg)


# ── Stale Position ────────────────────────────────────────────────────────────

def send_stale_exit_alert(ticker: str, fill_price: float, pnl: float, days_held: int) -> bool:
    currency = _exchange().currency_symbol
    direction = "profit" if pnl >= 0 else "small loss"
    msg = (
        f"⏱ *POSITION CLOSED — {ticker}* (time-based exit)\n"
        f"\n"
        f"This stock was held for {days_held} days without a meaningful move, "
        f"so it was sold to free up capital for better opportunities.\n"
        f"\n"
        f"  Sold at: `{_fmt(fill_price, currency)}`\n"
        f"  Result:  `{currency}{pnl:+,.2f}` ({direction})\n"
    )
    return _send(msg)


# ── Weekly Summary ────────────────────────────────────────────────────────────

def send_weekly_summary(
    backtest_results: dict,
    top_signals: list,
    portfolio_summary: dict,
    regime: dict,
) -> bool:
    ex = _exchange()
    currency = ex.currency_symbol
    wins     = sum(1 for r in backtest_results.values()
                   if isinstance(r, dict) and r.get("win_rate", 0) >= 0.55)
    total    = len(backtest_results)
    port_pnl = portfolio_summary.get("total_unrealised_pnl", 0)
    positions = portfolio_summary.get("total_positions", 0)

    top_lines = ""
    for i, s in enumerate(top_signals[:5], 1):
        ep = s.get("entry_price", 0)
        top_lines += (
            f"  {i}. *{s['ticker']}* — Score `{s['composite_score']:.0f}` "
            f"at `{_fmt(ep, currency)}`\n"
        )

    regime_str = "Bullish ✅" if regime.get("regime_ok") else "Cautious ⚠️"
    index_val  = regime.get("index", regime.get("xjo", "N/A"))

    msg = (
        f"📅 *WEEKLY SUMMARY — {ex.name}*\n"
        f"\n"
        f"*Market:* {regime_str} | {ex.index_name} `{index_val}`\n"
        f"*Portfolio:* {positions} open positions | P&L `{currency}{port_pnl:+,.2f}`\n"
        f"\n"
        f"*Backtest (last 6 months):*\n"
        f"  {wins}/{total} strategies beating 55% win rate\n"
        f"\n"
        f"*Top 5 Stocks on Radar:*\n"
        f"{top_lines}"
        f"\n"
        f"_Full analysis runs Sunday morning._"
    )
    return _send(msg)


# ── Volume Spike Alert ────────────────────────────────────────────────────────

def send_volume_spike_alert(
    ticker: str, price: float, volume_ratio: float, score: float,
) -> bool:
    currency = _exchange().currency_symbol
    msg = (
        f"📈 *UNUSUAL ACTIVITY — {ticker}*\n"
        f"\n"
        f"Trading volume is *{volume_ratio:.1f}× the normal level* today at "
        f"`{_fmt(price, currency)}`. This often signals institutional buying "
        f"or a major news catalyst.\n"
        f"\n"
        f"  Current signal score: `{score:.0f}/100`\n"
        f"\n"
        f"_Worth watching — no trade placed yet._"
    )
    return _send(msg)


# ── Test Message ──────────────────────────────────────────────────────────────

def send_test_message() -> bool:
    ex = _exchange()
    return _send(
        f"✅ *AI Trading System — {ex.name}* — Telegram connected successfully!"
    )
