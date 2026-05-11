"""
Layer 03 · AI Engine — Claude API Weekly Batch Summarizer
Runs every Sunday. Deep analysis of top 20 stocks using Claude claude-sonnet-4-6.
Uses prompt caching to minimise token costs (~$5-10/month).
"""
import logging
from datetime import date, timedelta
from typing import List, Optional

import anthropic

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, TOP_N_CLAUDE_BATCH
from data_ingestion.news_fetcher import get_recent_headlines
from data_ingestion.price_fetcher import get_price_series
from data_ingestion.macro_fetcher import get_macro_snapshot
from storage.database import get_session
from storage.models import Signal

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert ASX equity analyst. Your role is to synthesise quantitative signals,
recent news, and macroeconomic context into concise investment insights.
Be specific, data-driven, and concise. Focus on Australian market dynamics."""


def _build_stock_context(ticker: str) -> str:
    headlines = get_recent_headlines(ticker, hours=168)  # 7 days
    headlines_text = "\n".join(f"  • {h}" for h in headlines[:10]) or "  No recent news."

    prices = get_price_series(ticker, days=30)
    if prices:
        latest = prices[0][1]
        month_ago = prices[-1][1]
        change_pct = ((latest - month_ago) / month_ago) * 100
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
                f"  Composite score: {signal.composite_score:.1f}/100\n"
                f"  Sentiment: {signal.sentiment_score:.1f} | "
                f"Fundamental: {signal.fundamental_score:.1f} | "
                f"Technical: {signal.technical_score:.1f} | "
                f"Insider: {signal.insider_score:.1f}"
            )
        else:
            signal_context = "  No signal data."

    return f"""
### {ticker}
{price_context}
{signal_context}
Recent news:
{headlines_text}"""


def generate_weekly_summaries(top_tickers: List[str] = None) -> dict:
    """
    Generates deep summaries for the top N stocks using Claude.
    Uses prompt caching on the system prompt and macro context block.
    Returns {ticker: summary_text}.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude summaries")
        return {}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    macro = get_macro_snapshot()

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
        logger.info("No signals for today — skipping Claude batch")
        return {}

    macro_context = f"""
## Macro Environment ({date.today()})
- AUD/USD: {macro.get('aud_usd', 'N/A')}
- XJO Index: {macro.get('xjo_index', 'N/A')}
- Gold (USD): {macro.get('gold_usd', 'N/A')}
- Oil Brent: {macro.get('oil_brent', 'N/A')}
- VIX: {macro.get('vix', 'N/A')}
- S&P 500: {macro.get('sp500', 'N/A')}
"""

    summaries = {}
    for ticker in top_tickers:
        stock_context = _build_stock_context(ticker)
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=500,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": macro_context,
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"{stock_context}\n\n"
                                    "Provide a 3-4 sentence investment thesis for this stock. "
                                    "Include: key catalyst, main risk, and your conviction level (Low/Medium/High)."
                                ),
                            },
                        ],
                    }
                ],
            )
            summaries[ticker] = response.content[0].text
            logger.info("Claude summary generated for %s", ticker)
        except Exception as e:
            logger.warning("Claude summary failed for %s: %s", ticker, e)
            summaries[ticker] = "Summary unavailable."

    return summaries
