"""
Layer 01 · Data Ingestion — Google News RSS per ticker
Runs every 2 hours. Headlines per ASX200 stock.
"""
import logging
from datetime import datetime, timezone
from typing import List
from urllib.parse import quote_plus

import feedparser

from config.asx200_tickers import ASX200_TICKERS
from storage.database import get_session
from storage.models import NewsItem

logger = logging.getLogger(__name__)

GNEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-AU&gl=AU&ceid=AU:en"


def _gnews_url(ticker: str) -> str:
    code = ticker.replace(".AX", "")
    query = quote_plus(f"{code} ASX stock")
    return GNEWS_RSS.format(query=query)


def _parse_published(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)


def fetch_news(tickers: List[str] = None, max_per_ticker: int = 10) -> int:
    tickers = tickers or ASX200_TICKERS
    stored = 0

    for ticker in tickers:
        url = _gnews_url(ticker)
        try:
            feed = feedparser.parse(url)
            with get_session() as session:
                for entry in feed.entries[:max_per_ticker]:
                    headline = entry.get("title", "").strip()
                    link = entry.get("link", "")
                    if not headline:
                        continue

                    pub_dt = _parse_published(entry)
                    exists = (
                        session.query(NewsItem)
                        .filter(
                            NewsItem.ticker == ticker,
                            NewsItem.headline == headline,
                            NewsItem.source == "google_news",
                        )
                        .first()
                    )
                    if not exists:
                        session.add(NewsItem(
                            ticker=ticker,
                            source="google_news",
                            headline=headline,
                            url=link,
                            published_at=pub_dt,
                        ))
                        stored += 1
        except Exception as e:
            logger.warning("Google News fetch failed for %s: %s", ticker, e)

    logger.info("Stored %d Google News items", stored)
    return stored


def get_recent_headlines(ticker: str, hours: int = 48) -> List[str]:
    from datetime import timedelta
    # Use naive UTC datetime to match DB TIMESTAMP storage (no timezone)
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    with get_session() as session:
        rows = (
            session.query(NewsItem.headline)
            .filter(
                NewsItem.ticker == ticker,
                NewsItem.published_at >= cutoff,
            )
            .order_by(NewsItem.published_at.desc())
            .limit(20)
            .all()
        )
        return [r.headline for r in rows]
