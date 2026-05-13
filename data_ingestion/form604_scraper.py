"""
Layer 01 · Data Ingestion — ASX Form 604 Director Trade Disclosures
Runs daily. ASX Form 604 = "Change in director's interest notice".
Queries the ASX announcements API and parses director buy/sell details.

NOTE: ASX API sometimes returns 403 without a live browser session.
      Results are best-effort; the insider_pattern scorer handles missing data.
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import List

import requests
from bs4 import BeautifulSoup

from storage.database import get_session
from storage.models import DirectorTrade

logger = logging.getLogger(__name__)

ASX_DISCLOSURE_URL = (
    "https://www.asx.com.au/asx/1/company/{code}/announcements"
    "?count=20&market_sensitive=false"
)

_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Referer": "https://www.asx.com.au/",
})


def _parse_trade_value(text: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_announcement_detail(url: str, header: str):
    """Best-effort extraction from announcement header and HTML."""
    trade_type = "buy"
    if any(w in header.lower() for w in ["sell", "sold", "disposal", "decrease"]):
        trade_type = "sell"

    shares = 0.0
    price = 0.0
    director = "Unknown"

    if url and url.startswith("http"):
        try:
            resp = _session.get(url, timeout=8)
            if resp.status_code == 200 and "html" in resp.headers.get("content-type", ""):
                soup = BeautifulSoup(resp.text, "html.parser")
                text = soup.get_text(" ", strip=True)

                share_match = re.search(r"([\d,]+)\s+(?:ordinary\s+)?shares?", text, re.I)
                if share_match:
                    shares = _parse_trade_value(share_match.group(1))

                price_match = re.search(r"\$\s*([\d.,]+)\s*(?:per\s+share)?", text, re.I)
                if price_match:
                    price = _parse_trade_value(price_match.group(1))

                name_match = re.search(r"Name of director[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", text)
                if name_match:
                    director = name_match.group(1)
        except Exception:
            pass

    return trade_type, shares, price, director


def _fetch_for_code(code: str) -> int:
    """Fetch and store Form 604 disclosures for one ASX bare code."""
    url = ASX_DISCLOSURE_URL.format(code=code)
    stored = 0
    try:
        resp = _session.get(url, timeout=10)
        if resp.status_code != 200:
            return 0
        announcements = resp.json().get("data", [])

        for ann in announcements:
            header = ann.get("header", "")
            if "604" not in header and "director" not in header.lower():
                continue

            doc_url = ann.get("url", "")
            trade_date_str = ann.get("document_date", "")
            try:
                trade_date = datetime.fromisoformat(
                    trade_date_str.replace("Z", "+00:00")
                ).date()
            except Exception:
                trade_date = date.today()

            trade_type, shares, price, director = _parse_announcement_detail(doc_url, header)
            ticker = f"{code}.AX"

            with get_session() as session:
                exists = (
                    session.query(DirectorTrade)
                    .filter(
                        DirectorTrade.ticker == ticker,
                        DirectorTrade.trade_date == trade_date,
                        DirectorTrade.director_name == director,
                    )
                    .first()
                )
                if not exists:
                    session.add(DirectorTrade(
                        ticker=ticker,
                        director_name=director,
                        trade_date=trade_date,
                        trade_type=trade_type,
                        shares=shares,
                        price=price,
                        value=shares * price if shares and price else 0,
                    ))
                    stored += 1
    except Exception as e:
        logger.warning("Form 604 fetch failed for %s: %s", code, e)
    return stored


def fetch_director_trades(codes: List[str] = None) -> int:
    """
    Fetch ASX Form 604 director trade disclosures.
    If no codes supplied, uses the active exchange's ticker_codes.
    """
    if codes is None:
        from config import get_active_exchange
        codes = get_active_exchange().ticker_codes

    stored = 0
    try:
        _session.get("https://www.asx.com.au", timeout=8)
    except Exception:
        pass

    for code in codes:
        stored += _fetch_for_code(code)

    logger.info("Stored %d ASX director trade records (Form 604)", stored)
    return stored


# Backward-compat alias
def fetch_form604(codes: List[str] = None) -> int:
    return fetch_director_trades(codes)


def get_recent_director_trades(ticker: str, days: int = 90) -> List[DirectorTrade]:
    cutoff = date.today() - timedelta(days=days)
    with get_session() as session:
        return (
            session.query(DirectorTrade)
            .filter(DirectorTrade.ticker == ticker, DirectorTrade.trade_date >= cutoff)
            .order_by(DirectorTrade.trade_date.desc())
            .all()
        )
