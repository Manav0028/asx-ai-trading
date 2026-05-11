"""
Layer 05 · Alerts — Telegram Bot
Sends signal alerts, stop-loss triggers, and daily reports via Telegram.
"""
import logging
from typing import Dict, List, Optional

import requests

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send(text: str, parse_mode: str = "Markdown") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — skipping message")
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


def send_signal_alert(signal: Dict) -> bool:
    ticker = signal["ticker"]
    score = signal["composite_score"]
    entry = signal.get("entry_price", 0)
    target = signal.get("target_price", 0)
    stop = signal.get("stop_loss_price", 0)
    pos_aud = signal.get("position_size_aud", 0)

    text = (
        f"🟢 *NEW SIGNAL: {ticker}*\n"
        f"Score: `{score:.1f}/100`\n"
        f"Entry: `${entry:.3f}` | Target: `${target:.3f}` | Stop: `${stop:.3f}`\n"
        f"Position size: `${pos_aud:,.0f}`\n"
        f"Sentiment: `{signal.get('sentiment_score', 0):.0f}` | "
        f"Fund: `{signal.get('fundamental_score', 0):.0f}` | "
        f"Tech: `{signal.get('technical_score', 0):.0f}` | "
        f"Insider: `{signal.get('insider_score', 0):.0f}`"
    )
    return _send(text)


def send_stop_loss_alert(ticker: str, fill_price: float, pnl: float) -> bool:
    emoji = "🔴" if pnl < 0 else "🟡"
    text = (
        f"{emoji} *STOP-LOSS TRIGGERED: {ticker}*\n"
        f"Fill: `${fill_price:.3f}`\n"
        f"P&L: `${pnl:+,.2f}`"
    )
    return _send(text)


def send_target_alert(ticker: str, fill_price: float, pnl: float) -> bool:
    text = (
        f"🎯 *TARGET HIT: {ticker}*\n"
        f"Fill: `${fill_price:.3f}`\n"
        f"P&L: `${pnl:+,.2f}` ✅"
    )
    return _send(text)


def send_daily_report(report_text: str) -> bool:
    return _send(f"📊 *ASX DAILY REPORT*\n\n{report_text}")


def send_regime_change(regime_ok: bool, xjo: float, ema200: float) -> bool:
    if regime_ok:
        text = f"✅ *REGIME: RISK-ON*\nXJO `{xjo:.0f}` > EMA200 `{ema200:.0f}`"
    else:
        text = f"⚠️ *REGIME: RISK-OFF*\nXJO `{xjo:.0f}` < EMA200 `{ema200:.0f}` — signals suppressed"
    return _send(text)


def send_test_message() -> bool:
    return _send("✅ ASX AI Trading System — Telegram connected successfully!")
