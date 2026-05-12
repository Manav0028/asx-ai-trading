"""
Layer 01 · Data Ingestion — NSE India Corporate Announcements
Fetches filings from NSE's public API and BSE's announcement RSS.
Falls back to Google News for tickers that return no API data.
"""
import logging
import time
from datetime import datetime, timezone
from typing import List

import feedparser
import requests

from config.nifty100_tickers import NIFTY100_CODES
from storage.database import get_session
from storage.models import NewsItem

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
})

# NSE public API for company announcements (count=20, recent filings)
NSE_ANNOUNCE_URL = (
    "https://www.nseindia.com/api/corp-info?symbol={symbol}&corpType=announcements"
)
# BSE filing RSS — broader fallback
BSE_ANNOUNCE_RSS = (
    "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?"
    "scrip_cd={scrip_cd}&type=rss"
)


def _store_item(ticker: str, headline: str, url: str, pub_dt: datetime, source: str) -> bool:
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


def _parse_dt(value: str) -> datetime:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return datetime.now(tz=timezone.utc)


def _fetch_nse_api(symbol: str) -> int:
    """Query NSE's corp-info API. Returns count of new items stored."""
    url = NSE_ANNOUNCE_URL.format(symbol=symbol)
    try:
        # NSE requires a prior homepage hit to set cookies
        _session.get("https://www.nseindia.com", timeout=8)
        resp = _session.get(url, timeout=12)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        announcements = data.get("data", [])
        ticker = f"{symbol}.NS"
        stored = 0
        for ann in announcements:
            headline = (ann.get("subject") or ann.get("details") or "").strip()
            doc_url = ann.get("attchmntFile", "")
            pub_str = ann.get("an_dt") or ann.get("exchdisstime") or ""
            pub_dt = _parse_dt(pub_str)
            if _store_item(ticker, headline, doc_url, pub_dt, "nse_api"):
                stored += 1
        return stored
    except Exception as e:
        logger.debug("NSE API failed for %s: %s", symbol, e)
        return 0


def fetch_nse_announcements(codes: List[str] = None) -> int:
    codes = codes or NIFTY100_CODES
    stored = 0
    api_hits = 0

    for i, code in enumerate(codes):
        n = _fetch_nse_api(code)
        if n > 0:
            api_hits += 1
            stored += n

        # Polite rate-limiting
        if i % 10 == 9:
            time.sleep(1.5)
        else:
            time.sleep(0.4)

    logger.info(
        "NSE announcements: %d new items stored (API succeeded for %d/%d tickers)",
        stored, api_hits, len(codes),
    )
    return stored
