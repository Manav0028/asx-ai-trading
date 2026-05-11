"""
Layer 01 · Data Ingestion — ASX Announcements RSS
Polls every 30 minutes. Stores company news and updates.
"""
import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import requests
from bs4 import BeautifulSoup

from config.asx200_tickers import ASX200_CODES
from storage.database import get_session
from storage.models import NewsItem

logger = logging.getLogger(__name__)

ASX_RSS_URL = "https://www.asx.com.au/asx/1/company/{code}/announcements?count=20&market_sensitive=false"
ASX_RSS_BASE = "https://www.asx.com.au/asx/v2/statistics/todaysAnnouncementsRSS.do"


def _parse_published(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)


def fetch_asx_announcements(codes: List[str] = None) -> int:
    codes = codes or ASX200_CODES
    stored = 0

    for code in codes:
        url = ASX_RSS_URL.format(code=code)
        try:
            resp = requests.get(url, timeout=10, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                continue
            data = resp.json()
            announcements = data.get("data", [])

            with get_session() as session:
                for ann in announcements:
                    headline = ann.get("header", "").strip()
                    if not headline:
                        continue
                    pub_str = ann.get("document_date", "")
                    try:
                        pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    except Exception:
                        pub_dt = datetime.now(tz=timezone.utc)

                    # dedup by headline + ticker
                    exists = (
                        session.query(NewsItem)
                        .filter(
                            NewsItem.ticker == f"{code}.AX",
                            NewsItem.headline == headline,
                            NewsItem.source == "asx_rss",
                        )
                        .first()
                    )
                    if exists:
                        continue

                    item = NewsItem(
                        ticker=f"{code}.AX",
                        source="asx_rss",
                        headline=headline,
                        url=ann.get("url", ""),
                        published_at=pub_dt,
                    )
                    session.add(item)
                    stored += 1
        except Exception as e:
            logger.warning("ASX announcement fetch failed for %s: %s", code, e)

    logger.info("Stored %d ASX announcement items", stored)
    return stored


def fetch_all_asx_rss() -> int:
    """Fallback: scrape the market-wide RSS feed."""
    stored = 0
    try:
        feed = feedparser.parse(ASX_RSS_BASE)
        with get_session() as session:
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                # Try to extract ticker from title (format: "CODE: Headline")
                ticker = None
                if ":" in title:
                    code_part = title.split(":")[0].strip()
                    if 2 <= len(code_part) <= 5 and code_part.upper() == code_part:
                        ticker = f"{code_part}.AX"
                if not ticker:
                    continue

                pub_dt = _parse_published(entry)
                exists = (
                    session.query(NewsItem)
                    .filter(NewsItem.ticker == ticker, NewsItem.headline == title, NewsItem.source == "asx_rss")
                    .first()
                )
                if not exists:
                    session.add(NewsItem(
                        ticker=ticker, source="asx_rss",
                        headline=title, url=link, published_at=pub_dt,
                    ))
                    stored += 1
    except Exception as e:
        logger.error("ASX RSS feed failed: %s", e)

    logger.info("Stored %d items from ASX RSS feed", stored)
    return stored
