"""
Layer 01 · Data Ingestion — ASX Announcements
Multi-strategy scraper: tries JSON API first, falls back to RSS, then
the ASX investor-relations feed. Uses browser-like headers to avoid 403s.
"""
import logging
import time
from datetime import datetime, timezone
from typing import List

import feedparser
import requests

from config.asx200_tickers import ASX200_CODES
from storage.database import get_session
from storage.models import NewsItem

logger = logging.getLogger(__name__)

# Browser-like session reused across requests to maintain cookies
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.asx.com.au/",
})

ASX_API_URL = "https://www.asx.com.au/asx/1/company/{code}/announcements?count=20&market_sensitive=false"
ASX_RSS_TODAY = "https://www.asx.com.au/asx/v2/statistics/todaysAnnouncementsRSS.do"
ASX_COMPANY_RSS = "https://www.asx.com.au/asx/v2/announcements/announcementsFilter.do?timeframe=W&type=A&industry=A&ticker={code}"


def _store_item(ticker: str, headline: str, url: str, pub_dt: datetime, source: str) -> bool:
    """Store a news item, return True if new."""
    if not headline.strip():
        return False
    with get_session() as session:
        exists = (
            session.query(NewsItem)
            .filter(
                NewsItem.ticker == ticker,
                NewsItem.headline == headline,
                NewsItem.source == source,
            )
            .first()
        )
        if exists:
            return False
        session.add(NewsItem(
            ticker=ticker,
            source=source,
            headline=headline,
            url=url,
            published_at=pub_dt,
        ))
        return True


def _parse_pub_dt(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)


# ── Strategy 1: ASX JSON API (needs browser session) ──────────────────────────

def _fetch_via_api(code: str) -> int:
    url = ASX_API_URL.format(code=code)
    try:
        # Warm the session cookie with a homepage hit first (once per run)
        resp = _session.get(url, timeout=12)
        if resp.status_code == 403:
            return 0
        if resp.status_code != 200:
            return 0
        data = resp.json()
        announcements = data.get("data", [])
        stored = 0
        for ann in announcements:
            headline = ann.get("header", "").strip()
            doc_url = ann.get("url", "")
            pub_str = ann.get("document_date", "")
            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except Exception:
                pub_dt = datetime.now(tz=timezone.utc)
            if _store_item(f"{code}.AX", headline, doc_url, pub_dt, "asx_rss"):
                stored += 1
        return stored
    except Exception as e:
        logger.debug("ASX API failed for %s: %s", code, e)
        return 0


# ── Strategy 2: Per-company RSS feed ──────────────────────────────────────────

def _fetch_via_company_rss(code: str) -> int:
    url = ASX_COMPANY_RSS.format(code=code)
    try:
        feed = feedparser.parse(url)
        stored = 0
        for entry in feed.entries:
            headline = entry.get("title", "").strip()
            link = entry.get("link", "")
            pub_dt = _parse_pub_dt(entry)
            if _store_item(f"{code}.AX", headline, link, pub_dt, "asx_rss"):
                stored += 1
        return stored
    except Exception:
        return 0


# ── Strategy 3: Market-wide today RSS (fallback) ──────────────────────────────

def fetch_all_asx_rss() -> int:
    """Scrape the ASX market-wide today announcements RSS."""
    stored = 0
    try:
        feed = feedparser.parse(ASX_RSS_TODAY)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            pub_dt = _parse_pub_dt(entry)

            # Title format: "CODE: Headline text"
            if ":" not in title:
                continue
            code_part = title.split(":")[0].strip().upper()
            if not (2 <= len(code_part) <= 5):
                continue
            ticker = f"{code_part}.AX"
            if _store_item(ticker, title, link, pub_dt, "asx_rss"):
                stored += 1
    except Exception as e:
        logger.warning("ASX market RSS failed: %s", e)
    return stored


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_asx_announcements(codes: List[str] = None) -> int:
    codes = codes or ASX200_CODES
    stored = 0
    api_hits = 0

    # Warm the session with a homepage visit
    try:
        _session.get("https://www.asx.com.au", timeout=8)
    except Exception:
        pass

    for i, code in enumerate(codes):
        n = _fetch_via_api(code)
        if n > 0:
            api_hits += 1
            stored += n
        else:
            stored += _fetch_via_company_rss(code)

        # Polite rate-limiting: 0.3s between requests
        if i % 10 == 9:
            time.sleep(1)
        else:
            time.sleep(0.3)

    # Always run the market-wide RSS as a supplement
    stored += fetch_all_asx_rss()

    logger.info(
        "ASX announcements: %d new items stored (API succeeded for %d/%d tickers)",
        stored, api_hits, len(codes),
    )
    return stored
