"""
Layer 03 · AI Engine — Claude API Weekly Batch Summarizer
Runs every Sunday. Deep analysis of top 20 stocks.
Uses prompt caching to minimise token costs.
Falls back to a rule-based summary if API key is not set.
"""
import logging
from datetime import date, timedelta
from typing import List

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, TOP_N_CLAUDE_BATCH
from data_ingestion.news_fetcher import get_recent_headlines
from data_ingestion.price_fetcher import get_price_series
from data_ingestion.macro_fetcher import get_macro_snapshot
from storage.database import get_session
from storage.models import Signal

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a plain-English ASX stock analyst. Explain everything as if talking to a smart investor who is NOT a financial professional.
Avoid jargon. Be specific, honest, and concise. Flag both opportunities AND risks clearly."""


def _build_stock_context(ticker: str) -> str:
    headlines = get_recent_headlines(ticker, hours=168)
    headlines_text = "\n".join(f"  • {h}" for h in headlines[:8]) or "  No recent news."

    prices = get_price_series(ticker, days=30)
    if prices:
        latest = prices[0][1]
        month_ago = prices[-1][1]
        change_pct = (latest - month_ago) / month_ago * 100
        price_context = f"  Price: ${latest:.2f} | 30-day change: {change_pct:+.1f}%"
    else:
        price_context = "  Price data unavailable."

    with get_session() as session:
        signal = (
            session.query(Signal)
            .filter(Signal.ticker == ticker)
            .order_by(Signal.date.desc())
            .first()
        )
        if signal:
            signal_context = (
                f"  Overall score: {signal.composite_score:.0f}/100\n"
                f"  News sentiment: {signal.sentiment_score:.0f} | "
                f"Business health: {signal.fundamental_score:.0f} | "
                f"Chart: {signal.technical_score:.0f} | "
                f"Director activity: {signal.insider_score:.0f}"
            )
        else:
            signal_context = "  No signal data."

    return f"### {ticker}\n{price_context}\n{signal_context}\nRecent news:\n{headlines_text}"


def _rule_based_summary(ticker: str) -> str:
    """Fallback when Claude API key is not set."""
    with get_session() as session:
        sig = (
            session.query(Signal)
            .filter(Signal.ticker == ticker)
            .order_by(Signal.date.desc())
            .first()
        )
    if not sig:
        return f"{ticker}: No data available yet."

    score = sig.composite_score or 50
    sent  = sig.sentiment_score or 50
    fund  = sig.fundamental_score or 50
    tech  = sig.technical_score or 50

    if score >= 80:
        conviction = "Strong buy candidate"
    elif score >= 70:
        conviction = "Watchlist — approaching buy zone"
    else:
        conviction = "Monitor only"

    strengths = []
    weaknesses = []
    if sent >= 70: strengths.append("positive news flow")
    elif sent < 40: weaknesses.append("negative news")
    if fund >= 70: strengths.append("strong financials")
    elif fund < 45: weaknesses.append("weak fundamentals")
    if tech >= 70: strengths.append("bullish chart pattern")
    elif tech < 40: weaknesses.append("bearish technicals")

    parts = [f"{ticker}: {conviction} (score {score:.0f}/100)."]
    if strengths: parts.append(f"Positives: {', '.join(strengths)}.")
    if weaknesses: parts.append(f"Watch: {', '.join(weaknesses)}.")
    return " ".join(parts)


def generate_weekly_summaries(top_tickers: List[str] = None) -> dict:
    if not top_tickers:
        with get_session() as session:
            rows = (
                session.query(Signal.ticker, Signal.composite_score)
                .filter(Signal.date == date.today())
                .order_by(Signal.composite_score.desc())
                .limit(TOP_N_CLAUDE_BATCH)
                .all()
            )
            top_tickers = [r.ticker for r in rows]

    if not top_tickers:
        logger.info("No signals for Claude batch — skipping")
        return {}

    # Rule-based fallback if no API key
    if not ANTHROPIC_API_KEY:
        logger.info("No ANTHROPIC_API_KEY — using rule-based summaries")
        return {t: _rule_based_summary(t) for t in top_tickers}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    macro = get_macro_snapshot()

    macro_context = (
        f"## Australian Market Context ({date.today()})\n"
        f"- AUD/USD: {macro.get('aud_usd', 'N/A')}\n"
        f"- ASX 200 index: {macro.get('xjo_index', 'N/A')}\n"
        f"- Gold: ${macro.get('gold_usd', 'N/A')}/oz\n"
        f"- Oil (Brent): ${macro.get('oil_brent', 'N/A')}/barrel\n"
        f"- VIX fear index: {macro.get('vix', 'N/A')}\n"
    )

    summaries = {}
    for ticker in top_tickers:
        stock_ctx = _build_stock_context(ticker)
        try:
            resp = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=350,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                          "cache_control": {"type": "ephemeral"}}],
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": macro_context,
                         "cache_control": {"type": "ephemeral"}},
                        {"type": "text", "text": (
                            f"{stock_ctx}\n\n"
                            "In 3-4 plain-English sentences: what is the main reason this stock "
                            "is on the radar this week, what is the biggest risk, and what would "
                            "need to happen for you to be wrong? Conviction: Low/Medium/High."
                        )},
                    ],
                }],
            )
            summaries[ticker] = resp.content[0].text
            logger.info("Claude summary: %s", ticker)
        except Exception as e:
            logger.warning("Claude failed for %s: %s — using rule-based", ticker, e)
            summaries[ticker] = _rule_based_summary(ticker)

    return summaries
