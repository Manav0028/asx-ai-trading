"""
Layer 01 · Data Ingestion — Form 604 Director Trade Disclosures
Runs daily at 7:00 AM. ASX Form 604 = change in director's interest.
"""
import logging
import re
from datetime import date, datetime, timezone
from typing import List

import requests
from bs4 import BeautifulSoup

from config.asx200_tickers import ASX200_CODES
from storage.database import get_session
from storage.models import DirectorTrade

logger = logging.getLogger(__name__)

ASX_DISCLOSURE_URL = (
    "https://www.asx.com.au/asx/1/company/{code}/announcements"
    "?count=20&market_sensitive=false"
)


def _parse_trade_value(text: str) -> float:
    """Extract numeric value from strings like '$1,234,567'."""
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def fetch_form604(codes: List[str] = None) -> int:
    codes = codes or ASX200_CODES
    stored = 0

    for code in codes:
        url = ASX_DISCLOSURE_URL.format(code=code)
        try:
            resp = requests.get(url, timeout=10, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                continue
            announcements = resp.json().get("data", [])

            for ann in announcements:
                header = ann.get("header", "")
                # Form 604 = "Change in director's interest notice"
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

                # Fetch PDF/HTML for details (best-effort parse)
                trade_type, shares, price, director = _parse_announcement_detail(doc_url, header)

                with get_session() as session:
                    exists = (
                        session.query(DirectorTrade)
                        .filter(
                            DirectorTrade.ticker == f"{code}.AX",
                            DirectorTrade.trade_date == trade_date,
                            DirectorTrade.director_name == director,
                        )
                        .first()
                    )
                    if not exists:
                        session.add(DirectorTrade(
                            ticker=f"{code}.AX",
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

    logger.info("Stored %d director trade records", stored)
    return stored


def _parse_announcement_detail(url: str, header: str):
    """Best-effort extraction from announcement header text."""
    trade_type = "buy"
    if any(w in header.lower() for w in ["sell", "sold", "disposal", "decrease"]):
        trade_type = "sell"

    shares = 0.0
    price = 0.0
    director = "Unknown"

    # Try to pull from HTML if URL is accessible
    if url and url.startswith("http"):
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200 and "html" in resp.headers.get("content-type", ""):
                soup = BeautifulSoup(resp.text, "html.parser")
                text = soup.get_text(" ", strip=True)

                # Extract share count
                share_match = re.search(r"([\d,]+)\s+(?:ordinary\s+)?shares?", text, re.I)
                if share_match:
                    shares = _parse_trade_value(share_match.group(1))

                # Extract price
                price_match = re.search(r"\$\s*([\d.,]+)\s*(?:per\s+share)?", text, re.I)
                if price_match:
                    price = _parse_trade_value(price_match.group(1))

                # Extract director name (rough heuristic)
                name_match = re.search(r"Name of director[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", text)
                if name_match:
                    director = name_match.group(1)
        except Exception:
            pass

    return trade_type, shares, price, director


def get_recent_director_trades(ticker: str, days: int = 90) -> List[DirectorTrade]:
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)
    with get_session() as session:
        return (
            session.query(DirectorTrade)
            .filter(DirectorTrade.ticker == ticker, DirectorTrade.trade_date >= cutoff)
            .order_by(DirectorTrade.trade_date.desc())
            .all()
        )
