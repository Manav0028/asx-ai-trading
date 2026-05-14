"""
Layer 05 · Alerts — Telegram Bot
Every message carries a clear exchange badge so ASX and NSE alerts
are instantly distinguishable in the same chat.
Exchange-aware: currency symbol, index name, and country flag are all
read from the active exchange at send-time.
"""
import logging
from typing import Dict, List, Optional

import requests

from config.settings import SIGNAL_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ── Exchange badge helpers ────────────────────────────────────────────────────

def _exchange_badge() -> str:
    """Returns e.g. '🇦🇺 ASX 200' or '🇮🇳 NSE NIFTY 100'."""
    try:
        from config import get_active_exchange
        ex = get_active_exchange()
        return f"{ex.flag} {ex.name}"
    except Exception:
        return "📈 Market"


def _currency() -> str:
    try:
        from config import get_active_exchange
        return get_active_exchange().currency_symbol
    except Exception:
        return "$"


def _index_name() -> str:
    try:
        from config import get_active_exchange
        return get_active_exchange().index_name
    except Exception:
        return "Index"


# ── Core sender ───────────────────────────────────────────────────────────────

def _send(text: str, parse_mode: str = "Markdown") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured")
        return False
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN),
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


# ── Formatting helpers ────────────────────────────────────────────────────────

def _score_bar(score: float, length: int = 10) -> str:
    filled = round(score / 100 * length)
    return "█" * filled + "░" * (length - filled)


def _conviction(score: float) -> str:
    """Conviction tiers relative to SIGNAL_THRESHOLD so they scale with any threshold."""
    if score >= SIGNAL_THRESHOLD + 23: return "⭐⭐⭐ Very High"
    if score >= SIGNAL_THRESHOLD + 15: return "⭐⭐ High"
    if score >= SIGNAL_THRESHOLD + 10: return "⭐ Moderate-High"
    return "— Moderate"

# Backward-compat alias
_conviction_label = _conviction


def _divider(badge: str) -> str:
    return f"{'─' * 30}\n{badge}\n{'─' * 30}"


def _upside_pct(entry: float, target: float) -> str:
    if not entry or not target: return "N/A"
    return f"+{(target - entry) / entry * 100:.1f}%"


def _downside_pct(entry: float, stop: float) -> str:
    if not entry or not stop: return "N/A"
    return f"-{(entry - stop) / entry * 100:.1f}%"


# ── New Trade Signal ──────────────────────────────────────────────────────────

def send_signal_alert(signal: Dict, tech_meta: dict = None,
                      fund_meta: dict = None, sent_meta: dict = None) -> bool:
    badge    = _exchange_badge()
    cur      = _currency()
    ticker   = signal["ticker"]
    score    = signal["composite_score"]
    entry    = signal.get("entry_price") or 0
    target   = signal.get("target_price") or 0
    stop     = signal.get("stop_loss_price") or 0
    pos      = signal.get("position_size_aud") or 0
    shares   = int(pos / entry) if entry > 0 else 0

    upside   = _upside_pct(entry, target)
    downside = _downside_pct(entry, stop)

    s_sent = signal.get("sentiment_score", 50)
    s_fund = signal.get("fundamental_score", 50)
    s_tech = signal.get("technical_score", 50)
    s_ins  = signal.get("insider_score", 50)

    news_line = (sent_meta or {}).get("reasoning", "Recent news is broadly positive.")
    fund_line = (fund_meta or {}).get("highlights", "")
    tech_sigs = (tech_meta or {}).get("signals", [])
    tech_line = tech_sigs[0] if tech_sigs else "Technicals looking constructive."

    msg = (
        f"🟢 *NEW BUY SIGNAL*\n"
        f"{_divider(badge)}\n"
        f"\n"
        f"*{ticker}* — Conviction: {_conviction(score)}\n"
        f"Score: `{score:.1f}/100` {_score_bar(score)}\n"
        f"\n"
        f"💰 *Trade Setup*\n"
        f"  Buy at:    `{cur}{entry:.2f}`\n"
        f"  Target:    `{cur}{target:.2f}` ({upside} upside)\n"
        f"  Stop-loss: `{cur}{stop:.2f}` ({downside} max loss)\n"
        f"  Position:  `{shares} shares ≈ {cur}{pos:,.0f}`\n"
        f"\n"
        f"📊 *Why this stock?*\n"
        f"  News     `{s_sent:.0f}/100` — {news_line}\n"
        f"  Business `{s_fund:.0f}/100` — {fund_line}\n"
        f"  Chart    `{s_tech:.0f}/100` — {tech_line}\n"
        f"  Insiders `{s_ins:.0f}/100`\n"
        f"\n"
        f"⚠️ _Paper trade only — not real money_"
    )
    return _send(msg)


# ── Stop-Loss Triggered ───────────────────────────────────────────────────────

def send_stop_loss_alert(ticker: str, fill_price: float, pnl: float,
                         entry_price: float = None, days_held: int = None) -> bool:
    badge    = _exchange_badge()
    cur      = _currency()
    loss_pct = abs(pnl / entry_price * 100) if entry_price else 0
    held_str = f" after {days_held} days" if days_held else ""
    msg = (
        f"🔴 *STOP-LOSS HIT*\n"
        f"{_divider(badge)}\n"
        f"\n"
        f"*{ticker}* dropped from entry, triggering the automatic safety exit{held_str}.\n"
        f"\n"
        f"  Sold at: `{cur}{fill_price:.2f}`\n"
        f"  Loss:    `{cur}{abs(pnl):,.2f}` ({loss_pct:.1f}% of position)\n"
        f"\n"
        f"✅ _Small losses protect capital — staying in the game._"
    )
    return _send(msg)


# ── Target Hit ────────────────────────────────────────────────────────────────

def send_target_alert(ticker: str, fill_price: float, pnl: float,
                      entry_price: float = None, days_held: int = None) -> bool:
    badge    = _exchange_badge()
    cur      = _currency()
    gain_pct = (pnl / entry_price * 100) if entry_price else 0
    held_str = f" in {days_held} days" if days_held else ""
    msg = (
        f"🎯 *TARGET REACHED*\n"
        f"{_divider(badge)}\n"
        f"\n"
        f"*{ticker}* hit the profit target{held_str} and was sold automatically.\n"
        f"\n"
        f"  Sold at: `{cur}{fill_price:.2f}`\n"
        f"  Profit:  `{cur}{pnl:,.2f}` (+{gain_pct:.1f}%) ✅\n"
        f"\n"
        f"💼 _Profit locked in. Scanning for the next opportunity._"
    )
    return _send(msg)


# ── Daily Report ──────────────────────────────────────────────────────────────

def send_daily_report(report_text: str) -> bool:
    # The report body already contains the full exchange banner — no prefix needed
    return _send(report_text)


# ── Regime Change ─────────────────────────────────────────────────────────────

def send_regime_change(regime_ok: bool, index_val: float, ema200: float) -> bool:
    badge = _exchange_badge()
    idx   = _index_name()
    pct   = (index_val - ema200) / ema200 * 100
    if regime_ok:
        msg = (
            f"✅ *MARKET TURNED BULLISH*\n"
            f"{_divider(badge)}\n"
            f"\n"
            f"The {idx} has climbed back above its 200-day average — a positive sign.\n"
            f"\n"
            f"  {idx}: `{index_val:,.0f}` ({pct:+.1f}% above average)\n"
            f"\n"
            f"🟢 _Full signals active. New trade alerts may follow._"
        )
    else:
        msg = (
            f"⚠️ *MARKET TURNED CAUTIOUS*\n"
            f"{_divider(badge)}\n"
            f"\n"
            f"The {idx} dropped below its 200-day average. Position sizes halved as a precaution.\n"
            f"\n"
            f"  {idx}: `{index_val:,.0f}` ({pct:.1f}% below average)\n"
            f"\n"
            f"🔴 _Smaller positions until market recovers._"
        )
    return _send(msg)


# ── Stale Position ────────────────────────────────────────────────────────────

def send_stale_exit_alert(ticker: str, fill_price: float, pnl: float, days_held: int) -> bool:
    badge     = _exchange_badge()
    cur       = _currency()
    direction = "small profit" if pnl >= 0 else "small loss"
    msg = (
        f"⏱ *TIME-BASED EXIT*\n"
        f"{_divider(badge)}\n"
        f"\n"
        f"*{ticker}* was held {days_held} days without a meaningful move.\n"
        f"Sold to free up capital for better opportunities.\n"
        f"\n"
        f"  Sold at: `{cur}{fill_price:.2f}`\n"
        f"  Result:  `{cur}{pnl:+,.2f}` ({direction})\n"
    )
    return _send(msg)


# ── Volume Spike Alert ────────────────────────────────────────────────────────

def send_volume_spike_alert(ticker: str, price: float, volume_ratio: float, score: float) -> bool:
    badge = _exchange_badge()
    cur   = _currency()
    msg = (
        f"📈 *UNUSUAL ACTIVITY*\n"
        f"{_divider(badge)}\n"
        f"\n"
        f"*{ticker}* is trading at *{volume_ratio:.1f}× normal volume* at `{cur}{price:.2f}`.\n"
        f"This often signals institutional buying or a major news catalyst.\n"
        f"\n"
        f"  Signal score: `{score:.0f}/100`\n"
        f"\n"
        f"_Watching closely — no trade placed yet._"
    )
    return _send(msg)


# ── Weekly Summary ────────────────────────────────────────────────────────────

def send_weekly_summary(backtest_results: dict, top_signals: list,
                        portfolio_summary: dict, regime: dict) -> bool:
    badge     = _exchange_badge()
    cur       = _currency()
    wins      = sum(1 for r in backtest_results.values()
                    if isinstance(r, dict) and r.get("win_rate", 0) >= 0.55)
    total     = len(backtest_results)
    port_pnl  = portfolio_summary.get("total_unrealised_pnl", 0)
    positions = portfolio_summary.get("total_positions", 0)
    regime_str = "Bullish ✅" if regime.get("regime_ok") else "Cautious ⚠️"
    # Support both 'index' (new) and 'xjo' (legacy) regime dict keys
    index_val = regime.get("index", regime.get("xjo", "N/A"))

    top_lines = ""
    for i, s in enumerate(top_signals[:5], 1):
        ep = s.get("entry_price", 0)
        top_lines += f"  {i}. *{s['ticker']}* — Score `{s['composite_score']:.0f}` @ `{cur}{ep:.2f}`\n"

    msg = (
        f"📅 *WEEKLY SUMMARY*\n"
        f"{_divider(badge)}\n"
        f"\n"
        f"*Market:* {regime_str} | {_index_name()} `{index_val}`\n"
        f"*Portfolio:* {positions} open | P&L `{cur}{port_pnl:+,.2f}`\n"
        f"\n"
        f"*Backtest (6 months):* {wins}/{total} strategies ≥ 55% win rate\n"
        f"\n"
        f"*Top 5 on Radar:*\n{top_lines}"
        f"\n"
        f"_Full summaries follow. Next report: tomorrow 7:30 AM._"
    )
    return _send(msg)


# ── Test Message ──────────────────────────────────────────────────────────────

def send_test_message() -> bool:
    badge = _exchange_badge()
    return _send(f"✅ *{badge}* — Trading system connected successfully!")
